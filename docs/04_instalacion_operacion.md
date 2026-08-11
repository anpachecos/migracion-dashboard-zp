# 04 — Instalación y operación

## Requisitos

- Python compatible con `requirements.txt`.
- Acceso de red a Oracle.
- Oracle Client si se usa modo Thick.
- Escritura sobre `db.sqlite3`, `temp_uploads/` y `staticfiles/`.

Dependencias principales: Django 6.0.5, python-oracledb 4.0.1, APScheduler 3.11.2, pandas 3.0.3 y openpyxl 3.1.5.

## Preparación en Windows

```powershell
py -m venv venv_pc
.\venv_pc\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Complete `.env` sin versionarlo.

## Configuración

| Variable | Uso |
|---|---|
| `SECRET_KEY` | Obligatoria y única en producción. |
| `DEBUG` | Debe ser `False` en producción. |
| `ALLOWED_HOSTS` | Hosts separados por coma. |
| `ORACLE_USER`, `ORACLE_PASSWORD` | Credenciales Oracle. |
| `ORACLE_HOST`, `ORACLE_PORT` | Listener; puerto por defecto 1521. |
| `ORACLE_SERVICE_NAME` | Service name Oracle. |
| `ORACLE_CLIENT_PATH` | Cliente para modo Thick, si aplica. |
| `DASHBOARD_SCHEDULER_ENABLED` | `False` por defecto; requiere instancia única. |

`.env.example` debe listar estas claves con valores vacíos o seguros.

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
| `/perfil/ejecutar-comando/` | Acciones administrativas. |
| `/baterias/exportar/`, `/gps/exportar/`, `/alertas/exportar/` | Exportaciones XLSX. |
| `/admin/` | Administración Django. |

## Comandos

| Comando | Estado | Uso |
|---|---|---|
| `probar_oracle` | Vigente | Prueba conexión y registra resultado. |
| `importar_ubicaciones_esperadas <xlsx>` | Vigente | Carga ubicaciones e historial. |
| `registrar_estado_oracle` | Vigente | Registra estado Oracle en SQLite. |
| `limpiar_historial_ubicacion_oracle` | Vigente | Aplica retención al historial. |
| `limpiar_tablas_sqlite_antiguas` | Excepcional/destructivo | Requiere confirmación explícita. |
| `actualizar_validadores`, `cargar_validadores_limpios`, `limpiar_registros_antiguos` | Deshabilitados | Flujo SQLite antiguo. |
| `importar_validadores_csv`, `importar_validadores_oracle` | Históricos | No usar sin revisión. |

Use `python manage.py <comando> --help` antes de operaciones de escritura o eliminación.

## Despliegue y diagnóstico

En producción: `DEBUG=False`, clave única, hosts restrictivos, `migrate`, `check --deploy`, pruebas, `collectstatic` y servidor WSGI para `config.wsgi:application`. Proteja `.env` y SQLite con ACL.

- Fallo Oracle: revisar variables/red/service name y ejecutar `probar_oracle`.
- SQLite bloqueado: revisar concurrencia y jobs duplicados.
- Sin estilos: ejecutar `collectstatic` y publicar `STATIC_ROOT`.
- Alertas antiguas: revisar resumen, reglas y `PRC_UPD_ALERTAS_VAL`.

