-- Fase 1: mejoras aditivas para alertas.
--
-- Garantias de este script:
-- - No contiene DROP.
-- - No contiene TRUNCATE.
-- - No elimina ni reemplaza datos.
-- - No modifica ESTATUS_ZP ni JOBS_STATUS_ZP.
-- - No reemplaza PRC_UPD_ALERTAS_VAL.
--
-- Crea:
-- 1. Una vista que excluye AMID inactivos sin borrar su resumen.
-- 2. Un procedimiento rapido que reaplica reglas sobre metricas existentes.
-- 3. Una fecha separada para registrar la reclasificacion sin falsear la fecha
--    del ultimo calculo completo de metricas.
--
-- Importante:
-- Si cambian BAT_CAIDA_MIN_DETECTAR o BAT_CAIDA_MAX_HORAS se debe ejecutar
-- PRC_UPD_ALERTAS_VAL, porque esas claves modifican la deteccion de eventos.

DECLARE
    v_existe NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO v_existe
    FROM USER_TAB_COLUMNS
    WHERE TABLE_NAME = 'ALERTA_VALIDADOR_RESUMEN'
      AND COLUMN_NAME = 'FECHA_REGLAS_APLICADAS';

    IF v_existe = 0 THEN
        EXECUTE IMMEDIATE 'ALTER TABLE USR_LAB.ALERTA_VALIDADOR_RESUMEN ADD FECHA_REGLAS_APLICADAS DATE';
    END IF;
END;
/

CREATE OR REPLACE VIEW USR_LAB.VW_ALERTA_VALIDADOR_ACTIVA AS
SELECT r.*
FROM USR_LAB.ALERTA_VALIDADOR_RESUMEN r
JOIN USR_LAB.AMID_MAESTRO_ALERTAS m
  ON m.AMID = r.AMID
WHERE m.ACTIVO = 1;
/

CREATE OR REPLACE PROCEDURE USR_LAB.PRC_APLICAR_REGLAS_ALERTA
AS
    v_filas_actualizadas NUMBER := 0;
BEGIN
    MERGE INTO USR_LAB.ALERTA_VALIDADOR_RESUMEN destino
    USING (
        WITH config AS (
            SELECT
                NVL(MAX(CASE WHEN CLAVE = 'GPS_CERO_HOY_CRITICA' THEN VALOR_NUMERO END), 22) AS gps_cero_hoy_critica,
                NVL(MAX(CASE WHEN CLAVE = 'GPS_PORC_HOY_CRITICA' THEN VALOR_NUMERO END), 90) AS gps_porc_hoy_critica,
                NVL(MAX(CASE WHEN CLAVE = 'GPS_TOTAL_HOY_CRITICA' THEN VALOR_NUMERO END), 10) AS gps_total_hoy_critica,
                NVL(MAX(CASE WHEN CLAVE = 'GPS_RACHA_CRITICA' THEN VALOR_NUMERO END), 784) AS gps_racha_critica,
                NVL(MAX(CASE WHEN CLAVE = 'GPS_CERO_HOY_ALTA' THEN VALOR_NUMERO END), 6) AS gps_cero_hoy_alta,
                NVL(MAX(CASE WHEN CLAVE = 'GPS_CERO_HOY_ALTA_MAX' THEN VALOR_NUMERO END), 21) AS gps_cero_hoy_alta_max,
                NVL(MAX(CASE WHEN CLAVE = 'GPS_PORC_HOY_ALTA' THEN VALOR_NUMERO END), 66.67) AS gps_porc_hoy_alta,
                NVL(MAX(CASE WHEN CLAVE = 'GPS_TOTAL_HOY_ALTA' THEN VALOR_NUMERO END), 5) AS gps_total_hoy_alta,
                NVL(MAX(CASE WHEN CLAVE = 'GPS_RACHA_ALTA' THEN VALOR_NUMERO END), 306) AS gps_racha_alta,
                NVL(MAX(CASE WHEN CLAVE = 'GPS_CERO_HOY_ADV' THEN VALOR_NUMERO END), 1) AS gps_cero_hoy_adv,
                NVL(MAX(CASE WHEN CLAVE = 'GPS_CERO_HOY_ADV_MAX' THEN VALOR_NUMERO END), 5) AS gps_cero_hoy_adv_max,
                NVL(MAX(CASE WHEN CLAVE = 'GPS_CERO_HIST_ADV' THEN VALOR_NUMERO END), 113) AS gps_cero_hist_adv,
                NVL(MAX(CASE WHEN CLAVE = 'GPS_PORC_HIST_ADV' THEN VALOR_NUMERO END), 16.43) AS gps_porc_hist_adv,
                NVL(MAX(CASE WHEN CLAVE = 'BAT_CAIDA_HOY_CRITICA' THEN VALOR_NUMERO END), 50) AS bat_caida_hoy_critica,
                NVL(MAX(CASE WHEN CLAVE = 'BAT_CAIDA_HOY_CRITICA_CON_HIST' THEN VALOR_NUMERO END), 30) AS bat_caida_hoy_critica_con_hist,
                NVL(MAX(CASE WHEN CLAVE = 'BAT_CAIDAS_HOY_CRITICA' THEN VALOR_NUMERO END), 3) AS bat_caidas_hoy_critica,
                NVL(MAX(CASE WHEN CLAVE = 'BAT_CERO_HOY_CRITICA' THEN VALOR_NUMERO END), 10) AS bat_cero_hoy_critica,
                NVL(MAX(CASE WHEN CLAVE = 'BAT_CAIDA_HOY_ALTA' THEN VALOR_NUMERO END), 20) AS bat_caida_hoy_alta,
                NVL(MAX(CASE WHEN CLAVE = 'BAT_CAIDAS_HIST_ALTA' THEN VALOR_NUMERO END), 3) AS bat_caidas_hist_alta,
                NVL(MAX(CASE WHEN CLAVE = 'BAT_CAIDA_MAX_HIST_ALTA' THEN VALOR_NUMERO END), 50) AS bat_caida_max_hist_alta,
                NVL(MAX(CASE WHEN CLAVE = 'BAT_CERO_HOY_ALTA_MIN' THEN VALOR_NUMERO END), 3) AS bat_cero_hoy_alta_min,
                NVL(MAX(CASE WHEN CLAVE = 'BAT_CERO_HOY_ALTA_MAX' THEN VALOR_NUMERO END), 9) AS bat_cero_hoy_alta_max,
                NVL(MAX(CASE WHEN CLAVE = 'BAT_CERO_HOY_ADV_MIN' THEN VALOR_NUMERO END), 1) AS bat_cero_hoy_adv_min,
                NVL(MAX(CASE WHEN CLAVE = 'BAT_CERO_HOY_ADV_MAX' THEN VALOR_NUMERO END), 2) AS bat_cero_hoy_adv_max,
                NVL(MAX(CASE WHEN CLAVE = 'BAT_CERO_HIST_ADV' THEN VALOR_NUMERO END), 12) AS bat_cero_hist_adv
            FROM USR_LAB.ALERTA_REGLA_PARAM
            WHERE ACTIVO = 1
        ),
        clasificacion AS (
            SELECT
                r.AMID,
                CASE
                    WHEN r.GPS_CERO_HOY >= c.gps_cero_hoy_critica THEN 'CRITICA'
                    WHEN r.GPS_CERO_PORC_HOY >= c.gps_porc_hoy_critica
                     AND r.GPS_TOTAL_HOY >= c.gps_total_hoy_critica THEN 'CRITICA'
                    WHEN r.RACHA_MAX_GPS_CERO >= c.gps_racha_critica
                     AND r.ULTIMA_FECHA_GPS_CERO >= r.FECHA_HOY THEN 'CRITICA'
                    WHEN r.GPS_CERO_HOY BETWEEN c.gps_cero_hoy_alta AND c.gps_cero_hoy_alta_max THEN 'ALTA'
                    WHEN r.GPS_CERO_PORC_HOY >= c.gps_porc_hoy_alta
                     AND r.GPS_TOTAL_HOY >= c.gps_total_hoy_alta THEN 'ALTA'
                    WHEN r.RACHA_MAX_GPS_CERO >= c.gps_racha_alta
                     AND r.ULTIMA_FECHA_GPS_CERO >= r.FECHA_HOY THEN 'ALTA'
                    WHEN r.ULTIMO_GPS_ES_CERO = 1 THEN 'ADVERTENCIA'
                    WHEN r.GPS_CERO_HOY BETWEEN c.gps_cero_hoy_adv AND c.gps_cero_hoy_adv_max THEN 'ADVERTENCIA'
                    WHEN r.GPS_CERO_HIST >= c.gps_cero_hist_adv THEN 'ADVERTENCIA'
                    WHEN r.GPS_CERO_PORC_HIST >= c.gps_porc_hist_adv THEN 'ADVERTENCIA'
                    ELSE 'OK'
                END AS nivel_gps,
                CASE
                    WHEN r.GPS_CERO_HOY >= c.gps_cero_hoy_critica THEN 'GPS 0,0 critico hoy'
                    WHEN r.GPS_CERO_PORC_HOY >= c.gps_porc_hoy_critica
                     AND r.GPS_TOTAL_HOY >= c.gps_total_hoy_critica THEN 'Porcentaje critico de GPS 0,0 hoy'
                    WHEN r.RACHA_MAX_GPS_CERO >= c.gps_racha_critica
                     AND r.ULTIMA_FECHA_GPS_CERO >= r.FECHA_HOY THEN 'Racha critica de GPS 0,0 hoy'
                    WHEN r.GPS_CERO_HOY BETWEEN c.gps_cero_hoy_alta AND c.gps_cero_hoy_alta_max THEN 'GPS 0,0 alto hoy'
                    WHEN r.GPS_CERO_PORC_HOY >= c.gps_porc_hoy_alta
                     AND r.GPS_TOTAL_HOY >= c.gps_total_hoy_alta THEN 'Porcentaje alto de GPS 0,0 hoy'
                    WHEN r.RACHA_MAX_GPS_CERO >= c.gps_racha_alta
                     AND r.ULTIMA_FECHA_GPS_CERO >= r.FECHA_HOY THEN 'Racha alta de GPS 0,0 hoy'
                    WHEN r.ULTIMO_GPS_ES_CERO = 1 THEN 'Ultimo GPS reportado es 0,0'
                    WHEN r.GPS_CERO_HOY BETWEEN c.gps_cero_hoy_adv AND c.gps_cero_hoy_adv_max THEN 'GPS 0,0 aislado hoy'
                    WHEN r.GPS_CERO_HIST >= c.gps_cero_hist_adv THEN 'GPS 0,0 historico alto'
                    WHEN r.GPS_CERO_PORC_HIST >= c.gps_porc_hist_adv THEN 'Porcentaje historico GPS 0,0 alto'
                    ELSE 'Sin alerta GPS'
                END AS motivo_gps,
                CASE
                    WHEN r.CAIDA_MAX_HOY >= c.bat_caida_hoy_critica THEN 'CRITICA'
                    WHEN r.ULTIMA_CAIDA_HASTA = 0
                     AND r.ULTIMA_FECHA_CAIDA >= r.FECHA_HOY THEN 'CRITICA'
                    WHEN r.CAIDAS_HOY >= c.bat_caidas_hoy_critica THEN 'CRITICA'
                    WHEN r.CAIDA_MAX_HOY >= c.bat_caida_hoy_critica_con_hist
                     AND r.CAIDAS_HIST >= 1 THEN 'CRITICA'
                    WHEN NVL(r.BATERIA_ACTUAL, -1) = 0
                     AND r.BATERIA_CERO_HOY >= c.bat_cero_hoy_critica THEN 'CRITICA'
                    WHEN r.CAIDA_MAX_HOY >= c.bat_caida_hoy_alta
                     AND r.CAIDA_MAX_HOY < c.bat_caida_hoy_critica THEN 'ALTA'
                    WHEN r.CAIDAS_HOY BETWEEN 1 AND 2
                     AND r.CAIDAS_HIST >= 1 THEN 'ALTA'
                    WHEN r.CAIDAS_HIST >= c.bat_caidas_hist_alta THEN 'ALTA'
                    WHEN r.CAIDA_MAX_HIST >= c.bat_caida_max_hist_alta THEN 'ALTA'
                    WHEN r.BATERIA_CERO_HOY BETWEEN c.bat_cero_hoy_alta_min AND c.bat_cero_hoy_alta_max
                     AND NVL(r.BATERIA_ACTUAL, -1) = 0 THEN 'ALTA'
                    WHEN r.BATERIA_CERO_HOY BETWEEN c.bat_cero_hoy_adv_min AND c.bat_cero_hoy_adv_max THEN 'ADVERTENCIA'
                    WHEN r.BATERIA_CERO_HOY >= c.bat_cero_hoy_alta_min
                     AND NVL(r.BATERIA_ACTUAL, -1) > 0 THEN 'ADVERTENCIA'
                    WHEN r.BATERIA_CERO_HIST >= c.bat_cero_hist_adv THEN 'ADVERTENCIA'
                    WHEN r.CAIDAS_HIST BETWEEN 1 AND 2
                     AND r.CAIDAS_HOY = 0 THEN 'ADVERTENCIA'
                    ELSE 'OK'
                END AS nivel_bateria,
                CASE
                    WHEN r.CAIDA_MAX_HOY >= c.bat_caida_hoy_critica THEN 'Caida critica de bateria hoy'
                    WHEN r.ULTIMA_CAIDA_HASTA = 0
                     AND r.ULTIMA_FECHA_CAIDA >= r.FECHA_HOY THEN 'Caida confirmada hacia 0% hoy'
                    WHEN r.CAIDAS_HOY >= c.bat_caidas_hoy_critica THEN 'Caidas recurrentes hoy'
                    WHEN r.CAIDA_MAX_HOY >= c.bat_caida_hoy_critica_con_hist
                     AND r.CAIDAS_HIST >= 1 THEN 'Caida severa hoy con historial'
                    WHEN NVL(r.BATERIA_ACTUAL, -1) = 0
                     AND r.BATERIA_CERO_HOY >= c.bat_cero_hoy_critica THEN 'Bateria 0 persistente hoy'
                    WHEN r.CAIDA_MAX_HOY >= c.bat_caida_hoy_alta
                     AND r.CAIDA_MAX_HOY < c.bat_caida_hoy_critica THEN 'Caida brusca de bateria hoy'
                    WHEN r.CAIDAS_HOY BETWEEN 1 AND 2
                     AND r.CAIDAS_HIST >= 1 THEN 'Caida hoy con historial'
                    WHEN r.CAIDAS_HIST >= c.bat_caidas_hist_alta THEN 'Caidas recurrentes historicas'
                    WHEN r.CAIDA_MAX_HIST >= c.bat_caida_max_hist_alta THEN 'Caida historica severa'
                    WHEN r.BATERIA_CERO_HOY BETWEEN c.bat_cero_hoy_alta_min AND c.bat_cero_hoy_alta_max
                     AND NVL(r.BATERIA_ACTUAL, -1) = 0 THEN 'Bateria 0 activa hoy'
                    WHEN r.BATERIA_CERO_HOY BETWEEN c.bat_cero_hoy_adv_min AND c.bat_cero_hoy_adv_max THEN 'Bateria 0 aislada hoy'
                    WHEN r.BATERIA_CERO_HOY >= c.bat_cero_hoy_alta_min
                     AND NVL(r.BATERIA_ACTUAL, -1) > 0 THEN 'Bateria 0 reportada hoy, actual normal'
                    WHEN r.BATERIA_CERO_HIST >= c.bat_cero_hist_adv THEN 'Bateria 0 historica alta'
                    WHEN r.CAIDAS_HIST BETWEEN 1 AND 2
                     AND r.CAIDAS_HOY = 0 THEN 'Caida historica aislada'
                    ELSE 'Sin alerta bateria'
                END AS motivo_bateria
            FROM USR_LAB.ALERTA_VALIDADOR_RESUMEN r
            JOIN USR_LAB.AMID_MAESTRO_ALERTAS m
              ON m.AMID = r.AMID
             AND m.ACTIVO = 1
            CROSS JOIN config c
        ),
        globalizada AS (
            SELECT
                c.*,
                CASE
                    WHEN c.nivel_gps = 'CRITICA' OR c.nivel_bateria = 'CRITICA' THEN 'CRITICA'
                    WHEN c.nivel_gps = 'ALTA' OR c.nivel_bateria = 'ALTA' THEN 'ALTA'
                    WHEN c.nivel_gps = 'ADVERTENCIA' AND c.nivel_bateria = 'ADVERTENCIA' THEN 'ALTA'
                    WHEN c.nivel_gps = 'ADVERTENCIA' OR c.nivel_bateria = 'ADVERTENCIA' THEN 'ADVERTENCIA'
                    ELSE 'OK'
                END AS nivel_global
            FROM clasificacion c
        )
        SELECT
            g.AMID,
            g.nivel_gps,
            g.motivo_gps,
            g.nivel_bateria,
            g.motivo_bateria,
            g.nivel_global,
            CASE
                WHEN g.nivel_gps = 'CRITICA' THEN g.motivo_gps
                WHEN g.nivel_bateria = 'CRITICA' THEN g.motivo_bateria
                WHEN g.nivel_gps = 'ALTA' AND g.nivel_bateria = 'ALTA' THEN 'GPS y bateria con alertas altas'
                WHEN g.nivel_gps = 'ALTA' THEN g.motivo_gps
                WHEN g.nivel_bateria = 'ALTA' THEN g.motivo_bateria
                WHEN g.nivel_gps = 'ADVERTENCIA' AND g.nivel_bateria = 'ADVERTENCIA' THEN 'GPS y bateria con advertencias'
                WHEN g.nivel_gps = 'ADVERTENCIA' THEN g.motivo_gps
                WHEN g.nivel_bateria = 'ADVERTENCIA' THEN g.motivo_bateria
                ELSE 'Sin alertas'
            END AS motivo_principal,
            CASE
                WHEN g.nivel_gps <> 'OK' AND g.nivel_bateria <> 'OK' THEN 'Revisar GPS y bateria'
                WHEN g.nivel_gps <> 'OK' THEN 'Revisar GPS'
                WHEN g.nivel_bateria <> 'OK' THEN 'Revisar bateria'
                ELSE 'Sin accion'
            END AS accion_sugerida
        FROM globalizada g
    ) origen
    ON (destino.AMID = origen.AMID)
    WHEN MATCHED THEN UPDATE SET
        destino.NIVEL_ALERTA_GPS = origen.nivel_gps,
        destino.MOTIVO_ALERTA_GPS = origen.motivo_gps,
        destino.NIVEL_ALERTA_BATERIA = origen.nivel_bateria,
        destino.MOTIVO_ALERTA_BATERIA = origen.motivo_bateria,
        destino.NIVEL_ALERTA_GLOBAL = origen.nivel_global,
        destino.MOTIVO_PRINCIPAL = origen.motivo_principal,
        destino.ACCION_SUGERIDA = origen.accion_sugerida,
        destino.TIENE_ALERTA = CASE WHEN origen.nivel_global <> 'OK' THEN 1 ELSE 0 END,
        destino.FECHA_REGLAS_APLICADAS = SYSDATE;

    v_filas_actualizadas := SQL%ROWCOUNT;
    COMMIT;

    DBMS_OUTPUT.PUT_LINE(
        'Reglas reaplicadas. Filas actualizadas: ' || v_filas_actualizadas
    );
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        DBMS_OUTPUT.PUT_LINE('Error reaplicando reglas: ' || SQLERRM);
        RAISE;
END;
/

PROMPT === Validacion de objetos creados ===
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN (
    'VW_ALERTA_VALIDADOR_ACTIVA',
    'PRC_APLICAR_REGLAS_ALERTA'
)
ORDER BY object_name;

PROMPT === Errores de compilacion, si existen ===
SELECT name, type, line, position, text
FROM user_errors
WHERE name IN (
    'VW_ALERTA_VALIDADOR_ACTIVA',
    'PRC_APLICAR_REGLAS_ALERTA'
)
ORDER BY name, sequence;

PROMPT === Comparacion de filas activas ===
SELECT
    (SELECT COUNT(*)
     FROM USR_LAB.AMID_MAESTRO_ALERTAS
     WHERE ACTIVO = 1) AS amids_activos,
    (SELECT COUNT(*)
     FROM USR_LAB.VW_ALERTA_VALIDADOR_ACTIVA) AS resumenes_activos;

-- Ejecucion manual opcional, despues de validar la compilacion:
-- BEGIN
--     USR_LAB.PRC_APLICAR_REGLAS_ALERTA;
-- END;
-- /

