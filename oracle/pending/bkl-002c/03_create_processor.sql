-- BKL-002C - procesa como maximo una solicitud manual pendiente por invocacion.
-- La contencion -20071/-20072 deja la solicitud PENDIENTE y retorna normalmente.

WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK

CREATE OR REPLACE PROCEDURE USR_LAB.PRC_PROCESAR_RECALC_ALERTA
AS
    v_solicitud_id VARCHAR2(32);
    v_modo VARCHAR2(16);
    v_owner_token VARCHAR2(32);
    v_lease_version NUMBER;
    v_error_codigo NUMBER;
    v_error_mensaje VARCHAR2(2000);
    v_error_backtrace VARCHAR2(2000);
    v_lease_adquirido BOOLEAN := FALSE;
    v_solicitud_bloqueada BOOLEAN := FALSE;

    PROCEDURE INFORMAR_SIN_PROPAGAR(p_mensaje IN VARCHAR2) AS
    BEGIN
        DBMS_OUTPUT.PUT_LINE(SUBSTR(p_mensaje, 1, 32767));
    EXCEPTION
        WHEN OTHERS THEN
            NULL;
    END INFORMAR_SIN_PROPAGAR;

    PROCEDURE ROLLBACK_SIN_PROPAGAR(p_contexto IN VARCHAR2) AS
    BEGIN
        ROLLBACK;
    EXCEPTION
        WHEN OTHERS THEN
            INFORMAR_SIN_PROPAGAR(
                'Error secundario en rollback (' || p_contexto || '): ' || SQLERRM
            );
    END ROLLBACK_SIN_PROPAGAR;
BEGIN
    BEGIN
        SELECT SOLICITUD_ID
        INTO v_solicitud_id
        FROM (
            SELECT SOLICITUD_ID
            FROM USR_LAB.ALERTA_RECALCULO_SOLICITUD
            WHERE ESTADO = 'PENDIENTE'
            ORDER BY FECHA_SOLICITUD, SOLICITUD_ID
        )
        WHERE ROWNUM = 1;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RETURN;
    END;

    BEGIN
        USR_LAB.PKG_ALERTA_LEASE.ADQUIRIR;
        v_lease_adquirido := TRUE;
    EXCEPTION
        WHEN OTHERS THEN
            IF SQLCODE IN (
                USR_LAB.PKG_ALERTA_LEASE.C_ERR_ACTIVO,
                USR_LAB.PKG_ALERTA_LEASE.C_ERR_SOSPECHOSO
            ) THEN
                RETURN;
            END IF;
            RAISE;
    END;

    -- Todo lo posterior al acquire queda cubierto por este bloque finally-like.
    BEGIN
        v_owner_token := USR_LAB.PKG_ALERTA_LEASE.TOKEN_ACTUAL;
        v_lease_version := USR_LAB.PKG_ALERTA_LEASE.VERSION_ACTUAL;

        BEGIN
            SELECT MODO
            INTO v_modo
            FROM USR_LAB.ALERTA_RECALCULO_SOLICITUD
            WHERE SOLICITUD_ID = v_solicitud_id
              AND ESTADO = 'PENDIENTE'
            FOR UPDATE;
            v_solicitud_bloqueada := TRUE;
        EXCEPTION
            WHEN NO_DATA_FOUND THEN
                ROLLBACK;
                v_solicitud_bloqueada := FALSE;
        END;

        IF v_solicitud_bloqueada THEN
            UPDATE USR_LAB.ALERTA_RECALCULO_SOLICITUD
            SET ESTADO = 'EJECUTANDO',
                FECHA_INICIO = SYSTIMESTAMP,
                FECHA_FIN = NULL,
                FECHA_ACTUALIZACION = SYSTIMESTAMP,
                INTENTOS = INTENTOS + 1,
                OWNER_TOKEN = v_owner_token,
                LEASE_VERSION = v_lease_version,
                ERROR_CODIGO = NULL,
                ERROR_MENSAJE = NULL
            WHERE SOLICITUD_ID = v_solicitud_id
              AND ESTADO = 'PENDIENTE';

            IF SQL%ROWCOUNT <> 1 THEN
                ROLLBACK;
                v_solicitud_bloqueada := FALSE;
            END IF;
        END IF;

        IF v_solicitud_bloqueada THEN
            -- Hace durable EJECUTANDO antes de iniciar el calculo. Un crash queda visible.
            COMMIT;

            IF v_modo = 'RAPIDO' THEN
                USR_LAB.PRC_RECLASIFICAR_ALERTAS;
            ELSIF v_modo = 'COMPLETO' THEN
                USR_LAB.PRC_RECALCULAR_ALERTAS_SEGURO;
            ELSE
                RAISE_APPLICATION_ERROR(
                    USR_LAB.PKG_ALERTA_LEASE.C_ERR_MODO_INVALIDO,
                    'Modo manual invalido: ' || v_modo
                );
            END IF;

            UPDATE USR_LAB.ALERTA_RECALCULO_SOLICITUD
            SET ESTADO = 'OK',
                FECHA_FIN = SYSTIMESTAMP,
                FECHA_ACTUALIZACION = SYSTIMESTAMP,
                ERROR_CODIGO = NULL,
                ERROR_MENSAJE = NULL
            WHERE SOLICITUD_ID = v_solicitud_id
              AND ESTADO = 'EJECUTANDO'
              AND OWNER_TOKEN = v_owner_token
              AND LEASE_VERSION = v_lease_version;
            COMMIT;
        END IF;
    EXCEPTION
        WHEN OTHERS THEN
            v_error_codigo := SQLCODE;
            v_error_mensaje := SUBSTR(SQLERRM, 1, 2000);
            v_error_backtrace := SUBSTR(DBMS_UTILITY.FORMAT_ERROR_BACKTRACE, 1, 2000);
            ROLLBACK_SIN_PROPAGAR('error original');

            BEGIN
                UPDATE USR_LAB.ALERTA_RECALCULO_SOLICITUD
                SET ESTADO = 'ERROR',
                    FECHA_FIN = SYSTIMESTAMP,
                    FECHA_ACTUALIZACION = SYSTIMESTAMP,
                    ERROR_CODIGO = v_error_codigo,
                    ERROR_MENSAJE = v_error_mensaje
                WHERE SOLICITUD_ID = v_solicitud_id
                  AND ESTADO = 'EJECUTANDO'
                  AND OWNER_TOKEN = v_owner_token
                  AND LEASE_VERSION = v_lease_version;
                COMMIT;
            EXCEPTION
                WHEN OTHERS THEN
                    INFORMAR_SIN_PROPAGAR(
                        'Error guardando estado ERROR: ' || SQLERRM
                    );
                    ROLLBACK_SIN_PROPAGAR('estado ERROR');
            END;

            BEGIN
                IF v_lease_adquirido THEN
                    USR_LAB.PKG_ALERTA_LEASE.LIBERAR;
                    v_lease_adquirido := FALSE;
                END IF;
            EXCEPTION
                WHEN OTHERS THEN
                    INFORMAR_SIN_PROPAGAR(
                        'Error secundario liberando lease: ' || SQLERRM
                    );
            END;

            INFORMAR_SIN_PROPAGAR(
                'Error original ' || v_error_codigo || ': ' || v_error_mensaje
            );
            INFORMAR_SIN_PROPAGAR(v_error_backtrace);
            RAISE;
    END;

    IF v_lease_adquirido THEN
        USR_LAB.PKG_ALERTA_LEASE.LIBERAR;
        v_lease_adquirido := FALSE;
    END IF;
END PRC_PROCESAR_RECALC_ALERTA;
/

SHOW ERRORS PROCEDURE USR_LAB.PRC_PROCESAR_RECALC_ALERTA
