-- Validación de V010: sólo lectura.
-- Debe devolver al menos un índice cuyas dos primeras columnas sean
-- AMID y FECHA_REGISTRO, en ese orden.

SELECT
    i.INDEX_NAME,
    i.STATUS,
    i.VISIBILITY,
    LISTAGG(c.COLUMN_NAME || ' ' || c.DESCEND, ', ')
        WITHIN GROUP (ORDER BY c.COLUMN_POSITION) AS COLUMNAS
FROM USER_INDEXES i
JOIN USER_IND_COLUMNS c
  ON c.INDEX_NAME = i.INDEX_NAME
 AND c.TABLE_NAME = i.TABLE_NAME
WHERE i.TABLE_NAME = 'ESTATUS_ZP'
GROUP BY i.INDEX_NAME, i.STATUS, i.VISIBILITY
HAVING MAX(
           CASE
               WHEN c.COLUMN_POSITION = 1 AND c.COLUMN_NAME = 'AMID'
               THEN 1 ELSE 0
           END
       ) = 1
   AND MAX(
           CASE
               WHEN c.COLUMN_POSITION = 2 AND c.COLUMN_NAME = 'FECHA_REGISTRO'
               THEN 1 ELSE 0
           END
       ) = 1
ORDER BY i.INDEX_NAME;