-- BKL-002C - matriz/manual de pruebas PRE. NO ejecutar como script completo.
-- Requiere dos sesiones SQL separadas y una ventana controlada.
-- No usa DBMS_LOCK. Para probar expiracion se deja una sesion abierta >20 minutos.

-- Consulta comun de observacion (READ ONLY):
SELECT RECURSO, OWNER_TOKEN, OWNER_TIPO, OWNER_JOB_NAME, OWNER_SESSION_ID,
       OWNER_RUNNING_INSTANCE, LEASE_VERSION, FECHA_ADQUISICION,
       FECHA_EXPIRACION,
       CASE WHEN OWNER_TOKEN IS NULL THEN 'LIBRE'
            WHEN FECHA_EXPIRACION > SYSTIMESTAMP THEN 'ACTIVO'
            ELSE 'SOSPECHOSO' END AS ESTADO
FROM USR_LAB.ALERTA_RECALCULO_CONTROL
WHERE RECURSO = 'ALERTAS_RECALCULO';

-- T01 dos sesiones compitiendo
-- Sesion A: EXEC USR_LAB.PKG_ALERTA_LEASE.ADQUIRIR;
-- Sesion B: EXEC USR_LAB.PKG_ALERTA_LEASE.ADQUIRIR; -- espera ORA-20071
-- Sesion A: EXEC USR_LAB.PKG_ALERTA_LEASE.LIBERAR;

-- T02 reentrancia 1 -> 2 -> 1 -> 0 (misma sesion)
BEGIN
    USR_LAB.PKG_ALERTA_LEASE.ADQUIRIR;
    DBMS_OUTPUT.PUT_LINE('depth=' || USR_LAB.PKG_ALERTA_LEASE.PROFUNDIDAD);
    USR_LAB.PKG_ALERTA_LEASE.ADQUIRIR;
    DBMS_OUTPUT.PUT_LINE('depth=' || USR_LAB.PKG_ALERTA_LEASE.PROFUNDIDAD);
    USR_LAB.PKG_ALERTA_LEASE.LIBERAR;
    DBMS_OUTPUT.PUT_LINE('depth=' || USR_LAB.PKG_ALERTA_LEASE.PROFUNDIDAD);
    USR_LAB.PKG_ALERTA_LEASE.LIBERAR;
    DBMS_OUTPUT.PUT_LINE('depth=' || USR_LAB.PKG_ALERTA_LEASE.PROFUNDIDAD);
END;
/

-- T03/T04 COMMIT y ROLLBACK de negocio no liberan el lease
-- Sesion A: ADQUIRIR; COMMIT;   -- Sesion B sigue recibiendo -20071
-- Sesion A: LIBERAR;
-- Repetir con ADQUIRIR; ROLLBACK; -- Sesion B sigue recibiendo -20071

-- T05 manual esperando automatico
-- Mientras USER_SCHEDULER_RUNNING_JOBS muestre JOB_UPD_ALERTAS_VAL,
-- insertar una solicitud PENDIENTE controlada y ejecutar el processor.
-- Esperado: PENDIENTE, INTENTOS sin cambio, retorno normal del processor.

-- T06 automatico chocando manual
-- Sesion A adquiere lease DIRECT y lo conserva.
-- Sesion B ejecuta PRC_UPD_ALERTAS_VAL.
-- Esperado: ORA-20071 y ningun calculo parcial.

-- T07 y T14 lease >20 minutos sigue siendo owner y bloquea takeover
-- Sesion A adquiere y permanece abierta/idle mas de 20 minutos.
-- Sesion B intenta adquirir: ORA-20072.
-- Sesion A libera con su token/version: debe funcionar aun expirado.

-- T08 recovery activo rechazado
-- Capturar TOKEN_ACTUAL/VERSION_ACTUAL en sesion A y, antes de 20 minutos,
-- llamar RECUPERAR_LEASE_SOSPECHOSO desde sesion administrativa.
-- Esperado: ORA-20075.

-- T09 stale token/version rechazado
-- Tras liberar y adquirir una nueva version, intentar recovery con la anterior.
-- Esperado: ORA-20076.

-- T10 Scheduler running rechazado
-- Con owner SCHEDULER visible en USER_SCHEDULER_RUNNING_JOBS y lease sospechoso,
-- intentar recovery con token/version exactos.
-- Esperado: ORA-20077. No detener el job para fabricar esta prueba.

-- T11 DIRECT sin evidencia/confirmacion rechazado
-- Para owner DIRECT sospechoso, usar confirmacion distinta de
-- CONFIRMO_RECOVERY o motivo/evidencia vacios.
-- Esperado: -20075 o -20078.

-- T12 crash con solicitud EJECUTANDO
-- Requiere coordinación operativa: iniciar una solicitud controlada y terminar
-- el proceso/sesion del processor desde fuera. No usar KILL SESSION sin DBA.
-- Esperado: solicitud EJECUTANDO durable y lease SOSPECHOSO tras 20 minutos.
-- Recovery autorizado debe marcar ERROR -20079, resultado indeterminado.

-- T13 error real de calculo
-- Ejecutar solo con un fallo controlado aprobado que no altere reglas productivas.
-- Esperado: codigo Oracle original en ERROR, no remapeado a -20071/-20072,
-- rollback del procedure y liberacion del lease.

-- T14 release de owner incorrecto
-- Sesion A adquiere. Sesion B llama LIBERAR sin estado de package.
-- Esperado: ORA-20073; owner A permanece intacto.

-- Validacion final de cada caso:
-- 1. consultar control y auditoria;
-- 2. comprobar fencing token+version;
-- 3. liberar desde owner legitimo o recovery aprobado;
-- 4. no dejar solicitudes sinteticas PENDIENTE/EJECUTANDO.

