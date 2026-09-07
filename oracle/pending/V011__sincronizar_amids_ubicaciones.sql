-- V011 - Sincronizacion preventiva de AMID sin ubicacion esperada
-- Estado: PENDIENTE DE EJECUCION EN ORACLE.
--
-- Objetivo:
-- 1. Incorporar en UBICACION_ESPERADA_VALIDADOR todo AMID activo del maestro
--    que todavia no tenga una fila vigente.
-- 2. Abrir historial desde el momento real de la incorporacion, sin inventar
--    vigencia para dias anteriores.
-- 3. Programar la misma operacion todos los dias a las 06:10, despues de
--    JOB_UPD_AMID_ALERTAS (06:00).
--
-- Seguridad:
-- - No actualiza ubicaciones existentes.
-- - No cierra historiales vigentes.
-- - No usa DROP, TRUNCATE ni DELETE.
-- - Es idempotente: al repetirlo solo incorpora faltantes.
--
-- Ejecutar en DBeaver como script completo (Alt+X), no sentencia por sentencia.

SET SERVEROUTPUT ON;

CREATE OR REPLACE PROCEDURE USR_LAB.PRC_SINC_UBIC_AMID (
    p_ubicaciones_creadas OUT NUMBER,
    p_historiales_creados OUT NUMBER
)
AS
BEGIN
    p_ubicaciones_creadas := 0;
    p_historiales_creados := 0;

    INSERT INTO USR_LAB.UBICACION_ESPERADA_VALIDADOR (
        AMID,
        NOMBRE,
        IDDS,
        LATITUD_ESPERADA,
        LONGITUD_ESPERADA,
        OPERATIVA,
        RADIO_METROS,
        VERSION_ZP,
        ARCHIVO_ORIGEN,
        FECHA_CARGA
    )
    SELECT
        TRIM(CAST(m.AMID AS VARCHAR2(20))),
        'Laboratorio Zonas Pagas',
        TRIM(CAST(m.AMID AS VARCHAR2(20))),
        -33.437191,
        -70.656102,
        0,
        150,
        NULL,
        'SINCRONIZACION_ORACLE',
        SYSDATE
    FROM USR_LAB.AMID_MAESTRO_ALERTAS m
    WHERE m.ACTIVO = 1
      AND m.AMID IS NOT NULL
      AND NOT EXISTS (
          SELECT 1
          FROM USR_LAB.UBICACION_ESPERADA_VALIDADOR u
          WHERE TRIM(u.AMID) = TRIM(CAST(m.AMID AS VARCHAR2(20)))
      );

    p_ubicaciones_creadas := SQL%ROWCOUNT;

    INSERT INTO USR_LAB.HISTORIAL_UBICACION_ESPERADA (
        AMID,
        CODIGO_ZP_TS,
        COD_PARADA1,
        COD_PARADA2,
        NOMBRE,
        COMUNA,
        UNIDAD,
        OPERADOR,
        UN,
        UN_SECUNDARIA_1,
        UN_SECUNDARIA_2,
        UN_SECUNDARIA_3,
        PST,
        SERVICIOS,
        TOTAL_VAL_VIGENTES_ZP,
        HORARIO,
        HORARIO_LABORAL_PM,
        HORARIO_SABADO,
        HORARIO_DOMINGO,
        INICIO_OPERACION,
        FIN_OPERACION,
        PATENTE,
        OP_ID,
        BUS_ID,
        SERIE_VALIDADOR,
        IDDS,
        NUM_VAL,
        LATITUD_ESPERADA,
        LONGITUD_ESPERADA,
        X,
        Y,
        OPERATIVA,
        CONTINGENCIA,
        MIXTA,
        RADIO_METROS,
        TIPO,
        RENOVADA,
        ORIGEN_UBICACION,
        VERSION_ZP,
        ARCHIVO_ORIGEN,
        FECHA_INICIO_VIGENCIA,
        FECHA_FIN_VIGENCIA,
        FECHA_CARGA
    )
    SELECT
        u.AMID,
        u.CODIGO_ZP_TS,
        u.COD_PARADA1,
        u.COD_PARADA2,
        u.NOMBRE,
        u.COMUNA,
        u.UNIDAD,
        u.OPERADOR,
        u.UN,
        u.UN_SECUNDARIA_1,
        u.UN_SECUNDARIA_2,
        u.UN_SECUNDARIA_3,
        u.PST,
        u.SERVICIOS,
        u.TOTAL_VAL_VIGENTES_ZP,
        u.HORARIO,
        u.HORARIO_LABORAL_PM,
        u.HORARIO_SABADO,
        u.HORARIO_DOMINGO,
        u.INICIO_OPERACION,
        u.FIN_OPERACION,
        u.PATENTE,
        u.OP_ID,
        u.BUS_ID,
        u.SERIE_VALIDADOR,
        u.IDDS,
        u.NUM_VAL,
        u.LATITUD_ESPERADA,
        u.LONGITUD_ESPERADA,
        u.X,
        u.Y,
        u.OPERATIVA,
        u.CONTINGENCIA,
        u.MIXTA,
        u.RADIO_METROS,
        u.TIPO,
        u.RENOVADA,
        CASE
            WHEN u.NOMBRE = 'Laboratorio Zonas Pagas'
            THEN 'laboratorio_default'
            ELSE 'reparacion_vigente'
        END,
        u.VERSION_ZP,
        u.ARCHIVO_ORIGEN,
        SYSDATE,
        NULL,
        NVL(u.FECHA_CARGA, SYSDATE)
    FROM USR_LAB.UBICACION_ESPERADA_VALIDADOR u
    JOIN USR_LAB.AMID_MAESTRO_ALERTAS m
      ON TRIM(CAST(m.AMID AS VARCHAR2(20))) = TRIM(u.AMID)
     AND m.ACTIVO = 1
    WHERE NOT EXISTS (
        SELECT 1
        FROM USR_LAB.HISTORIAL_UBICACION_ESPERADA h
        WHERE TRIM(h.AMID) = TRIM(u.AMID)
          AND h.FECHA_FIN_VIGENCIA IS NULL
    );

    p_historiales_creados := SQL%ROWCOUNT;

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/

DECLARE
    v_existe  NUMBER := 0;
    v_enabled VARCHAR2(5);
BEGIN
    SELECT COUNT(*)
      INTO v_existe
      FROM USER_SCHEDULER_JOBS
     WHERE JOB_NAME = 'JOB_SINC_UBIC_AMID';

    IF v_existe = 0 THEN
        DBMS_SCHEDULER.CREATE_JOB(
            job_name        => 'USR_LAB.JOB_SINC_UBIC_AMID',
            job_type        => 'PLSQL_BLOCK',
            job_action      => 'DECLARE v_u NUMBER; v_h NUMBER; BEGIN USR_LAB.PRC_SINC_UBIC_AMID(v_u, v_h); END;',
            start_date      => SYSTIMESTAMP,
            repeat_interval => 'FREQ=DAILY;BYHOUR=6;BYMINUTE=10;BYSECOND=0',
            enabled         => FALSE,
            auto_drop       => FALSE,
            comments        => 'Completa ubicacion e historial de AMID activos faltantes.'
        );
    ELSE
        SELECT ENABLED
          INTO v_enabled
          FROM USER_SCHEDULER_JOBS
         WHERE JOB_NAME = 'JOB_SINC_UBIC_AMID';

        IF v_enabled = 'TRUE' THEN
            DBMS_SCHEDULER.DISABLE('USR_LAB.JOB_SINC_UBIC_AMID');
        END IF;

        DBMS_SCHEDULER.SET_ATTRIBUTE(
            name      => 'USR_LAB.JOB_SINC_UBIC_AMID',
            attribute => 'job_action',
            value     => 'DECLARE v_u NUMBER; v_h NUMBER; BEGIN USR_LAB.PRC_SINC_UBIC_AMID(v_u, v_h); END;'
        );
        DBMS_SCHEDULER.SET_ATTRIBUTE(
            name      => 'USR_LAB.JOB_SINC_UBIC_AMID',
            attribute => 'repeat_interval',
            value     => 'FREQ=DAILY;BYHOUR=6;BYMINUTE=10;BYSECOND=0'
        );
    END IF;

    DBMS_SCHEDULER.ENABLE('USR_LAB.JOB_SINC_UBIC_AMID');
END;
/

-- Primera reparacion inmediata. Las siguientes ejecuciones quedan a cargo del job
-- o del boton administrativo de Django.
DECLARE
    v_ubicaciones NUMBER;
    v_historiales NUMBER;
BEGIN
    USR_LAB.PRC_SINC_UBIC_AMID(v_ubicaciones, v_historiales);
    DBMS_OUTPUT.PUT_LINE('Ubicaciones creadas: ' || v_ubicaciones);
    DBMS_OUTPUT.PUT_LINE('Historiales abiertos: ' || v_historiales);
END;
/
