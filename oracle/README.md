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
├── pending/
│   └── V010__indice_estatus_zp_amid_fecha_registro.sql
└── diagnostics/
    ├── 00_auditoria_previa.sql
    ├── 01_auditoria_rendimiento_etapa3.sql
    ├── V009_VALIDAR__detalle_caidas_bateria.sql
    └── V010_VALIDAR__indice_gps_fecha_registro.sql
```

## Uso correcto

- `current/` es la referencia consolidada para comprender o reconstruir los
  objetos incorporados por este proyecto.
- `history/` documenta lo que ya se ejecutó. No debe repetirse en el esquema
  actual.
- `pending/` contiene cambios preparados que todavía deben ejecutarse y
  validarse en Oracle.
- `diagnostics/` contiene consultas de inspección sin modificaciones.
- Los archivos `resultados_*.sql` son exportaciones locales y no se publican.

El baseline presupone que ya existen los objetos heredados, entre ellos
`ESTATUS_ZP`, `JOBS_STATUS_ZP`, `ALERTA_REGLA_PARAM`,
`ALERTA_VALIDADOR_RESUMEN`, `AMID_MAESTRO_ALERTAS` y
`PRC_UPD_ALERTAS_VAL`. No crea el sistema Oracle completo desde cero.

## V010 — índice temporal del historial GPS (pendiente)

El Panel GPS interpreta `FECHA_REGISTRO` como hora del bloque y `FECHA_HORA`
como hora informada por el validador. Si `FECHA_HORA` no cambia entre dos
bloques consecutivos, Django muestra el bloque como **Sin transmisión** y no
reutiliza sus coordenadas.

La consulta del período filtra por `(AMID, FECHA_REGISTRO)`. Para que siga
siendo escalable sobre `ESTATUS_ZP`, se debe ejecutar una vez
`pending/V010__indice_estatus_zp_amid_fecha_registro.sql`, idealmente fuera de
hora punta, y luego validar con
`diagnostics/V010_VALIDAR__indice_gps_fecha_registro.sql`. El script es
idempotente, no modifica datos y evita crear un índice si ya existe uno
compatible.

Una vez ejecutado y validado, V010 debe moverse de `pending/` a `history/`.

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