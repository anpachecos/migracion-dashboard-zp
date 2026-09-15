import pandas as pd

from apps.dashboard.services.oracle_connection import obtener_conexion_oracle


COLUMNAS_ORACLE = [
    "AMID",
    "CODIGO_ZP_TS",
    "COD_PARADA1",
    "COD_PARADA2",
    "NOMBRE",
    "COMUNA",
    "UNIDAD",
    "OPERADOR",
    "UN",
    "UN_SECUNDARIA_1",
    "UN_SECUNDARIA_2",
    "UN_SECUNDARIA_3",
    "PST",
    "SERVICIOS",
    "TOTAL_VAL_VIGENTES_ZP",
    "HORARIO",
    "HORARIO_LABORAL_PM",
    "HORARIO_SABADO",
    "HORARIO_DOMINGO",
    "INICIO_OPERACION",
    "FIN_OPERACION",
    "PATENTE",
    "OP_ID",
    "BUS_ID",
    "SERIE_VALIDADOR",
    "IDDS",
    "NUM_VAL",
    "LATITUD_ESPERADA",
    "LONGITUD_ESPERADA",
    "X",
    "Y",
    "OPERATIVA",
    "CONTINGENCIA",
    "MIXTA",
    "RADIO_METROS",
    "TIPO",
    "RENOVADA",
    "VERSION_ZP",
    "ARCHIVO_ORIGEN",
    "FECHA_CARGA",
]

COLUMNAS_HISTORIAL = [
    "AMID",
    "CODIGO_ZP_TS",
    "COD_PARADA1",
    "COD_PARADA2",
    "NOMBRE",
    "COMUNA",
    "UNIDAD",
    "OPERADOR",
    "UN",
    "UN_SECUNDARIA_1",
    "UN_SECUNDARIA_2",
    "UN_SECUNDARIA_3",
    "PST",
    "SERVICIOS",
    "TOTAL_VAL_VIGENTES_ZP",
    "HORARIO",
    "HORARIO_LABORAL_PM",
    "HORARIO_SABADO",
    "HORARIO_DOMINGO",
    "INICIO_OPERACION",
    "FIN_OPERACION",
    "PATENTE",
    "OP_ID",
    "BUS_ID",
    "SERIE_VALIDADOR",
    "IDDS",
    "NUM_VAL",
    "LATITUD_ESPERADA",
    "LONGITUD_ESPERADA",
    "X",
    "Y",
    "OPERATIVA",
    "CONTINGENCIA",
    "MIXTA",
    "RADIO_METROS",
    "TIPO",
    "RENOVADA",
    "ORIGEN_UBICACION",
    "VERSION_ZP",
    "ARCHIVO_ORIGEN",
    "FECHA_INICIO_VIGENCIA",
    "FECHA_FIN_VIGENCIA",
    "FECHA_CARGA",
]


def persistir_importacion(
    filas_normalizadas,
    fecha_carga,
    archivo_origen,
    version_zp,
    referencia_laboratorio,
    estadisticas,
):
    amids_excel = set()

    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            for datos in filas_normalizadas:
                if datos is None:
                    estadisticas["omitidos"] += 1
                    continue

                amid = datos["AMID"]
                amids_excel.add(amid)

                existe = existe_vigente(cursor, amid)
                upsert_vigente(cursor, datos)

                if existe:
                    estadisticas["actualizados_vigente"] += 1
                else:
                    estadisticas["creados_vigente"] += 1

                resultado_historial = actualizar_historial(
                    cursor=cursor,
                    datos=datos,
                    fecha_carga=fecha_carga,
                )

                if resultado_historial == "nuevo":
                    estadisticas["nuevos_historial"] += 1
                elif resultado_historial == "cerrado_y_nuevo":
                    estadisticas["cerrados_historial"] += 1
                    estadisticas["nuevos_historial"] += 1
                elif resultado_historial == "sin_cambios":
                    estadisticas["sin_cambios_historial"] += 1

            (
                movidos_laboratorio,
                cerrados_por_ausencia,
                historicos_por_ausencia,
            ) = mover_ausentes_a_laboratorio(
                cursor=cursor,
                amids_excel=amids_excel,
                fecha_carga=fecha_carga,
                archivo_origen=archivo_origen,
                version_zp=version_zp,
                referencia_laboratorio=referencia_laboratorio,
            )

            estadisticas["movidos_laboratorio"] += movidos_laboratorio
            estadisticas["cerrados_historial"] += cerrados_por_ausencia
            estadisticas["nuevos_historial"] += historicos_por_ausencia

        conexion.commit()

    return estadisticas


def existe_vigente(cursor, amid):
    cursor.execute(
        """
            SELECT COUNT(*)
            FROM USR_LAB.UBICACION_ESPERADA_VALIDADOR
            WHERE AMID = :amid
            """,
        {"amid": amid},
    )

    return cursor.fetchone()[0] > 0


def upsert_vigente(cursor, datos):
    columnas_update = [
        columna for columna in COLUMNAS_ORACLE
        if columna != "AMID"
    ]

    set_sql = ", ".join([
        f"{columna} = :{columna}"
        for columna in columnas_update
    ])

    columnas_insert = ", ".join(COLUMNAS_ORACLE)
    valores_insert = ", ".join([
        f":{columna}" for columna in COLUMNAS_ORACLE
    ])

    sql = f"""
            MERGE INTO USR_LAB.UBICACION_ESPERADA_VALIDADOR destino
            USING (
                SELECT :AMID AS AMID FROM DUAL
            ) origen
            ON (destino.AMID = origen.AMID)
            WHEN MATCHED THEN
                UPDATE SET {set_sql}
            WHEN NOT MATCHED THEN
                INSERT ({columnas_insert})
                VALUES ({valores_insert})
        """

    parametros = {
        columna: datos.get(columna)
        for columna in COLUMNAS_ORACLE
    }

    cursor.execute(sql, parametros)


def actualizar_historial(cursor, datos, fecha_carga):
    historial_vigente = obtener_historial_vigente(cursor, datos["AMID"])

    if historial_vigente is None:
        crear_historial(cursor, datos, fecha_carga)
        return "nuevo"

    if historial_es_igual(historial_vigente, datos):
        return "sin_cambios"

    cursor.execute(
        """
            UPDATE USR_LAB.HISTORIAL_UBICACION_ESPERADA
            SET FECHA_FIN_VIGENCIA = :fecha_carga
            WHERE ID = :id
            """,
        {
            "fecha_carga": fecha_carga,
            "id": historial_vigente["ID"],
        },
    )

    crear_historial(cursor, datos, fecha_carga)

    return "cerrado_y_nuevo"


def obtener_historial_vigente(cursor, amid):
    cursor.execute(
        """
            SELECT
                ID,
                AMID,
                NOMBRE,
                SERIE_VALIDADOR,
                LATITUD_ESPERADA,
                LONGITUD_ESPERADA,
                RADIO_METROS,
                OPERATIVA,
                ORIGEN_UBICACION,
                VERSION_ZP
            FROM USR_LAB.HISTORIAL_UBICACION_ESPERADA
            WHERE AMID = :amid
              AND FECHA_FIN_VIGENCIA IS NULL
            ORDER BY FECHA_INICIO_VIGENCIA DESC
            """,
        {"amid": amid},
    )

    fila = cursor.fetchone()

    if not fila:
        return None

    columnas = [col[0] for col in cursor.description]
    return dict(zip(columnas, fila))


def crear_historial(cursor, datos, fecha_carga):
    datos_historial = {
        columna: datos.get(columna)
        for columna in COLUMNAS_HISTORIAL
    }

    datos_historial["FECHA_INICIO_VIGENCIA"] = fecha_carga
    datos_historial["FECHA_FIN_VIGENCIA"] = None

    columnas_insert = ", ".join(COLUMNAS_HISTORIAL)
    valores_insert = ", ".join([
        f":{columna}" for columna in COLUMNAS_HISTORIAL
    ])

    cursor.execute(
        f"""
            INSERT INTO USR_LAB.HISTORIAL_UBICACION_ESPERADA (
                {columnas_insert}
            )
            VALUES (
                {valores_insert}
            )
            """,
        datos_historial,
    )


def historial_es_igual(historial, datos):
    return (
        texto(historial.get("NOMBRE")) == texto(datos.get("NOMBRE"))
        and texto(historial.get("SERIE_VALIDADOR"))
        == texto(datos.get("SERIE_VALIDADOR"))
        and numero_igual(
            historial.get("LATITUD_ESPERADA"),
            datos.get("LATITUD_ESPERADA"),
        )
        and numero_igual(
            historial.get("LONGITUD_ESPERADA"),
            datos.get("LONGITUD_ESPERADA"),
        )
        and numero_igual(
            historial.get("RADIO_METROS"),
            datos.get("RADIO_METROS"),
        )
        and valor_entero(historial.get("OPERATIVA"))
        == valor_entero(datos.get("OPERATIVA"))
        and texto(historial.get("ORIGEN_UBICACION"))
        == texto(datos.get("ORIGEN_UBICACION"))
        and texto(historial.get("VERSION_ZP"))
        == texto(datos.get("VERSION_ZP"))
    )


def mover_ausentes_a_laboratorio(
    cursor,
    amids_excel,
    fecha_carga,
    archivo_origen,
    version_zp,
    referencia_laboratorio,
):
    movidos = 0
    cerrados_historial = 0
    nuevos_historial = 0

    cursor.execute(
        """
            SELECT
                maestro.AMID,
                vigente.SERIE_VALIDADOR
            FROM (
                SELECT DISTINCT
                    TRIM(CAST(AMID AS VARCHAR2(20))) AS AMID
                FROM USR_LAB.AMID_MAESTRO_ALERTAS
                WHERE ACTIVO = 1
            ) maestro
            LEFT JOIN USR_LAB.UBICACION_ESPERADA_VALIDADOR vigente
              ON vigente.AMID = maestro.AMID
            ORDER BY maestro.AMID
            """
    )

    filas_maestro = cursor.fetchall()
    columnas = [col[0] for col in cursor.description]

    for fila in filas_maestro:
        registro_maestro = dict(zip(columnas, fila))
        amid = str(registro_maestro["AMID"]).strip()

        if amid in amids_excel:
            continue

        datos_laboratorio = {
            columna: None
            for columna in COLUMNAS_ORACLE
        }

        datos_laboratorio.update(referencia_laboratorio)
        datos_laboratorio.update(
            {
                "AMID": amid,
                "SERIE_VALIDADOR": registro_maestro.get("SERIE_VALIDADOR"),
                "IDDS": amid,
                "VERSION_ZP": version_zp,
                "ARCHIVO_ORIGEN": archivo_origen,
                "FECHA_CARGA": fecha_carga,
            }
        )

        historial_vigente = obtener_historial_vigente(cursor, amid)

        ya_esta_en_laboratorio = (
            historial_vigente
            and texto(historial_vigente.get("NOMBRE"))
            == texto(referencia_laboratorio["NOMBRE"])
            and numero_igual(
                historial_vigente.get("LATITUD_ESPERADA"),
                referencia_laboratorio["LATITUD_ESPERADA"],
            )
            and numero_igual(
                historial_vigente.get("LONGITUD_ESPERADA"),
                referencia_laboratorio["LONGITUD_ESPERADA"],
            )
            and numero_igual(
                historial_vigente.get("RADIO_METROS"),
                referencia_laboratorio["RADIO_METROS"],
            )
            and valor_entero(historial_vigente.get("OPERATIVA")) == 0
        )

        if ya_esta_en_laboratorio:
            continue

        upsert_vigente(cursor, datos_laboratorio)
        movidos += 1

        if historial_vigente:
            cursor.execute(
                """
                    UPDATE USR_LAB.HISTORIAL_UBICACION_ESPERADA
                    SET FECHA_FIN_VIGENCIA = :fecha_carga
                    WHERE ID = :id
                    """,
                {
                    "fecha_carga": fecha_carga,
                    "id": historial_vigente["ID"],
                },
            )
            cerrados_historial += 1

        datos_historial = dict(datos_laboratorio)
        datos_historial["ORIGEN_UBICACION"] = "laboratorio_default"

        crear_historial(cursor, datos_historial, fecha_carga)
        nuevos_historial += 1

    return movidos, cerrados_historial, nuevos_historial


def sincronizar_amids_ubicaciones():
    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            ubicaciones_creadas_var = cursor.var(int)
            historiales_creados_var = cursor.var(int)

            cursor.callproc(
                "USR_LAB.PRC_SINC_UBIC_AMID",
                [ubicaciones_creadas_var, historiales_creados_var],
            )

            cursor.execute(
                """
                SELECT
                    (
                        SELECT COUNT(*)
                        FROM USR_LAB.AMID_MAESTRO_ALERTAS m
                        WHERE m.ACTIVO = 1
                          AND NOT EXISTS (
                              SELECT 1
                              FROM USR_LAB.UBICACION_ESPERADA_VALIDADOR u
                              WHERE TRIM(u.AMID) =
                                    TRIM(CAST(m.AMID AS VARCHAR2(20)))
                          )
                    ) AS sin_ubicacion,
                    (
                        SELECT COUNT(*)
                        FROM USR_LAB.AMID_MAESTRO_ALERTAS m
                        JOIN USR_LAB.UBICACION_ESPERADA_VALIDADOR u
                          ON TRIM(u.AMID) =
                             TRIM(CAST(m.AMID AS VARCHAR2(20)))
                        WHERE m.ACTIVO = 1
                          AND NOT EXISTS (
                              SELECT 1
                              FROM USR_LAB.HISTORIAL_UBICACION_ESPERADA h
                              WHERE TRIM(h.AMID) = TRIM(u.AMID)
                                AND h.FECHA_FIN_VIGENCIA IS NULL
                          )
                    ) AS sin_historial_abierto
                FROM dual
                """
            )
            fila_validacion = cursor.fetchone() or (0, 0)
            ubicaciones_creadas = int(
                ubicaciones_creadas_var.getvalue() or 0
            )
            historiales_creados = int(
                historiales_creados_var.getvalue() or 0
            )

    return {
        "ubicaciones_creadas": ubicaciones_creadas,
        "historiales_creados": historiales_creados,
        "sin_ubicacion": int(fila_validacion[0] or 0),
        "sin_historial_abierto": int(fila_validacion[1] or 0),
    }


def limpiar_historial(dias_retencion):
    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            filas_eliminadas_var = cursor.var(int)

            cursor.callproc(
                "USR_LAB.PRC_LIMPIAR_HIST_UBICACION",
                [
                    dias_retencion,
                    filas_eliminadas_var,
                ],
            )

            return filas_eliminadas_var.getvalue() or 0


def texto(valor):
    if valor is None:
        return ""

    if pd.isna(valor):
        return ""

    return str(valor).strip()


def valor_entero(valor):
    if valor is None or pd.isna(valor):
        return None

    try:
        return int(float(valor))
    except (ValueError, TypeError):
        return None


def numero_igual(valor_1, valor_2):
    if valor_1 is None and valor_2 is None:
        return True

    if valor_1 is None or valor_2 is None:
        return False

    try:
        return round(float(valor_1), 7) == round(float(valor_2), 7)
    except (ValueError, TypeError):
        return False
