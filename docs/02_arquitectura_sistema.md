# 02 — Arquitectura del sistema

## Resumen

Dashboard ZP es una aplicación monolítica Django con HTML renderizado en servidor y JavaScript de cliente. Separa sus datos en:

- **Oracle (`USR_LAB`)**: telemetría, batería, ubicaciones, alertas y reglas.
- **SQLite (`db.sqlite3`)**: usuarios, permisos, sesiones, migraciones y logs.

No expone una API pública. Recibe parámetros GET/POST y genera páginas HTML o archivos Excel.

## Componentes

| Componente | Responsabilidad |
|---|---|
| `config/` | Settings, rutas y entradas WSGI/ASGI. |
| `views.py` | Autorización, coordinación, render y exportaciones. |
| `services/` | SQL Oracle, transformaciones y lógica funcional. |
| `templates/`, `static/` | Presentación e interacción. |
| `management/commands/` | Importación, diagnóstico y mantenimiento. |
| `context_processors.py` | Estado común con caché local por proceso. |

```text
Navegador -> URL -> sesión Django -> view -> service
           -> pool python-oracledb -> Oracle
           -> contexto -> HTML o XLSX
```

Los paneles y exportaciones requieren login. Las acciones administrativas comprueban superusuario o grupo Django `Admin`.

## Flujos

### Baterías

`panel_baterias` delega en `obtener_contexto_baterias`. El servicio obtiene último estado, bloques de 30 minutos y resumen de alertas; luego construye tarjetas, tabla y gráficos. `/baterias/exportar/` entrega XLSX.

### GPS

`gps_service.py` consulta `VW_ESTATUS_ZP_DJANGO`, busca ubicación esperada vigente o histórica y calcula distancia y métricas. Si falta referencia usa el laboratorio definido en código. `panel_gps.js` muestra el mapa y `/gps/exportar/` entrega XLSX.

### Alertas

`alertas_service.py` consulta `VW_ALERTA_VALIDADOR_ACTIVA`, filtra y pagina en Oracle. Las prioridades son `CRITICA`, `ALTA`, `ADVERTENCIA` y `OK`. Los cambios de clasificación usan el wrapper rápido y los cambios de detección usan el cálculo completo.

### Perfil

Reúne datos del usuario, logs, carga de ubicaciones y reglas. Solo permite claves incluidas en `CLAVES_PERMITIDAS`. El recálculo puede ejecutarse en un hilo daemon y escribe `temp_uploads/alertas_recalculo.log`.

## Segundo plano

`APScheduler` solo se inicia con `DASHBOARD_SCHEDULER_ENABLED=True`; por defecto está apagado. Como vive dentro del proceso web, varios workers pueden duplicar jobs. Debe garantizarse una instancia única o usarse un scheduler externo.

## Límites

- Oracle se consulta con SQL directo; no es backend Django.
- `EstatusZP` es no administrado sobre `VW_ESTATUS_ZP_DJANGO`.
- Las exportaciones viven en `views.py` y pueden consumir recursos con rangos grandes.
- `LocMemCache` no se comparte entre procesos.
- La referencia/radio GPS del laboratorio están en `gps_service.py`.

