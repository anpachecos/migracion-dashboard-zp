# 05 — Instalación y operación

## Requisitos

- Python compatible con `requirements.txt`.
- Acceso de red a Oracle.
- Oracle Client si se usa modo Thick.
- Escritura sobre `db.sqlite3`, `temp_uploads/` y `staticfiles/`.

Dependencias principales: Django 6.0.5, python-oracledb 4.0.1, APScheduler 3.11.2, pandas 3.0.3 y openpyxl 3.1.5.

## Almacenamiento

| Artefacto | Qué guarda | ¿Se puede borrar? |
|---|---|---|
| `db.sqlite3` | Base de datos `default` de Django: usuarios, sesiones, permisos y el panel `admin`. | **No.** Borrarla elimina los usuarios y el login deja de funcionar. |
| Base de datos Oracle | Todo el dato de negocio. Se accede por conexión cruda con `python-oracledb`, no por el ORM de Django. | No aplica. |
| `temp_uploads/` | Archivos subidos mientras se procesan. | Sí, se limpia por sí sola. |
| `staticfiles/` | Salida de `collectstatic`. | Sí, se regenera. |

Que el proyecto use Oracle **no** vuelve a `db.sqlite3` un residuo de una era
anterior: Django lo necesita para autenticación y permisos. Está declarado en
`config/settings.py` y no se versiona porque contiene datos de usuarios.

## Preparación en Windows

```powershell
py -m venv venv_pc
.\venv_pc\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

El nombre del entorno es libre: `venv_pc` es el de la documentación, pero
`venv` funciona igual y ambos están contemplados en `.gitignore`.

Complete `.env` sin versionarlo.

Genere una `SECRET_KEY` diferente para cada entorno con:

```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copie el resultado únicamente al `.env` privado del entorno correspondiente.
No suba ese archivo ni reutilice la misma clave entre desarrollo, PRE y
producción. Si `SECRET_KEY` falta, está vacía o contiene solo espacios, Django
no inicia.

Verifique que el entorno quedó completo antes de seguir:

```powershell
python manage.py check
```

Debe responder `System check identified no issues (0 silenced)`. Si reporta
problemas, no avance: la configuración de este proyecto es *fail-closed* y
Django no arranca con valores faltantes.

## Configuración

| Variable | Uso |
|---|---|
| `SECRET_KEY` | Obligatoria y distinta en cada entorno. |
| `DEBUG` | `False` en producción; desarrollo/PRE puede habilitarlo solo explícitamente. |
| `ALLOWED_HOSTS` | Hosts separados por coma. |
| `ORACLE_USER`, `ORACLE_PASSWORD` | Credenciales Oracle. |
| `ORACLE_HOST`, `ORACLE_PORT` | Listener; puerto por defecto 1521. |
| `ORACLE_SERVICE_NAME` | Service name Oracle. |
| `ORACLE_CLIENT_PATH` | Cliente para modo Thick, si aplica. |
| `DASHBOARD_SCHEDULER_ENABLED` | `False` por defecto; requiere instancia única. |
| `TRX_GRUPOS_PERMITIDOS` | Grupos de Django con acceso al módulo de transacciones. Vaciarlo deja la sección solo para superusuarios. |

`.env.example` debe listar estas claves con valores vacíos o seguros.
`DEBUG` acepta `true`, `1`, `yes`, `on`, `false`, `0`, `no` y `off`, sin
distinguir mayúsculas/minúsculas y tolerando espacios externos. Si falta,
queda en `False`; cualquier otro valor impide el arranque.

## Inicialización

```powershell
python manage.py migrate
python manage.py check
python manage.py test
python manage.py probar_oracle
python manage.py createsuperuser
python manage.py runserver
```

## Rutas

| Ruta | Uso |
|---|---|
| `/login/`, `/logout/` | Sesión. |
| `/`, `/baterias/` | Baterías. |
| `/gps/`, `/alertas/`, `/perfil/` | Paneles GPS, alertas y perfil. |
| `/alertas/buscar-exclusiones/` | Sugerencias JSON acotadas para AMID y ubicaciones; requiere login. |
| `/alertas/caidas-bateria/` | Detalle JSON de eventos oficiales de caída; se consulta al desplegar una alerta. |
| `/perfil/reglas-alertas/editor/` | Fragmento protegido del editor; se solicita sólo al desplegar la configuración. |
| `/perfil/ejecutar-comando/` | Acciones administrativas. |
| `/baterias/exportar/`, `/gps/exportar/` | Exportaciones XLSX vigentes. |
| `/alertas/exportar/` | Ruta conservada, pero la exportación está deshabilitada en el flujo actual. |
| `/transacciones/`, `/transacciones/informe-interno/`, `/transacciones/mayor-15/`, `/transacciones/rezagadas/` | Módulo de transacciones. Requieren sesión **y** ser superusuario o miembro de un grupo de `TRX_GRUPOS_PERMITIDOS`; en caso contrario devuelven `403`. |
| `/admin/` | Administración Django. |

## Comandos

| Comando | Estado | Uso |
|---|---|---|
| `probar_oracle` | Vigente | Prueba conexión y registra resultado. |
| `importar_ubicaciones_esperadas <xlsx>` | Vigente | Carga ubicaciones e historial. |
| `registrar_estado_oracle` | Vigente | Registra estado Oracle en SQLite. |
| `limpiar_historial_ubicacion_oracle` | Vigente | Aplica retención al historial. |
| `limpiar_tablas_sqlite_antiguas` | Deshabilitado | Era un `VACUUM` destructivo sobre `db.sqlite3`; quedó inerte porque esa base es la `default` de Django. |
| `actualizar_validadores`, `cargar_validadores_limpios`, `limpiar_registros_antiguos` | Retirados (BKL-002C) | No hacían nada (imprimían un aviso) y su pertenencia al flujo SQLite antiguo estaba confirmada. |

Los comandos históricos `importar_validadores_csv` e
`importar_validadores_oracle` fueron retirados en BKL-015 porque dependían de
modelos SQLite eliminados y no pertenecían a la operación vigente.

Use `python manage.py <comando> --help` antes de operaciones de escritura o eliminación.

## Operación del editor de reglas

1. Al abrir `/perfil/`, la tarjeta **Configuración de alertas** permanece cerrada y no consulta `ALERTA_REGLA_PARAM`.
2. Al pulsar **Administrar reglas**, el navegador solicita una sola vez el editor a Django. Cerrar y volver a abrir la tarjeta no repite la consulta.
3. **Guardar para el próximo ciclo** actualiza y valida los valores en Oracle, pero no inicia un recálculo manual.
4. **Guardar y aplicar ahora** actualiza, valida e inicia en segundo plano `PRC_RECLASIFICAR_ALERTAS` o `PRC_RECALCULAR_ALERTAS_SEGURO`, según el tipo de las reglas modificadas.
5. Después del POST, Django vuelve al perfil con `?editor_reglas=1` para mostrar el resultado y recargar valores vigentes.

No se requieren migraciones Django ni scripts Oracle para el rediseño. Si se agrega una clave nueva a `CLAVES_PERMITIDAS`, también se debe documentar en `catalogo_reglas_alertas.py`; la validación al importar impide publicar un catálogo incompleto.

La interfaz no calcula una vista previa de AMID afectados. Para incorporar esa función de manera segura se necesita un procedimiento Oracle de simulación de solo lectura que acepte parámetros candidatos. No usar actualizaciones temporales con `ROLLBACK`, porque pueden bloquear la tabla global y el recálculo completo puede ser costoso.

## Operación de preferencias de alertas

- La tarjeta de preferencias se carga cerrada y muestra el total de exclusiones.
- El buscador comienza con dos caracteres, espera 300 ms y devuelve hasta 15
  sugerencias; no se deben reemplazar estos límites por una precarga completa.
- **Guardar preferencias** reemplaza atómicamente en SQLite las exclusiones del
  usuario. **Restablecer preferencias** deja ambas listas vacías.
- Las exclusiones se aplican a tarjetas, tabla, filtros y paginación del usuario,
  pero no actualizan objetos Oracle.
- Si cambian los modelos `AlertaAmidExcluido` o `AlertaUbicacionExcluida`, sí se
  requiere `makemigrations` y `migrate`. Los cambios visuales no los requieren.

## Despliegue y diagnóstico

En producción: `DEBUG=False`, clave única, hosts restrictivos, `migrate`, `check --deploy`, pruebas, `collectstatic` y servidor WSGI para `config.wsgi:application`. Proteja `.env` y SQLite con ACL.

- Fallo Oracle: revisar variables/red/service name y ejecutar `probar_oracle`.
- SQLite bloqueado: revisar concurrencia y jobs duplicados.
- Sin estilos: ejecutar `collectstatic` y publicar `STATIC_ROOT`.
- Mensaje APScheduler `run time ... was missed` para `registrar_estado_oracle_job`: el job tolera hasta 60 segundos de retraso y combina ejecuciones pendientes mediante `misfire_grace_time=60` y `coalesce=True`.
- Alertas antiguas: revisar `JOB_UPD_ALERTAS_VAL`, `PRC_UPD_ALERTAS_VAL` y la
  fecha de cálculo de `ALERTA_BATERIA_CAIDA_EVENTO`.
- Detalle de caídas no disponible: validar los objetos de V009 y ejecutar el
  diagnóstico `oracle/diagnostics/V009_VALIDAR__detalle_caidas_bateria.sql`.

