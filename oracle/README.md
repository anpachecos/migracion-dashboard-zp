# Oracle del Dashboard ZP

Esta carpeta separa el estado vigente, el historial de cambios y los
diagnósticos.

## Estructura

```text
oracle/
├── current/
│   └── alertas_oracle_estado_actual.sql
├── history/
│   ├── V006__...
│   ├── V007__...
│   ├── V007_FIX_...
│   └── V009__detalle_caidas_bateria_fuente_unica.sql
└── diagnostics/
    ├── 00_auditoria_previa.sql
    ├── 01_auditoria_rendimiento_etapa3.sql
    └── V009_VALIDAR__detalle_caidas_bateria.sql
```

## Uso correcto

- `current/` es la referencia consolidada para comprender o reconstruir los
  objetos incorporados por este proyecto.
- `history/` documenta lo que ya se ejecutó. No debe repetirse en el esquema
  actual.
- `diagnostics/` contiene consultas de inspección sin modificaciones.
- Los archivos `resultados_*.sql` son exportaciones locales y no se publican.

El baseline presupone que ya existen los objetos heredados, entre ellos
`ESTATUS_ZP`, `JOBS_STATUS_ZP`, `ALERTA_REGLA_PARAM`,
`ALERTA_VALIDADOR_RESUMEN`, `AMID_MAESTRO_ALERTAS` y
`PRC_UPD_ALERTAS_VAL`. No crea el sistema Oracle completo desde cero.

## V009 — detalle de caídas

V009 se ejecuta una sola vez. Crea `ALERTA_BATERIA_CAIDA_EVENTO`, crea
`PRC_REFRESCAR_CAIDAS_BAT` y actualiza `PRC_UPD_ALERTAS_VAL`. A partir de ese
momento, el job completo existente refresca automáticamente el detalle cada 30
minutos. El procedimiento reemplaza la tabla por la ventana vigente de 14 días,
por lo que no existe un job separado de limpieza.

Después de ejecutarla se debe usar el diagnóstico
`V009_VALIDAR__detalle_caidas_bateria.sql`.

## Antes de eliminar tablas de respaldo

No se deben borrar solo por su nombre. Primero se necesita la lista exacta y se
debe comprobar que ningún objeto vigente las use:

```sql
SELECT NAME, TYPE, REFERENCED_NAME, REFERENCED_TYPE
FROM USER_DEPENDENCIES
WHERE REFERENCED_NAME IN ('NOMBRE_BACKUP_1', 'NOMBRE_BACKUP_2')
ORDER BY REFERENCED_NAME, NAME;
```

También se debe conservar un export DDL o un respaldo recuperable. Ninguno de
los scripts de esta carpeta elimina tablas de respaldo.

## GitHub

Se publican definiciones y diagnósticos sin resultados. No se publican datos,
credenciales, exports de producción ni database links con contraseñas.