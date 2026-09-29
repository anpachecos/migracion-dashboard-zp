# 09. Módulo de Transacciones (TRX C2D)

## Propósito

Sustituir los Excel de trabajo de transacciones C2D por un módulo del dashboard
con tres salidas:

| Salida | OrigenExcel | Regla |
|---|---|---|
| Informe Interno ZP trxC2D | `Informe_ZP_trxC2D_Interno` | Universos de TRX del día, con desglose por tramo y operador |
| Mayor a 15 min | análisis mensual de TRX sobre 15 min | Mismo día calendario y más de 15 minutos |
| Rezagadas | detalle de TRX rezagadas | Día de registro en BD distinto al día de la TRX |

El módulo es **de solo lectura**. No crea objetos Oracle, no guarda TRX en
SQLite y no tiene modelos ni migraciones propias.

## Fuente de datos

```
DBPTE.TRANSACCION_FLUJO_VC2D_FISC@CLEAMTT3PRODG
```

DB link sin calificar, igual que el resto del dashboard.

### Campos usados

| Alias | Origen | Uso |
|---|---|---|
| `FEC_TRX` | `TO_DATE(TVF_SFECTRANSACCION, 'YYYY/MM/DD HH24:MI:SS')` | Momento de generación de la TRX |
| `FEC_BD` | `TVF_DFECREGISTRO` | Momento de llegada a la base de datos |
| `NID_CONTEXTO_OPTE` | `TVF_NIDCONTEXTOPTE` | Identificador de la transacción, usado para orden estable |
| `NUM_ABT` | `TVF_SNUMABTC2D` | Número de abortos |
| `AMID` | `TVF_NIDAS` | Identificador del validador. **Es un AMID, no un NID** |
| `NID_SITIO` | `TVF_NIDSITIO` | Sitio / BUS_ID |
| `NOMBRE_SITIO` | `DBCLEARING.SITIO.SIT_SNOMSITIO` | Nombre del sitio (LEFT JOIN) |
| `NID_ENTIDAD_OT` | `TVF_NIDENTIDADOT` | Entidad de origen |
| `NOMBRE_ENTIDAD` | `DBCLEARING.ENTIDAD.ENT_SNOMENTIDAD` | Nombre del operador (LEFT JOIN) |
| `NID_TERMINAL` | `TVF_NIDTERMINAL` | Terminal |
| `COD_TIPO_TRANSACCION` | `TVF_SCODTIPOTRANSACCION` | Tipo de transacción |
| `N_MODO` | `TVF_NMODO` | Modo. `4` = Zonas Pagas |
| `COD_PROCESO` | `TVF_SCODPROCESO` | Código de proceso |
| `ESTADO_ENVIO` | `TVF_SESTADOENVIO` | Estado de envío |

`TVF_NFILEID` no se usa. La guía de Roxana muestra `TVF_DFECFILEID`; su
existencia y significado están pendientes de confirmar
(`oracle/diagnostics/TRX_001__validar_fuente_lectura.sql`, bloque 8).

## Reglas funcionales

Viven únicamente en `apps/transacciones/services/trx_reglas.py`. Ningún otro
módulo debe volver a escribir un umbral.

### Diferencia temporal

```
tiempo_diferencia = FEC_BD - FEC_TRX
```

Si la diferencia es negativa se marca `desfase_reloj` y **no** se genera
duración: no se muestra un valor negativo como si fuera un retardo real.

### Clasificación

| Duración | Clasificación |
|---|---|
| `<= 00:05:00` | `<= 5 min` |
| `> 00:05:00` y `<= 00:15:00` | `> 5 y <= 15 min` |
| `> 00:15:00` | `> 15 min` |
| No calculable | `Sin dato` |

**Exactamente 15:00 no es `> 15 min`.** El corte es estricto.

### Tramos

| Tramo | Rango |
|---|---|
| Hasta 5 min | `00:00:00-00:05:00` |
| 5-6 | `00:05:01-00:06:00` |
| 6-7 | `00:06:01-00:07:00` |
| 7-8 | `00:07:01-00:08:00` |
| 8-10 | `00:08:01-00:10:00` |
| 10-15 | `00:10:01-00:15:00` |
| 15-30 | `00:15:01-00:30:00` |
| 30-60 | `00:30:01-01:00:00` |
| 1-2 hrs | `01:00:01-02:00:00` |
| Más de 2 hrs | `02:00:01+` |

Los límites son inclusivos y contiguos: cada tramo arranca un segundo después
del anterior. Hay pruebas que verifican ambas propiedades.

### Rezago

```
es_rezagada = DATE(FEC_TRX) != DATE(FEC_BD)
```

El cambio de día manda aunque la diferencia temporal sea mínima. Ejemplo:
`23:59 -> 00:01` ya es rezagada. No se impone techo de días: la evidencia
revisada muestra 1 a 4 días, pero el máximo real se desconoce.

### Exclusividad

`es_rezagada` y `es_mayor_15` son **mutuamente excluyentes por construcción**:
una TRX rezagada nunca entra a `> 15 min`, por larga que sea su duración.

```
es_mayor_15 = es_mismo_dia AND duracion_segundos > 900
```

### Precedencia de estados

La columna `Estado` de la tabla y el pill de cada fila resumen las dos reglas
en un solo valor. Es una lectura de indicadores ya calculados, no una tercera
regla, y su orden es `trx_reglas.PRECEDENCIA_ESTADOS`:

| Prioridad | Estado | Cuándo aplica |
|---|---|---|
| 1 | `Sin dato` | No se puede calcular duración (fecha ausente, o `FEC_BD < FEC_TRX`) |
| 2 | `Rezagada` | Cambió el día calendario |
| 3 | `Mayor a 15 min` | Mismo día y duración `> 15:00` |
| 4 | `Dentro de rango` | Mismo día y duración `<= 15:00` |

Por qué este orden:

- **`Sin dato` va primero** porque sin duración no hay nada que afirmar. Se
  evalúa antes que las otras dos por seguridad, aunque `es_rezagada` y
  `es_mayor_15` ya exigen datos válidos.
- **`Rezagada` antes que `Mayor a 15 min`** porque el cambio de día calendario es
  el problema dominante. Una TRX de las 23:50 que llega a las 00:05 está
  clasificada `<= 5 min` en verde, y eso no describe su problema real. Como las
  dos reglas ya son excluyentes, este orden solo desempata, no pisa.
- **`Dentro de rango`** es el residuo: mismo día y dentro del umbral.

La duración exacta (`HH:MM:SS`) sigue siendo la columna de referencia. El
estado es un resumen para lectura rápida, no reemplaza al dato.

## Arquitectura

```
apps/transacciones/
├── views.py                     # solo autorización, redirección y render
├── urls.py                      # 4 rutas
├── permisos.py                  # política de acceso y decorador 403
├── templatetags/trx_permisos.py    # visibilidad del enlace en el sidebar
├── repositories/trx_repository.py   # SQL Oracle, binds, paginación 11g
├── services/
│   ├── trx_reglas.py            # umbrales y reglas. Fuente única
│   ├── trx_service.py           # normalización y dataset común
│   ├── informe_interno_service.py
│   ├── mayor_15_service.py
│   ├── rezagadas_service.py
│   └── exportaciones_service.py # stubs: NotImplementedError
├── templates/transacciones/
└── static/transacciones/
```

El `trx_service` calcula **una sola vez** por fila todos los campos derivados
(`duracion_segundos`, `clasificacion`, `tramo_*`, `es_mismo_dia`, `es_rezagada`,
`es_mayor_15`, `dias_rezago`). Los tres informes solo consumen esas filas: no
recalculan nada y no vuelven a consultar Oracle.

## Acceso

La sección **no es pública**. Solo la ven los superusuarios y los miembros de
los grupos que indique `TRX_GRUPOS_PERMITIDOS` (por defecto `Admin` y `SONDA`).
El resto de los paneles sigue abierto para cualquier usuario con sesión, igual
que antes de añadir este módulo.

| Situación | Resultado |
|---|---|
| Sin sesión | `302` a `/login/?next=...`, como el resto del dashboard |
| Con sesión, sin grupo en `TRX_GRUPOS_PERMITIDOS` | `403`, sin armar contexto ni consultar Oracle |
| Superusuario o grupo configurado | `200` |

La comprobación vive en `apps/transacciones/permisos.py` y se aplica con
`@requiere_permiso_transacciones` sobre las cuatro vistas, incluida la raíz
`/transacciones/`. El permiso se resuelve **antes** de invocar la vista, así
que el camino denegado no toca Oracle.

Se replica a propósito la semántica de `usuario_es_admin`
(`apps/dashboard/views.py`): admin es superusuario **o** grupo `Admin`. El gate
del panel de alertas es otro módulo y no se modifica, y
`TRX_GRUPOS_PERMITIDOS` no lo afecta.

### Configurar quién entra

La política está en la variable de entorno `TRX_GRUPOS_PERMITIDOS`, separada
por comas:

```bash
TRX_GRUPOS_PERMITIDOS=Admin,SONDA
```

Dos detalles importan:

- Los nombres deben coincidir **exactamente** con los de `auth_group`. La
  comparación es case-sensitive: `Sonda` no es `SONDA` y deja al usuario fuera.
- Vaciar la variable deja el módulo únicamente para superusuarios.

Cambiar quién entra no requiere desplegar código, solo reiniciar con la
variable cargada. Los grupos y sus miembros se administran en `/admin/` en
*Authentication and Groups*; no hace falta comando de gestión ni migración.

### Visibilidad en el menú

El enlace del sidebar se oculta con el tag
`{% puede_ver_transacciones user %}` en
`dashboard/base_dashboard.html`. Es una comodidad visual, **no** la garantía:
la garantía es el `403` de las vistas. Se prefirió un template tag y no un
context processor porque el sidebar se renderiza en todas las páginas y un
context processor añadiría una consulta a cada request del sistema.

## Filtros

| Parámetro | Valores | Efecto |
|---|---|---|
| `fecha_desde` / `fecha_hasta` | `AAAA-MM-DD` | Rango inclusivo |
| `fecha` | `AAAA-MM-DD` | Atajo de un día |
| `origen` | `trx` / `bd` | Columna del filtro de rango |
| `amid` | 1 a 7 dígitos | Filtra validador |
| `nidsitio` | numérico | Filtra sitio |
| `nmodo` | numérico | Filtra modo (`4` = ZP) |
| `solo_mismo_dia` | `1` | Solo TRX con llegada a BD el mismo día |

`fecha_hasta` es inclusiva para la persona; internamente se envía a Oracle como
exclusiva (`< fecha_hasta + 1 día`).

El rango por defecto es el día de hoy. Si no se pasan fechas, el módulo muestra
la estructura sin datos.

## Comportamiento de Oracle

- `TVF_NIDAS > 7500000` define el universo ZP. Es el mismo criterio que
  `AMID_MINIMO_ALERTAS` del panel de alertas.
- Los dos `LEFT JOIN` a `DBCLEARING.ENTIDAD` y `DBCLEARING.SITIO` se hacen en la
  misma consulta que el conteo, con los mismos filtros.
  La guía de Roxana usa `INNER JOIN`, lo que descarta TRX sin entidad o sin
  sitio. Ver `TRX_001`, bloque 4, para cuantificar la diferencia.
- Paginación con `ROW_NUMBER() OVER (...)`. Nunca `FETCH FIRST` (Oracle 11g).
- Todo el SQL usa binds. Nunca se concatena un valor del usuario.
- Proyección explícita de columnas. Nunca `SELECT *`.
- El conteo y el detalle comparten `armar_filtros_trx`, por lo que no pueden
  divergir.
- Cuando el origen es `bd` se agrega un límite inferior sobre `FEC_TRX` y
  **ningún** techo superior, para no descartar rezagadas de días anteriores.

## Configuración

| Variable | Default | Significado |
|---|---|---|
| `TRX_ORACLE_HABILITADO` | `False` | Interruptor maestro. Apagado = el panel no consulta |
| `TRX_AMID_MINIMO` | `7500000` | Universo ZP |
| `TRX_RANGO_MAXIMO_DIAS` | `7` | Tope de rango por consulta |
| `TRX_FILAS_POR_PAGINA` | `200` | Filas por página |
| `TRX_MAX_FILAS_DETALLE` | `2000` | Tope de filas en memoria |
| `TRX_MODO_FECHA_BASE` | `trx` | Columna por defecto del filtro de rango |
| `TRX_GRUPOS_PERMITIDOS` | `Admin,SONDA` | Grupos de Django con acceso. Vacío = solo superusuarios |

`TRX_ORACLE_HABILITADO` está **apagado por defecto** y debe seguir apagado
hasta completar la validación contra los Excel de referencia.

## Estado de validación

**Las cifras no están validadas contra los Excel.** La constante
`CONSULTAS_VALIDADAS` en `trx_service.py` está en `False` a propósito, y la
interfaz muestra una advertencia permanente en la zona de KPIs.

Excel de referencia pendiente:
- `27-08-2026 Informe_ZP_trxC2D_Interno.xlsx`
- `28-08-2026 Informe_ZP_trxC2D_Interno.xlsx`

Para dar por validado el Informe Interno deben coincidir, para los mismos días:
total de TRX, cantidad de AMID, TRX con ZP, desglose por operador y por tramo,
y la clasificación temporal.

### TODO — los agregados se calculan sobre una muestra

Este es el **bloqueante conocido** para la validación funcional.

`obtener_dataset_base` trae como máximo `min(TRX_FILAS_POR_PAGINA,
TRX_MAX_FILAS_DETALLE)` filas, y sobre esas filas calcula `resumir_dataset`. Por
lo tanto, hoy:

| Dato | Origen | ¿Exacto? |
|---|---|---|
| Total de TRX del rango | `COUNT(*)` en Oracle (`total_universo`) | **Sí** |
| Tabla de detalle | Filas de la muestra | Parcial, acotado |
| Conteos por validador, sitio, operador | Muestra | **No** |
| Porcentajes de rezago y `> 15 min` | Muestra | **No** |
| Distribución por tramo, matriz, ranking | Muestra | **No** |

Las tres pantallas muestran el total real en la tarjeta *"Total TRX del rango"*
y un contador *"Total TRX analizados"* que aclara cuántos de esos se analizaron,
para que el número acotado no se lea como el total del día.

**Antes de la validación funcional**, los conteos, porcentajes, distribución por
tramo, matriz validador x día y ranking deben pasar a consultas agregadas
(`COUNT`, `SUM(CASE ...)`, `GROUP BY`) sobre el universo completo en Oracle, con
el mismo WHERE que `armar_filtros_trx`. Marcado como `TODO(trx-001)` en
`trx_service.resumir_dataset`, `informe_interno_service._construir_kpis`,
`mayor_15_service._construir_kpis` y `mayor_15_service._matriz_validador_dia`.

Los KPI calculados únicamente sobre la muestra **no se consideran válidos**
contra los Excel de referencia, y por eso `CONSULTAS_VALIDADAS` permanece en
`False` aunque el resto del módulo esté correcto.

## Supuesto abierto: S1 (día base)

**Este supuesto está sin confirmar y es el punto funcional más delicado del
módulo.**

La guía de Roxana describe el Informe Interno sobre TRX cuyo día de generación
y su día de llegada a BD coinciden. La lectura directa de esa guía equivale a
filtrar `es_mismo_dia`.

El módulo **no fija** ese comportamiento por defecto. Expone las dos lecturas y
deja que se elija:

- Sin `solo_mismo_dia`: todas las TRX del rango, rezagadas incluidas. Esto es
  lo que hacen los análisis de rezago y `> 15 min`.
- Con `solo_mismo_dia=1`: solo TRX con llegada el mismo día. Equivale a la
  lectura de la guía.

La pantalla muestra un enlace para alternar entre ambas y deja explícito cuál
está activa. Hay que confirmar con Roxana cuál usa su Excel antes de encender
el módulo.

## Qué falta implementar

| Zona | Estado |
|---|---|
| Gráficos (distribución por tramo, tendencia diaria) | Placeholder |
| Análisis mensual | Placeholder |
| Exportación XLSX | `NotImplementedError` en `exportaciones_service.py` |
| Paginación real en Oracle | El rango está acotado; se hace en memoria |
| **Agregados sobre el universo completo** | **Bloqueante: hoy se usan agregados en Python sobre la muestra** |
| Información LAB (cruce con laboratorio ZP) | Requiere fuente de Zonas Pagas validada |
| Confirmación de `TVF_NFILEID` | Pendiente |

Las zonas sin implementar se muestran con un marcador explícito. **No hay datos
simulados ni valores inventados en ninguna pantalla.**

## Diagnóstico

`oracle/diagnostics/TRX_001__validar_fuente_lectura.sql`

Solo `SELECT`. Cubre:

1. Contexto de sesión y versión.
2. Longitud y formato real de `TVF_SFECTRANSACCION` (detecta el riesgo
   `ORA-01861`).
3. Verificación de que la conversión `TO_DATE` funciona.
4. Diferencia entre `LEFT JOIN` e `INNER JOIN` sobre el universo.
5. Cobertura de entidad y sitio.
6. Control de magnitudes de `> 15 min` y desfase de reloj.
7. Distribución de días de rezago.
8. Existencia de columnas `%FILEID%`.

Ejecutarlo **antes** de poner `TRX_ORACLE_HABILITADO=True`.

El script es un único bloque PL/SQL de solo lectura con salida etiquetada por
`DBMS_OUTPUT`. Para cambiar el rango hay que editar **un solo lugar**: las
variables `v_fecha_inicio` y `v_fecha_fin` del `DECLARE`. El SQL de las ocho
consultas las referencia por nombre, así que no hay fechas repetidas.

- DBeaver: seleccionar todo el archivo y `Ctrl+Enter` (o *Run Script*).
- SQLcl / SQL\*Plus: `@trx_001.sql`.

`SET SERVEROUTPUT ON` es necesario para ver la salida. Requiere privileges de
lectura sobre `V$VERSION` y `ALL_TAB_COLUMNS`; si faltan, los bloques 0 y 8 lo
reportan y el resto sigue funcionando.

## Pruebas

```
venv\Scripts\python.exe manage.py test apps.transacciones
```

Cubren: límites de clasificación y tramos, contigüidad de tramos, exclusividad
rezagada / `> 15 min`, precedencia de estados, formateo de duración,
normalización de fila cruda, validación de filtros, flag maestro, contención de
fallos de Oracle, SQL sin `SELECT *` y sin binds huérfanos, igualdad de filtros
entre conteo y detalle, separación entre total real y total de la muestra, las
tres vistas, y el comportamiento de las exportaciones no implementadas.

El acceso se cubre en `test_permisos.py` (la política sale de
`TRX_GRUPOS_PERMITIDOS`, no del código; case-sensitivity; una sola consulta;
fail-closed con lista vacía; y el parseo de la variable de entorno) y en
`test_transacciones_views.py` (302 anónimo, 403 sin rol, 200 para
sonda / admin / superusuario, y que el sidebar muestre u oculte el enlace).
