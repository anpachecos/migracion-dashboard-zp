-- Reparacion de V007 cuando DBeaver envio PRC_VALIDAR_REGLAS_ALERTA solo
-- hasta el primer punto y coma interno.
--
-- DBEAVER: ejecutar como "script SQL" completo (Alt+X), no como sentencia
-- aislada con Ctrl+Enter. Este archivo no modifica datos.

CREATE OR REPLACE PROCEDURE USR_LAB.PRC_VALIDAR_REGLAS_ALERTA
AS
    v_total NUMBER;
    v_valor NUMBER;

    FUNCTION regla(p_clave VARCHAR2) RETURN NUMBER
    AS
        v_resultado NUMBER;
    BEGIN
        SELECT VALOR_NUMERO
        INTO v_resultado
        FROM USR_LAB.ALERTA_REGLA_PARAM
        WHERE CLAVE = p_clave
          AND ACTIVO = 1
          AND VALOR_NUMERO IS NOT NULL;

        RETURN v_resultado;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(
                -20001,
                'Falta una regla activa con valor: ' || p_clave
            );
    END regla;
BEGIN
    SELECT COUNT(*)
    INTO v_total
    FROM USR_LAB.ALERTA_REGLA_PARAM
    WHERE CLAVE IN (
        'GPS_CERO_HOY_CRITICA', 'GPS_PORC_HOY_CRITICA',
        'GPS_TOTAL_HOY_CRITICA', 'GPS_RACHA_CRITICA',
        'GPS_CERO_HOY_ALTA', 'GPS_CERO_HOY_ALTA_MAX',
        'GPS_PORC_HOY_ALTA', 'GPS_TOTAL_HOY_ALTA',
        'GPS_RACHA_ALTA', 'GPS_CERO_HOY_ADV',
        'GPS_CERO_HOY_ADV_MAX', 'GPS_CERO_HIST_ADV',
        'GPS_PORC_HIST_ADV', 'BAT_CAIDA_MIN_DETECTAR',
        'BAT_CAIDA_MAX_HORAS', 'BAT_CAIDA_HOY_CRITICA',
        'BAT_CAIDA_HOY_CRITICA_CON_HIST',
        'BAT_CAIDAS_HOY_CRITICA', 'BAT_CERO_HOY_CRITICA',
        'BAT_CAIDA_HOY_ALTA', 'BAT_CAIDAS_HIST_ALTA',
        'BAT_CAIDA_MAX_HIST_ALTA', 'BAT_CERO_HOY_ALTA_MIN',
        'BAT_CERO_HOY_ALTA_MAX', 'BAT_CERO_HOY_ADV_MIN',
        'BAT_CERO_HOY_ADV_MAX', 'BAT_CERO_HIST_ADV'
    )
      AND ACTIVO = 1
      AND VALOR_NUMERO IS NOT NULL;

    IF v_total <> 27 THEN
        RAISE_APPLICATION_ERROR(
            -20002,
            'Deben existir 27 reglas activas y con valor. Encontradas: ' || v_total
        );
    END IF;

    SELECT COUNT(*)
    INTO v_total
    FROM USR_LAB.ALERTA_REGLA_PARAM
    WHERE ACTIVO = 1
      AND VALOR_NUMERO < 0;

    IF v_total > 0 THEN
        RAISE_APPLICATION_ERROR(-20003, 'Los umbrales no pueden ser negativos.');
    END IF;

    SELECT COUNT(*)
    INTO v_total
    FROM USR_LAB.ALERTA_REGLA_PARAM
    WHERE ACTIVO = 1
      AND CLAVE LIKE 'GPS_PORC_%'
      AND (VALOR_NUMERO < 0 OR VALOR_NUMERO > 100);

    IF v_total > 0 THEN
        RAISE_APPLICATION_ERROR(-20004, 'Los porcentajes deben estar entre 0 y 100.');
    END IF;

    IF regla('GPS_CERO_HOY_ADV') > regla('GPS_CERO_HOY_ADV_MAX')
       OR regla('GPS_CERO_HOY_ADV_MAX') >= regla('GPS_CERO_HOY_ALTA')
       OR regla('GPS_CERO_HOY_ALTA') > regla('GPS_CERO_HOY_ALTA_MAX')
       OR regla('GPS_CERO_HOY_ALTA_MAX') >= regla('GPS_CERO_HOY_CRITICA') THEN
        RAISE_APPLICATION_ERROR(-20005, 'Rangos GPS por cantidad incoherentes.');
    END IF;

    IF regla('GPS_PORC_HOY_ALTA') > regla('GPS_PORC_HOY_CRITICA')
       OR regla('GPS_TOTAL_HOY_ALTA') > regla('GPS_TOTAL_HOY_CRITICA')
       OR regla('GPS_RACHA_ALTA') > regla('GPS_RACHA_CRITICA') THEN
        RAISE_APPLICATION_ERROR(-20006, 'Umbrales GPS ALTA/CRITICA incoherentes.');
    END IF;

    IF regla('BAT_CERO_HOY_ADV_MIN') > regla('BAT_CERO_HOY_ADV_MAX')
       OR regla('BAT_CERO_HOY_ADV_MAX') >= regla('BAT_CERO_HOY_ALTA_MIN')
       OR regla('BAT_CERO_HOY_ALTA_MIN') > regla('BAT_CERO_HOY_ALTA_MAX')
       OR regla('BAT_CERO_HOY_ALTA_MAX') >= regla('BAT_CERO_HOY_CRITICA') THEN
        RAISE_APPLICATION_ERROR(-20007, 'Rangos de bateria en cero incoherentes.');
    END IF;

    IF regla('BAT_CAIDA_MIN_DETECTAR') <= 0
       OR regla('BAT_CAIDA_MAX_HORAS') <= 0 THEN
        RAISE_APPLICATION_ERROR(-20008, 'Las reglas de deteccion deben ser mayores que cero.');
    END IF;

    IF regla('BAT_CAIDA_HOY_ALTA') > regla('BAT_CAIDA_HOY_CRITICA_CON_HIST')
       OR regla('BAT_CAIDA_HOY_CRITICA_CON_HIST') > regla('BAT_CAIDA_HOY_CRITICA') THEN
        RAISE_APPLICATION_ERROR(-20009, 'Umbrales de caida ALTA/CRITICA incoherentes.');
    END IF;

    v_valor := regla('GPS_CERO_HIST_ADV');
    v_valor := regla('GPS_PORC_HIST_ADV');
    v_valor := regla('BAT_CAIDAS_HOY_CRITICA');
    v_valor := regla('BAT_CAIDAS_HIST_ALTA');
    v_valor := regla('BAT_CAIDA_MAX_HIST_ALTA');
    v_valor := regla('BAT_CERO_HIST_ADV');
END PRC_VALIDAR_REGLAS_ALERTA;
/

CREATE OR REPLACE PROCEDURE USR_LAB.PRC_RECLASIFICAR_ALERTAS
AS
BEGIN
    USR_LAB.PRC_VALIDAR_REGLAS_ALERTA;
    USR_LAB.PRC_APLICAR_REGLAS_ALERTA;
END PRC_RECLASIFICAR_ALERTAS;
/

CREATE OR REPLACE PROCEDURE USR_LAB.PRC_RECALCULAR_ALERTAS_SEGURO
AS
BEGIN
    USR_LAB.PRC_VALIDAR_REGLAS_ALERTA;
    USR_LAB.PRC_UPD_ALERTAS_VAL;
END PRC_RECALCULAR_ALERTAS_SEGURO;
/

SELECT OBJECT_NAME, OBJECT_TYPE, STATUS
FROM USER_OBJECTS
WHERE OBJECT_NAME IN (
    'PRC_VALIDAR_REGLAS_ALERTA',
    'PRC_RECLASIFICAR_ALERTAS',
    'PRC_RECALCULAR_ALERTAS_SEGURO'
)
ORDER BY OBJECT_NAME;

SELECT NAME, TYPE, LINE, POSITION, TEXT
FROM USER_ERRORS
WHERE NAME IN (
    'PRC_VALIDAR_REGLAS_ALERTA',
    'PRC_RECLASIFICAR_ALERTAS',
    'PRC_RECALCULAR_ALERTAS_SEGURO'
)
ORDER BY NAME, SEQUENCE;

