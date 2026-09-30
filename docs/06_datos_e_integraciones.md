# 06 — Datos e integraciones

## Persistencia

| Almacén | Datos | Acceso |
|---|---|---|
| SQLite | Auth, sesiones, permisos, migraciones, `LogImportacion` y exclusiones de alertas por usuario. | ORM Django. |
| Oracle `USR_LAB` | Telemetría, agregados, ubicaciones, alertas y reglas. | Pool python-oracledb. |

No deben copiarse datos operativos a SQLite en el flujo vigente.

## Objetos Oracle

| Objeto | Contrato principal |
|---|---|
| `VW_ESTATUS_ZP_DJANGO` | Estado/telemetría por AMID y fecha. |
| `BATERIA_BLOQUE_30MIN` | Batería agregada cada 30 minutos. |
| `ALERTA_BATERIA_CAIDA_EVENTO` | Detalle derivado de caídas confirmadas en la ventana móvil de 14 días. |
| ALERTA_VALIDADOR_RESUMEN | Resultado calculado: prioridad, motivos y métricas por AMID. |
| VW_ALERTA_VALIDADOR_ACTIVA | Resúmenes limitados a los AMID activos. |
| ALERTA_REGLA_PARAM | Reglas configurables y tipo de aplicación. |
| ALERTA_REGLA_HISTORIAL | Auditoría de valores anteriores y nuevos. |
| `UBICACION_ESPERADA_VALIDADOR` | Referencia y horario vigente por AMID: `HORARIO`, `HORARIO_LABORAL_PM`, `HORARIO_SABADO` y `HORARIO_DOMINGO`. |
| `HISTORIAL_UBICACION_ESPERADA` | Vigencias históricas. |
| `PRC_REFRESCAR_CAIDAS_BAT` | Reemplaza transaccionalmente los eventos de caída usando las reglas de detección. |
| PRC_UPD_ALERTAS_VAL | Recalcula métricas y clasificación histórica. |
| PRC_RECLASIFICAR_ALERTAS | Valida y reaplica solo clasificación. |
| PRC_RECALCULAR_ALERTAS_SEGURO | Valida y ejecuta el cálculo completo. |
| `PRC_LIMPIAR_HIST_UBICACION` | Limpia historial según retención. |

El baseline vigente se versiona en `oracle/current/`; los despliegues
preparados se mantienen en `oracle/pending/` y los resultados de auditoría no
se publican.

### Ciclo de vida de los eventos de caída

`ALERTA_BATERIA_CAIDA_EVENTO` es una tabla derivada y acotada, no un histórico
indefinido. No necesita un job de limpieza separado.

`JOB_UPD_ALERTAS_VAL` se ejecuta cada 30 minutos y llama indirectamente a
`PRC_REFRESCAR_CAIDAS_BAT` a través de `PRC_UPD_ALERTAS_VAL`. En la misma
transacción se eliminan los eventos derivados anteriores, se insertan los de la
ventana vigente de 14 días y se recalcula `ALERTA_VALIDADOR_RESUMEN`. Si ocurre
un error antes del `COMMIT`, Oracle recupera la versión anterior mediante
`ROLLBACK`.

`CAIDAS_HIST` es el total de los 14 días e incluye `CAIDAS_HOY`. Django no debe
sumarlas ni aplicar nuevamente `BAT_CAIDA_MIN_DETECTAR` o
`BAT_CAIDA_MAX_HORAS`.

### Contrato de telemetría GPS

- `FECHA_REGISTRO` identifica el bloque temporal y se usa para ordenar y filtrar.
- `FECHA_HORA` identifica la última transmisión informada por el validador.
- Si `FECHA_HORA` se repite entre bloques consecutivos, el bloque nuevo se
  interpreta como **Sin transmisión** y no reutiliza la coordenada anterior.
- `LATITUD = 0 AND LONGITUD = 0` representa una transmisión `0,0`, no una
  coordenada válida ni un registro fuera del radio.
- **Fuera del radio** se reserva para coordenadas válidas cuya distancia
  Haversine es mayor que `RADIO_METROS`.

### Contrato de la fuente de transacciones C2D

La app `apps/transacciones/` consume una sola fuente, de **solo lectura**:

```
DBPTE.TRANSACCION_FLUJO_VC2D_FISC@CLEAMTT3PRODG
```

- `TVF_SFECTRANSACCION` es `VARCHAR2` y se convierte con
  `TO_DATE(..., 'YYYY/MM/DD HH24:MI:SS')`. Ese formato está validado sobre
  muestras; si el dato real difiere, Oracle responde `ORA-01861`. Debe
  verificarse con `oracle/diagnostics/TRX_001__validar_fuente_lectura.sql`
  antes de encender el módulo.
- `TVF_DFECREGISTRO` es la fecha de llegada a BD y ya es tipo fecha.
- `TVF_NIDAS` es un **AMID**, no un NID. El universo ZP es
  `TVF_NIDAS > AMID_MINIMO_ALERTAS` (7 500 000), el mismo criterio que usa el
  panel de alertas.
- Entidad y sitio se resuelven con `LEFT JOIN` a `DBCLEARING.ENTIDAD` y
  `DBCLEARING.SITIO` en la **misma** consulta, con los mismos filtros que el
  conteo. Una TRX sin entidad o sin sitio sigue siendo TRX válida del
  universo: la interfaz muestra `Sin operador` / `Sin sitio` en lugar de
  descartarla.
- El módulo **no persiste** TRX en SQLite y no tiene modelos ni migraciones
  propias.
- `TVF_NFILEID` no forma parte del contrato: la guía menciona `TVF_DFECFILEID`
  y su significado está sin confirmar.

Las reglas funcionales derivadas de esta fuente (corte de 15 minutos,
tramos, cambio de día, exclusividad) están especificadas en
[09_transacciones_trx.md](09_transacciones_trx.md) y se implementan solo en
`apps/transacciones/services/trx_reglas.py`.

### Datos locales de preferencias

`AlertaAmidExcluido` y `AlertaUbicacionExcluida` pertenecen a SQLite y tienen
unicidad por usuario y valor. Su propósito es controlar visibilidad; no son una
copia de `ALERTA_VALIDADOR_RESUMEN` ni de las ubicaciones Oracle.

## Contratos de aplicación

- `LogImportacion` registra origen, estado, fechas, contadores y mensaje. Un fallo de logging no interrumpe la operación principal.
- Las preferencias de alertas se guardan atómicamente y se eliminan en cascada
  si se elimina el usuario Django.
- La vista Oracle `VW_ESTATUS_ZP_DJANGO` se lee por SQL directo; el modelo Django `EstatusZP` que la referenciaba se retiró en BKL-002C (Django no administra la vista).
- Código nuevo debe reutilizar `oracle_connection.py` y parámetros enlazados (`:nombre`).
- Las reglas solo se editan si están en `CLAVES_PERMITIDAS`; la app no crea ni elimina claves.
- La importación Excel actualiza ubicación vigente y conserva historial en Oracle; los temporales no se versionan.
- El horario usado por los paneles es el vigente de
  `UBICACION_ESPERADA_VALIDADOR`; no se consulta historial de horarios.
- La importación de ubicaciones procesa primero el Excel y usa después
  `AMID_MAESTRO_ALERTAS` con `ACTIVO = 1` como universo de reconciliación.
  Un AMID activo presente en el Excel conserva su ubicación real; uno ausente
  se registra como Laboratorio Zonas Pagas. La primera vigencia comienza en la
  fecha de esa carga y no se reconstruye historial anterior.

## Fechas y cambios

Django usa `USE_TZ=True` y `America/Santiago`; Oracle usa `SYSDATE`. Deben probarse límites diarios durante cambios de horario de verano. `LocMemCache` solo es consistente dentro de un proceso.

Un cambio Oracle incompatible debe incluir columnas/parámetros afectados, coordinación del despliegue, consultas de prueba, validación de paneles/exportaciones y reversa.

## Exportación del Panel de Alertas

La ruta `alertas/exportar/` consulta `VW_ALERTA_VALIDADOR_ACTIVA` únicamente al
solicitar la descarga. Incluye todos los AMID activos —también los de nivel
`OK`— y deliberadamente ignora búsqueda, filtros visibles y exclusiones de
usuario guardadas en SQLite. El archivo contiene una hoja `Panel de Alertas`
con filtros de Excel, encabezado fijo y colores por nivel y estado.

