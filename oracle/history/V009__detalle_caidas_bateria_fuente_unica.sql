-- V009 - Fuente unica para el detalle y el resumen de caidas de bateria.
-- No elimina ni modifica datos operativos. La tabla creada contiene datos
-- derivados y se reemplaza dentro de la misma transaccion del resumen.

DECLARE
    v_existe NUMBER;
BEGIN
    SELECT COUNT(*)
      INTO v_existe
      FROM USER_TABLES
     WHERE TABLE_NAME = 'ALERTA_BATERIA_CAIDA_EVENTO';

    IF v_existe = 0 THEN
        EXECUTE IMMEDIATE q'[
            CREATE TABLE USR_LAB.ALERTA_BATERIA_CAIDA_EVENTO (
                AMID               NUMBER NOT NULL,
                FECHA_CAIDA_DESDE  DATE NOT NULL,
                FECHA_CAIDA        DATE NOT NULL,
                BATERIA_DESDE      NUMBER(5,2) NOT NULL,
                BATERIA_HASTA      NUMBER(5,2) NOT NULL,
                CAIDA_DIF          NUMBER(5,2) NOT NULL,
                FECHA_CALCULO      DATE DEFAULT SYSDATE NOT NULL,
                CONSTRAINT PK_ALERTA_BAT_CAIDA_EVT
                    PRIMARY KEY (AMID, FECHA_CAIDA)
            )
        ]';
    END IF;
END;
/

CREATE OR REPLACE PROCEDURE USR_LAB.PRC_REFRESCAR_CAIDAS_BAT
AS
BEGIN
    -- Oracle mantiene la version confirmada anterior hasta el COMMIT. Si la
    -- actualizacion general falla, su ROLLBACK restaura tambien estos eventos.
    DELETE FROM USR_LAB.ALERTA_BATERIA_CAIDA_EVENTO;

    INSERT INTO USR_LAB.ALERTA_BATERIA_CAIDA_EVENTO (
        AMID,
        FECHA_CAIDA_DESDE,
        FECHA_CAIDA,
        BATERIA_DESDE,
        BATERIA_HASTA,
        CAIDA_DIF,
        FECHA_CALCULO
    )
    WITH parametros AS (
        SELECT
            TRUNC(SYSDATE) - 13 AS fecha_ini_hist,
            SYSDATE AS fecha_fin_hist
        FROM dual
    ),
    config_reglas AS (
        SELECT
            NVL(
                MAX(CASE
                    WHEN CLAVE = 'BAT_CAIDA_MIN_DETECTAR'
                    THEN VALOR_NUMERO
                END),
                20
            ) AS bat_caida_min_detectar,
            NVL(
                MAX(CASE
                    WHEN CLAVE = 'BAT_CAIDA_MAX_HORAS'
                    THEN VALOR_NUMERO
                END),
                2
            ) AS bat_caida_max_horas
        FROM USR_LAB.ALERTA_REGLA_PARAM
        WHERE ACTIVO = 1
    ),
    bloques_bateria AS (
        SELECT
            b.AMID,
            b.FECHA_HORA_BLOQUE,
            b.PORCENTAJE_BATERIA
        FROM USR_LAB.BATERIA_BLOQUE_30MIN b
        CROSS JOIN parametros p
        WHERE b.FECHA_HORA_BLOQUE >= p.fecha_ini_hist
          AND b.FECHA_HORA_BLOQUE <= p.fecha_fin_hist
          AND b.TIENE_DATO = 1
          AND b.PORCENTAJE_BATERIA IS NOT NULL
    ),
    bateria_ordenada AS (
        SELECT
            b.*,
            LAG(b.PORCENTAJE_BATERIA) OVER (
                PARTITION BY b.AMID
                ORDER BY b.FECHA_HORA_BLOQUE
            ) AS bateria_anterior,
            LAG(b.FECHA_HORA_BLOQUE) OVER (
                PARTITION BY b.AMID
                ORDER BY b.FECHA_HORA_BLOQUE
            ) AS fecha_anterior,
            LEAD(b.PORCENTAJE_BATERIA) OVER (
                PARTITION BY b.AMID
                ORDER BY b.FECHA_HORA_BLOQUE
            ) AS bateria_siguiente,
            LEAD(b.FECHA_HORA_BLOQUE) OVER (
                PARTITION BY b.AMID
                ORDER BY b.FECHA_HORA_BLOQUE
            ) AS fecha_siguiente
        FROM bloques_bateria b
    )
    SELECT
        bo.AMID,
        bo.fecha_anterior,
        bo.FECHA_HORA_BLOQUE,
        bo.bateria_anterior,
        bo.PORCENTAJE_BATERIA,
        bo.bateria_anterior - bo.PORCENTAJE_BATERIA,
        SYSDATE
    FROM bateria_ordenada bo
    CROSS JOIN config_reglas c
    WHERE bo.bateria_anterior IS NOT NULL
      AND bo.fecha_anterior IS NOT NULL
      AND bo.bateria_anterior > bo.PORCENTAJE_BATERIA
      AND (bo.FECHA_HORA_BLOQUE - bo.fecha_anterior) * 24
            <= c.bat_caida_max_horas
      AND bo.bateria_anterior - bo.PORCENTAJE_BATERIA
            >= c.bat_caida_min_detectar
      AND (
            bo.PORCENTAJE_BATERIA > 0
            OR (
                bo.PORCENTAJE_BATERIA = 0
                AND bo.bateria_siguiente = 0
                AND bo.fecha_siguiente IS NOT NULL
                AND (bo.fecha_siguiente - bo.FECHA_HORA_BLOQUE) * 24
                      <= c.bat_caida_max_horas
            )
      );
END;
/

CREATE OR REPLACE PROCEDURE USR_LAB.PRC_UPD_ALERTAS_VAL
AS
    v_total_antes NUMBER := 0;
    v_total_despues NUMBER := 0;
    v_filas_merge NUMBER := 0;
BEGIN
    SELECT COUNT(*)
    INTO v_total_antes
    FROM USR_LAB.ALERTA_VALIDADOR_RESUMEN;

    USR_LAB.PRC_REFRESCAR_CAIDAS_BAT;

    MERGE INTO USR_LAB.ALERTA_VALIDADOR_RESUMEN destino
    USING (
        WITH parametros AS (
            SELECT
                TRUNC(SYSDATE) AS fecha_hoy,
                TRUNC(SYSDATE) - 13 AS fecha_ini_hist,
                SYSDATE AS fecha_fin_hist
            FROM dual
        ),

        config_reglas AS (
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

        registros_gps AS (
            SELECT
                v.AMID,
                v.FECHA_HORA,
                v.LATITUD,
                v.LONGITUD,
                CASE
                    WHEN v.LATITUD = 0 AND v.LONGITUD = 0 THEN 1
                    ELSE 0
                END AS es_gps_cero
            FROM USR_LAB.VW_ESTATUS_ZP_DJANGO v
            CROSS JOIN parametros p
            WHERE v.AMID IS NOT NULL
              AND v.FECHA_HORA >= p.fecha_ini_hist
              AND v.FECHA_HORA <= p.fecha_fin_hist
              AND v.LATITUD IS NOT NULL
              AND v.LONGITUD IS NOT NULL
        ),

        ultimo_estatus AS (
            SELECT
                v.AMID,
                MAX(v.FECHA_HORA) AS ultimo_estatus
            FROM USR_LAB.VW_ESTATUS_ZP_DJANGO v
            CROSS JOIN parametros p
            WHERE v.AMID IS NOT NULL
              AND v.FECHA_HORA >= p.fecha_ini_hist
              AND v.FECHA_HORA <= p.fecha_fin_hist
            GROUP BY v.AMID
        ),

        ultimo_gps AS (
            SELECT
                AMID,
                FECHA_HORA AS ultimo_gps_fecha,
                es_gps_cero AS ultimo_gps_es_cero
            FROM (
                SELECT
                    r.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY r.AMID
                        ORDER BY r.FECHA_HORA DESC
                    ) AS rn
                FROM registros_gps r
            )
            WHERE rn = 1
        ),

        ultima_gps_cero AS (
            SELECT
                AMID,
                MAX(FECHA_HORA) AS ultima_fecha_gps_cero
            FROM registros_gps
            WHERE es_gps_cero = 1
            GROUP BY AMID
        ),

        gps_base_racha AS (
            SELECT
                r.*,
                SUM(
                    CASE
                        WHEN r.es_gps_cero = 0 THEN 1
                        ELSE 0
                    END
                ) OVER (
                    PARTITION BY r.AMID
                    ORDER BY r.FECHA_HORA
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) AS grupo_racha
            FROM registros_gps r
        ),

        gps_rachas AS (
            SELECT
                AMID,
                COUNT(*) AS largo_racha
            FROM gps_base_racha
            WHERE es_gps_cero = 1
            GROUP BY AMID, grupo_racha
        ),

        gps_racha_max AS (
            SELECT
                AMID,
                MAX(largo_racha) AS racha_max_gps_cero
            FROM gps_rachas
            GROUP BY AMID
        ),

        gps_resumen AS (
            SELECT
                r.AMID,
                COUNT(CASE
                    WHEN r.FECHA_HORA >= TRUNC(SYSDATE)
                     AND r.FECHA_HORA < TRUNC(SYSDATE) + 1
                    THEN 1
                END) AS gps_total_hoy,

                SUM(CASE
                    WHEN r.FECHA_HORA >= TRUNC(SYSDATE)
                     AND r.FECHA_HORA < TRUNC(SYSDATE) + 1
                     AND r.es_gps_cero = 1
                    THEN 1
                    ELSE 0
                END) AS gps_cero_hoy,

                COUNT(*) AS gps_total_hist,

                SUM(CASE
                    WHEN r.es_gps_cero = 1 THEN 1
                    ELSE 0
                END) AS gps_cero_hist,

                COUNT(DISTINCT CASE
                    WHEN r.es_gps_cero = 1 THEN TRUNC(r.FECHA_HORA)
                END) AS gps_cero_dias_hist
            FROM registros_gps r
            GROUP BY r.AMID
        ),

        bloques_bateria AS (
            SELECT
                b.AMID,
                b.FECHA_HORA_BLOQUE,
                b.PORCENTAJE_BATERIA,
                b.TIENE_DATO
            FROM USR_LAB.BATERIA_BLOQUE_30MIN b
            CROSS JOIN parametros p
            WHERE b.FECHA_HORA_BLOQUE >= p.fecha_ini_hist
              AND b.FECHA_HORA_BLOQUE <= p.fecha_fin_hist
              AND b.TIENE_DATO = 1
              AND b.PORCENTAJE_BATERIA IS NOT NULL
        ),

        caidas_detectadas AS (
            SELECT
                e.AMID,
                e.FECHA_CAIDA_DESDE AS fecha_caida_desde,
                e.FECHA_CAIDA AS fecha_caida,
                e.BATERIA_DESDE AS caida_desde,
                e.BATERIA_HASTA AS caida_hasta,
                e.CAIDA_DIF AS caida_dif
            FROM USR_LAB.ALERTA_BATERIA_CAIDA_EVENTO e
        ),

        ultima_bateria AS (
            SELECT
                AMID,
                FECHA_HORA_BLOQUE AS ultima_fecha_bateria,
                PORCENTAJE_BATERIA AS bateria_actual,
                CASE
                    WHEN PORCENTAJE_BATERIA = 0 THEN 1
                    ELSE 0
                END AS ult_bloque_bat_es_cero
            FROM (
                SELECT
                    b.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY b.AMID
                        ORDER BY b.FECHA_HORA_BLOQUE DESC
                    ) AS rn
                FROM bloques_bateria b
            )
            WHERE rn = 1
        ),

        ultima_caida AS (
            SELECT
                AMID,
                fecha_caida AS ultima_fecha_caida,
                caida_desde AS ultima_caida_desde,
                caida_hasta AS ultima_caida_hasta,
                caida_dif AS ultima_caida_dif
            FROM (
                SELECT
                    c.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY c.AMID
                        ORDER BY c.fecha_caida DESC
                    ) AS rn
                FROM caidas_detectadas c
            )
            WHERE rn = 1
        ),

        bateria_resumen AS (
            SELECT
                b.AMID,

                SUM(CASE
                    WHEN b.FECHA_HORA_BLOQUE >= TRUNC(SYSDATE)
                     AND b.FECHA_HORA_BLOQUE < TRUNC(SYSDATE) + 1
                     AND b.PORCENTAJE_BATERIA = 0
                    THEN 1
                    ELSE 0
                END) AS bateria_cero_hoy,

                SUM(CASE
                    WHEN b.PORCENTAJE_BATERIA = 0 THEN 1
                    ELSE 0
                END) AS bateria_cero_hist,

                MAX(CASE
                    WHEN b.PORCENTAJE_BATERIA = 0 THEN b.FECHA_HORA_BLOQUE
                END) AS ultima_fecha_bat_cero
            FROM bloques_bateria b
            GROUP BY b.AMID
        ),

        caidas_resumen AS (
            SELECT
                c.AMID,

                SUM(CASE
                    WHEN c.fecha_caida >= TRUNC(SYSDATE)
                     AND c.fecha_caida < TRUNC(SYSDATE) + 1
                    THEN 1
                    ELSE 0
                END) AS caidas_hoy,

                COUNT(*) AS caidas_hist,

                MAX(CASE
                    WHEN c.fecha_caida >= TRUNC(SYSDATE)
                     AND c.fecha_caida < TRUNC(SYSDATE) + 1
                    THEN c.caida_dif
                    ELSE 0
                END) AS caida_max_hoy,

                MAX(c.caida_dif) AS caida_max_hist
            FROM caidas_detectadas c
            GROUP BY c.AMID
        ),

        base AS (
            SELECT
                m.AMID,
                p.fecha_hoy,
                p.fecha_ini_hist,
                p.fecha_fin_hist,

                ue.ultimo_estatus,

                NVL(g.gps_total_hoy, 0) AS gps_total_hoy,
                NVL(g.gps_cero_hoy, 0) AS gps_cero_hoy,
                NVL(g.gps_total_hist, 0) AS gps_total_hist,
                NVL(g.gps_cero_hist, 0) AS gps_cero_hist,
                NVL(g.gps_cero_dias_hist, 0) AS gps_cero_dias_hist,

                CASE
                    WHEN NVL(g.gps_total_hoy, 0) > 0
                    THEN ROUND((NVL(g.gps_cero_hoy, 0) / g.gps_total_hoy) * 100, 2)
                    ELSE 0
                END AS gps_cero_porc_hoy,

                CASE
                    WHEN NVL(g.gps_total_hist, 0) > 0
                    THEN ROUND((NVL(g.gps_cero_hist, 0) / g.gps_total_hist) * 100, 2)
                    ELSE 0
                END AS gps_cero_porc_hist,

                ug.ultimo_gps_fecha,
                NVL(ug.ultimo_gps_es_cero, 0) AS ultimo_gps_es_cero,
                zg.ultima_fecha_gps_cero,
                NVL(rm.racha_max_gps_cero, 0) AS racha_max_gps_cero,

                ub.bateria_actual,
                ub.ultima_fecha_bateria,

                NVL(cr.caidas_hoy, 0) AS caidas_hoy,
                NVL(cr.caidas_hist, 0) AS caidas_hist,
                uc.ultima_fecha_caida,
                uc.ultima_caida_desde,
                uc.ultima_caida_hasta,
                uc.ultima_caida_dif,
                NVL(cr.caida_max_hoy, 0) AS caida_max_hoy,
                NVL(cr.caida_max_hist, 0) AS caida_max_hist,

                NVL(br.bateria_cero_hoy, 0) AS bateria_cero_hoy,
                NVL(br.bateria_cero_hist, 0) AS bateria_cero_hist,
                br.ultima_fecha_bat_cero,
                NVL(ub.ult_bloque_bat_es_cero, 0) AS ult_bloque_bat_es_cero

            FROM USR_LAB.AMID_MAESTRO_ALERTAS m
            CROSS JOIN parametros p
            LEFT JOIN ultimo_estatus ue ON ue.AMID = m.AMID
            LEFT JOIN gps_resumen g ON g.AMID = m.AMID
            LEFT JOIN ultimo_gps ug ON ug.AMID = m.AMID
            LEFT JOIN ultima_gps_cero zg ON zg.AMID = m.AMID
            LEFT JOIN gps_racha_max rm ON rm.AMID = m.AMID
            LEFT JOIN ultima_bateria ub ON ub.AMID = m.AMID
            LEFT JOIN bateria_resumen br ON br.AMID = m.AMID
            LEFT JOIN caidas_resumen cr ON cr.AMID = m.AMID
            LEFT JOIN ultima_caida uc ON uc.AMID = m.AMID
            WHERE m.ACTIVO = 1
        ),

        alertas_parciales AS (
            SELECT
                b.*,

                CASE
                    WHEN b.gps_cero_hoy >= c.gps_cero_hoy_critica THEN 'CRITICA'

                    WHEN b.gps_cero_porc_hoy >= c.gps_porc_hoy_critica
                     AND b.gps_total_hoy >= c.gps_total_hoy_critica THEN 'CRITICA'

                    WHEN b.racha_max_gps_cero >= c.gps_racha_critica
                     AND b.ultima_fecha_gps_cero >= b.fecha_hoy THEN 'CRITICA'

                    WHEN b.gps_cero_hoy BETWEEN c.gps_cero_hoy_alta AND c.gps_cero_hoy_alta_max THEN 'ALTA'

                    WHEN b.gps_cero_porc_hoy >= c.gps_porc_hoy_alta
                     AND b.gps_total_hoy >= c.gps_total_hoy_alta THEN 'ALTA'

                    WHEN b.racha_max_gps_cero >= c.gps_racha_alta
                     AND b.ultima_fecha_gps_cero >= b.fecha_hoy THEN 'ALTA'

                    WHEN b.ultimo_gps_es_cero = 1 THEN 'ADVERTENCIA'

                    WHEN b.gps_cero_hoy BETWEEN c.gps_cero_hoy_adv AND c.gps_cero_hoy_adv_max THEN 'ADVERTENCIA'

                    WHEN b.gps_cero_hist >= c.gps_cero_hist_adv THEN 'ADVERTENCIA'

                    WHEN b.gps_cero_porc_hist >= c.gps_porc_hist_adv THEN 'ADVERTENCIA'

                    ELSE 'OK'
                END AS nivel_alerta_gps,

                CASE
                    WHEN b.gps_cero_hoy >= c.gps_cero_hoy_critica THEN 'GPS 0,0 crítico hoy'

                    WHEN b.gps_cero_porc_hoy >= c.gps_porc_hoy_critica
                     AND b.gps_total_hoy >= c.gps_total_hoy_critica THEN 'Porcentaje crítico de GPS 0,0 hoy'

                    WHEN b.racha_max_gps_cero >= c.gps_racha_critica
                     AND b.ultima_fecha_gps_cero >= b.fecha_hoy THEN 'Racha crítica de GPS 0,0 hoy'

                    WHEN b.gps_cero_hoy BETWEEN c.gps_cero_hoy_alta AND c.gps_cero_hoy_alta_max THEN 'GPS 0,0 alto hoy'

                    WHEN b.gps_cero_porc_hoy >= c.gps_porc_hoy_alta
                     AND b.gps_total_hoy >= c.gps_total_hoy_alta THEN 'Porcentaje alto de GPS 0,0 hoy'

                    WHEN b.racha_max_gps_cero >= c.gps_racha_alta
                     AND b.ultima_fecha_gps_cero >= b.fecha_hoy THEN 'Racha alta de GPS 0,0 hoy'

                    WHEN b.ultimo_gps_es_cero = 1 THEN 'Último GPS reportado es 0,0'

                    WHEN b.gps_cero_hoy BETWEEN c.gps_cero_hoy_adv AND c.gps_cero_hoy_adv_max THEN 'GPS 0,0 aislado hoy'

                    WHEN b.gps_cero_hist >= c.gps_cero_hist_adv THEN 'GPS 0,0 histórico alto'

                    WHEN b.gps_cero_porc_hist >= c.gps_porc_hist_adv THEN 'Porcentaje histórico GPS 0,0 alto'

                    ELSE 'Sin alerta GPS'
                END AS motivo_alerta_gps,

                CASE
                    WHEN b.caida_max_hoy >= c.bat_caida_hoy_critica THEN 'CRITICA'

                    WHEN b.ultima_caida_hasta = 0
                     AND b.ultima_fecha_caida >= b.fecha_hoy THEN 'CRITICA'

                    WHEN b.caidas_hoy >= c.bat_caidas_hoy_critica THEN 'CRITICA'

                    WHEN b.caida_max_hoy >= c.bat_caida_hoy_critica_con_hist
                     AND b.caidas_hist >= 1 THEN 'CRITICA'

                    WHEN NVL(b.bateria_actual, -1) = 0
                     AND b.bateria_cero_hoy >= c.bat_cero_hoy_critica THEN 'CRITICA'

                    WHEN b.caida_max_hoy >= c.bat_caida_hoy_alta
                     AND b.caida_max_hoy < c.bat_caida_hoy_critica THEN 'ALTA'

                    WHEN b.caidas_hoy BETWEEN 1 AND 2
                     AND b.caidas_hist >= 1 THEN 'ALTA'

                    WHEN b.caidas_hist >= c.bat_caidas_hist_alta THEN 'ALTA'

                    WHEN b.caida_max_hist >= c.bat_caida_max_hist_alta THEN 'ALTA'

                    WHEN b.bateria_cero_hoy BETWEEN c.bat_cero_hoy_alta_min AND c.bat_cero_hoy_alta_max
                     AND NVL(b.bateria_actual, -1) = 0 THEN 'ALTA'

                    WHEN b.bateria_cero_hoy BETWEEN c.bat_cero_hoy_adv_min AND c.bat_cero_hoy_adv_max THEN 'ADVERTENCIA'

                    WHEN b.bateria_cero_hoy >= c.bat_cero_hoy_alta_min
                     AND NVL(b.bateria_actual, -1) > 0 THEN 'ADVERTENCIA'

                    WHEN b.bateria_cero_hist >= c.bat_cero_hist_adv THEN 'ADVERTENCIA'

                    WHEN b.caidas_hist BETWEEN 1 AND 2
                     AND b.caidas_hoy = 0 THEN 'ADVERTENCIA'

                    ELSE 'OK'
                END AS nivel_alerta_bateria,

                CASE
                    WHEN b.caida_max_hoy >= c.bat_caida_hoy_critica THEN 'Caída crítica de batería hoy'

                    WHEN b.ultima_caida_hasta = 0
                     AND b.ultima_fecha_caida >= b.fecha_hoy THEN 'Caída confirmada hacia 0% hoy'

                    WHEN b.caidas_hoy >= c.bat_caidas_hoy_critica THEN 'Caídas recurrentes hoy'

                    WHEN b.caida_max_hoy >= c.bat_caida_hoy_critica_con_hist
                     AND b.caidas_hist >= 1 THEN 'Caída severa hoy con historial'

                    WHEN NVL(b.bateria_actual, -1) = 0
                     AND b.bateria_cero_hoy >= c.bat_cero_hoy_critica THEN 'Batería 0 persistente hoy'

                    WHEN b.caida_max_hoy >= c.bat_caida_hoy_alta
                     AND b.caida_max_hoy < c.bat_caida_hoy_critica THEN 'Caída brusca de batería hoy'

                    WHEN b.caidas_hoy BETWEEN 1 AND 2
                     AND b.caidas_hist >= 1 THEN 'Caída hoy con historial'

                    WHEN b.caidas_hist >= c.bat_caidas_hist_alta THEN 'Caídas recurrentes históricas'

                    WHEN b.caida_max_hist >= c.bat_caida_max_hist_alta THEN 'Caída histórica severa'

                    WHEN b.bateria_cero_hoy BETWEEN c.bat_cero_hoy_alta_min AND c.bat_cero_hoy_alta_max
                     AND NVL(b.bateria_actual, -1) = 0 THEN 'Batería 0 activa hoy'

                    WHEN b.bateria_cero_hoy BETWEEN c.bat_cero_hoy_adv_min AND c.bat_cero_hoy_adv_max THEN 'Batería 0 aislada hoy'

                    WHEN b.bateria_cero_hoy >= c.bat_cero_hoy_alta_min
                     AND NVL(b.bateria_actual, -1) > 0 THEN 'Batería 0 reportada hoy, actual normal'

                    WHEN b.bateria_cero_hist >= c.bat_cero_hist_adv THEN 'Batería 0 histórica alta'

                    WHEN b.caidas_hist BETWEEN 1 AND 2
                     AND b.caidas_hoy = 0 THEN 'Caída histórica aislada'

                    ELSE 'Sin alerta batería'
                END AS motivo_alerta_bateria

            FROM base b
            CROSS JOIN config_reglas c
        ),

        alertas_globales AS (
            SELECT
                a.*,
                CASE
                    WHEN a.nivel_alerta_gps = 'CRITICA'
                      OR a.nivel_alerta_bateria = 'CRITICA'
                    THEN 'CRITICA'

                    WHEN a.nivel_alerta_gps = 'ALTA'
                      OR a.nivel_alerta_bateria = 'ALTA'
                    THEN 'ALTA'

                    WHEN a.nivel_alerta_gps = 'ADVERTENCIA'
                      AND a.nivel_alerta_bateria = 'ADVERTENCIA'
                    THEN 'ALTA'

                    WHEN a.nivel_alerta_gps = 'ADVERTENCIA'
                      OR a.nivel_alerta_bateria = 'ADVERTENCIA'
                    THEN 'ADVERTENCIA'

                    ELSE 'OK'
                END AS nivel_alerta_global
            FROM alertas_parciales a
        ),

        final_alertas AS (
            SELECT
                ag.*,

                CASE
                    WHEN ag.nivel_alerta_gps = 'CRITICA' THEN ag.motivo_alerta_gps
                    WHEN ag.nivel_alerta_bateria = 'CRITICA' THEN ag.motivo_alerta_bateria

                    WHEN ag.nivel_alerta_gps = 'ALTA'
                     AND ag.nivel_alerta_bateria = 'ALTA'
                    THEN 'GPS y batería con alertas altas'

                    WHEN ag.nivel_alerta_gps = 'ALTA' THEN ag.motivo_alerta_gps
                    WHEN ag.nivel_alerta_bateria = 'ALTA' THEN ag.motivo_alerta_bateria

                    WHEN ag.nivel_alerta_gps = 'ADVERTENCIA'
                     AND ag.nivel_alerta_bateria = 'ADVERTENCIA'
                    THEN 'GPS y batería con advertencias'

                    WHEN ag.nivel_alerta_gps = 'ADVERTENCIA' THEN ag.motivo_alerta_gps
                    WHEN ag.nivel_alerta_bateria = 'ADVERTENCIA' THEN ag.motivo_alerta_bateria

                    ELSE 'Sin alertas'
                END AS motivo_principal,

                CASE
                    WHEN ag.nivel_alerta_gps <> 'OK'
                     AND ag.nivel_alerta_bateria <> 'OK'
                    THEN 'Revisar GPS y batería'

                    WHEN ag.nivel_alerta_gps <> 'OK'
                    THEN 'Revisar GPS'

                    WHEN ag.nivel_alerta_bateria <> 'OK'
                    THEN 'Revisar batería'

                    ELSE 'Sin acción'
                END AS accion_sugerida,

                CASE
                    WHEN ag.nivel_alerta_global <> 'OK' THEN 1
                    ELSE 0
                END AS tiene_alerta

            FROM alertas_globales ag
        )

        SELECT
            AMID,
            fecha_hoy,
            fecha_ini_hist,
            fecha_fin_hist,
            ultimo_estatus,

            gps_total_hoy,
            gps_cero_hoy,
            gps_total_hist,
            gps_cero_hist,
            gps_cero_dias_hist,
            gps_cero_porc_hoy,
            gps_cero_porc_hist,
            ultimo_gps_fecha,
            ultimo_gps_es_cero,
            ultima_fecha_gps_cero,
            racha_max_gps_cero,
            nivel_alerta_gps,
            motivo_alerta_gps,

            bateria_actual,
            ultima_fecha_bateria,
            caidas_hoy,
            caidas_hist,
            ultima_fecha_caida,
            ultima_caida_desde,
            ultima_caida_hasta,
            ultima_caida_dif,
            caida_max_hoy,
            caida_max_hist,
            bateria_cero_hoy,
            bateria_cero_hist,
            ultima_fecha_bat_cero,
            ult_bloque_bat_es_cero,
            nivel_alerta_bateria,
            motivo_alerta_bateria,

            nivel_alerta_global,
            motivo_principal,
            accion_sugerida,
            tiene_alerta,
            SYSDATE AS fecha_actualizacion
        FROM final_alertas
    ) origen
    ON (destino.AMID = origen.AMID)

    WHEN MATCHED THEN
        UPDATE SET
            destino.FECHA_HOY = origen.fecha_hoy,
            destino.FECHA_INI_HIST = origen.fecha_ini_hist,
            destino.FECHA_FIN_HIST = origen.fecha_fin_hist,
            destino.ULTIMO_ESTATUS = origen.ultimo_estatus,

            destino.GPS_TOTAL_HOY = origen.gps_total_hoy,
            destino.GPS_CERO_HOY = origen.gps_cero_hoy,
            destino.GPS_TOTAL_HIST = origen.gps_total_hist,
            destino.GPS_CERO_HIST = origen.gps_cero_hist,
            destino.GPS_CERO_DIAS_HIST = origen.gps_cero_dias_hist,
            destino.GPS_CERO_PORC_HOY = origen.gps_cero_porc_hoy,
            destino.GPS_CERO_PORC_HIST = origen.gps_cero_porc_hist,
            destino.ULTIMO_GPS_FECHA = origen.ultimo_gps_fecha,
            destino.ULTIMO_GPS_ES_CERO = origen.ultimo_gps_es_cero,
            destino.ULTIMA_FECHA_GPS_CERO = origen.ultima_fecha_gps_cero,
            destino.RACHA_MAX_GPS_CERO = origen.racha_max_gps_cero,
            destino.NIVEL_ALERTA_GPS = origen.nivel_alerta_gps,
            destino.MOTIVO_ALERTA_GPS = origen.motivo_alerta_gps,

            destino.BATERIA_ACTUAL = origen.bateria_actual,
            destino.ULTIMA_FECHA_BATERIA = origen.ultima_fecha_bateria,
            destino.CAIDAS_HOY = origen.caidas_hoy,
            destino.CAIDAS_HIST = origen.caidas_hist,
            destino.ULTIMA_FECHA_CAIDA = origen.ultima_fecha_caida,
            destino.ULTIMA_CAIDA_DESDE = origen.ultima_caida_desde,
            destino.ULTIMA_CAIDA_HASTA = origen.ultima_caida_hasta,
            destino.ULTIMA_CAIDA_DIF = origen.ultima_caida_dif,
            destino.CAIDA_MAX_HOY = origen.caida_max_hoy,
            destino.CAIDA_MAX_HIST = origen.caida_max_hist,
            destino.BATERIA_CERO_HOY = origen.bateria_cero_hoy,
            destino.BATERIA_CERO_HIST = origen.bateria_cero_hist,
            destino.ULTIMA_FECHA_BAT_CERO = origen.ultima_fecha_bat_cero,
            destino.ULT_BLOQUE_BAT_ES_CERO = origen.ult_bloque_bat_es_cero,
            destino.NIVEL_ALERTA_BATERIA = origen.nivel_alerta_bateria,
            destino.MOTIVO_ALERTA_BATERIA = origen.motivo_alerta_bateria,

            destino.NIVEL_ALERTA_GLOBAL = origen.nivel_alerta_global,
            destino.MOTIVO_PRINCIPAL = origen.motivo_principal,
            destino.ACCION_SUGERIDA = origen.accion_sugerida,
            destino.TIENE_ALERTA = origen.tiene_alerta,
            destino.FECHA_ACTUALIZACION = SYSDATE

    WHEN NOT MATCHED THEN
        INSERT (
            AMID,
            FECHA_HOY,
            FECHA_INI_HIST,
            FECHA_FIN_HIST,
            ULTIMO_ESTATUS,

            GPS_TOTAL_HOY,
            GPS_CERO_HOY,
            GPS_TOTAL_HIST,
            GPS_CERO_HIST,
            GPS_CERO_DIAS_HIST,
            GPS_CERO_PORC_HOY,
            GPS_CERO_PORC_HIST,
            ULTIMO_GPS_FECHA,
            ULTIMO_GPS_ES_CERO,
            ULTIMA_FECHA_GPS_CERO,
            RACHA_MAX_GPS_CERO,
            NIVEL_ALERTA_GPS,
            MOTIVO_ALERTA_GPS,

            BATERIA_ACTUAL,
            ULTIMA_FECHA_BATERIA,
            CAIDAS_HOY,
            CAIDAS_HIST,
            ULTIMA_FECHA_CAIDA,
            ULTIMA_CAIDA_DESDE,
            ULTIMA_CAIDA_HASTA,
            ULTIMA_CAIDA_DIF,
            CAIDA_MAX_HOY,
            CAIDA_MAX_HIST,
            BATERIA_CERO_HOY,
            BATERIA_CERO_HIST,
            ULTIMA_FECHA_BAT_CERO,
            ULT_BLOQUE_BAT_ES_CERO,
            NIVEL_ALERTA_BATERIA,
            MOTIVO_ALERTA_BATERIA,

            NIVEL_ALERTA_GLOBAL,
            MOTIVO_PRINCIPAL,
            ACCION_SUGERIDA,
            TIENE_ALERTA,
            FECHA_ACTUALIZACION
        )
        VALUES (
            origen.AMID,
            origen.fecha_hoy,
            origen.fecha_ini_hist,
            origen.fecha_fin_hist,
            origen.ultimo_estatus,

            origen.gps_total_hoy,
            origen.gps_cero_hoy,
            origen.gps_total_hist,
            origen.gps_cero_hist,
            origen.gps_cero_dias_hist,
            origen.gps_cero_porc_hoy,
            origen.gps_cero_porc_hist,
            origen.ultimo_gps_fecha,
            origen.ultimo_gps_es_cero,
            origen.ultima_fecha_gps_cero,
            origen.racha_max_gps_cero,
            origen.nivel_alerta_gps,
            origen.motivo_alerta_gps,

            origen.bateria_actual,
            origen.ultima_fecha_bateria,
            origen.caidas_hoy,
            origen.caidas_hist,
            origen.ultima_fecha_caida,
            origen.ultima_caida_desde,
            origen.ultima_caida_hasta,
            origen.ultima_caida_dif,
            origen.caida_max_hoy,
            origen.caida_max_hist,
            origen.bateria_cero_hoy,
            origen.bateria_cero_hist,
            origen.ultima_fecha_bat_cero,
            origen.ult_bloque_bat_es_cero,
            origen.nivel_alerta_bateria,
            origen.motivo_alerta_bateria,

            origen.nivel_alerta_global,
            origen.motivo_principal,
            origen.accion_sugerida,
            origen.tiene_alerta,
            SYSDATE
        );

    v_filas_merge := SQL%ROWCOUNT;

    SELECT COUNT(*)
    INTO v_total_despues
    FROM USR_LAB.ALERTA_VALIDADOR_RESUMEN;

    COMMIT;

    DBMS_OUTPUT.PUT_LINE('Actualización alertas finalizada.');
    DBMS_OUTPUT.PUT_LINE('Total antes: ' || v_total_antes);
    DBMS_OUTPUT.PUT_LINE('Total después: ' || v_total_despues);
    DBMS_OUTPUT.PUT_LINE('Filas afectadas MERGE: ' || v_filas_merge);

EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        DBMS_OUTPUT.PUT_LINE('Error actualizando alertas: ' || SQLERRM);
        RAISE;
END;
/
