-- Auditoria de solo lectura antes de optimizar Oracle.
-- No modifica objetos ni datos.

SET SERVEROUTPUT ON;
SET LINESIZE 220;
SET PAGESIZE 500;

PROMPT === Version de Oracle ===
SELECT banner_full
FROM v$version
WHERE banner_full LIKE 'Oracle Database%';

PROMPT === Objetos principales y estado ===
SELECT object_name, object_type, status, last_ddl_time
FROM user_objects
WHERE object_name IN (
    'ESTATUS_ZP',
    'VW_ESTATUS_ZP_DJANGO',
    'BATERIA_BLOQUE_30MIN',
    'AMID_MAESTRO_ALERTAS',
    'ALERTA_REGLA_PARAM',
    'ALERTA_VALIDADOR_RESUMEN',
    'UBICACION_ESPERADA_VALIDADOR',
    'HISTORIAL_UBICACION_ESPERADA',
    'JOBS_STATUS_ZP',
    'PRC_ACTUALIZAR_BATERIA_BLOQUES',
    'PRC_UPD_AMID_ALERTAS',
    'PRC_UPD_ALERTAS_VAL'
)
ORDER BY object_type, object_name;

PROMPT === Columnas actuales ===
SELECT table_name,
       column_id,
       column_name,
       data_type,
       data_length,
       data_precision,
       data_scale,
       nullable
FROM user_tab_columns
WHERE table_name IN (
    'ESTATUS_ZP',
    'BATERIA_BLOQUE_30MIN',
    'AMID_MAESTRO_ALERTAS',
    'ALERTA_REGLA_PARAM',
    'ALERTA_VALIDADOR_RESUMEN'
)
ORDER BY table_name, column_id;

PROMPT === Indices y columnas ===
SELECT i.table_name,
       i.index_name,
       i.uniqueness,
       i.status,
       i.visibility,
       c.column_position,
       c.column_name,
       c.descend
FROM user_indexes i
JOIN user_ind_columns c
  ON c.index_name = i.index_name
 AND c.table_name = i.table_name
WHERE i.table_name IN (
    'ESTATUS_ZP',
    'BATERIA_BLOQUE_30MIN',
    'AMID_MAESTRO_ALERTAS',
    'ALERTA_REGLA_PARAM',
    'ALERTA_VALIDADOR_RESUMEN',
    'UBICACION_ESPERADA_VALIDADOR',
    'HISTORIAL_UBICACION_ESPERADA'
)
ORDER BY i.table_name, i.index_name, c.column_position;

PROMPT === Restricciones ===
SELECT c.table_name,
       c.constraint_name,
       c.constraint_type,
       c.status,
       c.validated,
       cc.position,
       cc.column_name
FROM user_constraints c
LEFT JOIN user_cons_columns cc
  ON cc.constraint_name = c.constraint_name
 AND cc.table_name = c.table_name
WHERE c.table_name IN (
    'ESTATUS_ZP',
    'BATERIA_BLOQUE_30MIN',
    'AMID_MAESTRO_ALERTAS',
    'ALERTA_REGLA_PARAM',
    'ALERTA_VALIDADOR_RESUMEN'
)
ORDER BY c.table_name, c.constraint_name, cc.position;

PROMPT === Jobs configurados ===
SELECT job_name,
       enabled,
       state,
       job_type,
       job_action,
       repeat_interval,
       last_start_date,
       last_run_duration,
       next_run_date,
       failure_count
FROM user_scheduler_jobs
WHERE job_name IN (
    'JOB_ACTUALIZAR_BATERIA_BLOQUES',
    'JOB_UPD_AMID_ALERTAS',
    'JOB_UPD_ALERTAS_VAL'
)
ORDER BY job_name;

PROMPT === Ultimas 20 ejecuciones ===
SELECT job_name,
       status,
       actual_start_date,
       run_duration,
       error#,
       additional_info
FROM user_scheduler_job_run_details
WHERE job_name IN (
    'JOB_ACTUALIZAR_BATERIA_BLOQUES',
    'JOB_UPD_AMID_ALERTAS',
    'JOB_UPD_ALERTAS_VAL'
)
ORDER BY actual_start_date DESC
FETCH FIRST 20 ROWS ONLY;

PROMPT === Volumen y frescura ===
SELECT 'ESTATUS_ZP' AS objeto,
       COUNT(*) AS filas,
       MAX(fecha_registro) AS ultima_fecha
FROM usr_lab.estatus_zp
UNION ALL
SELECT 'BATERIA_BLOQUE_30MIN',
       COUNT(*),
       MAX(fecha_actualizacion)
FROM usr_lab.bateria_bloque_30min
UNION ALL
SELECT 'AMID_MAESTRO_ALERTAS',
       COUNT(*),
       MAX(fecha_ultima_actualizacion)
FROM usr_lab.amid_maestro_alertas
UNION ALL
SELECT 'ALERTA_VALIDADOR_RESUMEN',
       COUNT(*),
       MAX(fecha_actualizacion)
FROM usr_lab.alerta_validador_resumen;

PROMPT === Duplicados de bloques (debe retornar cero filas) ===
SELECT amid, fecha_hora_bloque, COUNT(*) AS cantidad
FROM usr_lab.bateria_bloque_30min
GROUP BY amid, fecha_hora_bloque
HAVING COUNT(*) > 1;

PROMPT === Duplicados del resumen (debe retornar cero filas) ===
SELECT amid, COUNT(*) AS cantidad
FROM usr_lab.alerta_validador_resumen
GROUP BY amid
HAVING COUNT(*) > 1;

PROMPT === AMID activos sin resumen ===
SELECT m.amid
FROM usr_lab.amid_maestro_alertas m
WHERE m.activo = 1
  AND NOT EXISTS (
      SELECT 1
      FROM usr_lab.alerta_validador_resumen r
      WHERE r.amid = m.amid
  )
ORDER BY m.amid;

PROMPT === AMID inactivos que todavia tienen resumen ===
SELECT m.amid,
       r.nivel_alerta_global,
       r.fecha_actualizacion
FROM usr_lab.amid_maestro_alertas m
JOIN usr_lab.alerta_validador_resumen r
  ON r.amid = m.amid
WHERE m.activo = 0
ORDER BY m.amid;

PROMPT === Distribucion y frescura de alertas ===
SELECT nivel_alerta_global,
       COUNT(*) AS cantidad,
       MIN(fecha_actualizacion) AS actualizacion_mas_antigua,
       MAX(fecha_actualizacion) AS actualizacion_mas_reciente
FROM usr_lab.alerta_validador_resumen
GROUP BY nivel_alerta_global
ORDER BY CASE nivel_alerta_global
             WHEN 'CRITICA' THEN 1
             WHEN 'ALTA' THEN 2
             WHEN 'ADVERTENCIA' THEN 3
             ELSE 4
         END;

PROMPT === Reglas activas ===
SELECT clave, valor_numero, descripcion, activo, fecha_actualizacion
FROM usr_lab.alerta_regla_param
ORDER BY clave;

