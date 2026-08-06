# Mapa general del Dashboard ZP

## Objetivo

El Dashboard ZP permite revisar información operativa de validadores MK 2.0 mediante paneles de batería, GPS y alertas.

## Flujo general

Usuario → URL Django → View → Service Python → Oracle → Contexto → Template HTML → Navegador

## Paneles principales

| Panel | Objetivo | Archivo principal |
|---|---|---|
| Baterías | Revisar evolución de batería por AMID | `baterias_service.py`, `panel_baterias.html` |
| GPS | Revisar ubicación reportada y ubicación esperada | `gps_service.py`, `panel_gps.html` |
| Alertas | Mostrar validadores con prioridad crítica, alta, advertencia u OK | `alertas_service.py`, `panel_alertas.html` |
| Perfil | Administrar usuarios, reglas y procesos | `views.py`, `panel_perfil.html`, `reglas_alertas_service.py` |

## Capas del sistema

| Capa | Descripción |
|---|---|
| Oracle | Guarda y calcula datos operativos. |
| Django views | Recibe las solicitudes web. |
| Services Python | Consultan Oracle y preparan la información. |
| Templates HTML | Muestran la información. |
| CSS/JS | Controlan diseño y comportamiento visual. |
| SQLite | Mantiene usuarios, sesiones y logs propios de Django. |

## Pendientes de orden

- Separar código vigente de código antiguo.
- Documentar tablas y vistas Oracle.
- Unificar lógica de alertas de batería.
- Revisar comandos antiguos de importación SQLite.
- Limpiar archivos generados como `__pycache__` y revisar que `venv/` no se suba a Git.