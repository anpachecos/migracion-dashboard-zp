"""
Pruebas de las tres salidas del módulo de Transacciones.

Se inyecta un dataset ya normalizado en `construir_contexto_comun` para poder
verificar filtros y agregados sin Oracle. Lo que se prueba aquí es que cada
pestana aplica SU regla sobre el mismo dataset y que las agregaciones coinciden
con la clasificación.
"""

import datetime
from unittest import mock

from django.test import RequestFactory, SimpleTestCase

from apps.transacciones.services import (
    informe_interno_service,
    mayor_15_service,
    rezagadas_service,
    trx_service,
)

HOY = datetime.date(2026, 8, 27)


def construir_trx(
    nid_contexto_opte,
    fec_trx,
    fec_bd,
    amid=7_500_001,
    nombre_entidad="Operador Uno",
    nombre_sitio="Sitio Uno",
):
    """Atajo que produce una fila ya normalizada con las reglas reales."""

    return trx_service.normalizar_fila(
        {
            "nid_contexto_opte": nid_contexto_opte,
            "num_abt": "000000123",
            "nid_contexto_switch": "0",
            "nid_terminal": "999",
            "amid": amid,
            "nid_sitio": "1234",
            "nombre_sitio": nombre_sitio,
            "nid_entidad_ot": "1",
            "nombre_entidad": nombre_entidad,
            "cod_tipo_transaccion": "01",
            "n_modo": "4",
            "cod_proceso": "P1",
            "estado_envio": "E",
            "fec_trx": fec_trx,
            "fec_bd": fec_bd,
        }
    )


# Tres casos que cubren las tres clasificaciones posibles.
CASOS = [
    # 00:00:30, mismo día, no es "> 15 min".
    construir_trx(
        "1",
        datetime.datetime(2026, 8, 27, 10, 0, 0),
        datetime.datetime(2026, 8, 27, 10, 0, 30),
    ),
    # 00:20:00, mismo día, "> 15 min".
    construir_trx(
        "2",
        datetime.datetime(2026, 8, 27, 11, 0, 0),
        datetime.datetime(2026, 8, 27, 11, 20, 0),
    ),
    # Cambio de día por dos minutos: rezagada, nunca "> 15 min".
    construir_trx(
        "3",
        datetime.datetime(2026, 8, 26, 23, 59, 0),
        datetime.datetime(2026, 8, 27, 0, 1, 0),
    ),
]


class BaseInformeTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def contexto(self, servicio, **params):
        request = self.factory.get(
            "/transacciones/",
            params,
        )

        comun = {
            "dataset": list(CASOS),
            "total": len(CASOS),
            "consultado": True,
            "truncado": False,
            "mensaje": "",
        }

        with mock.patch.object(
            trx_service,
            "obtener_dataset_base",
            return_value=comun,
        ):
            return servicio(request, hoy=HOY)


class InformeInternoTests(BaseInformeTests):
    def test_muestra_el_dataset_completo_sin_filtro_de_mismo_dia(self):
        contexto = self.contexto(
            informe_interno_service.obtener_contexto_informe_interno,
        )

        self.assertEqual(len(contexto["filas"]), 3)
        self.assertFalse(contexto["solo_mismo_dia_aplicado"])

    def test_solo_mismo_dia_equivaldra_a_la_lectura_de_la_guia(self):
        contexto = self.contexto(
            informe_interno_service.obtener_contexto_informe_interno,
            solo_mismo_dia="1",
        )

        self.assertEqual(len(contexto["filas"]), 2)
        self.assertTrue(contexto["solo_mismo_dia_aplicado"])
        self.assertTrue(all(trx["es_mismo_dia"] for trx in contexto["filas"]))

    def test_oferta_las_dos_lecturas_del_universo(self):
        contexto = self.contexto(
            informe_interno_service.obtener_contexto_informe_interno,
        )

        self.assertIn("solo_mismo_dia=1", contexto["querystring_solo_mismo_dia"])

        activada = self.contexto(
            informe_interno_service.obtener_contexto_informe_interno,
            solo_mismo_dia="1",
        )

        self.assertNotIn("solo_mismo_dia", activada["querystring_solo_mismo_dia"])

    def test_resumen_por_tramo_cubre_todas_las_filas(self):
        contexto = self.contexto(
            informe_interno_service.obtener_contexto_informe_interno,
        )

        total_en_tramos = sum(fila["total"] for fila in contexto["resumen_tramos"])

        self.assertEqual(total_en_tramos, 3)
        self.assertTrue(
            all(fila["etiqueta"] for fila in contexto["resumen_tramos"]),
            "Ningún tramo puede quedar sin etiqueta.",
        )

    def test_con_datos_validos_no_marca_placeholder(self):
        contexto = self.contexto(
            informe_interno_service.obtener_contexto_informe_interno,
        )

        self.assertTrue(contexto["hay_datos"])
        self.assertTrue(
            all(not kpi["es_placeholder"] for kpi in contexto["kpis"])
        )

    def test_sin_consulta_los_kpis_muestran_guion(self):
        request = self.factory.get("/transacciones/")

        contexto = informe_interno_service.obtener_contexto_informe_interno(
            request,
            hoy=HOY,
        )

        self.assertFalse(contexto["hay_datos"])
        self.assertTrue(all(kpi["es_placeholder"] for kpi in contexto["kpis"]))
        self.assertTrue(all(kpi["valor"] == "—" for kpi in contexto["kpis"]))


class MayorQuinceMinTests(BaseInformeTests):
    def test_solo_incluye_mismo_dia_sobre_quince_minutos(self):
        contexto = self.contexto(
            mayor_15_service.obtener_contexto_mayor_15,
        )

        self.assertEqual(len(contexto["filas"]), 1)
        self.assertEqual(contexto["filas"][0]["nid_contexto_opte"], "2")

    def test_ordena_de_mayor_a_menor_duracion(self):
        contexto = self.contexto(
            mayor_15_service.obtener_contexto_mayor_15,
        )
        duraciones = [trx["duracion_segundos"] for trx in contexto["filas"]]

        self.assertEqual(duraciones, sorted(duraciones, reverse=True))

    def test_matriz_validador_dia_conserva_el_peor_caso(self):
        contexto = self.contexto(
            mayor_15_service.obtener_contexto_mayor_15,
        )

        self.assertEqual(len(contexto["matriz_validador_dia"]), 1)
        self.assertEqual(
            contexto["matriz_validador_dia"][0]["duracion_maxima"],
            "00:20:00",
        )

    def test_ranking_consolida_por_amid(self):
        contexto = self.contexto(
            mayor_15_service.obtener_contexto_mayor_15,
        )
        ranking = contexto["ranking_validadores"]

        self.assertEqual(len(ranking), 1)
        self.assertEqual(ranking[0]["amid"], "7500001")
        self.assertEqual(ranking[0]["total"], 1)
        self.assertEqual(ranking[0]["total_dias"], 1)

    def test_el_ranking_no_expone_sets_en_el_contexto(self):
        contexto = self.contexto(
            mayor_15_service.obtener_contexto_mayor_15,
        )

        for fila in contexto["ranking_validadores"]:
            for clave, valor in fila.items():
                with self.subTest(clave=clave):
                    self.assertNotIsInstance(valor, set)


class RezagadasTests(BaseInformeTests):
    def test_solo_incluye_cambio_de_dia(self):
        contexto = self.contexto(
            rezagadas_service.obtener_contexto_rezagadas,
        )

        self.assertEqual(len(contexto["filas"]), 1)
        self.assertEqual(contexto["filas"][0]["nid_contexto_opte"], "3")

    def test_ordena_peor_rezago_primero(self):
        trx = [
            construir_trx(
                "1",
                datetime.datetime(2026, 8, 24, 10, 0, 0),
                datetime.datetime(2026, 8, 25, 10, 0, 0),
            ),
            construir_trx(
                "2",
                datetime.datetime(2026, 8, 26, 10, 0, 0),
                datetime.datetime(2026, 8, 27, 10, 0, 0),
            ),
        ]

        request = self.factory.get("/transacciones/")
        comun = {
            "dataset": trx,
            "total": len(trx),
            "consultado": True,
            "truncado": False,
            "mensaje": "",
        }

        with mock.patch.object(
            trx_service,
            "obtener_dataset_base",
            return_value=comun,
        ):
            contexto = rezagadas_service.obtener_contexto_rezagadas(
                request,
                hoy=HOY,
            )

        self.assertEqual(
            [fila["nid_contexto_opte"] for fila in contexto["filas"]],
            ["1", "2"],
        )

    def test_matriz_y_resumen_de_dias_de_rezago(self):
        contexto = self.contexto(
            rezagadas_service.obtener_contexto_rezagadas,
        )

        self.assertEqual(contexto["resumen_por_dias_rezago"][0]["dias_rezago"], 1)
        self.assertEqual(contexto["resumen_por_dias_rezago"][0]["total"], 1)
        self.assertEqual(contexto["resumen_por_dias_rezago"][0]["porcentaje"], 100.0)
        self.assertEqual(len(contexto["matriz_dia_trx_dia_bd"]), 1)
        self.assertEqual(len(contexto["tendencia_por_dia"]), 1)
        self.assertEqual(contexto["analisis_por_amid"][0]["maximo_dias_rezago"], 1)

    def test_rezagadas_y_mayor_15_nunca_coinciden(self):
        rezagadas = self.contexto(
            rezagadas_service.obtener_contexto_rezagadas,
        )
        mayor_15 = self.contexto(
            mayor_15_service.obtener_contexto_mayor_15,
        )

        ids_rezagadas = {trx["nid_contexto_opte"] for trx in rezagadas["filas"]}
        ids_mayor_15 = {trx["nid_contexto_opte"] for trx in mayor_15["filas"]}

        self.assertEqual(ids_rezagadas & ids_mayor_15, set())


class ExportacionesTests(SimpleTestCase):
    """Los tres builders producen un XLSX básico aun sin filas."""

    CONSTRUCTORES = (
        "construir_excel_informe_interno",
        "construir_excel_mayor_15",
        "construir_excel_rezagadas",
    )

    def test_los_tres_excel_producen_xlsx(self):
        from apps.transacciones.services import exportaciones_service

        for nombre in self.CONSTRUCTORES:
            with self.subTest(funcion=nombre):
                contenido = getattr(exportaciones_service, nombre)([])
                self.assertTrue(contenido.startswith(b"PK"))

    def test_la_interfaz_ofrece_descarga(self):
        from apps.transacciones.services import exportaciones_service

        self.assertTrue(exportaciones_service.exportar_disponible())

    def test_el_nombre_sugerido_incluye_el_rango(self):
        from apps.transacciones.services import exportaciones_service

        nombre = exportaciones_service.nombre_archivo_sugerido(
            "Informe Interno",
            {"fecha_desde_texto": "2026-08-27"},
        )

        self.assertEqual(nombre, "transacciones_informe_interno_2026-08-27.xlsx")


class TotalRealVsMuestraTests(BaseInformeTests):
    """
    El total del rango y el conteo de la muestra son dos cosas distintas.

    `total_universo` viene del COUNT(*) de Oracle y es exacto. `total_trx` y los
    porcentajes salen de las filas acotadas. Las tres pantallas tienen que
    mostrarlos por separado, o el número acotado se lee como el total del día.
    """

    TOTAL_UNIVERSO = 5_000

    def _contexto_truncado(self, servicio):
        request = self.factory.get("/transacciones/")

        comun = {
            "dataset": list(CASOS),
            "total": self.TOTAL_UNIVERSO,
            "consultado": True,
            "truncado": True,
            "mensaje": "",
        }

        with mock.patch.object(
            trx_service,
            "obtener_dataset_base",
            return_value=comun,
        ):
            return servicio(request, hoy=HOY)

    SERVICIOS = (
        informe_interno_service.obtener_contexto_informe_interno,
        mayor_15_service.obtener_contexto_mayor_15,
        rezagadas_service.obtener_contexto_rezagadas,
    )

    def test_el_contexto_expone_el_total_real_y_el_de_la_muestra(self):
        for servicio in self.SERVICIOS:
            with self.subTest(servicio=servicio.__name__):
                contexto = self._contexto_truncado(servicio)

                self.assertEqual(contexto["total_universo"], self.TOTAL_UNIVERSO)
                self.assertEqual(contexto["total_muestra"], len(CASOS))
                self.assertTrue(contexto["es_muestra"])
                self.assertTrue(contexto["truncado"])

    def test_las_tarjetas_muestran_el_total_real_y_advierten_la_muestra(self):
        for servicio in self.SERVICIOS:
            with self.subTest(servicio=servicio.__name__):
                contexto = self._contexto_truncado(servicio)
                tarjetas = {kpi["etiqueta"]: kpi for kpi in contexto["kpis"]}

                self.assertIn("Total TRX del rango", tarjetas)
                self.assertEqual(
                    tarjetas["Total TRX del rango"]["valor"],
                    self.TOTAL_UNIVERSO,
                )

                self.assertIn("Total TRX analizados", tarjetas)
                self.assertEqual(
                    tarjetas["Total TRX analizados"]["valor"],
                    len(CASOS),
                )
                self.assertIn(
                    str(self.TOTAL_UNIVERSO),
                    tarjetas["Total TRX analizados"]["detalle"],
                )
                self.assertIn(
                    "muestra acotada",
                    tarjetas["Total TRX analizados"]["detalle"],
                )

    def test_los_porcentuales_avisan_que_son_de_la_muestra(self):
        # Solo mayor_15 y rezagadas exponen una tarjeta de porcentaje.
        for servicio in (
            mayor_15_service.obtener_contexto_mayor_15,
            rezagadas_service.obtener_contexto_rezagadas,
        ):
            with self.subTest(servicio=servicio.__name__):
                contexto = self._contexto_truncado(servicio)
                tarjetas = {kpi["etiqueta"]: kpi for kpi in contexto["kpis"]}

                self.assertEqual(
                    tarjetas["% sobre el período"]["detalle"],
                    "Del total de la muestra",
                )

    def test_sin_truncado_el_detalle_dice_rango_completo(self):
        for servicio in self.SERVICIOS:
            with self.subTest(servicio=servicio.__name__):
                contexto = self.contexto(servicio)
                tarjetas = {kpi["etiqueta"]: kpi for kpi in contexto["kpis"]}

                self.assertEqual(
                    tarjetas["Total TRX analizados"]["detalle"],
                    "Rango completo",
                )
                self.assertFalse(contexto["es_muestra"])
