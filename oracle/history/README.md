# Historial SQL aplicado

Estos archivos explican la evolución del esquema durante la optimización de
alertas:

- `V006__alertas_fase1_sin_perdida.sql`: vista activa y reclasificación rápida.
- `V007__gobierno_reglas_alertas.sql`: tipos, auditoría y validación.
- `V007_FIX__compilar_validacion_reglas.sql`: reparación integral para DBeaver.
- `V007_FIX_1__validar_reglas.sql`: compilación aislada del validador.
- `V007_FIX_2__wrapper_rapido.sql`: nombre compatible del wrapper rápido.
- `V007_FIX_3__wrapper_completo.sql`: wrapper del cálculo completo.

Todos ya fueron aplicados. Se conservan como evidencia y no deben ejecutarse de
nuevo sobre el esquema actual. La referencia vigente está en `../current/`.