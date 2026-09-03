from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from urllib.parse import parse_qs
from unittest.mock import MagicMock, Mock, patch

from django.test import RequestFactory, SimpleTestCase

from apps.dashboard.management.commands.importar_ubicaciones_esperadas import (
    Command as ImportarUbicacionesCommand,
)
from apps.dashboard.context_processors import datos_actualizacion_dashboard
from apps.dashboard.services.alertas_service import (
    _armar_filtros_alertas,
    alternar_direccion_orden_alertas,
    calcular_estado_estatus,
    construir_orden_alertas,
    construir_condicion_problema,
    construir_querystring_filtro,
    normalizar_amid_alertas,
    normalizar_orden_alertas,
    obtener_alertas_para_exportar,
    obtener_contexto_alertas,
    serializar_orden_alertas,
)
from apps.dashboard.services.horarios_zp_service import (
    crear_configuracion_horario_zp,
    filtrar_registros_por_horario_zp,
    obtener_columnas_media_hora_para_hoy,
)
from apps.dashboard.services.reglas_alertas_service import (
    actualizar_reglas_alertas,
    recalcular_alertas,
    usuario_puede_editar_reglas,
)


class ContextProcessorTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_anonymous_request_does_not_query_oracle(self):
        """
        Si el usuario no está autenticado, el context processor no debe consultar Oracle.
        Esto evita lentitud innecesaria en login/logout.
        """

        request = self.factory.get("/")
        request.user = SimpleNamespace(is_authenticated=False)

        with patch(
            "apps.dashboard.context_processors.obtener_ultima_carga_datos_oracle"
        ) as mock_ultima_carga, patch(
            "apps.dashboard.context_processors.obtener_ultima_version_zp_oracle"
        ) as mock_ultima_version:
            context = datos_actualizacion_dashboard(request)

        self.assertEqual(context, {})
        mock_ultima_carga.assert_not_called()
        mock_ultima_version.assert_not_called()

    def test_authenticated_request_returns_sidebar_context(self):
        """
        Si el usuario está autenticado, el context processor debe devolver
        las variables globales usadas por el sidebar.
        """

        request = self.factory.get("/")
        request.user = SimpleNamespace(is_authenticated=True)

        ultima_carga = datetime(2026, 8, 7, 9, 30)
        ultima_version = datetime(2026, 8, 7, 8, 0)

        with patch(
            "apps.dashboard.context_processors.obtener_ultima_carga_datos_oracle",
            return_value=ultima_carga,
        ) as mock_ultima_carga, patch(
            "apps.dashboard.context_processors.obtener_ultima_version_zp_oracle",
            return_value=ultima_version,
        ) as mock_ultima_version:
            context = datos_actualizacion_dashboard(request)

        self.assertIn("ultima_actualizacion_dashboard", context)
        self.assertEqual(context["ultima_carga_datos"], ultima_carga)
        self.assertEqual(context["ultima_actualizacion_version_zp"], ultima_version)

        mock_ultima_carga.assert_called_once()
        mock_ultima_version.assert_called_once()


class ImportarUbicacionesEsperadasTests(SimpleTestCase):
    def test_ausentes_usan_maestro_activo_y_respetan_amids_del_excel(self):
        comando = ImportarUbicacionesCommand()
        cursor = MagicMock()
        cursor.description = [("AMID",), ("SERIE_VALIDADOR",)]
        cursor.fetchall.return_value = [
            ("750001", "SERIE-1"),
            ("750002", None),
        ]

        comando.obtener_historial_vigente = Mock(return_value=None)
        comando.upsert_vigente = Mock()
        comando.crear_historial = Mock()

        resultado = comando.mover_ausentes_a_laboratorio(
            cursor=cursor,
            amids_excel={"750001"},
            fecha_carga=datetime(2026, 8, 27, 12, 0),
            archivo_origen="ZONA PAGA V755.xlsx",
            version_zp="V755",
        )

        consulta_maestro = cursor.execute.call_args.args[0]
        self.assertIn("AMID_MAESTRO_ALERTAS", consulta_maestro)
        self.assertIn("WHERE ACTIVO = 1", consulta_maestro)
        self.assertIn(
            "LEFT JOIN USR_LAB.UBICACION_ESPERADA_VALIDADOR",
            consulta_maestro,
        )

        comando.upsert_vigente.assert_called_once()
        datos_laboratorio = comando.upsert_vigente.call_args.args[1]
        self.assertEqual(datos_laboratorio["AMID"], "750002")
        self.assertEqual(datos_laboratorio["NOMBRE"], "Laboratorio Zonas Pagas")
        self.assertEqual(datos_laboratorio["OPERATIVA"], 0)
        self.assertIsNone(datos_laboratorio["HORARIO"])
        self.assertIsNone(datos_laboratorio["HORARIO_LABORAL_PM"])
        self.assertIsNone(datos_laboratorio["HORARIO_SABADO"])
        self.assertIsNone(datos_laboratorio["HORARIO_DOMINGO"])

        comando.crear_historial.assert_called_once()
        datos_historial = comando.crear_historial.call_args.args[1]
        self.assertEqual(
            datos_historial["ORIGEN_UBICACION"],
            "laboratorio_default",
        )
        self.assertEqual(resultado, (1, 0, 1))


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
                "texto_estatus": "Sin estatus",
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


class ReglasAlertasServiceTests(SimpleTestCase):
    def test_usuario_puede_editar_reglas_accepts_superuser(self):
        """
        Un superusuario puede editar reglas de alertas.
        """

        user = SimpleNamespace(is_superuser=True)

        self.assertTrue(usuario_puede_editar_reglas(user))

    def test_usuario_puede_editar_reglas_accepts_admin_group(self):
        """
        Un usuario del grupo Admin puede editar reglas de alertas.
        """

        class GrupoAdmin:
            def filter(self, name):
                self.name = name
                return self

            def exists(self):
                return self.name == "Admin"

        user = SimpleNamespace(is_superuser=False, groups=GrupoAdmin())

        self.assertTrue(usuario_puede_editar_reglas(user))

    def test_usuario_puede_editar_reglas_rejects_non_admin(self):
        """
        Un usuario que no es superusuario ni pertenece al grupo Admin
        no puede editar reglas.
        """

        class GrupoNoAdmin:
            def filter(self, name):
                self.name = name
                return self

            def exists(self):
                return False

        user = SimpleNamespace(is_superuser=False, groups=GrupoNoAdmin())

        self.assertFalse(usuario_puede_editar_reglas(user))

    def test_actualizar_reglas_alertas_rejects_unknown_keys(self):
        """
        No se deben aceptar claves de reglas que no estén permitidas.
        """

        with self.assertRaises(ValueError):
            actualizar_reglas_alertas({"regla_CLAVE_DESCONOCIDA": "3"})

    def _preparar_oracle(self, filas):
        conexion = MagicMock()
        cursor = MagicMock()
        cursor.fetchall.return_value = filas
        cursor.rowcount = 1
        conexion.cursor.return_value.__enter__.return_value = cursor

        contexto_conexion = MagicMock()
        contexto_conexion.__enter__.return_value = conexion
        return contexto_conexion, conexion, cursor

    def test_actualizar_reglas_alertas_omite_valores_sin_cambios(self):
        contexto, conexion, cursor = self._preparar_oracle(
            [("GPS_CERO_HOY_ADV", Decimal("2"), "CLASIFICACION")]
        )

        with patch(
            "apps.dashboard.services.reglas_alertas_service.obtener_conexion_oracle",
            return_value=contexto,
        ):
            resultado = actualizar_reglas_alertas(
                {"regla_GPS_CERO_HOY_ADV": "2.00"}
            )

        self.assertEqual(
            resultado,
            {"cantidad": 0, "claves": [], "modo_recalculo": None},
        )
        self.assertEqual(cursor.execute.call_count, 1)
        conexion.commit.assert_called_once()
        conexion.rollback.assert_not_called()

    def test_actualizar_clasificacion_solicita_recalculo_rapido(self):
        contexto, conexion, cursor = self._preparar_oracle(
            [("GPS_CERO_HOY_ADV", Decimal("2"), "CLASIFICACION")]
        )

        with patch(
            "apps.dashboard.services.reglas_alertas_service.obtener_conexion_oracle",
            return_value=contexto,
        ):
            resultado = actualizar_reglas_alertas(
                {"regla_GPS_CERO_HOY_ADV": "3"}
            )

        self.assertEqual(resultado["cantidad"], 1)
        self.assertEqual(resultado["claves"], ["GPS_CERO_HOY_ADV"])
        self.assertEqual(resultado["modo_recalculo"], "rapido")
        self.assertIn(
            "PRC_VALIDAR_REGLAS_ALERTA",
            cursor.execute.call_args_list[-1].args[0],
        )
        conexion.commit.assert_called_once()

    def test_actualizar_deteccion_solicita_recalculo_completo(self):
        contexto, _conexion, _cursor = self._preparar_oracle(
            [("BAT_CAIDA_MIN_DETECTAR", Decimal("20"), "DETECCION")]
        )

        with patch(
            "apps.dashboard.services.reglas_alertas_service.obtener_conexion_oracle",
            return_value=contexto,
        ):
            resultado = actualizar_reglas_alertas(
                {"regla_BAT_CAIDA_MIN_DETECTAR": "21"}
            )

        self.assertEqual(resultado["modo_recalculo"], "completo")

    def test_recalcular_alertas_usa_wrapper_segun_modo(self):
        contexto, _conexion, cursor = self._preparar_oracle([])

        with patch(
            "apps.dashboard.services.reglas_alertas_service.obtener_conexion_oracle",
            return_value=contexto,
        ):
            recalcular_alertas(modo_recalculo="rapido")

        cursor.execute.assert_called_once_with(
            "BEGIN USR_LAB.PRC_RECLASIFICAR_ALERTAS; END;"
        )

    def test_recalcular_alertas_rechaza_modo_desconocido(self):
        with self.assertRaises(ValueError):
            recalcular_alertas(modo_recalculo="desconocido")


class HorariosZonaPagaServiceTests(SimpleTestCase):
    def setUp(self):
        self.datos = {
            "NOMBRE": "Zona Paga de prueba",
            "HORARIO": "08:00 - 12:00",
            "HORARIO_LABORAL_PM": "14:00 – 18:00",
            "HORARIO_SABADO": None,
            "HORARIO_DOMINGO": "09:00 - 13:00",
        }

    def test_dia_habil_combina_tramos_am_y_pm(self):
        configuracion = crear_configuracion_horario_zp(
            self.datos,
            fecha_referencia=datetime(2026, 8, 24, 9, 0),
        )

        self.assertTrue(configuracion["tiene_horario_hoy"])
        self.assertEqual(
            configuracion["texto_hoy"],
            "08:00 a 12:00 · 14:00 a 18:00",
        )

        columnas = obtener_columnas_media_hora_para_hoy(configuracion)
        self.assertIn("08:00", columnas)
        self.assertIn("18:00", columnas)
        self.assertNotIn("13:00", columnas)

    def test_sabado_sin_horario_no_activa_filtro(self):
        configuracion = crear_configuracion_horario_zp(
            self.datos,
            fecha_referencia=datetime(2026, 8, 29, 9, 0),
        )

        self.assertFalse(configuracion["tiene_horario_hoy"])
        self.assertEqual(configuracion["texto_hoy"], "Sin horario asignado")

    def test_gps_filtra_por_dia_y_conserva_dias_sin_horario(self):
        configuracion = crear_configuracion_horario_zp(
            self.datos,
            fecha_referencia=datetime(2026, 8, 24, 9, 0),
        )
        registros = [
            SimpleNamespace(id=1, fecha_registro=datetime(2026, 8, 24, 9, 0)),
            SimpleNamespace(id=2, fecha_registro=datetime(2026, 8, 24, 13, 0)),
            SimpleNamespace(id=3, fecha_registro=datetime(2026, 8, 24, 15, 0)),
            SimpleNamespace(id=4, fecha_registro=datetime(2026, 8, 29, 22, 0)),
        ]

        filtrados, filtro_aplicado = filtrar_registros_por_horario_zp(
            registros,
            configuracion,
        )

        self.assertTrue(filtro_aplicado)
        self.assertEqual([registro.id for registro in filtrados], [1, 3, 4])
