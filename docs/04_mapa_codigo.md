# 04 — Mapa del código

## Objetivo

Este documento describe la estructura principal del proyecto Django y explica para qué sirve cada carpeta o archivo importante.

El objetivo es facilitar la mantención del código, entender dónde vive cada parte del sistema y poder explicar el funcionamiento general del dashboard sin tener que revisar todos los archivos desde cero.

---

## Estructura general

```txt
migracion-dashboard-web/
│
├── manage.py
├── requirements.txt
├── .env.example
├── .gitignore
├── config/
├── apps/
│   └── dashboard/
├── docs/
└── temp_uploads/
```

El proyecto está organizado como una aplicación Django. La carpeta principal de trabajo es `apps/dashboard/`, donde se encuentran las vistas, servicios, templates, archivos estáticos y comandos personalizados del dashboard.

Los archivos de configuración general se encuentran en `config/`. La documentación técnica del proyecto se mantiene en `docs/`.

---

## Archivos raíz

| Archivo | Descripción | Estado |
|---|---|---|
| `manage.py` | Archivo principal para ejecutar comandos Django, levantar el servidor, aplicar migraciones y ejecutar tareas administrativas. | Vigente |
| `requirements.txt` | Lista de librerías necesarias para instalar el proyecto. | Vigente |
| `.env.example` | Ejemplo de variables de entorno necesarias para configurar el sistema. No debe contener credenciales reales. | Vigente |
| `.env` | Archivo local con variables reales de configuración, incluyendo credenciales. No debe subirse al repositorio. | No subir |
| `.gitignore` | Define qué archivos o carpetas no deben ser versionados por Git. | Vigente |
| `db.sqlite3` | Base de datos local usada por Django para usuarios, sesiones, permisos, grupos, logs y migraciones internas. No se versiona porque contiene información local del entorno. | No subir |
| `estructura_proyecto.txt` | Archivo temporal generado para revisar la estructura del proyecto. No forma parte del funcionamiento del dashboard. | No subir |

---

## Archivos locales fuera del proyecto

Durante el desarrollo pueden existir scripts auxiliares usados solo para pruebas o diagnóstico. Estos archivos no forman parte del flujo normal del dashboard y no deben subirse al repositorio.

| Archivo | Descripción | Estado |
|---|---|---|
| `medir_oracle.py` | Script local usado para medir tiempos de conexión, pool y consultas Oracle. No es llamado por la web ni por el scheduler. Se mantiene fuera del proyecto como respaldo o herramienta de diagnóstico local. | Fuera del proyecto / No subir |

---

## Nota sobre scripts de Oracle

Los objetos Oracle mantenidos por este proyecto se organizan en:

- `oracle/current/`: baseline consolidado vigente;
- `oracle/history/`: scripts ya ejecutados;
- `oracle/diagnostics/`: auditorías de solo lectura.

La prueba oficial de conexión se realiza con:

```powershell
python manage.py probar_oracle
```

El comando vive en `apps/dashboard/management/commands/probar_oracle.py`; no se
debe conservar otro `probar_oracle.py` suelto en la raíz.
---

## Carpeta `config/`

La carpeta `config/` contiene la configuración global del proyecto Django. Aquí se definen las rutas principales del sistema, la configuración general del proyecto y los puntos de entrada para despliegue.

```txt
config/
├── settings.py
├── urls.py
├── asgi.py
├── wsgi.py
└── __init__.py
```

| Archivo | Descripción | Estado |
|---|---|---|
| `settings.py` | Configuración principal del proyecto: variables de entorno, apps instaladas, middleware, base SQLite local, archivos estáticos, login, sesiones, zona horaria, Oracle y scheduler. | Vigente / revisar antes de despliegue |
| `urls.py` | Define las rutas principales del proyecto y conecta con las rutas de la app `dashboard`. | Vigente |
| `wsgi.py` | Punto de entrada para despliegue en servidores WSGI, como Waitress u otros servidores compatibles. | Vigente |
| `asgi.py` | Punto de entrada para despliegue ASGI. Actualmente no es el foco principal del proyecto. | Vigente |
| `__init__.py` | Indica que la carpeta es un paquete Python. No requiere cambios. | Vigente |

### Observaciones

- Las credenciales reales y datos del entorno deben mantenerse en `.env`, no directamente en `settings.py`.
- `.env` no debe subirse al repositorio.
- `.env.example` debe quedar solo como plantilla, sin contraseñas reales.
- `ALLOWED_HOSTS` se configura desde `.env` para permitir acceso desde localhost, IPs internas o nombre del servidor.
- SQLite se usa para datos internos de Django, como usuarios, sesiones, permisos, logs y migraciones.
- Los datos operativos del dashboard se consultan desde Oracle.
- Antes de activar o mantener activo `DASHBOARD_SCHEDULER_ENABLED`, se debe revisar `apps/dashboard/services/scheduler.py`.

## Carpeta `apps/dashboard/`

Esta es la aplicación principal del sistema. Contiene la lógica del dashboard, las rutas internas, las vistas, los servicios, los templates, los archivos estáticos y los comandos de administración.

```txt
apps/dashboard/
├── admin.py
├── apps.py
├── context_processors.py
├── models.py
├── tests.py
├── urls.py
├── views.py
├── management/
├── migrations/
├── services/
├── static/
└── templates/
```

| Archivo | Descripción | Estado |
|---|---|---|
| `views.py` | Contiene las vistas principales del dashboard. Recibe solicitudes web, valida permisos, llama a servicios, renderiza templates y gestiona acciones como exportaciones o comandos administrativos. Actualmente también contiene lógica auxiliar de exportación Excel que podría moverse a un servicio dedicado. | Vigente / refactorizar |
| `urls.py` | Define las rutas internas de la app `dashboard`, incluyendo paneles principales, acciones administrativas y exportaciones Excel. | Vigente |
| `models.py` | Define modelos Django. Actualmente contiene `LogImportacion`, usado en SQLite para logs internos, y `EstatusZP`, modelo no administrado que referencia la vista Oracle `VW_ESTATUS_ZP_DJANGO`. | Vigente / revisar `EstatusZP` |
| `context_processors.py` | Agrega datos comunes al layout general del dashboard, como la hora de renderizado, último dato recibido desde Oracle y última actualización de versión ZP. Usa caché para evitar consultas Oracle en cada petición. | Vigente / revisar simplificación |
| `admin.py` | Configura qué modelos locales se muestran en el administrador de Django. Actualmente no registra modelos propios de la app. | Vigente / opcional |
| `apps.py` | Configura la app `dashboard`. Si `DASHBOARD_SCHEDULER_ENABLED=True`, puede iniciar el scheduler interno al levantar Django. | Vigente / revisar en despliegue |
| `tests.py` | Contiene pruebas unitarias básicas para funciones del dashboard, como context processor, filtros de alertas y permisos de edición de reglas. | Vigente / ampliar |
| `__init__.py` | Indica que la carpeta es un paquete Python. No requiere cambios. | Vigente |

### Observaciones

- `views.py` funciona correctamente, pero concentra varias responsabilidades. Más adelante se recomienda mover la lógica de exportación Excel a un servicio dedicado, por ejemplo `services/exportaciones_excel_service.py`.
- `EstatusZP` aparece como modelo de referencia sobre Oracle, pero actualmente las consultas operativas se realizan principalmente desde los servicios usando `python-oracledb`.
- `context_processors.py` usa caché para no consultar Oracle en cada petición. Se puede simplificar si se elimina la lógica de precarga en segundo plano.
- `admin.py` está vacío porque no hay modelos propios registrados en el administrador de Django. Si más adelante se quiere revisar `LogImportacion` desde `/admin`, se puede registrar ahí.
- `apps.py` puede iniciar el scheduler interno. Antes de usarlo en despliegue, se debe revisar que no active tareas antiguas o innecesarias.
- La carga de ubicaciones esperadas actualmente se realiza desde el panel Perfil mediante subida manual de Excel, no desde un archivo fijo programado en el scheduler.
- `tests.py` ya contiene pruebas básicas, pero todavía no cubre todo el sistema. Se recomienda ampliarlas progresivamente.
---

## Carpeta `services/`

La carpeta `services/` contiene la lógica de negocio del dashboard. Es una de las carpetas más importantes del proyecto porque aquí se consulta Oracle, se preparan datos para los paneles y se centralizan cálculos.

```txt
apps/dashboard/services/
├── alertas_bateria_utils.py
├── alertas_service.py
├── baterias_service.py
├── gps_service.py
├── logs_service.py
├── oracle_connection.py
├── reglas_alertas_service.py
├── scheduler.py
└── __init__.py
```

| Archivo | Descripción | Estado |
|---|---|---|
| `oracle_connection.py` | Maneja la conexión a Oracle usando `python-oracledb`. Centraliza la creación del pool y la obtención de conexiones. | Vigente |
| `baterias_service.py` | Prepara los datos del Panel Baterías: tarjetas, tabla por media hora, gráficos y alertas del período. | Vigente / revisar lógica de alertas |
| `gps_service.py` | Prepara los datos del Panel GPS: última ubicación, puntos del mapa, ubicación esperada y validación contra radio. | Vigente |
| `alertas_service.py` | Consulta desde Oracle la tabla resumen de alertas y prepara cards, filtros, paginación y tabla del Panel Alertas. | Vigente |
| `alertas_bateria_utils.py` | Funciones auxiliares para detectar caídas de batería en Python. Debe revisarse porque puede duplicar lógica que también existe o debería existir en Oracle. | Revisar |
| `reglas_alertas_service.py` | Consulta y actualiza reglas configurables de alertas desde el Panel Perfil/Admin. | Vigente |
| `logs_service.py` | Registra logs de procesos, ejecuciones o errores. | Vigente |
| `scheduler.py` | Define procesos automáticos programados desde Django. | Vigente / revisar |
| `__init__.py` | Indica que la carpeta es un paquete Python. | Vigente |

### Observación importante sobre alertas de batería

Actualmente el Panel Baterías y el Panel Alertas pueden no usar exactamente la misma lógica para detectar caídas de batería.

- El Panel Baterías puede calcular alertas desde Python.
- El Panel Alertas lee alertas ya resumidas desde Oracle.

Esto debe revisarse para evitar diferencias entre ambos paneles. La recomendación futura es tener una única lógica oficial para eventos de batería y que ambos paneles la consulten.

---

## Carpeta `templates/`

La carpeta `templates/` contiene las plantillas HTML usadas por Django para mostrar las páginas del dashboard.

```txt
apps/dashboard/templates/dashboard/
├── base_dashboard.html
├── login.html
├── panel_baterias.html
├── panel_gps.html
├── panel_alertas.html
├── panel_alertas_mantencion.html
└── panel_perfil.html
```

| Archivo | Descripción | Estado |
|---|---|---|
| `base_dashboard.html` | Template base del dashboard. Define la estructura general, sidebar, navegación, estado del sistema, bloque de contenido, CSS y JS extra por página. | Vigente |
| `login.html` | Template de inicio de sesión. Permite ingresar al dashboard con usuario y contraseña de Django. | Vigente |
| `panel_baterias.html` | Template del panel de baterías. Muestra búsqueda por AMID, tarjetas resumen, alertas del período, tabla por bloques de 30 minutos y gráficos. | Vigente |
| `panel_gps.html` | Template del panel GPS. Muestra filtros por AMID, fechas, horarios, métricas del período, mapa Leaflet y resumen de ubicación esperada. | Vigente |
| `panel_alertas.html` | Template activo del panel de alertas. Muestra resumen de prioridades, filtros, tabla de alertas, accesos a revisión GPS/Batería y paginación. | Vigente |
| `panel_alertas_mantencion.html` | Template antiguo usado cuando el panel de alertas estaba en mantención. Actualmente podría quedar como respaldo o eliminarse si ya no se usa. | Revisar / posible obsoleto |
| `panel_perfil.html` | Template del perfil de usuario y administración. Muestra datos del usuario conectado, métricas de usuarios, logs, carga de ubicaciones y configuración de reglas de alertas para administradores. | Vigente / extenso |

### Observaciones

- Los templates principales funcionan como capa de presentación. La lógica pesada debe mantenerse en `views.py` o, idealmente, en los servicios.
- `base_dashboard.html` centraliza la navegación y el estado del sistema, por lo que evita repetir estructura en cada panel.
- `panel_alertas_mantencion.html` parece ser una plantilla antigua. Se debe revisar si todavía existe alguna vista o ruta que la use.
- `panel_perfil.html` es el template más extenso, porque mezcla datos de usuario, administración, logs, carga de ubicaciones y reglas de alertas. Más adelante podría dividirse en fragmentos reutilizables.
- Si se busca mejorar mantenibilidad, se podrían crear templates parciales en una carpeta como `templates/dashboard/partials/`.
---

## Carpeta `static/dashboard/`

Contiene archivos estáticos usados por el frontend: CSS, JavaScript e imágenes.

```txt
apps/dashboard/static/dashboard/
├── css/
├── js/
└── img/
```

---

## Carpeta `static/dashboard/css/`

Contiene los estilos visuales de la aplicación.

```txt
apps/dashboard/static/dashboard/css/
├── base_dashboard.css
├── login.css
├── panel_alertas.css
├── panel_baterias.css
├── panel_gps.css
└── panel_perfil.css
```

| Archivo | Descripción | Estado |
|---|---|---|
| `base_dashboard.css` | Estilos generales compartidos por todo el dashboard. | Vigente |
| `login.css` | Estilos de la pantalla de login. | Vigente |
| `panel_baterias.css` | Estilos propios del Panel Baterías. | Vigente |
| `panel_gps.css` | Estilos propios del Panel GPS. | Vigente |
| `panel_alertas.css` | Estilos propios del Panel Alertas. | Vigente |
| `panel_perfil.css` | Estilos propios del Panel Perfil. | Vigente |

---

## Carpeta `static/dashboard/js/`

Contiene scripts JavaScript usados por los paneles.

```txt
apps/dashboard/static/dashboard/js/
├── panel_alertas.js
├── panel_baterias.js
└── panel_gps.js
```

| Archivo | Descripción | Estado |
|---|---|---|
| `panel_baterias.js` | Maneja gráficos y comportamiento dinámico del Panel Baterías. | Vigente |
| `panel_gps.js` | Maneja mapa, puntos GPS y comportamiento dinámico del Panel GPS. | Vigente |
| `panel_alertas.js` | JS asociado al Panel Alertas. Revisar si se sigue usando o si quedó de una versión anterior. | Revisar |

---

## Carpeta `static/dashboard/img/`

Contiene logos e imágenes usadas por el dashboard.

```txt
apps/dashboard/static/dashboard/img/
├── logo.png
├── logo2.png
├── zp.png
├── zp1.png
├── zp2.png
├── zp3.png
└── zp4.png
```

| Archivo | Descripción | Estado |
|---|---|---|
| `logo.png` | Imagen o logo usado en la interfaz. | Vigente / revisar uso |
| `logo2.png` | Imagen o logo alternativo. | Vigente / revisar uso |
| `zp.png` a `zp4.png` | Imágenes asociadas al dashboard o a Zonas Pagas. | Vigente / revisar uso |

---

## Carpeta `management/commands/`

Contiene comandos personalizados que se ejecutan con `python manage.py`.

```txt
apps/dashboard/management/commands/
├── actualizar_validadores.py
├── cargar_validadores_limpios.py
├── importar_ubicaciones_esperadas.py
├── importar_validadores_csv.py
├── importar_validadores_oracle.py
├── limpiar_historial_ubicacion_oracle.py
├── limpiar_registros_antiguos.py
├── limpiar_tablas_sqlite_antiguas.py
├── probar_oracle.py
└── registrar_estado_oracle.py
```

| Comando | Descripción | Estado |
|---|---|---|
| `probar_oracle.py` | Comando Django vigente para probar la conexión Oracle desde consola o desde acciones administrativas. Ejecuta `SELECT SYSDATE FROM dual` y registra el resultado en logs. | Vigente |
| `importar_ubicaciones_esperadas.py` | Importa ubicaciones esperadas desde archivo Excel hacia Oracle. | Vigente |
| `registrar_estado_oracle.py` | Registra estado o disponibilidad de Oracle en logs. | Vigente |
| `limpiar_historial_ubicacion_oracle.py` | Limpia historial antiguo de ubicaciones esperadas en Oracle. | Vigente |
| `limpiar_tablas_sqlite_antiguas.py` | Limpieza puntual de tablas antiguas en SQLite. | Uso puntual |
| `actualizar_validadores.py` | Flujo antiguo o pendiente de revisión. | Revisar |
| `cargar_validadores_limpios.py` | Flujo antiguo o pendiente de revisión. | Revisar |
| `importar_validadores_csv.py` | Flujo antiguo o pendiente de revisión. | Revisar |
| `importar_validadores_oracle.py` | Confirmar si sigue vigente o pertenece al flujo anterior. | Revisar |
| `limpiar_registros_antiguos.py` | Confirmar si sigue vigente o pertenece al flujo anterior. | Revisar |

---

## Carpeta `migrations/`

Contiene migraciones de Django para la base local SQLite.

```txt
apps/dashboard/migrations/
├── 0001_initial.py
├── 0002_logimportacion.py
├── 0003_estadovalidadorlimpio_estadovalidadorraw.py
├── 0004_alter_logimportacion_origen.py
├── 0005_remove_estadovalidadorlimpio_dashboard_e_estado__20839b_idx_and_more.py
├── 0006_ubicacionesperadavalidador.py
├── 0007_historialubicacionesperadavalidador.py
├── 0008_estadovalidadorlimpio_dashboard_e_amid_e28d3f_idx_and_more.py
├── 0009_estatuszp_alter_logimportacion_options_and_more.py
├── 0010_retira_modelos_sqlite_antiguos_solo_estado.py
└── __init__.py
```

Estas migraciones representan el historial de estructura de la base local Django. No se deben borrar sin revisar, porque permiten reconstruir o mantener la base local.

| Elemento | Descripción | Estado |
|---|---|---|
| Migraciones `0001` a `0010` | Cambios históricos en modelos Django. Algunas pertenecen al flujo anterior con SQLite. | Vigente / histórico |
| `__init__.py` | Indica que la carpeta es un paquete Python. | Vigente |

---

## Carpetas y archivos generados que no se deben versionar

Estas carpetas o archivos son generados automáticamente, corresponden al ambiente local o pueden contener información sensible.

```txt
venv/
__pycache__/
*.pyc
*.pyo
*.log
temp_uploads/
estructura_proyecto.txt
db.sqlite3
.env
medir_oracle.py
probar_oracle.py
```

Deben estar incluidos en `.gitignore`.

---

## Archivos que requieren revisión

| Archivo | Motivo |
|---|---|
| `alertas_bateria_utils.py` | Puede duplicar lógica de alertas de batería con Oracle. |
| `panel_alertas_mantencion.html` | Puede ser una versión antigua o temporal. Confirmar si se usa. |
| `actualizar_validadores.py` | Posible flujo antiguo SQLite. |
| `cargar_validadores_limpios.py` | Posible flujo antiguo SQLite. |
| `importar_validadores_csv.py` | Posible flujo antiguo. |
| `importar_validadores_oracle.py` | Confirmar si sigue vigente o si pertenece al flujo anterior. |
| `limpiar_registros_antiguos.py` | Confirmar si sigue vigente. |
| `panel_alertas.js` | Confirmar si todavía se usa en la versión actual del Panel Alertas. |
| `views.py` | Archivo funcional, pero podría ordenarse por secciones o separarse más adelante. |

---

## Relación entre capas del sistema

El flujo general del código se puede entender así:

```txt
URL → View → Service → Oracle → Contexto → Template → HTML/CSS/JS
```

Ejemplo Panel Baterías:

```txt
/baterias/
→ panel_baterias()
→ obtener_contexto_baterias()
→ Oracle: BATERIA_BLOQUE_30MIN + VW_ESTATUS_ZP_DJANGO
→ panel_baterias.html
→ panel_baterias.css + panel_baterias.js
```

Ejemplo Panel Alertas:

```txt
/alertas/
→ panel_alertas()
→ obtener_contexto_alertas()
→ Oracle: VW_ALERTA_VALIDADOR_ACTIVA
→ panel_alertas.html
→ panel_alertas.css
```

Ejemplo Panel GPS:

```txt
/gps/
→ panel_gps()
→ obtener_contexto_gps()
→ Oracle: datos GPS + ubicación esperada
→ panel_gps.html
→ panel_gps.css + panel_gps.js
```

---

## Resumen de archivos más importantes

Para entender y mantener el proyecto, los archivos principales son:

```txt
apps/dashboard/views.py
apps/dashboard/urls.py
apps/dashboard/context_processors.py
apps/dashboard/models.py
apps/dashboard/services/oracle_connection.py
apps/dashboard/services/baterias_service.py
apps/dashboard/services/gps_service.py
apps/dashboard/services/alertas_service.py
apps/dashboard/services/reglas_alertas_service.py
apps/dashboard/templates/dashboard/base_dashboard.html
apps/dashboard/templates/dashboard/panel_baterias.html
apps/dashboard/templates/dashboard/panel_gps.html
apps/dashboard/templates/dashboard/panel_alertas.html
apps/dashboard/templates/dashboard/panel_perfil.html
apps/dashboard/static/dashboard/css/
apps/dashboard/static/dashboard/js/
```

---

## Pendientes sugeridos

- Separar código vigente de código antiguo.
- Revisar comandos que pertenecen al flujo antiguo SQLite.
- Documentar tablas, vistas, procedures y jobs de Oracle.
- Unificar la lógica de alertas de batería entre Panel Baterías y Panel Alertas.
- Revisar si `panel_alertas_mantencion.html` sigue siendo necesario.
- Revisar si `panel_alertas.js` todavía se usa.
- Ordenar `views.py` por secciones o evaluar separación futura.
- Confirmar que `.env`, `db.sqlite3`, `venv/`, `__pycache__/` y archivos temporales estén ignorados por Git.

---

## Nota final

Este documento no busca modificar el proyecto, sino servir como mapa inicial para entenderlo. Antes de refactorizar o eliminar archivos, se recomienda marcar cada elemento como:

```txt
VIGENTE
ANTIGUO
REVISAR
NO TOCAR
```

De esta forma se puede ordenar el sistema sin romper funcionalidades que todavía estén en uso.
