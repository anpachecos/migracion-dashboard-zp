# 05 — Datos e integraciones

## Persistencia

| Almacén | Datos | Acceso |
|---|---|---|
| SQLite | Auth, sesiones, permisos, migraciones y `LogImportacion`. | ORM Django. |
| Oracle `USR_LAB` | Telemetría, agregados, ubicaciones, alertas y reglas. | Pool python-oracledb. |

No deben copiarse datos operativos a SQLite en el flujo vigente.

## Objetos Oracle

| Objeto | Contrato principal |
|---|---|
| `VW_ESTATUS_ZP_DJANGO` | Estado/telemetría por AMID y fecha. |
| `BATERIA_BLOQUE_30MIN` | Batería agregada cada 30 minutos. |
| `ALERTA_VALIDADOR_RESUMEN` | Prioridad, motivos, métricas y actualización. |
| `ALERTA_REGLA_PARAM` | Reglas numéricas configurables. |
| `UBICACION_ESPERADA_VALIDADOR` | Referencia vigente por AMID. |
| `HISTORIAL_UBICACION_ESPERADA` | Vigencias históricas. |
| `PRC_UPD_ALERTAS_VAL` | Recalcula alertas. |
| `PRC_LIMPIAR_HIST_UBICACION` | Limpia historial según retención. |

El DDL no está versionado aquí y debe gestionarse en el proceso propietario de Oracle.

## Contratos de aplicación

- `LogImportacion` registra origen, estado, fechas, contadores y mensaje. Un fallo de logging no interrumpe la operación principal.
- `EstatusZP` tiene `managed = False`: Django no crea ni migra la vista.
- Código nuevo debe reutilizar `oracle_connection.py` y parámetros enlazados (`:nombre`).
- Las reglas solo se editan si están en `CLAVES_PERMITIDAS`; la app no crea ni elimina claves.
- La importación Excel actualiza ubicación vigente y conserva historial en Oracle; los temporales no se versionan.

## Fechas y cambios

Django usa `USE_TZ=True` y `America/Santiago`; Oracle usa `SYSDATE`. Deben probarse límites diarios durante cambios de horario de verano. `LocMemCache` solo es consistente dentro de un proceso.

Un cambio Oracle incompatible debe incluir columnas/parámetros afectados, coordinación del despliegue, consultas de prueba, validación de paneles/exportaciones y reversa.

