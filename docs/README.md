# Documentación técnica — Dashboard ZP

Esta carpeta contiene la especificación vigente para desarrollo, soporte,
operación y presentación del sistema.

## Orden de lectura recomendado

1. [Visión general](01_vision_general.md): qué problema resuelve el proyecto.
2. [Arquitectura del sistema](02_arquitectura_sistema.md): componentes y responsabilidades.
3. [Flujo completo Oracle–Django](03_flujo_completo_oracle_django.md): recorrido de los datos, jobs y alertas.
4. [Mapa del código](04_mapa_codigo.md): ubicación de cada pieza en el repositorio.
5. [Instalación y operación](05_instalacion_operacion.md): preparación y comandos habituales.
6. [Datos e integraciones](06_datos_e_integraciones.md): contratos y objetos externos.
7. [Calidad y seguridad](07_calidad_y_seguridad.md): validaciones y riesgos.
8. [Historial de optimización de alertas](08_historial_optimizacion_alertas.md): cambios ya aplicados y decisiones.

Para explicar el sistema en una presentación, comenzar por los documentos 01,
02 y 03. El documento 03 contiene el diagrama principal y las reglas del flujo.

## Fuente de verdad

- El código Django desplegado es la fuente de verdad del backend.
- `oracle/current/alertas_oracle_estado_actual.sql` es la referencia consolidada
  de los objetos Oracle incorporados durante la optimización.
- `oracle/history/` conserva scripts ya ejecutados y no debe utilizarse como
  punto de partida para una instalación nueva.
- Si el código, Oracle y estos documentos difieren, deben corregirse juntos en
  el mismo cambio.

## Qué se versiona en GitHub

Sí se versionan:

- documentación técnica;
- SQL de definición, migración y diagnóstico sin datos reales;
- `.env.example` sin secretos;
- código Django y pruebas.

No se versionan:

- `.env`;
- credenciales o llaves;
- resultados exportados de auditorías Oracle;
- logs y cargas temporales;
- bases SQLite locales;
- archivos con datos reales de usuarios, AMID o ubicaciones.

## Mantenimiento

Cuando cambie el flujo Oracle o Django:

1. actualizar el archivo de `oracle/current/`;
2. agregar una migración puntual al historial si fue necesario ejecutar SQL;
3. actualizar el documento 03;
4. resumir la decisión en el documento 08.