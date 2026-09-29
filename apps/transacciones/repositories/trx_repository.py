"""
Acceso de solo lectura a la fuente de transacciones C2D.

Reglas de este modulo:
- unica responsabilidad: SQL Oracle y estructura de datos simple;
- ninguna regla funcional, ninguna clasificacion, ningun HTML;
- bind variables siempre, nunca concatenar valores del usuario;
- nunca `SELECT *`;
- compatible con Oracle 11g (ROW_NUMBER + ROWNUM, nunca FETCH FIRST);
- no crea, altera ni modifica ningun objeto Oracle.

TODO(refactor): `obtener_conexion_oracle` sigue viviendo en
`apps/dashboard/services/oracle_connection.py` porque hay una
refactorizacion en curso. Cuando exista un modulo compartido de conexion,
esta importacion debe cambiar y solo esa.
"""

from apps.dashboard.services.oracle_connection import obtener_conexion_oracle

# Objeto consumido, no administrado. No se debe modificar ni redefinir.
ORIGEN_TRX = "DBPTE.TRANSACCION_FLUJO_VC2D_FISC@CLEAMTT3PRODG"

# Joins de contexto ya demostrados en Queries_TRX_C2D_guia_Antonia_V2.sql.
# Son LEFT JOIN a proposito: la guia usa INNER JOIN y descarta las TRX sin
# entidad o sin sitio, lo que romperia el universo del Informe Interno.
SQL_DESDE_TRX = f"""
    FROM {ORIGEN_TRX} TR
    LEFT JOIN DBCLEARING.ENTIDAD@CLEAMTT3PRODG EN
           ON EN.ENT_NIDENTIDAD = TR.TVF_NIDENTIDADOT
    LEFT JOIN DBCLEARING.SITIO@CLEAMTT3PRODG SIT
           ON SIT.SIT_NIDSITIO = TR.TVF_NIDSITIO
"""

# TVF_SFECTRANSACCION es VARCHAR2; se convierte en Oracle con el formato que
# ya se validó en la guia de Roxana. Si el dato viene con otro formato Oracle
# responde ORA-01861: por eso existe TRX_001__validar_fuente_lectura.sql.
EXPRESION_FEC_TRX = "TO_DATE(TR.TVF_SFECTRANSACCION, 'YYYY/MM/DD HH24:MI:SS')"
EXPRESION_FEC_BD = "TR.TVF_DFECREGISTRO"

# (expresion, alias). El alias es la clave con la que sale la fila.
EXPRESIONES_TRX = (
    ("TR.TVF_NIDCONTEXTOPTE", "NID_CONTEXTO_OPTE"),
    ("TR.TVF_SNUMABTC2D", "NUM_ABT"),
    (EXPRESION_FEC_TRX, "FEC_TRX"),
    (EXPRESION_FEC_BD, "FEC_BD"),
    ("TR.TVF_NIDTERMINAL", "NID_TERMINAL"),
    ("TR.TVF_NIDAS", "AMID"),
    ("TR.TVF_NIDCONTEXTOSWITCH", "NID_CONTEXTO_SWITCH"),
    ("TR.TVF_NIDSITIO", "NID_SITIO"),
    ("SIT.SIT_SNOMSITIO", "NOMBRE_SITIO"),
    ("TR.TVF_NIDENTIDADOT", "NID_ENTIDAD_OT"),
    ("EN.ENT_SNOMENTIDAD", "NOMBRE_ENTIDAD"),
    ("TR.TVF_SCODTIPOTRANSACCION", "COD_TIPO_TRANSACCION"),
    ("TR.TVF_NMODO", "N_MODO"),
    ("TR.TVF_SCODPROCESO", "COD_PROCESO"),
    ("TR.TVF_SESTADOENVIO", "ESTADO_ENVIO"),
)

COLUMNAS_TRX = tuple(alias for _, alias in EXPRESIONES_TRX)

EXPRESION_POR_ORIGEN = {
    "trx": EXPRESION_FEC_TRX,
    "bd": EXPRESION_FEC_BD,
}

COLUMNA_ORDEN_POR_ORIGEN = {
    "trx": "FEC_TRX",
    "bd": "FEC_BD",
}

ORIGENES_VALIDOS = tuple(EXPRESION_POR_ORIGEN)


def seleccionar_columnas():
    """
    Proyeccion explicita del nivel mas interno. Nunca se usa `SELECT *`.

    Cada columna se expone con un alias estable, porque ese alias es la clave con
    la que el service lee el diccionario y la que reutiliza la paginacion.
    """

    return ",\n                ".join(
        f"{expresion} AS {alias}" for expresion, alias in EXPRESIONES_TRX
    )


def seleccionar_columnas_derivadas():
    """
    Columnas del nivel mas externo de la paginacion.

    En ese ambito solo existen los alias del nivel interno, nunca `TR.*` ni las
    expresiones originales. Por eso se listan los alias y no las expresiones.
    """

    return ",\n            ".join(COLUMNAS_TRX)


def armar_filtros_trx(
    fecha_desde,
    fecha_hasta,
    amid_minimo,
    amid=None,
    nidsitio=None,
    nmodo=None,
    origen="trx",
):
    """
    Construye el WHERE compartido por el conteo y el detalle.

    `fecha_desde` y `fecha_hasta` son obligatorios y acotan el rango. El rango
    se aplica sobre la columna del origen elegido y se agrega un limite
    inferior indexable sobre la otra columna, sin techo superior para no
    descartar rezagadas de dias anteriores.

    `amid_minimo` es obligatorio a proposito: es el piso del universo y su unica
    fuente es `settings.TRX_AMID_MINIMO`. Un default aqui seria una segunda
    copia de ese valor, que es justo lo que se quiere evitar.

    Devuelve (segmentos_where, binds).
    """

    if origen not in EXPRESION_POR_ORIGEN:
        raise ValueError(f"Origen de fecha no valido: {origen}")

    columna_rango = EXPRESION_POR_ORIGEN[origen]

    filtros = [
        f"{columna_rango} >= :fecha_desde",
        f"{columna_rango} < :fecha_hasta",
    ]

    params = {
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "amid_minimo": int(amid_minimo),
    }

    if origen == "trx":
        # Implicito (FEC_BD >= FEC_TRX >= :fecha_desde) pero se declara para
        # que Oracle pueda usar el indice de TVF_DFECREGISTRO.
        filtros.append("TR.TVF_DFECREGISTRO >= :fecha_desde")
    else:
        # Implicito (FEC_TRX <= FEC_BD < :fecha_hasta) y sin techo superior.
        filtros.append(f"{EXPRESION_FEC_TRX} < :fecha_hasta")

    filtros.append("TR.TVF_NIDAS > :amid_minimo")

    if amid:
        filtros.append("TR.TVF_NIDAS = :amid")
        params["amid"] = int(amid)

    if nidsitio:
        filtros.append("TR.TVF_NIDSITIO = :nidsitio")
        params["nidsitio"] = int(nidsitio)

    if nmodo:
        filtros.append("TR.TVF_NMODO = :nmodo")
        params["nmodo"] = int(nmodo)

    return filtros, params


def columna_orden_trx(origen):
    """Columna por la que se ordena la paginacion, segun el origen elegido."""

    if origen not in COLUMNA_ORDEN_POR_ORIGEN:
        raise ValueError(f"Origen de fecha no valido: {origen}")

    return COLUMNA_ORDEN_POR_ORIGEN[origen]


def construir_where(filtros):
    if not filtros:
        return ""
    return "WHERE " + "\n          AND ".join(filtros)


def contar_trx_base(fecha_desde, fecha_hasta, **filtros):
    """
    Total de TRX del rango con exactamente los mismos filtros del detalle.

    El detalle y el conteo comparten `armar_filtros_trx`, por lo que no pueden
    divergir. Es la unica forma de garantizarlo con SQL parametrizado.
    """

    segmentos, params = armar_filtros_trx(fecha_desde, fecha_hasta, **filtros)

    query = f"""
        SELECT COUNT(*)
        {SQL_DESDE_TRX}
        {construir_where(segmentos)}
    """

    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(query, params)
            fila = cursor.fetchone()

    return int(fila[0]) if fila and fila[0] is not None else 0


def obtener_trx_base(fecha_desde, fecha_hasta, limite=200, offset=0, **filtros):
    """
    Pagina de TRX del rango, ordenada por la fecha del origen elegido.

    `fecha_hasta` es exclusivo. La paginacion usa ROW_NUMBER sobre la
    subconsulta, que es el patron ya usado en el dashboard y funciona en
    Oracle 11g. Nunca se hace fetchall sin limite.
    """

    if limite <= 0:
        raise ValueError("El limite debe ser mayor que cero.")

    segmentos, params = armar_filtros_trx(fecha_desde, fecha_hasta, **filtros)
    columna_orden = columna_orden_trx(filtros.get("origen", "trx"))

    params["limite"] = int(limite)
    params["offset"] = int(offset)

    query = f"""
        SELECT
            {seleccionar_columnas_derivadas()}
        FROM (
            SELECT
                {seleccionar_columnas()},
                ROW_NUMBER() OVER (
                    ORDER BY {columna_orden} ASC, NID_CONTEXTO_OPTE ASC
                ) AS RN
            FROM (
                SELECT
                    {seleccionar_columnas()}
                {SQL_DESDE_TRX}
                {construir_where(segmentos)}
            ) q
        )
        WHERE RN BETWEEN :offset + 1 AND :offset + :limite
    """

    with obtener_conexion_oracle() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(query, params)
            columnas = [col[0].lower() for col in cursor.description if col and col[0]]
            return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
