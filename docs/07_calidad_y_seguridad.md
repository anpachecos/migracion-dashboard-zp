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
| Baterías | AMID válido/inválido, bloques, eventos oficiales, Horario Zona Paga reversible y XLSX. |
| GPS | Transmisión válida, repetida, `0,0`, radio, cumplimiento, horario, historial, mapa y XLSX. |
| Alertas | Orden y filtros combinables por prioridad/GPS/batería/estatus; filtro parcial por ubicación sin orden; sincronización con tarjetas, restablecimiento completo, conservación al paginar, totales, detalle de caídas, exclusiones por usuario y XLSX completo sin filtros. |
| Reglas | Permiso, allowlist, valores, commit y recálculo. |
| Importación | Archivo válido/inválido, duplicados, rollback e historial. |
| Scheduler | Instancia única, reintentos y solapamiento. |

Las pruebas unitarias actuales ya cubren el intérprete de horarios para días
hábiles y sábado, además de verificar que GPS filtre cada registro por su fecha
y conserve los días sin horario. Aún falta automatizar la matriz completa de
estados GPS y cumplimiento.

## Prueba manual mínima del Panel GPS

1. Seleccionar un rango que contenga una coordenada válida dentro del radio,
   una válida fuera, una transmisión `0,0` y un bloque sin transmisión.
2. Confirmar que solo la coordenada válida fuera aumenta **Fuera del radio**.
3. Confirmar que `0,0` aparece en su categoría y reduce el cumplimiento.
4. Confirmar que **Sin transmisión** aparece en su categoría y no entra en el
   denominador del cumplimiento.
5. Abrir **Historial GPS del período** desde el mapa y desde su encabezado;
   ambos accesos deben mostrar las filas y desplazar la vista hasta el contenido.
6. Activar **Horario Zona Paga** y comprobar que el resumen, mapa e historial
   muestran el mismo subconjunto. Si hoy no tiene horario, el filtro debe quedar
   inactivo y no ocultar registros.

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

