# 01 — Visión general del Dashboard ZP

> Ver también: [arquitectura](02_arquitectura_sistema.md), [flujo Oracle–Django](03_flujo_completo_oracle_django.md), [operación](05_instalacion_operacion.md) y [datos](06_datos_e_integraciones.md).

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

## Estado de organización

- El flujo Oracle y sus objetos vigentes están documentados.
- La lógica de clasificación de alertas está centralizada en Oracle.
- Los SQL actuales, históricos y de diagnóstico están separados.
- Los archivos generados, resultados Oracle y secretos están excluidos de Git.

Como mantenimiento futuro queda revisar los comandos históricos de importación
SQLite antes de eliminarlos y separar secciones de `views.py` si continúa
creciendo.