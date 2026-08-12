# 08 — Historial de optimización de alertas

Este documento resume cómo se llegó al estado actual. No es una guía de
ejecución; para trabajar hoy se deben usar `docs/03_flujo_completo_oracle_django.md`
y `oracle/current/alertas_oracle_estado_actual.sql`.

## Punto de partida

Oracle ya contenía el cálculo completo `PRC_UPD_ALERTAS_VAL`, los jobs, la tabla
de reglas y el resumen por AMID. El backend guardaba umbrales y siempre lanzaba
el cálculo histórico completo, incluso cuando solo cambiaba una clasificación.

No se podía modificar `JOBS_STATUS_ZP` ni la estructura de `ESTATUS_ZP`.

## Etapa 1 — Reclasificación rápida

Se incorporaron:

- `VW_ALERTA_VALIDADOR_ACTIVA`;
- `FECHA_REGLAS_APLICADAS`;
- `PRC_APLICAR_REGLAS_ALERTA`.

El procedimiento rápido reutiliza métricas calculadas. La comparación inicial
de los 930 AMID produjo cero diferencias respecto del cálculo completo.

## Etapa 2 — Gobierno de reglas

Se incorporaron:

- `TIPO_REGLA` con 2 reglas de `DETECCION` y 25 de `CLASIFICACION`;
- `ALERTA_REGLA_HISTORIAL`, secuencia y trigger;
- `PRC_VALIDAR_REGLAS_ALERTA`;
- `PRC_RECLASIFICAR_ALERTAS`;
- `PRC_RECALCULAR_ALERTAS_SEGURO`.

DBeaver dividió inicialmente el procedure de validación en sentencias y lo dejó
inválido. Después se compiló como script completo. El primer nombre propuesto
para el wrapper rápido superaba el límite de 30 caracteres de esa versión de
Oracle y se reemplazó por `PRC_RECLASIFICAR_ALERTAS`.

## Etapa 3 — Rendimiento

La auditoría mostró estadísticas vigentes, 4,1 millones de filas en
`ESTATUS_ZP`, 642 mil bloques de batería y 930 resúmenes. Los índices existentes
cubrían los accesos principales, por lo que no se agregaron ni eliminaron
índices.

Django pasó a consultar la vista de AMID activos y a cachear los totales durante
60 segundos.

## Etapa 4 — Operación

El log manual incorporó modo, duración, error, rotación a 1 MB y presentación de
las últimas 100 líneas. También se evita iniciar dos recálculos manuales dentro
del mismo proceso Django.

## Estado final

- Las reglas viven en Oracle y se editan desde Django.
- Oracle valida antes de confirmar cambios.
- Clasificación utiliza el camino rápido.
- Detección utiliza el cálculo completo.
- Los valores anteriores quedan auditados.
- Django consulta resultados preparados.

Los archivos de `oracle/history/` conservan las sentencias ejecutadas y sus
reparaciones. No deben volver a ejecutarse sobre el esquema actual.