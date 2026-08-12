# 07 — Calidad y seguridad

## Validación mínima

```powershell
python manage.py check
python manage.py test
```

En producción, añadir `python manage.py check --deploy`. Los cambios Oracle requieren pruebas controladas.

## Regresión

| Área | Verificación |
|---|---|
| Rutas | Login, permisos, HTTP y errores. |
| Baterías | AMID válido/inválido, bloques, resumen y XLSX. |
| GPS | Coordenadas válidas/cero, referencia/fallback y XLSX. |
| Alertas | Prioridades, filtros, paginación, totales y XLSX. |
| Reglas | Permiso, allowlist, valores, commit y recálculo. |
| Importación | Archivo válido/inválido, duplicados, rollback e historial. |
| Scheduler | Instancia única, reintentos y solapamiento. |

## Seguridad

- No versionar `.env`, `db.sqlite3`, cargas ni logs sensibles.
- Usar `DEBUG=False`, clave aleatoria y hosts restrictivos.
- Aplicar mínimos privilegios Oracle, CSRF y autorización del lado servidor.
- Validar tamaño, extensión y contenido de Excel.
- Usar parámetros SQL enlazados y allowlists.
- Tratar exportaciones como telemetría protegida.

## Riesgos conocidos

| Riesgo | Mitigación |
|---|---|
| Scheduler con varios workers | Instancia única o scheduler externo. |
| SQLite concurrente | Reducir concurrencia o migrar a motor servidor. |
| DDL Oracle fuera del repo | Versionar scripts y contrato. |
| Exportaciones en la request | Limitar rangos o procesar asíncronamente. |
| Constantes GPS en código | Mover a configuración validada. |
| Caché local | Usar caché compartida si se requiere consistencia global. |
| `views.py` concentrado | Extraer exportaciones y formularios. |

Una funcionalidad está terminada cuando valida entradas/permisos, maneja fallas sin filtrar secretos, incluye pruebas, actualiza `docs/` y pasa los checks.

