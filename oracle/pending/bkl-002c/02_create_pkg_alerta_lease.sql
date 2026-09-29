-- BKL-002C - lease global ALERTAS_RECALCULO, Oracle 11g.
-- FECHA_EXPIRACION solo clasifica un lease como SOSPECHOSO: nunca autoriza takeover.

WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK

CREATE OR REPLACE PACKAGE USR_LAB.PKG_ALERTA_LEASE AUTHID DEFINER AS
    C_ERR_ACTIVO                CONSTANT PLS_INTEGER := -20071;
    C_ERR_SOSPECHOSO            CONSTANT PLS_INTEGER := -20072;
    C_ERR_PROPIEDAD_INVALIDA    CONSTANT PLS_INTEGER := -20073;
    C_ERR_CONTROL_INVALIDO      CONSTANT PLS_INTEGER := -20074;
    C_ERR_RECOVERY_NO_PERMITIDO CONSTANT PLS_INTEGER := -20075;
    C_ERR_FENCING_CAMBIO        CONSTANT PLS_INTEGER := -20076;
    C_ERR_SCHEDULER_RUNNING     CONSTANT PLS_INTEGER := -20077;
    C_ERR_EVIDENCIA_INSUF       CONSTANT PLS_INTEGER := -20078;
    C_ERR_RESULTADO_INDETER     CONSTANT PLS_INTEGER := -20079;
    C_ERR_MODO_INVALIDO         CONSTANT PLS_INTEGER := -20080;

    PROCEDURE ADQUIRIR;
    PROCEDURE LIBERAR;
    FUNCTION TOKEN_ACTUAL RETURN VARCHAR2;
    FUNCTION VERSION_ACTUAL RETURN NUMBER;
    FUNCTION PROFUNDIDAD RETURN PLS_INTEGER;

    PROCEDURE RECUPERAR_LEASE_SOSPECHOSO(
        p_owner_token_esperado IN VARCHAR2,
        p_lease_version_esperada IN NUMBER,
        p_confirmacion IN VARCHAR2,
        p_motivo IN VARCHAR2,
        p_evidencia IN VARCHAR2
    );
END PKG_ALERTA_LEASE;
/

CREATE OR REPLACE PACKAGE BODY USR_LAB.PKG_ALERTA_LEASE AS
    C_RECURSO CONSTANT VARCHAR2(64) := 'ALERTAS_RECALCULO';
    C_TTL_MINUTOS CONSTANT PLS_INTEGER := 20;

    g_owner_token VARCHAR2(32);
    g_lease_version NUMBER;
    g_depth PLS_INTEGER := 0;

    PROCEDURE REGISTRAR_AUDITORIA(
        p_evento IN VARCHAR2,
        p_owner_token IN VARCHAR2,
        p_owner_tipo IN VARCHAR2,
        p_owner_job_name IN VARCHAR2,
        p_owner_session_id IN VARCHAR2,
        p_owner_running_instance IN NUMBER,
        p_lease_version IN NUMBER,
        p_motivo IN VARCHAR2 DEFAULT NULL,
        p_evidencia IN VARCHAR2 DEFAULT NULL
    ) AS
    BEGIN
        INSERT INTO USR_LAB.ALERTA_RECALCULO_CONTROL_AUD (
            AUDIT_ID, RECURSO, EVENTO, OWNER_TOKEN, OWNER_TIPO,
            OWNER_JOB_NAME, OWNER_SESSION_ID, OWNER_RUNNING_INSTANCE,
            LEASE_VERSION, FECHA_EVENTO, USUARIO_EVENTO, MOTIVO, EVIDENCIA
        ) VALUES (
            RAWTOHEX(SYS_GUID()), C_RECURSO, p_evento, p_owner_token,
            p_owner_tipo, p_owner_job_name, p_owner_session_id,
            p_owner_running_instance, p_lease_version, SYSTIMESTAMP,
            SYS_CONTEXT('USERENV', 'SESSION_USER'),
            SUBSTR(p_motivo, 1, 1000), SUBSTR(p_evidencia, 1, 2000)
        );
    END REGISTRAR_AUDITORIA;

    PROCEDURE DETECTAR_OWNER(
        p_owner_tipo OUT VARCHAR2,
        p_owner_job_name OUT VARCHAR2,
        p_owner_session_id OUT VARCHAR2,
        p_owner_running_instance OUT NUMBER
    ) AS
    BEGIN
        p_owner_session_id := SYS_CONTEXT('USERENV', 'SID');
        BEGIN
            SELECT JOB_NAME, RUNNING_INSTANCE
            INTO p_owner_job_name, p_owner_running_instance
            FROM (
                SELECT JOB_NAME, RUNNING_INSTANCE
                FROM USER_SCHEDULER_RUNNING_JOBS
                WHERE SESSION_ID = TO_NUMBER(SYS_CONTEXT('USERENV', 'SID'))
                ORDER BY JOB_NAME
            )
            WHERE ROWNUM = 1;
            p_owner_tipo := 'SCHEDULER';
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                p_owner_tipo := 'DIRECT';
                p_owner_job_name := NULL;
                p_owner_running_instance := NULL;
        END;
    END DETECTAR_OWNER;

    PROCEDURE ADQUIRIR_PERSISTENTE(
        p_owner_token OUT VARCHAR2,
        p_lease_version OUT NUMBER
    ) AS
        PRAGMA AUTONOMOUS_TRANSACTION;
        v_token_actual VARCHAR2(32);
        v_tipo_actual VARCHAR2(16);
        v_job_actual VARCHAR2(128);
        v_session_actual VARCHAR2(64);
        v_instancia_actual NUMBER;
        v_version_actual NUMBER;
        v_expiracion_actual TIMESTAMP(6) WITH TIME ZONE;
        v_owner_tipo VARCHAR2(16);
        v_owner_job_name VARCHAR2(128);
        v_owner_session_id VARCHAR2(64);
        v_owner_running_instance NUMBER;
    BEGIN
        BEGIN
            SELECT OWNER_TOKEN, OWNER_TIPO, OWNER_JOB_NAME, OWNER_SESSION_ID,
                   OWNER_RUNNING_INSTANCE, LEASE_VERSION, FECHA_EXPIRACION
            INTO v_token_actual, v_tipo_actual, v_job_actual, v_session_actual,
                 v_instancia_actual, v_version_actual, v_expiracion_actual
            FROM USR_LAB.ALERTA_RECALCULO_CONTROL
            WHERE RECURSO = C_RECURSO
            FOR UPDATE;
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                ROLLBACK;
                RAISE_APPLICATION_ERROR(
                    C_ERR_CONTROL_INVALIDO,
                    'No existe el control ALERTAS_RECALCULO.'
                );
        END;

        IF v_token_actual IS NOT NULL THEN
            REGISTRAR_AUDITORIA(
                CASE
                    WHEN v_expiracion_actual > SYSTIMESTAMP
                    THEN 'ADQUISICION_DENEGADA'
                    ELSE 'LEASE_SOSPECHOSO'
                END,
                v_token_actual, v_tipo_actual, v_job_actual, v_session_actual,
                v_instancia_actual, v_version_actual,
                'Otro owner conserva el lease.', NULL
            );
            COMMIT;

            IF v_expiracion_actual > SYSTIMESTAMP THEN
                RAISE_APPLICATION_ERROR(
                    C_ERR_ACTIVO,
                    'ALERTAS_RECALCULO ya tiene un lease activo.'
                );
            END IF;
            RAISE_APPLICATION_ERROR(
                C_ERR_SOSPECHOSO,
                'ALERTAS_RECALCULO tiene un lease sospechoso; no hay takeover automatico.'
            );
        END IF;

        DETECTAR_OWNER(
            v_owner_tipo,
            v_owner_job_name,
            v_owner_session_id,
            v_owner_running_instance
        );
        p_owner_token := RAWTOHEX(SYS_GUID());
        p_lease_version := v_version_actual + 1;

        UPDATE USR_LAB.ALERTA_RECALCULO_CONTROL
        SET OWNER_TOKEN = p_owner_token,
            OWNER_TIPO = v_owner_tipo,
            OWNER_JOB_NAME = v_owner_job_name,
            OWNER_SESSION_ID = v_owner_session_id,
            OWNER_RUNNING_INSTANCE = v_owner_running_instance,
            LEASE_VERSION = p_lease_version,
            FECHA_ADQUISICION = SYSTIMESTAMP,
            FECHA_EXPIRACION = SYSTIMESTAMP
                + NUMTODSINTERVAL(C_TTL_MINUTOS, 'MINUTE')
        WHERE RECURSO = C_RECURSO
          AND OWNER_TOKEN IS NULL
          AND LEASE_VERSION = v_version_actual;

        IF SQL%ROWCOUNT <> 1 THEN
            ROLLBACK;
            RAISE_APPLICATION_ERROR(
                C_ERR_FENCING_CAMBIO,
                'El control cambio durante la adquisicion.'
            );
        END IF;

        REGISTRAR_AUDITORIA(
            'ADQUIRIDO', p_owner_token, v_owner_tipo, v_owner_job_name,
            v_owner_session_id, v_owner_running_instance, p_lease_version,
            'TTL operativo de sospecha: 20 minutos; sin takeover automatico.',
            NULL
        );
        COMMIT;
    END ADQUIRIR_PERSISTENTE;

    PROCEDURE LIBERAR_PERSISTENTE(
        p_owner_token IN VARCHAR2,
        p_lease_version IN NUMBER
    ) AS
        PRAGMA AUTONOMOUS_TRANSACTION;
        v_owner_tipo VARCHAR2(16);
        v_owner_job_name VARCHAR2(128);
        v_owner_session_id VARCHAR2(64);
        v_owner_running_instance NUMBER;
    BEGIN
        BEGIN
            SELECT OWNER_TIPO, OWNER_JOB_NAME, OWNER_SESSION_ID,
                   OWNER_RUNNING_INSTANCE
            INTO v_owner_tipo, v_owner_job_name, v_owner_session_id,
                 v_owner_running_instance
            FROM USR_LAB.ALERTA_RECALCULO_CONTROL
            WHERE RECURSO = C_RECURSO
              AND OWNER_TOKEN = p_owner_token
              AND LEASE_VERSION = p_lease_version
            FOR UPDATE;
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                ROLLBACK;
                RAISE_APPLICATION_ERROR(
                    C_ERR_PROPIEDAD_INVALIDA,
                    'Token/version no poseen el lease actual.'
                );
        END;

        UPDATE USR_LAB.ALERTA_RECALCULO_CONTROL
        SET OWNER_TOKEN = NULL,
            OWNER_TIPO = NULL,
            OWNER_JOB_NAME = NULL,
            OWNER_SESSION_ID = NULL,
            OWNER_RUNNING_INSTANCE = NULL,
            FECHA_ADQUISICION = NULL,
            FECHA_EXPIRACION = NULL
        WHERE RECURSO = C_RECURSO
          AND OWNER_TOKEN = p_owner_token
          AND LEASE_VERSION = p_lease_version;

        IF SQL%ROWCOUNT <> 1 THEN
            ROLLBACK;
            RAISE_APPLICATION_ERROR(
                C_ERR_PROPIEDAD_INVALIDA,
                'El owner cambio antes de liberar el lease.'
            );
        END IF;

        REGISTRAR_AUDITORIA(
            'LIBERADO', p_owner_token, v_owner_tipo, v_owner_job_name,
            v_owner_session_id, v_owner_running_instance, p_lease_version,
            NULL, NULL
        );
        COMMIT;
    END LIBERAR_PERSISTENTE;

    PROCEDURE ADQUIRIR AS
        v_owner_token VARCHAR2(32);
        v_lease_version NUMBER;
    BEGIN
        IF g_depth > 0 THEN
            g_depth := g_depth + 1;
            RETURN;
        END IF;

        ADQUIRIR_PERSISTENTE(v_owner_token, v_lease_version);
        g_owner_token := v_owner_token;
        g_lease_version := v_lease_version;
        g_depth := 1;
    END ADQUIRIR;

    PROCEDURE LIBERAR AS
    BEGIN
        IF g_depth <= 0 OR g_owner_token IS NULL OR g_lease_version IS NULL THEN
            RAISE_APPLICATION_ERROR(
                C_ERR_PROPIEDAD_INVALIDA,
                'La sesion no posee un lease para liberar.'
            );
        END IF;

        IF g_depth > 1 THEN
            g_depth := g_depth - 1;
            RETURN;
        END IF;

        LIBERAR_PERSISTENTE(g_owner_token, g_lease_version);
        g_owner_token := NULL;
        g_lease_version := NULL;
        g_depth := 0;
    END LIBERAR;

    FUNCTION TOKEN_ACTUAL RETURN VARCHAR2 AS
    BEGIN
        RETURN g_owner_token;
    END TOKEN_ACTUAL;

    FUNCTION VERSION_ACTUAL RETURN NUMBER AS
    BEGIN
        RETURN g_lease_version;
    END VERSION_ACTUAL;

    FUNCTION PROFUNDIDAD RETURN PLS_INTEGER AS
    BEGIN
        RETURN g_depth;
    END PROFUNDIDAD;

    PROCEDURE RECUPERAR_LEASE_SOSPECHOSO(
        p_owner_token_esperado IN VARCHAR2,
        p_lease_version_esperada IN NUMBER,
        p_confirmacion IN VARCHAR2,
        p_motivo IN VARCHAR2,
        p_evidencia IN VARCHAR2
    ) AS
        PRAGMA AUTONOMOUS_TRANSACTION;
        v_owner_tipo VARCHAR2(16);
        v_owner_job_name VARCHAR2(128);
        v_owner_session_id VARCHAR2(64);
        v_owner_running_instance NUMBER;
        v_owner_token_actual VARCHAR2(32);
        v_lease_version_actual NUMBER;
        v_fecha_adquisicion TIMESTAMP(6) WITH TIME ZONE;
        v_fecha_expiracion TIMESTAMP(6) WITH TIME ZONE;
        v_running NUMBER := 0;
        v_evidencia_scheduler NUMBER := 0;
    BEGIN
        BEGIN
            SELECT OWNER_TOKEN, LEASE_VERSION, OWNER_TIPO, OWNER_JOB_NAME,
                   OWNER_SESSION_ID, OWNER_RUNNING_INSTANCE,
                   FECHA_ADQUISICION, FECHA_EXPIRACION
            INTO v_owner_token_actual, v_lease_version_actual,
                 v_owner_tipo, v_owner_job_name, v_owner_session_id,
                 v_owner_running_instance, v_fecha_adquisicion, v_fecha_expiracion
            FROM USR_LAB.ALERTA_RECALCULO_CONTROL
            WHERE RECURSO = C_RECURSO
            FOR UPDATE;
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                ROLLBACK;
                RAISE_APPLICATION_ERROR(
                    C_ERR_CONTROL_INVALIDO,
                    'No existe el control ALERTAS_RECALCULO.'
                );
        END;

        IF v_owner_token_actual IS NULL
           OR v_owner_token_actual <> p_owner_token_esperado
           OR v_lease_version_actual <> p_lease_version_esperada THEN
            REGISTRAR_AUDITORIA(
                'RECOVERY_DENEGADO', v_owner_token_actual, v_owner_tipo,
                v_owner_job_name, v_owner_session_id, v_owner_running_instance,
                v_lease_version_actual,
                'Token/version esperado no coincide con el owner actual.',
                p_evidencia
            );
            COMMIT;
            RAISE_APPLICATION_ERROR(
                C_ERR_FENCING_CAMBIO,
                'Token/version cambiaron; recovery rechazado.'
            );
        END IF;

        IF v_fecha_expiracion IS NULL OR v_fecha_expiracion > SYSTIMESTAMP THEN
            REGISTRAR_AUDITORIA(
                'RECOVERY_DENEGADO', v_owner_token_actual, v_owner_tipo,
                v_owner_job_name, v_owner_session_id, v_owner_running_instance,
                v_lease_version_actual, 'El lease no esta sospechoso.', p_evidencia
            );
            COMMIT;
            RAISE_APPLICATION_ERROR(
                C_ERR_RECOVERY_NO_PERMITIDO,
                'El lease no esta en estado sospechoso.'
            );
        END IF;

        IF p_motivo IS NULL OR TRIM(p_motivo) IS NULL
           OR p_evidencia IS NULL OR TRIM(p_evidencia) IS NULL THEN
            REGISTRAR_AUDITORIA(
                'RECOVERY_DENEGADO', v_owner_token_actual, v_owner_tipo,
                v_owner_job_name, v_owner_session_id, v_owner_running_instance,
                v_lease_version_actual,
                'Faltan motivo o evidencia explicitos.', p_evidencia
            );
            COMMIT;
            RAISE_APPLICATION_ERROR(
                C_ERR_EVIDENCIA_INSUF,
                'Recovery requiere motivo y evidencia explicitos.'
            );
        END IF;

        IF v_owner_tipo = 'SCHEDULER' THEN
            SELECT COUNT(*)
            INTO v_running
            FROM USER_SCHEDULER_RUNNING_JOBS
            WHERE JOB_NAME = v_owner_job_name
              AND SESSION_ID = TO_NUMBER(v_owner_session_id)
              AND RUNNING_INSTANCE = v_owner_running_instance;

            IF v_running > 0 THEN
                REGISTRAR_AUDITORIA(
                    'RECOVERY_DENEGADO', v_owner_token_actual, v_owner_tipo,
                    v_owner_job_name, v_owner_session_id,
                    v_owner_running_instance, v_lease_version_actual,
                    'Scheduler owner aun figura running.', p_evidencia
                );
                COMMIT;
                RAISE_APPLICATION_ERROR(
                    C_ERR_SCHEDULER_RUNNING,
                    'El owner Scheduler aun figura en ejecucion.'
                );
            END IF;

            SELECT COUNT(*)
            INTO v_evidencia_scheduler
            FROM USER_SCHEDULER_JOB_RUN_DETAILS
            WHERE JOB_NAME = v_owner_job_name
              AND ACTUAL_START_DATE BETWEEN
                  v_fecha_adquisicion - NUMTODSINTERVAL(5, 'MINUTE')
                  AND v_fecha_adquisicion + NUMTODSINTERVAL(5, 'MINUTE')
              AND STATUS IN ('SUCCEEDED', 'FAILED', 'STOPPED', 'BROKEN');

            IF v_evidencia_scheduler = 0 THEN
                REGISTRAR_AUDITORIA(
                    'RECOVERY_DENEGADO', v_owner_token_actual, v_owner_tipo,
                    v_owner_job_name, v_owner_session_id,
                    v_owner_running_instance, v_lease_version_actual,
                    'Sin ejecucion Scheduler terminal correlacionable.',
                    p_evidencia
                );
                COMMIT;
                RAISE_APPLICATION_ERROR(
                    C_ERR_EVIDENCIA_INSUF,
                    'No existe evidencia Scheduler terminal suficiente.'
                );
            END IF;
        ELSIF v_owner_tipo = 'DIRECT' THEN
            IF p_confirmacion <> 'CONFIRMO_RECOVERY' THEN
                REGISTRAR_AUDITORIA(
                    'RECOVERY_DENEGADO', v_owner_token_actual, v_owner_tipo,
                    v_owner_job_name, v_owner_session_id,
                    v_owner_running_instance, v_lease_version_actual,
                    'Falta confirmacion administrativa explicita.', p_evidencia
                );
                COMMIT;
                RAISE_APPLICATION_ERROR(
                    C_ERR_RECOVERY_NO_PERMITIDO,
                    'Owner DIRECT requiere confirmacion administrativa explicita.'
                );
            END IF;
        ELSE
            REGISTRAR_AUDITORIA(
                'RECOVERY_DENEGADO', v_owner_token_actual, v_owner_tipo,
                v_owner_job_name, v_owner_session_id, v_owner_running_instance,
                v_lease_version_actual, 'OWNER_TIPO inconsistente.', p_evidencia
            );
            COMMIT;
            RAISE_APPLICATION_ERROR(
                C_ERR_CONTROL_INVALIDO,
                'OWNER_TIPO inexistente o inconsistente.'
            );
        END IF;

        UPDATE USR_LAB.ALERTA_RECALCULO_SOLICITUD
        SET ESTADO = 'ERROR',
            FECHA_FIN = SYSTIMESTAMP,
            FECHA_ACTUALIZACION = SYSTIMESTAMP,
            ERROR_CODIGO = C_ERR_RESULTADO_INDETER,
            ERROR_MENSAJE = 'Lease recuperado administrativamente; resultado indeterminado.'
        WHERE ESTADO = 'EJECUTANDO'
          AND OWNER_TOKEN = p_owner_token_esperado
          AND LEASE_VERSION = p_lease_version_esperada;

        UPDATE USR_LAB.ALERTA_RECALCULO_CONTROL
        SET OWNER_TOKEN = NULL,
            OWNER_TIPO = NULL,
            OWNER_JOB_NAME = NULL,
            OWNER_SESSION_ID = NULL,
            OWNER_RUNNING_INSTANCE = NULL,
            LEASE_VERSION = LEASE_VERSION + 1,
            FECHA_ADQUISICION = NULL,
            FECHA_EXPIRACION = NULL
        WHERE RECURSO = C_RECURSO
          AND OWNER_TOKEN = p_owner_token_esperado
          AND LEASE_VERSION = p_lease_version_esperada;

        IF SQL%ROWCOUNT <> 1 THEN
            ROLLBACK;
            RAISE_APPLICATION_ERROR(
                C_ERR_FENCING_CAMBIO,
                'Token/version cambiaron durante recovery.'
            );
        END IF;

        REGISTRAR_AUDITORIA(
            'RECUPERADO', p_owner_token_esperado, v_owner_tipo,
            v_owner_job_name, v_owner_session_id, v_owner_running_instance,
            p_lease_version_esperada, p_motivo, p_evidencia
        );
        COMMIT;
    END RECUPERAR_LEASE_SOSPECHOSO;
END PKG_ALERTA_LEASE;
/

SHOW ERRORS PACKAGE USR_LAB.PKG_ALERTA_LEASE
SHOW ERRORS PACKAGE BODY USR_LAB.PKG_ALERTA_LEASE
