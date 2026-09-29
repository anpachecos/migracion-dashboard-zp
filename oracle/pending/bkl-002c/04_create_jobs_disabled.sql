-- BKL-002C / BKL-002A - crea jobs NUEVOS siempre deshabilitados.
-- No modifica JOB_UPD_ALERTAS_VAL ni su horario :05/:35.

WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK

DECLARE
    v_existe NUMBER;
BEGIN
    SELECT COUNT(*) INTO v_existe
    FROM USER_SCHEDULER_JOBS
    WHERE JOB_NAME = 'JOB_PROCESAR_RECALC_ALERTAS';

    IF v_existe = 0 THEN
        DBMS_SCHEDULER.CREATE_JOB(
            job_name        => 'USR_LAB.JOB_PROCESAR_RECALC_ALERTAS',
            job_type        => 'PLSQL_BLOCK',
            job_action      => 'BEGIN USR_LAB.PRC_PROCESAR_RECALC_ALERTA; END;',
            start_date      => NULL,
            repeat_interval => 'FREQ=MINUTELY;INTERVAL=1',
            enabled         => FALSE,
            auto_drop       => FALSE,
            comments        => 'BKL-002C solicitudes manuales; iniciar solo tras validacion PRE.'
        );
        DBMS_SCHEDULER.SET_ATTRIBUTE(
            'USR_LAB.JOB_PROCESAR_RECALC_ALERTAS',
            'restartable',
            FALSE
        );
    ELSE
        RAISE_APPLICATION_ERROR(
            -20074,
            'JOB_PROCESAR_RECALC_ALERTAS ya existe; revisar antes de continuar.'
        );
    END IF;
END;
/

DECLARE
    v_existe NUMBER;
BEGIN
    SELECT COUNT(*) INTO v_existe
    FROM USER_SCHEDULER_JOBS
    WHERE JOB_NAME = 'JOB_LIMPIAR_HIST_UBICACION';

    IF v_existe = 0 THEN
        DBMS_SCHEDULER.CREATE_JOB(
            job_name        => 'USR_LAB.JOB_LIMPIAR_HIST_UBICACION',
            job_type        => 'PLSQL_BLOCK',
            job_action      => 'DECLARE v_filas_eliminadas NUMBER; BEGIN USR_LAB.PRC_LIMPIAR_HIST_UBICACION(16, v_filas_eliminadas); END;',
            start_date      => NULL,
            repeat_interval => 'FREQ=DAILY;BYHOUR=19;BYMINUTE=10;BYSECOND=0',
            enabled         => FALSE,
            auto_drop       => FALSE,
            comments        => 'BKL-002A limpieza Oracle; reemplazo futuro del scheduler Django.'
        );
        DBMS_SCHEDULER.SET_ATTRIBUTE(
            'USR_LAB.JOB_LIMPIAR_HIST_UBICACION',
            'restartable',
            FALSE
        );
    ELSE
        RAISE_APPLICATION_ERROR(
            -20074,
            'JOB_LIMPIAR_HIST_UBICACION ya existe; revisar antes de continuar.'
        );
    END IF;
END;
/

SELECT JOB_NAME, ENABLED, STATE, JOB_ACTION, REPEAT_INTERVAL,
       AUTO_DROP, RESTARTABLE
FROM USER_SCHEDULER_JOBS
WHERE JOB_NAME IN (
    'JOB_PROCESAR_RECALC_ALERTAS',
    'JOB_LIMPIAR_HIST_UBICACION'
)
ORDER BY JOB_NAME;
