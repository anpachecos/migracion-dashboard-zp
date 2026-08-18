# 05 — Instalación y operación

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
| `/perfil/reglas-alertas/editor/` | Fragmento protegido del editor; se solicita sólo al desplegar la configuración. |
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

## Operación del editor de reglas

1. Al abrir `/perfil/`, la tarjeta **Configuración de alertas** permanece cerrada y no consulta `ALERTA_REGLA_PARAM`.
2. Al pulsar **Administrar reglas**, el navegador solicita una sola vez el editor a Django. Cerrar y volver a abrir la tarjeta no repite la consulta.
3. **Guardar para el próximo ciclo** actualiza y valida los valores en Oracle, pero no inicia un recálculo manual.
4. **Guardar y aplicar ahora** actualiza, valida e inicia en segundo plano `PRC_RECLASIFICAR_ALERTAS` o `PRC_RECALCULAR_ALERTAS_SEGURO`, según el tipo de las reglas modificadas.
5. Después del POST, Django vuelve al perfil con `?editor_reglas=1` para mostrar el resultado y recargar valores vigentes.

No se requieren migraciones Django ni scripts Oracle para el rediseño. Si se agrega una clave nueva a `CLAVES_PERMITIDAS`, también se debe documentar en `catalogo_reglas_alertas.py`; la validación al importar impide publicar un catálogo incompleto.

La interfaz no calcula una vista previa de AMID afectados. Para incorporar esa función de manera segura se necesita un procedimiento Oracle de simulación de solo lectura que acepte parámetros candidatos. No usar actualizaciones temporales con `ROLLBACK`, porque pueden bloquear la tabla global y el recálculo completo puede ser costoso.
## Despliegue y diagnóstico

En producción: `DEBUG=False`, clave única, hosts restrictivos, `migrate`, `check --deploy`, pruebas, `collectstatic` y servidor WSGI para `config.wsgi:application`. Proteja `.env` y SQLite con ACL.

- Fallo Oracle: revisar variables/red/service name y ejecutar `probar_oracle`.
- SQLite bloqueado: revisar concurrencia y jobs duplicados.
- Sin estilos: ejecutar `collectstatic` y publicar `STATIC_ROOT`.
- Alertas antiguas: revisar `JOB_UPD_ALERTAS_VAL`, `PRC_UPD_ALERTAS_VAL` y la
  fecha de cálculo de `ALERTA_BATERIA_CAIDA_EVENTO`.
- Detalle de caídas no disponible: validar los objetos de V009 y ejecutar el
  diagnóstico `oracle/diagnostics/V009_VALIDAR__detalle_caidas_bateria.sql`.

