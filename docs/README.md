# Documentación técnica — Dashboard ZP

Especificación vigente para desarrollo, soporte y operación.

## Índice

1. [Mapa general](01_mapa_general.md)
2. [Arquitectura y flujos](02_arquitectura.md)
3. [Mapa de archivos](03_mapa_archivos.md)
4. [Instalación y operación](04_instalacion_operacion.md)
5. [Datos e integraciones](05_datos_integraciones.md)
6. [Calidad y seguridad](06_calidad_seguridad.md)

El código y el esquema Oracle desplegado son la fuente de verdad. Si difieren de estos documentos, la documentación debe corregirse en el mismo cambio.

No se deben incorporar valores reales de `.env`, credenciales, direcciones internas ni datos de usuarios.

## Mantenimiento

- Documentar nuevas variables, rutas, comandos y dependencias Oracle.
- Marcar expresamente componentes históricos o deshabilitados.
- Validar cambios con `python manage.py check` y las pruebas.

