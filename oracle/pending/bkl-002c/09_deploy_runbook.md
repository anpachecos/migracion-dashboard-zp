# BKL-002C — runbook de despliegue y rollback

## Estado de este paquete

Este directorio es una propuesta revisable. Ningún script fue ejecutado contra
Oracle. Los jobs nuevos se crean deshabilitados y la feature flag Django queda
apagada por defecto.

Baseline Oracle: 11.2.0.3.0, usuario runtime `USR_LAB`. Privilegios confirmados:
`CREATE TABLE`, `CREATE PROCEDURE` y `CREATE JOB`. No se usa `DBMS_LOCK`,
`MANAGE SCHEDULER`, secuencias ni triggers.

`OWNER_LOG_ID` se omitió: Oracle 11g no permite obtener de manera fiable el
`LOG_ID` de la ejecución Scheduler actual desde la misma sesión. El fencing usa
`OWNER_TOKEN + LEASE_VERSION`; para Scheduler se conservan job, SID, instancia
y fecha de adquisición.

## Semántica del lease

- `OWNER_TOKEN IS NULL`: LIBRE.
- Token presente y expiración futura: ACTIVO.
- Token presente y expiración alcanzada: SOSPECHOSO.
- SOSPECHOSO continúa bloqueando; jamás existe takeover por TTL.
- TTL de 20 minutos es únicamente umbral de investigación.
- Toda liberación y recovery compara token y versión.
- Recovery incrementa la versión para invalidar al owner antiguo.

Las escrituras de control se concentran en `PKG_ALERTA_LEASE`. Como `USR_LAB`
es dueño de sus tablas, Oracle no puede revocar DML al propio owner; la regla es
arquitectónica y se verifica por revisión/búsqueda de código.

## Transacciones autónomas y deadlock

`ADQUIRIR`, la liberación final y recovery delegan en operaciones privadas con
`PRAGMA AUTONOMOUS_TRANSACTION`. Así, sus commits no confirman negocio y un
rollback del cálculo no revierte el ownership.

El orden de locks es estable:

1. adquirir/recuperar bloquea `ALERTA_RECALCULO_CONTROL` y confirma;
2. el processor actualiza la solicitud y confirma `EJECUTANDO`;
3. recién después ejecuta el cálculo;
4. el cálculo nunca escribe la tabla de control;
5. la liberación ocurre después del commit/rollback de negocio.

El processor no mantiene bloqueada una solicitud al entrar en el package. El
recovery toma control y luego solicitud, el mismo orden lógico. No se identificó
un ciclo de locks en este diseño. Cambiar ese orden reabre el riesgo de deadlock.

## Orden exacto propuesto para PRE

1. Mantener `ALERTAS_RECALCULO_DURABLE_ENABLED=False`.
2. Mantener los jobs nuevos inexistentes o deshabilitados.
3. Ejecutar `00_preflight_readonly.sql` y guardar su salida como evidencia no
   versionada.
4. Confirmar Oracle 11g, usuario `USR_LAB`, los tres privilegios requeridos,
   ausencia de objetos nuevos y definición vigente de `JOB_UPD_ALERTAS_VAL`.
5. Exportar nuevamente `USER_SOURCE` de `PRC_UPD_ALERTAS_VAL` y
   `PRC_APLICAR_REGLAS_ALERTA`; ejecutar `generate_patches.py`. Si los hashes no
   coinciden, detener el despliegue.
6. Elegir una ventana fuera de los minutos `:05/:35`; esperar que
   `USER_SCHEDULER_RUNNING_JOBS` no muestre `JOB_UPD_ALERTAS_VAL`.
7. Deshabilitar temporalmente `JOB_UPD_ALERTAS_VAL` y registrar su definición,
   horario, estado y próxima ejecución.
8. Ejecutar `01_create_recalculo_tables.sql`.
9. Ejecutar `02_create_pkg_alerta_lease.sql`.
10. Ejecutar `03_create_processor.sql`.
11. Ejecutar `04_create_jobs_disabled.sql`; comprobar ambos `ENABLED=FALSE`.
12. Ejecutar `05_patch_prc_upd_alertas_val.sql`.
13. Ejecutar `06_patch_prc_aplicar_reglas_alerta.sql`.
14. Ejecutar `07_health_checks.sql`; no aceptar objetos inválidos ni lease
    ocupado.
15. Ejecutar manualmente en PRE la matriz `08_concurrency_tests.sql`, caso por
    caso y con dos sesiones. Nunca ejecutar el archivo completo.
16. Rehabilitar `JOB_UPD_ALERTAS_VAL` con su definición original `:05/:35`.
17. Observar al menos dos ejecuciones automáticas correctas y sus duraciones.
18. Mantener todavía deshabilitados `JOB_PROCESAR_RECALC_ALERTAS` y
    `JOB_LIMPIAR_HIST_UBICACION`.
19. En una segunda autorización, habilitar primero el processor, comprobarlo y
    recién entonces activar la feature flag Django y reiniciar el web.
20. La sustitución del scheduler Django de limpieza es otro cutover: habilitar
    el job Oracle y desactivar solo ese schedule Python de forma coordinada.

Este encargo termina antes de los pasos 19 y 20.

## Rollback

1. Apagar `ALERTAS_RECALCULO_DURABLE_ENABLED` y reiniciar Django. El thread
   anterior continúa presente en código.
2. Deshabilitar `JOB_PROCESAR_RECALC_ALERTAS` y
   `JOB_LIMPIAR_HIST_UBICACION` si fueron habilitados posteriormente.
3. Detener nuevas solicitudes manuales.
4. Consultar `07_health_checks.sql`; esperar que no haya cálculo activo.
5. Si existe lease sospechoso, investigar; no limpiar manualmente la tabla.
6. Deshabilitar temporalmente `JOB_UPD_ALERTAS_VAL`.
7. Ejecutar `10_rollback.sql`, que restaura literalmente ambos procedures desde
   `USER_SOURCE_202609241052.txt`.
8. Validar compilación y ejecutar health checks funcionales de alertas.
9. Rehabilitar `JOB_UPD_ALERTAS_VAL` con horario `:05/:35`.
10. Mantener tablas de control, auditoría y solicitudes para preservar evidencia.
11. Restaurar/continuar el scheduler Django de limpieza si ese cutover llegó a
    realizarse. En esta iteración nunca se retiró.

## Riesgos abiertos antes de PRE

- Compilación real de package/procedures en Oracle 11.2.0.3 aún no comprobada.
- Falta ejecutar el preflight para confirmar privilegios en la sesión efectiva.
- Falta confirmar que `JOB_UPD_ALERTAS_VAL` conserva exactamente `:05/:35`.
- Falta validar columnas reales de las vistas `USER_SCHEDULER_*` en 11.2.0.3.
- Falta medir el recálculo completo bajo lease y probar duración >20 minutos.
- El recovery Scheduler es deliberadamente conservador: sin ejecución terminal
  correlacionable por job/fecha, devuelve -20078.
- Un recovery DIRECT depende de confirmación, motivo y evidencia administrativa;
  nunca infiere muerte del owner.
- SQLite/UNC y separación definitiva del worker pertenecen al cierre posterior
  de BKL-002/BKL-029, no a estos scripts.

## Código Django preparado

Con la flag apagada no consulta tablas nuevas. Con la flag encendida, Django
inserta una solicitud `DJANGO_PANEL/PENDIENTE` con UUID hexadecimal generado en
Python. El repository expone además consulta por `SOLICITUD_ID`; la UI de
seguimiento/polling queda para el cutover posterior.

