-- BKL-002C - preflight READ ONLY para DBeaver y Oracle 11g 11.2.0.3.
-- Ejecutar cada consulta por separado y conservar sus resultados como evidencia.

-- Q01 Version Oracle
-- Esperado: Oracle Database 11g Enterprise Edition Release 11.2.0.3.0.
SELECT BANNER
FROM V$VERSION
WHERE UPPER(BANNER) LIKE 'ORACLE DATABASE%'
ORDER BY BANNER;

-- Q02 Usuario actual
-- Revisar: el usuario debe ser el esquema autorizado para el despliegue BKL-002C.
SELECT USER AS USUARIO_ACTUAL
FROM DUAL;

-- Q03 Privilegios efectivos
-- Revisar: registrar cuales de los privilegios requeridos estan presentes en la sesion.
SELECT PRIVILEGE
FROM SESSION_PRIVS
WHERE PRIVILEGE IN (
    'CREATE TABLE',
    'CREATE PROCEDURE',
    'CREATE JOB',
    'CREATE SEQUENCE',
    'CREATE TRIGGER',
    'MANAGE SCHEDULER',
    'CREATE ANY JOB'
)
ORDER BY PRIVILEGE;

-- Q04 Objetos BKL-002C preexistentes
-- Esperado antes del despliegue inicial: cero filas; cualquier coincidencia requiere revision manual.
SELECT OBJECT_NAME, OBJECT_TYPE, STATUS, LAST_DDL_TIME
FROM USER_OBJECTS
WHERE OBJECT_NAME IN (
    'ALERTA_RECALCULO_CONTROL',
    'ALERTA_RECALCULO_CONTROL_AUD',
    'ALERTA_RECALCULO_SOLICITUD',
    'IX_ARS_ESTADO_FECHA',
    'PKG_ALERTA_LEASE',
    'PRC_PROCESAR_RECALC_ALERTA',
    'JOB_PROCESAR_RECALC_ALERTAS',
    'JOB_LIMPIAR_HIST_UBICACION'
)
ORDER BY OBJECT_NAME, OBJECT_TYPE;

-- Q05 JOB_UPD_ALERTAS_VAL definicion actual
-- Revisar: conservar enabled, action, intervalo, fechas y contador de fallos como baseline.
SELECT JOB_NAME, ENABLED, STATE, JOB_TYPE, JOB_ACTION, REPEAT_INTERVAL,
       LAST_START_DATE, LAST_RUN_DURATION, NEXT_RUN_DATE, FAILURE_COUNT,
       AUTO_DROP, RESTARTABLE
FROM USER_SCHEDULER_JOBS
WHERE JOB_NAME = 'JOB_UPD_ALERTAS_VAL';

-- Q06 JOB_UPD_ALERTAS_VAL running ahora
-- Esperado para intervenir: cero filas; una fila significa que el job esta ejecutandose.
SELECT JOB_NAME, SESSION_ID, RUNNING_INSTANCE, ELAPSED_TIME, CPU_USED
FROM USER_SCHEDULER_RUNNING_JOBS
WHERE JOB_NAME = 'JOB_UPD_ALERTAS_VAL'
ORDER BY JOB_NAME;

-- Q07 Firmas procedures relevantes
-- Revisar: nombres, posiciones, tipos y direcciones deben coincidir con el contrato vigente.
SELECT OBJECT_NAME, PACKAGE_NAME, OVERLOAD, POSITION, SEQUENCE,
       ARGUMENT_NAME, IN_OUT, DATA_TYPE, DEFAULTED
FROM USER_ARGUMENTS
WHERE OBJECT_NAME IN (
    'PRC_UPD_ALERTAS_VAL',
    'PRC_APLICAR_REGLAS_ALERTA',
    'PRC_RECALCULAR_ALERTAS_SEGURO',
    'PRC_RECLASIFICAR_ALERTAS',
    'PRC_REFRESCAR_CAIDAS_BAT',
    'PRC_VALIDAR_REGLAS_ALERTA',
    'PRC_LIMPIAR_HIST_UBICACION'
)
ORDER BY OBJECT_NAME, OVERLOAD, SEQUENCE;

-- Q08 Columnas USER_SCHEDULER_RUNNING_JOBS
-- Esperado: DBeaver debe mostrar estas cinco columnas aunque la consulta retorne cero filas.
SELECT JOB_NAME, SESSION_ID, RUNNING_INSTANCE, ELAPSED_TIME, CPU_USED
FROM USER_SCHEDULER_RUNNING_JOBS
WHERE 1 = 0;

-- Q09 Columnas USER_SCHEDULER_JOB_RUN_DETAILS
-- Esperado: DBeaver debe reconocer las columnas usadas para evidencia de ejecuciones terminales.
SELECT LOG_ID, JOB_NAME, STATUS, ERROR#, ACTUAL_START_DATE,
       RUN_DURATION, ADDITIONAL_INFO
FROM USER_SCHEDULER_JOB_RUN_DETAILS
WHERE 1 = 0;

-- Q10 Jobs nuevos BKL-002C preexistentes
-- Esperado antes del despliegue inicial: cero filas; no continuar si alguno ya existe sin revision.
SELECT JOB_NAME, ENABLED, STATE, JOB_TYPE, JOB_ACTION, REPEAT_INTERVAL,
       AUTO_DROP, RESTARTABLE
FROM USER_SCHEDULER_JOBS
WHERE JOB_NAME IN (
    'JOB_PROCESAR_RECALC_ALERTAS',
    'JOB_LIMPIAR_HIST_UBICACION'
)
ORDER BY JOB_NAME;

-- Q11 Jobs relevantes running ahora
-- Esperado para intervenir: cero filas para los tres jobs; registrar cualquier ejecucion activa.
SELECT JOB_NAME, SESSION_ID, RUNNING_INSTANCE, ELAPSED_TIME, CPU_USED
FROM USER_SCHEDULER_RUNNING_JOBS
WHERE JOB_NAME IN (
    'JOB_UPD_ALERTAS_VAL',
    'JOB_PROCESAR_RECALC_ALERTAS',
    'JOB_LIMPIAR_HIST_UBICACION'
)
ORDER BY JOB_NAME;

-- Q12 Ultimas ejecuciones de jobs relevantes
-- Revisar: conservar las 20 ejecuciones mas recientes como baseline de estado y errores.
SELECT LOG_ID, JOB_NAME, STATUS, ERROR#, ACTUAL_START_DATE,
       RUN_DURATION, ADDITIONAL_INFO
FROM (
    SELECT LOG_ID, JOB_NAME, STATUS, ERROR#, ACTUAL_START_DATE,
           RUN_DURATION, ADDITIONAL_INFO
    FROM USER_SCHEDULER_JOB_RUN_DETAILS
    WHERE JOB_NAME IN (
        'JOB_UPD_ALERTAS_VAL',
        'JOB_PROCESAR_RECALC_ALERTAS',
        'JOB_LIMPIAR_HIST_UBICACION'
    )
    ORDER BY LOG_ID DESC
)
WHERE ROWNUM <= 20;

-- Q13 Cantidad de lineas de procedures a instrumentar
-- Esperado: comparar nombres y cantidades con el manifiesto fuente aprobado antes del despliegue.
SELECT NAME, TYPE, COUNT(*) AS LINEAS, MIN(LINE) AS PRIMERA, MAX(LINE) AS ULTIMA
FROM USER_SOURCE
WHERE NAME IN ('PRC_UPD_ALERTAS_VAL', 'PRC_APLICAR_REGLAS_ALERTA')
GROUP BY NAME, TYPE
ORDER BY NAME;

-- Q14 Fuente vigente de procedures a instrumentar
-- Revisar: exportar el resultado ordenado para verificarlo contra el baseline aprobado.
SELECT NAME, TYPE, LINE, TEXT
FROM USER_SOURCE
WHERE NAME IN ('PRC_UPD_ALERTAS_VAL', 'PRC_APLICAR_REGLAS_ALERTA')
ORDER BY NAME, TYPE, LINE;
