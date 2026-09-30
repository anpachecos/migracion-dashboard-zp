# 10 — BKL-017: diagnóstico de pruebas de caracterización

> **Resumen del informe original.** Este documento condensa el informe técnico
> BKL-017. La fuente completa, con sus 8 tablas y 310 celdas de detalle, sigue
> en `docs/BKL-017_Diagnostico_Pruebas_Caracterizacion.docx` (no versionada).

| Dato | Definición |
| --- | --- |
| Fecha del diagnóstico | 10 de septiembre de 2026 |
| Entorno | PREPRODUCCIÓN |
| Objetivo | Congelar y proteger el comportamiento actual antes del refactor arquitectónico |
| Alcance | Diagnóstico y plan de implementación, en modo solo lectura |

## Conclusión principal

BKL-017 puede implementarse **sin refactorizar ni modificar la arquitectura
productiva**. Los servicios actuales permiten caracterizar el comportamiento
antes de tocarlo.

## Los tres problemas que identificó

1. Existían 32 pruebas, pero `manage.py test` no descubría ninguna.
2. Ejecutando los módulos explícitamente, corrían 31 pruebas de `tests.py`, y
   una fallaba porque esperaba `Sin estatus` y recibía otra cosa.
3. No había cobertura significativa para baterías, GPS, vistas, generación de
   Excel ni el flujo completo de importación.

## Estrategia de aislamiento de Oracle

El riesgo central: la suite no debe abrir nunca una conexión real a Oracle.

| Flujo | Acceso real ingenuo | Estrategia segura |
| --- | --- | --- |
| Baterías | Solo lectura | Patch de conexión o funciones de acceso |
| Importación | **Escribe** en Oracle | Nunca usar conexión real en la suite normal |
| Credenciales | Reales en `.env` | Patch obligatorio y settings de test sin credenciales |

## Estado actual, corregido a la fecha de este documento

El informe original quedó desactualizado en tres puntos. La realidad actual:

| Afirmación del informe | Realidad hoy |
| --- | --- |
| `manage.py test` descubre 0 pruebas | Descubre **490** |
| 31 pruebas en `apps/dashboard/tests.py` | `tests.py` ya no existe: se repartió en `test_alertas_service.py`, `test_reglas_alertas_service.py`, `test_horarios_zp_service.py` y `test_scheduler.py` |
| Estructura recomendada: archivos planos junto a la app | Se adoptó la contraria: los tests viven en el paquete `apps/dashboard/tests/` |
| Menciona `docs/como_crear_venv_txt` | Ese archivo se eliminó; su contenido está ahora en el documento 05 |

Comando vigente:

```powershell
.\venv\Scripts\python.exe manage.py test
```

**Falla pendiente.** `test_recalculo_segundo_plano_crea_thread_mock_sin_iniciarlo_real`
sigue errando porque alcanza el driver real `oracledb` sin mock. Es el incumplimiento
más claro del principio de aislamiento de este diagnóstico, y por lo tanto la
prioridad número uno para cerrar BKL-017.

## Riesgos

1. Credenciales Oracle reales presentes en `.env`.
2. El comando de importación escribe en Oracle: nunca debe ejecutarse dentro de
   la suite normal.
3. El error de la prueba de scheduler es exactamente el fallo que este
   diagnóstico quería evitar.

## Criterio de terminación

BKL-017 se considera cerrada cuando:

- `manage.py test` descubre y ejecuta toda la suite y queda completamente verde.
- Ninguna prueba normal abre una conexión Oracle real.
- Los contratos P0 de batería, GPS, importación, exportación y respuestas HTTP
  están cubiertos.
- Cero y ausencia quedan diferenciados explícitamente.
- El fallback de GPS, la referencia histórica vigente de laboratorio y el radio
  quedan congelados.
- La importación caracteriza vigencia, historial, ausentes y errores de Excel.
