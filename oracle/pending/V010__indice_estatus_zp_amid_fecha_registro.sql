-- V010 - Índice para el historial GPS por hora de bloque
-- Estado: PENDIENTE DE EJECUCIÓN EN ORACLE.
--
-- Motivo:
-- Django filtra ESTATUS_ZP por AMID y FECHA_REGISTRO. FECHA_REGISTRO es la
-- hora real del bloque; FECHA_HORA es la hora informada por el validador.
--
-- Este script no elimina ni actualiza datos. CREATE INDEX realiza COMMIT
-- implícito en Oracle. Ejecutar una sola vez, idealmente fuera de hora punta.

SET SERVEROUTPUT ON;

DECLARE
    v_indices_compatibles NUMBER := 0;
BEGIN
    SELECT COUNT(*)
      INTO v_indices_compatibles
      FROM (
          SELECT INDEX_NAME
            FROM USER_IND_COLUMNS
           WHERE TABLE_NAME = 'ESTATUS_ZP'
           GROUP BY INDEX_NAME
          HAVING MAX(
                     CASE
                         WHEN COLUMN_POSITION = 1 AND COLUMN_NAME = 'AMID'
                         THEN 1 ELSE 0
                     END
                 ) = 1
             AND MAX(
                     CASE
                         WHEN COLUMN_POSITION = 2 AND COLUMN_NAME = 'FECHA_REGISTRO'
                         THEN 1 ELSE 0
                     END
                 ) = 1
      );

    IF v_indices_compatibles = 0 THEN
        EXECUTE IMMEDIATE '
            CREATE INDEX USR_LAB.IDX_ESTATUS_ZP_AMID_FREG
                ON USR_LAB.ESTATUS_ZP (AMID, FECHA_REGISTRO)
        ';
        DBMS_OUTPUT.PUT_LINE(
            'Creado IDX_ESTATUS_ZP_AMID_FREG (AMID, FECHA_REGISTRO).'
        );
    ELSE
        DBMS_OUTPUT.PUT_LINE(
            'No se creó el índice: ya existe uno compatible con '
            || '(AMID, FECHA_REGISTRO) como primeras columnas.'
        );
    END IF;
END;
/