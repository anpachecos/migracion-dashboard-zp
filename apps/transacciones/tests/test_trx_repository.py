"""
Pruebas del repositorio de solo lectura de la fuente TRX.

No se abre ninguna conexión a Oracle. Aquí se verifica lo que sí se puede
probar sin base de datos: que el SQL se arma con binds, que nunca selecciona
todas las columnas, que el conteo y el detalle comparten exactamente el mismo
WHERE, y que no aparece sintaxis prohibida en Oracle 11g.
"""

import datetime
import re
from unittest import mock

from django.test import SimpleTestCase

from apps.transacciones.repositories import trx_repository


class SeleccionDeColumnasTests(SimpleTestCase):
    def test_la_proyeccion_nunca_usa_asterisco(self):
        with self.subTest(nivel="interno"):
            self.assertNotIn("*", trx_repository.seleccionar_columnas())

        with self.subTest(nivel="externo"):
            self.assertNotIn("*", trx_repository.seleccionar_columnas_derivadas())

    def test_cada_expresion_tiene_alias_estable(self):
        for expresion, alias in trx_repository.EXPRESIONES_TRX:
            with self.subTest(alias=alias):
                self.assertRegex(alias, r"^[A-Z][A-Z0-9_]*$")
                self.assertIn(f"AS {alias}", trx_repository.seleccionar_columnas())

    def test_la_proyeccion_externa_usa_alias_y_no_expresiones(self):
        externa = trx_repository.seleccionar_columnas_derivadas()

        for alias in trx_repository.COLUMNAS_TRX:
            self.assertIn(alias, externa)

        self.assertNotIn("TR.", externa)
        self.assertNotIn("TO_DATE(", externa)

    def test_los_alias_no_se_repiten(self):
        self.assertEqual(
            len(trx_repository.COLUMNAS_TRX),
            len(set(trx_repository.COLUMNAS_TRX)),
        )


class FiltrosTests(SimpleTestCase):
    fecha_desde = datetime.date(2026, 8, 27)
    fecha_hasta = datetime.date(2026, 8, 28)
    # El repositorio exige el piso del universo: no tiene default proprio para
    # no duplicar el valor de settings.TRX_AMID_MINIMO.
    amid_minimo = 7_500_000

    def test_filtros_obligatorios_son_binds(self):
        segmentos, params = trx_repository.armar_filtros_trx(
            self.fecha_desde,
            self.fecha_hasta,
            self.amid_minimo,
        )

        where = " ".join(segmentos)

        self.assertIn(":fecha_desde", where)
        self.assertIn(":fecha_hasta", where)
        self.assertEqual(params["fecha_desde"], self.fecha_desde)
        self.assertEqual(params["fecha_hasta"], self.fecha_hasta)

    def test_el_piso_del_universo_es_obligatorio(self):
        with self.assertRaises(TypeError):
            trx_repository.armar_filtros_trx(
                self.fecha_desde,
                self.fecha_hasta,
            )

    def test_universo_zp_usa_comparacion_estricta_sobre_el_minimo(self):
        segmentos, params = trx_repository.armar_filtros_trx(
            self.fecha_desde,
            self.fecha_hasta,
            amid_minimo=self.amid_minimo,
        )

        where = " ".join(segmentos)

        self.assertIn("TR.TVF_NIDAS > :amid_minimo", where)
        self.assertEqual(params["amid_minimo"], self.amid_minimo)

    def test_rango_por_defecto_es_dia_trx(self):
        segmentos, _ = trx_repository.armar_filtros_trx(
            self.fecha_desde,
            self.fecha_hasta,
            self.amid_minimo,
        )

        where = " ".join(segmentos)

        self.assertIn("TO_DATE(TR.TVF_SFECTRANSACCION", where)
        self.assertIn("TR.TVF_DFECREGISTRO >= :fecha_desde", where)

    def test_rango_por_dia_bd_no_descarta_rezagadas_anteriores(self):
        segmentos, _ = trx_repository.armar_filtros_trx(
            self.fecha_desde,
            self.fecha_hasta,
            self.amid_minimo,
            origen="bd",
        )

        where = " ".join(segmentos)

        self.assertIn("TR.TVF_DFECREGISTRO >= :fecha_desde", where)
        self.assertIn("TR.TVF_DFECREGISTRO < :fecha_hasta", where)
        self.assertNotIn(
            "TO_DATE(TR.TVF_SFECTRANSACCION, 'YYYY/MM/DD HH24:MI:SS') >= :fecha_desde",
            where,
        )

    def test_filtros_opcionales_son_binds_y_no_texto(self):
        segmentos, params = trx_repository.armar_filtros_trx(
            self.fecha_desde,
            self.fecha_hasta,
            self.amid_minimo,
            amid="7500001",
            nidsitio="1234",
            nmodo="4",
        )

        where = " ".join(segmentos)

        for nombre in ("amid", "nidsitio", "nmodo"):
            with self.subTest(filtro=nombre):
                self.assertIn(f"= :{nombre}", where)

        for valor in ("7500001", "1234"):
            with self.subTest(valor=valor):
                self.assertNotIn(valor, where)

        self.assertEqual(params["amid"], 7500001)
        self.assertEqual(params["nidsitio"], 1234)
        self.assertEqual(params["nmodo"], 4)

    def test_sin_filtros_opcionales_no_hay_binds_huerfanos(self):
        segmentos, params = trx_repository.armar_filtros_trx(
            self.fecha_desde,
            self.fecha_hasta,
            self.amid_minimo,
        )

        where = " ".join(segmentos)
        binds = set(re.findall(r":([a-z_]+)", where))

        self.assertEqual(binds, set(params))

    def test_origen_invalido_falla(self):
        with self.assertRaises(ValueError):
            trx_repository.armar_filtros_trx(
                self.fecha_desde,
                self.fecha_hasta,
                self.amid_minimo,
                origen="otro",
            )

    def test_where_vacio_no_produce_where_huerfano(self):
        self.assertEqual(trx_repository.construir_where([]), "")


class OrigenYOrdenTests(SimpleTestCase):
    def test_cada_origen_expone_una_expresion_y_una_columna_de_orden(self):
        for origen in trx_repository.ORIGENES_VALIDOS:
            with self.subTest(origen=origen):
                self.assertIn(origen, trx_repository.EXPRESION_POR_ORIGEN)
                self.assertIn(origen, trx_repository.COLUMNA_ORDEN_POR_ORIGEN)
                self.assertIn(
                    trx_repository.COLUMNA_ORDEN_POR_ORIGEN[origen],
                    trx_repository.COLUMNAS_TRX,
                )

    def test_orden_invalido_falla(self):
        with self.assertRaises(ValueError):
            trx_repository.columna_orden_trx("otro")


class ConstruccionWhereTests(SimpleTestCase):
    def test_where_une_con_and(self):
        where = trx_repository.construir_where(["A = 1", "B = 2"])

        self.assertTrue(where.startswith("WHERE "))
        self.assertIn("AND", where)


class OrigenTrxTests(SimpleTestCase):
    def test_el_origen_es_el_consumido_y_no_se_administra(self):
        origen = trx_repository.ORIGEN_TRX

        self.assertTrue(origen.startswith("DBPTE.TRANSACCION_FLUJO_VC2D_FISC@"))
        self.assertIn("LEFT JOIN", trx_repository.SQL_DESDE_TRX)
        self.assertEqual(
            trx_repository.SQL_DESDE_TRX.count("JOIN"),
            2,
            "Solo se permiten los dos joins de contexto.",
        )

    def test_to_date_usa_el_formato_validado(self):
        self.assertIn(
            "TO_DATE(TR.TVF_SFECTRANSACCION, 'YYYY/MM/DD HH24:MI:SS')",
            trx_repository.EXPRESION_FEC_TRX,
        )


class LimiteDePaginaTests(SimpleTestCase):
    def test_limite_debe_ser_positivo(self):
        with self.assertRaises(ValueError):
            trx_repository.obtener_trx_base(
                datetime.date(2026, 8, 27),
                datetime.date(2026, 8, 28),
                limite=0,
                amid_minimo=7_500_000,
            )


class _CursorGrabador:
    """Cursor falso: guarda el SQL y los binds de cada `execute`."""

    def __init__(self, registro):
        self.registro = registro
        self.description = [("NID_CONTEXTO_OPTE",), ("FEC_TRX",), ("FEC_BD",)]

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, query, params=None):
        self.registro.append({"sql": query, "params": dict(params or {})})

    def fetchone(self):
        return (7,)

    def fetchall(self):
        return []


class _ConexionGrabadora:
    def __init__(self, registro):
        self.registro = registro

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def cursor(self):
        return _CursorGrabador(self.registro)


class ConteoYDetalleCompartenFiltrosTests(SimpleTestCase):
    """
    El conteo y el detalle deben aplicar exactamente los mismos filtros.

    No basta con que ambos llamen a `armar_filtros_trx`: esto intercepta el SQL
    y los binds que cada uno ejecuta de verdad y los compara.
    """

    fecha_desde = datetime.date(2026, 8, 27)
    fecha_hasta = datetime.date(2026, 8, 29)

    def _ejecutar_ambos(self, **filtros):
        registro = []

        with mock.patch(
            "apps.dashboard.services.oracle_connection.obtener_conexion_oracle",
            return_value=_ConexionGrabadora(registro),
        ):
            trx_repository.contar_trx_base(self.fecha_desde, self.fecha_hasta, **filtros)
            trx_repository.obtener_trx_base(
                self.fecha_desde,
                self.fecha_hasta,
                limite=50,
                offset=0,
                **filtros,
            )

        self.assertEqual(len(registro), 2, "Se esperaba el conteo y el detalle.")
        return registro

    def test_el_where_es_identico_en_ambos_sentencias(self):
        registro = self._ejecutar_ambos(
            amid="7500001",
            nidsitio="1234",
            nmodo="4",
            origen="trx",
            amid_minimo=7_500_000,
        )
        sql_conteo, sql_detalle = registro[0]["sql"], registro[1]["sql"]
        segmentos, _ = trx_repository.armar_filtros_trx(
            self.fecha_desde,
            self.fecha_hasta,
            7_500_000,
            amid="7500001",
            nidsitio="1234",
            nmodo="4",
            origen="trx",
        )

        for segmento in segmentos:
            with self.subTest(segmento=segmento):
                self.assertIn(segmento, sql_conteo)
                self.assertIn(segmento, sql_detalle)

    def test_los_binds_de_filtro_tienen_los_mismos_valores(self):
        registro = self._ejecutar_ambos(
            amid="7500001",
            nidsitio="1234",
            origen="trx",
            amid_minimo=7_500_000,
        )
        binds_conteo = dict(registro[0]["params"])
        binds_detalle = dict(registro[1]["params"])

        # El detalle solo puede agregar los binds de paginacion.
        self.assertEqual(
            set(binds_detalle) - set(binds_conteo),
            {"limite", "offset"},
        )
        self.assertEqual(set(binds_conteo) - set(binds_detalle), set())

        for nombre, valor in binds_conteo.items():
            with self.subTest(bind=nombre):
                self.assertEqual(binds_detalle[nombre], valor)

    def test_el_detalle_no_agrega_binds_de_filtro_por_la_paginacion(self):
        registro = self._ejecutar_ambos(
            origen="trx",
            amid_minimo=7_500_000,
        )
        sql_detalle, binds_detalle = registro[1]["sql"], registro[1]["params"]

        # La paginacion se resuelve en la capa externa, nunca en el WHERE.
        self.assertIn("RN BETWEEN :offset + 1 AND :offset + :limite", sql_detalle)
        self.assertNotIn(":limite", trx_repository.construir_where(
            trx_repository.armar_filtros_trx(
                self.fecha_desde,
                self.fecha_hasta,
                7_500_000,
                origen="trx",
            )[0]
        ))
        self.assertEqual(binds_detalle["limite"], 50)
        self.assertEqual(binds_detalle["offset"], 0)

    def test_el_origen_bd_tambien_comparte_los_filtros(self):
        registro = self._ejecutar_ambos(
            origen="bd",
            amid_minimo=7_500_000,
        )
        segmentos, _ = trx_repository.armar_filtros_trx(
            self.fecha_desde,
            self.fecha_hasta,
            7_500_000,
            origen="bd",
        )

        for segmento in segmentos:
            with self.subTest(segmento=segmento):
                self.assertIn(segmento, registro[0]["sql"])
                self.assertIn(segmento, registro[1]["sql"])
