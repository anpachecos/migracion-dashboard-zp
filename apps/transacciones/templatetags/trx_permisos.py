"""
Tags de plantilla de Transacciones.

Se registran aquí y no en un context processor a propósito: el sidebar vive
en el template base, que se renderiza en todas las páginas. Un context
processor evaluaría el permiso en cada request del sistema; este tag solo se
resuelve donde realmente se usa.
"""

from django import template

from apps.transacciones.permisos import usuario_puede_ver_transacciones

register = template.Library()


@register.simple_tag
def puede_ver_transacciones(user):
    """Permite ocultar enlaces a la sección para quien no tiene acceso."""

    return usuario_puede_ver_transacciones(user)
