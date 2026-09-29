from datetime import datetime, timedelta
from urllib.parse import parse_qs
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from apps.dashboard.services.alertas_service import (
    _armar_filtros_alertas,
    alternar_direccion_orden_alertas,
    calcular_estado_estatus,
    construir_condicion_problema,
    construir_orden_alertas,
    construir_querystring_filtro,
    normalizar_amid_alertas,
    normalizar_orden_alertas,
    obtener_alertas_para_exportar,
    obtener_contexto_alertas,
    serializar_orden_alertas,
)


class AlertasServiceTests(SimpleTestCase):
    def test_normalizar_amid_alertas_acepta_vacio_y_rango_valido(self):
        self.assertEqual(normalizar_amid_alertas(""), "")
        self.assertEqual(normalizar_amid_alertas(" 7500000 "), "7500000")
        self.assertEqual(normalizar_amid_alertas("9999999"), "9999999")

    def test_normalizar_amid_alertas_rechaza_formato_y_rango_invalidos(self):
        for amid in ("7500ABC", "75000000", "7499999"):
            with self.subTest(amid=amid):
                with self.assertRaises(ValueError):
                    normalizar_amid_alertas(amid)

    @patch("apps.dashboard.services.alertas_service.contar_alertas_validadores")
    def test_contexto_rechaza_amid_invalido_antes_de_consultar_oracle(
        self,
        mock_contar,
    ):
        request = RequestFactory().get("/alertas/", {"amid": "7499999"})

        with self.assertRaisesMessage(
            ValueError,
            "El AMID debe ser mayor o igual a 7500000.",
        ):
            obtener_contexto_alertas(request)

        mock_contar.assert_not_called()

    @patch("apps.dashboard.services.alertas_service.obtener_alertas_validadores")
    @patch("apps.dashboard.services.alertas_service.contar_alertas_validadores")
    def test_exportacion_usa_todos_los_activos_sin_filtros(
        self,
        mock_contar,
        mock_obtener,
    ):
        mock_contar.return_value = 930
        mock_obtener.return_value = [{"amid": 750001}]

        resultado = obtener_alertas_para_exportar()

        self.assertEqual(resultado, [{"amid": 750001}])
        mock_contar.assert_called_once_with(solo_con_alerta=False)
        mock_obtener.assert_called_once_with(
            solo_con_alerta=False,
            limite=930,
            offset=0,
            orden=(
                ("prioridad", "asc"),
                ("gps", "asc"),
                ("bateria", "asc"),
                ("estatus", "asc"),
            ),
        )

    @patch("apps.dashboard.services.alertas_service.contar_alertas_validadores")
    def test_exportacion_vacia_no_ejecuta_consulta_de_detalle(self, mock_contar):
        mock_contar.return_value = 0

        with patch(
            "apps.dashboard.services.alertas_service.obtener_alertas_validadores"
        ) as mock_obtener:
            self.assertEqual(obtener_alertas_para_exportar(), [])
            mock_obtener.assert_not_called()

    def test_construir_condicion_problema_maps_known_values(self):
        """
        Verifica que los filtros visibles del panel de alertas se traduzcan
        a condiciones SQL esperadas.
        """

        self.assertEqual(
            construir_condicion_problema("bateria_caida"),
            "CAIDAS_HOY > 0 OR CAIDAS_HIST > 0",
        )

        self.assertEqual(
            construir_condicion_problema("ambos"),
            "NIVEL_ALERTA_GPS <> 'OK' AND NIVEL_ALERTA_BATERIA <> 'OK'",
        )

    def test_calcular_estado_estatus_classifies_statuses(self):
        """
        Verifica la clasificación visual del último estatus:
        - sin estatus;
        - estatus antiguo;
        - estatus reciente.
        """

        self.assertEqual(
            calcular_estado_estatus(None),
            {
                "estado_estatus": "sin_estatus",
                "texto_estatus": "Sin estatus hoy",
                "clase_estatus": "estatus-sin",
            },
        )

        antigua = datetime.now() - timedelta(hours=2)

        self.assertEqual(
            calcular_estado_estatus(antigua),
            {
                "estado_estatus": "estatus_antiguo",
                "texto_estatus": "Hace más de 1 hora",
                "clase_estatus": "estatus-antiguo",
            },
        )

        reciente = datetime.now() - timedelta(minutes=10)

        self.assertEqual(
            calcular_estado_estatus(reciente),
            {
                "estado_estatus": "con_estatus",
                "texto_estatus": "Con estatus",
                "clase_estatus": "estatus-ok",
            },
        )

    def test_orden_predeterminado_prioriza_global_gps_bateria_y_estatus(self):
        orden = normalizar_orden_alertas("")
        sql = construir_orden_alertas(orden)

        self.assertEqual(
            [campo for campo, _ in orden],
            ["prioridad", "gps", "bateria", "estatus"],
        )
        self.assertLess(
            sql.index("NIVEL_ALERTA_GLOBAL"),
            sql.index("NIVEL_ALERTA_GPS"),
        )
        self.assertLess(
            sql.index("NIVEL_ALERTA_GPS"),
            sql.index("NIVEL_ALERTA_BATERIA"),
        )
        self.assertLess(
            sql.index("NIVEL_ALERTA_BATERIA"),
            sql.index("ULTIMO_ESTATUS"),
        )
        self.assertIn("ULTIMO_ESTATUS DESC NULLS LAST", sql)

    def test_invertir_un_nivel_conserva_los_otros(self):
        orden = normalizar_orden_alertas("")
        invertido = alternar_direccion_orden_alertas(orden, "estatus")

        self.assertEqual(dict(invertido)["estatus"], "desc")
        self.assertEqual(dict(invertido)["prioridad"], "asc")
        self.assertEqual(dict(invertido)["gps"], "asc")
        self.assertEqual(dict(invertido)["bateria"], "asc")

    def test_orden_de_url_ignora_campos_y_direcciones_desconocidos(self):
        orden = normalizar_orden_alertas(
            "prioridad:desc,gps:incorrecto,campo:asc,amid:desc"
        )

        self.assertEqual(dict(orden)["prioridad"], "desc")
        self.assertEqual(dict(orden)["gps"], "asc")
        self.assertNotIn("amid", dict(orden))

        querystring = construir_querystring_filtro(orden=orden)
        parametros = parse_qs(querystring)
        self.assertEqual(parametros["orden"], [serializar_orden_alertas(orden)])

    def test_querystring_permite_quitar_solo_el_filtro_de_prioridad(self):
        querystring = construir_querystring_filtro(
            amid="7500679",
            ubicacion="Vespucio",
            nivel="CRITICA",
            nivel_gps="ALTA",
            nivel_bateria="ADVERTENCIA",
            estatus="ANTIGUO",
            tipo_alerta="GPS",
            nivel_override="",
        )
        self.assertEqual(
            parse_qs(querystring),
            {
                "amid": ["7500679"],
                "ubicacion": ["Vespucio"],
                "nivel_gps": ["ALTA"],
                "nivel_bateria": ["ADVERTENCIA"],
                "estatus": ["ANTIGUO"],
                "tipo_alerta": ["GPS"],
            },
        )

    def test_querystring_combina_y_quita_filtros_de_encabezado(self):
        querystring = construir_querystring_filtro(
            nivel="CRITICA",
            nivel_gps="ALTA",
            nivel_bateria="OK",
            estatus="CON_ESTATUS",
            nivel_gps_override="",
        )
        parametros = parse_qs(querystring)

        self.assertEqual(parametros["nivel"], ["CRITICA"])
        self.assertEqual(parametros["nivel_bateria"], ["OK"])
        self.assertEqual(parametros["estatus"], ["CON_ESTATUS"])
        self.assertNotIn("nivel_gps", parametros)

    def test_filtros_gps_y_bateria_utilizan_variables_enlazadas(self):
        filtros, parametros = _armar_filtros_alertas(
            nivel_gps="CRITICA",
            nivel_bateria="ALTA",
            solo_con_alerta=False,
        )

        self.assertIn("NIVEL_ALERTA_GPS = :nivel_gps", filtros)
        self.assertIn("NIVEL_ALERTA_BATERIA = :nivel_bateria", filtros)
        self.assertEqual(parametros["nivel_gps"], "CRITICA")
        self.assertEqual(parametros["nivel_bateria"], "ALTA")

    def test_querystring_permite_quitar_solo_el_filtro_de_ubicacion(self):
        querystring = construir_querystring_filtro(
            ubicacion="Vespucio",
            nivel="CRITICA",
            ubicacion_override="",
        )
        parametros = parse_qs(querystring)

        self.assertNotIn("ubicacion", parametros)
        self.assertEqual(parametros["nivel"], ["CRITICA"])

    def test_filtro_ubicacion_utiliza_busqueda_parcial_enlazada(self):
        filtros, parametros = _armar_filtros_alertas(
            ubicacion="Vespucio",
            solo_con_alerta=False,
        )

        self.assertIn(
            "UPPER(NVL(TRIM(u.NOMBRE), :ubicacion_sin_asignar)) "
            "LIKE :ubicacion",
            filtros,
        )
        self.assertEqual(parametros["ubicacion"], "%VESPUCIO%")
        self.assertIn("ubicacion_sin_asignar", parametros)
