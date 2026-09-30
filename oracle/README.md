# Oracle del Dashboard ZP

Esta carpeta separa el estado vigente, los cambios preparados y los
diagnósticos.

## Estructura

```text
oracle/
├── current/
│   └── alertas_oracle_estado_actual.sql
├── pending/
│   └── bkl-002c/  # lease/solicitudes/jobs preparados; no desplegados
├── diagnostics/
│   ├── V009_VALIDAR__detalle_caidas_bateria.sql
│   └── TRX_001__validar_fuente_lectura.sql
└── notas/
    └── Queries_TRX_C2D_*.sql  # guias personales; no se publican
```

## Uso correcto

- `current/` es la referencia consolidada para comprender o reconstruir los
  objetos incorporados por este proyecto.
- `pending/` contiene cambios preparados que todavía deben ejecutarse y
  validarse en Oracle. Por ahora solo incluye `bkl-002c/` (recálculo durable de
  alertas, detrás de `ALERTAS_RECALCULO_DURABLE_ENABLED`).
- `diagnostics/` contiene consultas de inspección sin modificaciones.
- `notas/` contiene guías y consultas de trabajo personal. Son material de
  consulta, no scripts de despliegue: no se publican.
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