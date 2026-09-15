from apps.dashboard.repositories import ubicaciones_repository


def sincronizar_amids_ubicaciones_oracle():
    """
    Ejecuta la sincronización definida en Oracle y comprueba su resultado.

    Django no decide ubicaciones ni escribe las tablas: solamente invoca el
    mismo procedimiento utilizado por el job programado.
    """

    return ubicaciones_repository.sincronizar_amids_ubicaciones()
