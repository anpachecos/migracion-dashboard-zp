# 02 — Arquitectura del sistema

## Resumen

Dashboard ZP es una aplicación monolítica Django con HTML renderizado en servidor y JavaScript de cliente. Separa sus datos en:

- **Oracle (`USR_LAB`)**: telemetría, batería, ubicaciones, alertas y reglas.
- **SQLite (`db.sqlite3`)**: usuarios, permisos, sesiones, migraciones, logs y preferencias personales.

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

`panel_baterias` delega en `obtener_contexto_baterias`. El servicio obtiene el
último estado, bloques de 30 minutos, resumen de alertas y eventos oficiales de
caída; luego construye tarjetas, tabla y gráficos. El filtro **Horario Zona
Paga** utiliza `horarios_zp_service.py` y afecta solo la presentación de la
tabla. `/baterias/exportar/` entrega XLSX.

### GPS

`gps_service.py` consulta `VW_ESTATUS_ZP_DJANGO`, ordena los bloques por
`FECHA_REGISTRO`, identifica si `FECHA_HORA` representa una nueva transmisión y
busca la ubicación esperada vigente o histórica aplicable a cada registro. La
distancia se calcula únicamente para coordenadas válidas distintas de `0,0`;
si falta una referencia se usa el laboratorio definido en código.

El mismo conjunto consultado alimenta métricas, mapa e historial. La tabla se
construye en el navegador al desplegarla, sin repetir la consulta Oracle.
`panel_gps.js` también maneja el filtro **Horario Zona Paga**, la navegación
mapa–historial y la selección de filas. `/gps/exportar/` entrega XLSX.

### Alertas

`alertas_service.py` consulta `VW_ALERTA_VALIDADOR_ACTIVA`, filtra y pagina en
Oracle. Las prioridades son `CRITICA`, `ALTA`, `ADVERTENCIA` y `OK`. Los cambios
de clasificación usan el wrapper rápido y los cambios de detección usan el
cálculo completo.

Las exclusiones del panel son personales: `preferencias_alertas_service.py`
guarda en SQLite los AMID y ubicaciones que cada usuario no quiere ver. Se
aplican como filtros enlazados en las consultas Oracle, sin alterar alertas ni
telemetría. El autocompletado consulta bajo demanda desde dos caracteres, con
debounce de 300 ms y hasta 15 sugerencias; no carga catálogos completos en el
HTML inicial.

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

