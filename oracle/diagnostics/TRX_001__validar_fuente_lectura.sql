-- ============================================================================
-- TRX_001: validación de la fuente de transacciones C2D. Sólo lectura.
-- ============================================================================
-- Objetivo: confirmar, ANTES de encender TRX_ORACLE_HABILITADO, que el módulo
-- puede leer la fuente con el SQL que usa apps/transacciones.
--
-- Este script NO crea, altera ni modifica ningún objeto. Solo SELECT.
-- No usar FETCH FIRST: la instancia es Oracle 11g.
--
-- ----------------------------------------------------------------------------
-- CÓMO EDITAR LAS FECHAS
-- ----------------------------------------------------------------------------
-- Hay UN solo lugar para cambiar el rango: las dos líneas v_fecha_inicio y
-- v_fecha_fin del bloque DECLARE, más abajo. El SQL de cada consulta las
-- referencia por nombre (PL/SQL las resuelve al compilar el bloque), así que
-- no hay fechas repetidas por el script.
--
-- Edita ese bloque y vuelve a ejecutar el archivo completo.
--   DBeaver: seleccionar todo el bloque y Ctrl+Enter (o botón Run Script).
--   SQLcl / SQL*Plus: @trx_001.sql
-- SET SERVEROUTPUT ON es necesario para ver la salida etiquetada.
--
-- El rango es [v_fecha_inicio, v_fecha_fin] INCLUSIVO de ambos días: la variable
-- v_fecha_hasta_exclusiva = v_fecha_fin + 1 es la que se compara con "<", igual
-- que el bind :fecha_hasta del repositorio. No editar esa línea.
--
-- Riesgo conocido: TVF_SFECTRANSACCION es VARCHAR2 y se convierte con
-- TO_DATE(..., 'YYYY/MM/DD HH24:MI:SS'). Si el dato real viene con otro
-- separador u otro orden, la consulta responde ORA-01861. El bloque 1 mide
-- la longitud y los formatos reales antes de confiar en la conversión.
-- ============================================================================

SET SERVEROUTPUT ON
SET LINESIZE 200
SET PAGESIZE 200

DECLARE
    -- =========================================================================
    -- >>> ÚNICO PUNTO DE EDICIÓN DEL RANGO <<<
    -- =========================================================================
    v_fecha_inicio  DATE := DATE '2026-08-27';
    v_fecha_fin     DATE := DATE '2026-08-28';
    -- =========================================================================
    -- Fin del bloque de parámetros. No editar nada más arriba.
    -- =========================================================================

    v_fecha_hasta_exclusiva DATE := v_fecha_fin + 1;
    v_amid_minimo           NUMBER := 7500000;
    v_muestra               PLS_INTEGER := 5;

    -- Salida etiquetada. El ancho de linea no depende de la sesion.
    PROCEDURE titulo(p_texto VARCHAR2) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE('');
        DBMS_OUTPUT.PUT_LINE(RPAD('=== ' || p_texto || ' ', 76, '='));
    END titulo;

    PROCEDURE linea(p_etiqueta VARCHAR2, p_valor VARCHAR2) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE('  ' || RPAD(p_etiqueta, 42) || ' : ' || p_valor);
    END linea;

    PROCEDURE nota(p_texto VARCHAR2) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE('  ' || p_texto);
    END nota;

BEGIN
    titulo('0. Contexto de la sesión');
    linea('Base de datos', SYS_CONTEXT('USERENV', 'DB_NAME'));
    linea('Servicio', SYS_CONTEXT('USERENV', 'SERVICE_NAME'));
    linea('Usuario', SYS_CONTEXT('USERENV', 'SESSION_USER'));

    DECLARE
        v_banner VARCHAR2(200);
    BEGIN
        SELECT BANNER INTO v_banner
        FROM V$VERSION
        WHERE ROWNUM = 1;

        linea('Version', v_banner);
    EXCEPTION
        WHEN OTHERS THEN
            linea('Version', 'no disponible sin privilegios sobre V$VERSION');
    END;

    linea(
        'Rango validado',
        TO_CHAR(v_fecha_inicio, 'DD/MM/YYYY') || ' a ' ||
        TO_CHAR(v_fecha_fin, 'DD/MM/YYYY') || ' (ambos dias incluidos)'
    );
    linea('Piso del universo AMID', '> ' || TO_CHAR(v_amid_minimo));

    ------------------------------------------------------------------
    titulo('1. Formato real de TVF_SFECTRANSACCION');
    nota('Si LENGTH <> 19, el TO_DATE del repositorio va a fallar.');

    FOR r_formato IN (
        SELECT
            LENGTH(TR.TVF_SFECTRANSACCION) AS LONGITUD,
            COUNT(*)                        AS TOTAL,
            MIN(TR.TVF_SFECTRANSACCION)    AS EJEMPLO_MINIMO,
            MAX(TR.TVF_SFECTRANSACCION)    AS EJEMPLO_MAXIMO
        FROM DBPTE.TRANSACCION_FLUJO_VC2D_FISC@CLEAMTT3PRODG TR
        WHERE TR.TVF_NIDAS > v_amid_minimo
          AND TR.TVF_DFECREGISTRO >= v_fecha_inicio
          AND TR.TVF_DFECREGISTRO < v_fecha_hasta_exclusiva
        GROUP BY LENGTH(TR.TVF_SFECTRANSACCION)
        ORDER BY 1
    ) LOOP
        linea(
            'LONGITUD ' || TO_CHAR(r_formato.LONGITUD),
            'total=' || TO_CHAR(r_formato.TOTAL) ||
            '  ej_min=' || NVL(r_formato.EJEMPLO_MINIMO, '(null)') ||
            '  ej_max=' || NVL(r_formato.EJEMPLO_MAXIMO, '(null)')
        );
    END LOOP;

    ------------------------------------------------------------------
    titulo('2. La conversion TO_DATE funciona');
    nota('Si esta seccion no aparece, la consulta lanzo ORA-01861: revisar bloque 1.');

    DECLARE
        v_interpretable NUMBER;
    BEGIN
        SELECT COUNT(*)
        INTO v_interpretable
        FROM DBPTE.TRANSACCION_FLUJO_VC2D_FISC@CLEAMTT3PRODG TR
        WHERE TR.TVF_NIDAS > v_amid_minimo
          AND TR.TVF_DFECREGISTRO >= v_fecha_inicio
          AND TR.TVF_DFECREGISTRO < v_fecha_hasta_exclusiva
          AND TO_DATE(TR.TVF_SFECTRANSACCION, 'YYYY/MM/DD HH24:MI:SS') IS NOT NULL;

        linea('TRX con fecha interpretable', TO_CHAR(v_interpretable));
    EXCEPTION
        WHEN OTHERS THEN
            linea('TRX con fecha interpretable', 'ERROR ' || SQLERRM);
    END;

    ------------------------------------------------------------------
    titulo('3. Fila cruda de muestra');
    nota('Primeras ' || v_muestra || ' TRX del rango, ordenadas por FEC_TRX.');

    DECLARE
        v_orden NUMBER := 0;
    BEGIN
        FOR r_fila IN (
            SELECT * FROM (
                SELECT
                    TR.TVF_NIDCONTEXTOPTE,
                    TR.TVF_SNUMABTC2D,
                    TR.TVF_SFECTRANSACCION,
                    TR.TVF_DFECREGISTRO,
                    TR.TVF_NIDAS,
                    TR.TVF_NIDSITIO,
                    TR.TVF_NIDENTIDADOT,
                    TR.TVF_NMODO
                FROM DBPTE.TRANSACCION_FLUJO_VC2D_FISC@CLEAMTT3PRODG TR
                WHERE TR.TVF_NIDAS > v_amid_minimo
                  AND TR.TVF_DFECREGISTRO >= v_fecha_inicio
                  AND TR.TVF_DFECREGISTRO < v_fecha_hasta_exclusiva
                ORDER BY TR.TVF_DFECREGISTRO ASC
            ) WHERE ROWNUM <= v_muestra
        ) LOOP
            v_orden := v_orden + 1;
            linea(
                'Fila ' || v_orden || ' TVF_NIDCONTEXTOPTE',
                NVL(TO_CHAR(r_fila.TVF_NIDCONTEXTOPTE), '(null)')
            );
            linea(
                '  TVF_SNUMABTC2D',
                NVL(r_fila.TVF_SNUMABTC2D, '(null)')
            );
            linea(
                '  TVF_SFECTRANSACCION',
                NVL(r_fila.TVF_SFECTRANSACCION, '(null)')
            );
            linea(
                '  TVF_DFECREGISTRO',
                NVL(TO_CHAR(r_fila.TVF_DFECREGISTRO, 'DD/MM/YYYY HH24:MI:SS'), '(null)')
            );
            linea('  TVF_NIDAS', TO_CHAR(r_fila.TVF_NIDAS));
            linea('  TVF_NIDSITIO', TO_CHAR(r_fila.TVF_NIDSITIO));
            linea('  TVF_NIDENTIDADOT', TO_CHAR(r_fila.TVF_NIDENTIDADOT));
            linea('  TVF_NMODO', TO_CHAR(r_fila.TVF_NMODO));
        END LOOP;

        IF v_orden = 0 THEN
            nota('Sin filas en el rango con AMID > ' || v_amid_minimo ||
                 '. Revisar fechas o piso del universo.');
        END IF;
    END;

    ------------------------------------------------------------------
    titulo('4. Los LEFT JOIN de contexto no descartan TRX');
    nota('Compara el total simple contra el total con los dos LEFT JOIN.');
    nota('Si difieren, hay INNER JOIN de mas en la guia y el universo cambia.');

    DECLARE
        v_sin_join  NUMBER;
        v_left_join NUMBER;
        v_inner     NUMBER;
    BEGIN
        SELECT COUNT(*)
        INTO v_sin_join
        FROM DBPTE.TRANSACCION_FLUJO_VC2D_FISC@CLEAMTT3PRODG TR
        WHERE TR.TVF_NIDAS > v_amid_minimo
          AND TR.TVF_DFECREGISTRO >= v_fecha_inicio
          AND TR.TVF_DFECREGISTRO < v_fecha_hasta_exclusiva;

        SELECT COUNT(*)
        INTO v_left_join
        FROM DBPTE.TRANSACCION_FLUJO_VC2D_FISC@CLEAMTT3PRODG TR
        LEFT JOIN DBCLEARING.ENTIDAD@CLEAMTT3PRODG EN
               ON EN.ENT_NIDENTIDAD = TR.TVF_NIDENTIDADOT
        LEFT JOIN DBCLEARING.SITIO@CLEAMTT3PRODG SIT
               ON SIT.SIT_NIDSITIO = TR.TVF_NIDSITIO
        WHERE TR.TVF_NIDAS > v_amid_minimo
          AND TR.TVF_DFECREGISTRO >= v_fecha_inicio
          AND TR.TVF_DFECREGISTRO < v_fecha_hasta_exclusiva;

        SELECT COUNT(*)
        INTO v_inner
        FROM DBPTE.TRANSACCION_FLUJO_VC2D_FISC@CLEAMTT3PRODG TR
        JOIN DBCLEARING.ENTIDAD@CLEAMTT3PRODG EN
          ON EN.ENT_NIDENTIDAD = TR.TVF_NIDENTIDADOT
        JOIN DBCLEARING.SITIO@CLEAMTT3PRODG SIT
          ON SIT.SIT_NIDSITIO = TR.TVF_NIDSITIO
        WHERE TR.TVF_NIDAS > v_amid_minimo
          AND TR.TVF_DFECREGISTRO >= v_fecha_inicio
          AND TR.TVF_DFECREGISTRO < v_fecha_hasta_exclusiva;

        linea('TOTAL_SIN_JOIN', TO_CHAR(v_sin_join));
        linea('TOTAL_CON_LEFT_JOIN', TO_CHAR(v_left_join));
        linea('TOTAL_CON_INNER_JOIN', TO_CHAR(v_inner));
        linea('LEFT JOIN preserva el universo', v_left_join = v_sin_join
            ? 'OK' : 'REVISAR: descartan ' || (v_sin_join - v_left_join) || ' TRX');
    EXCEPTION
        WHEN OTHERS THEN
            linea('ERROR', SQLERRM);
    END;

    ------------------------------------------------------------------
    titulo('5. Cobertura de entidad y sitio');
    nota('TRX sin operador o sin sitio siguen siendo TRX validas del universo.');

    FOR r_cobertura IN (
        SELECT
            CASE WHEN EN.ENT_NIDENTIDAD IS NULL THEN 'SIN ENTIDAD' ELSE 'CON ENTIDAD' END
                AS ESTADO_ENTIDAD,
            CASE WHEN SIT.SIT_NIDSITIO IS NULL THEN 'SIN SITIO' ELSE 'CON SITIO' END
                AS ESTADO_SITIO,
            COUNT(*) AS TOTAL
        FROM DBPTE.TRANSACCION_FLUJO_VC2D_FISC@CLEAMTT3PRODG TR
        LEFT JOIN DBCLEARING.ENTIDAD@CLEAMTT3PRODG EN
               ON EN.ENT_NIDENTIDAD = TR.TVF_NIDENTIDADOT
        LEFT JOIN DBCLEARING.SITIO@CLEAMTT3PRODG SIT
               ON SIT.SIT_NIDSITIO = TR.TVF_NIDSITIO
        WHERE TR.TVF_NIDAS > v_amid_minimo
          AND TR.TVF_DFECREGISTRO >= v_fecha_inicio
          AND TR.TVF_DFECREGISTRO < v_fecha_hasta_exclusiva
        GROUP BY
            CASE WHEN EN.ENT_NIDENTIDAD IS NULL THEN 'SIN ENTIDAD' ELSE 'CON ENTIDAD' END,
            CASE WHEN SIT.SIT_NIDSITIO IS NULL THEN 'SIN SITIO' ELSE 'CON SITIO' END
        ORDER BY 1, 2
    ) LOOP
        linea(
            r_cobertura.ESTADO_ENTIDAD || ' / ' || r_cobertura.ESTADO_SITIO,
            TO_CHAR(r_cobertura.TOTAL)
        );
    END LOOP;

    ------------------------------------------------------------------
    titulo('6. Corte "> umbral" contra el total del rango');
    nota('Aqui NO se exige el mismo dia: es solo un control de magnitudes.');

    DECLARE
        v_total     NUMBER;
        v_mayor_15  NUMBER;
        v_desfase   NUMBER;
    BEGIN
        SELECT
            COUNT(*),
            SUM(CASE
                    WHEN MOD(TR.TVF_DFECREGISTRO, 1) - MOD(
                             TO_DATE(TR.TVF_SFECTRANSACCION, 'YYYY/MM/DD HH24:MI:SS'), 1
                         ) > 15 / 1440
                    THEN 1 ELSE 0
                END),
            SUM(CASE
                    WHEN MOD(TR.TVF_DFECREGISTRO, 1) - MOD(
                             TO_DATE(TR.TVF_SFECTRANSACCION, 'YYYY/MM/DD HH24:MI:SS'), 1
                         ) < 0
                    THEN 1 ELSE 0
                END)
        INTO v_total, v_mayor_15, v_desfase
        FROM DBPTE.TRANSACCION_FLUJO_VC2D_FISC@CLEAMTT3PRODG TR
        WHERE TR.TVF_NIDAS > v_amid_minimo
          AND TR.TVF_DFECREGISTRO >= v_fecha_inicio
          AND TR.TVF_DFECREGISTRO < v_fecha_hasta_exclusiva;

        linea('TOTAL_UNIVERSO', NVL(TO_CHAR(v_total), '0'));
        linea('MAYOR_15_MIN', NVL(TO_CHAR(v_mayor_15), '0'));
        linea('DESFASE_RELOJ', NVL(TO_CHAR(v_desfase), '0'));
    EXCEPTION
        WHEN OTHERS THEN
            linea('ERROR', SQLERRM);
    END;

    ------------------------------------------------------------------
    titulo('7. Cambio de dia (rezago)');
    nota('Mismo criterio que trx_reglas.es_rezagada: DATE(TRX) != DATE(BD).');

    FOR r_rezago IN (
        SELECT
            CASE
                WHEN TRUNC(TO_DATE(TR.TVF_SFECTRANSACCION, 'YYYY/MM/DD HH24:MI:SS'))
                     = TRUNC(TR.TVF_DFECREGISTRO)
                THEN 0
                ELSE TRUNC(TR.TVF_DFECREGISTRO)
                     - TRUNC(TO_DATE(TR.TVF_SFECTRANSACCION, 'YYYY/MM/DD HH24:MI:SS'))
            END AS DIAS_REZAGO,
            COUNT(*) AS TOTAL
        FROM DBPTE.TRANSACCION_FLUJO_VC2D_FISC@CLEAMTT3PRODG TR
        WHERE TR.TVF_NIDAS > v_amid_minimo
          AND TR.TVF_DFECREGISTRO >= v_fecha_inicio
          AND TR.TVF_DFECREGISTRO < v_fecha_hasta_exclusiva
          AND TRUNC(TO_DATE(TR.TVF_SFECTRANSACCION, 'YYYY/MM/DD HH24:MI:SS'))
              <> TRUNC(TR.TVF_DFECREGISTRO)
        GROUP BY
            CASE
                WHEN TRUNC(TO_DATE(TR.TVF_SFECTRANSACCION, 'YYYY/MM/DD HH24:MI:SS'))
                     = TRUNC(TR.TVF_DFECREGISTRO)
                THEN 0
                ELSE TRUNC(TR.TVF_DFECREGISTRO)
                     - TRUNC(TO_DATE(TR.TVF_SFECTRANSACCION, 'YYYY/MM/DD HH24:MI:SS'))
            END
        ORDER BY 1
    ) LOOP
        linea('DIAS_REZAGO = ' || TO_CHAR(r_rezago.DIAS_REZAGO), TO_CHAR(r_rezago.TOTAL));
    END LOOP;

    ------------------------------------------------------------------
    titulo('8. TVF_NFILEID: confirmar si existe antes de usarlo');
    nota('La guia menciona TVF_DFECFILEID. No se incluye en el modulo.');

    DECLARE
        v_columnas NUMBER := 0;
    BEGIN
        FOR r_columna IN (
            SELECT c.COLUMN_NAME, c.DATA_TYPE, c.DATA_LENGTH
            FROM ALL_TAB_COLUMNS@CLEAMTT3PRODG c
            WHERE c.OWNER = 'DBPTE'
              AND c.TABLE_NAME = 'TRANSACCION_FLUJO_VC2D_FISC'
              AND c.COLUMN_NAME LIKE '%FILEID%'
            ORDER BY c.COLUMN_NAME
        ) LOOP
            v_columnas := v_columnas + 1;
            linea(
                r_columna.COLUMN_NAME,
                r_columna.DATA_TYPE || '(' || TO_CHAR(r_columna.DATA_LENGTH) || ')'
            );
        END LOOP;

        IF v_columnas = 0 THEN
            nota('Ninguna columna %FILEID% en DBPTE.TRANSACCION_FLUJO_VC2D_FISC.');
        END IF;
    EXCEPTION
        WHEN OTHERS THEN
            linea('ERROR', SQLERRM);
    END;

    DBMS_OUTPUT.PUT_LINE('');
    DBMS_OUTPUT.PUT_LINE(RPAD('=== Fin de TRX_001 ', 76, '='));
END;
/
