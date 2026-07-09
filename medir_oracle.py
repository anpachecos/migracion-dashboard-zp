import os
import time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from apps.dashboard.services.oracle_connection import obtener_pool_oracle, inicializar_oracle_client


def medir_consulta(query, nombre):
    print(f"\n=== {nombre} ===")

    inicio_total = time.perf_counter()

    inicio_cliente = time.perf_counter()
    inicializar_oracle_client()
    print(f"Cliente Oracle inicializado en {time.perf_counter() - inicio_cliente:.3f}s")

    inicio_pool = time.perf_counter()
    pool = obtener_pool_oracle()
    print(f"Pool creado/adquirido en {time.perf_counter() - inicio_pool:.3f}s")

    inicio_conn = time.perf_counter()
    with pool.acquire() as conexion:
        print(f"Conexión adquirida en {time.perf_counter() - inicio_conn:.3f}s")

        inicio_cursor = time.perf_counter()
        with conexion.cursor() as cursor:
            cursor.execute(query)
            resultado = cursor.fetchone()
            print(f"Consulta ejecutada en {time.perf_counter() - inicio_cursor:.3f}s")
            print(f"Resultado: {resultado}")

    print(f"Tiempo total para {nombre}: {time.perf_counter() - inicio_total:.3f}s")


if __name__ == "__main__":
    consultas = [
        ("SELECT MAX(FECHA_HORA) FROM USR_LAB.VW_ESTATUS_ZP_DJANGO", "Ultimo dato recibido"),
        ("SELECT MAX(FECHA_CARGA) FROM USR_LAB.UBICACION_ESPERADA_VALIDADOR", "Ultima versión ZP"),
    ]

    for query, nombre in consultas:
        medir_consulta(query, nombre)
