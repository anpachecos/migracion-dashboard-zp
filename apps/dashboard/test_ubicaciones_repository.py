from datetime import datetime
from unittest.mock import MagicMock, call, patch

from django.test import SimpleTestCase

from apps.dashboard.repositories import ubicaciones_repository


class UbicacionesRepositoryTests(SimpleTestCase):
    FECHA_CARGA = datetime(2026, 9, 15, 12, 0)

    def preparar_oracle(self):
        contexto = MagicMock(name="contexto_conexion_falsa")
        conexion = contexto.__enter__.return_value
        cursor = conexion.cursor.return_value.__enter__.return_value
        return contexto, conexion, cursor

    def estadisticas(self):
        return {
            "creados_vigente": 0,
            "actualizados_vigente": 0,
            "omitidos": 0,
            "nuevos_historial": 0,
            "cerrados_historial": 0,
            "sin_cambios_historial": 0,
            "movidos_laboratorio": 0,
        }

    def referencia_laboratorio(self):
        return {
            "NOMBRE": "Laboratorio Zonas Pagas",
            "LATITUD_ESPERADA": -33.437191,
            "LONGITUD_ESPERADA": -70.656102,
            "RADIO_METROS": 150,
            "OPERATIVA": 0,
            "ORIGEN_UBICACION": "laboratorio_default",
        }

    def test_existe_vigente_conserva_select_bind_y_escalar(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = (1,)

        resultado = ubicaciones_repository.existe_vigente(cursor, "7500900")

        query, parametros = cursor.execute.call_args.args
        self.assertIn(
            "FROM USR_LAB.UBICACION_ESPERADA_VALIDADOR",
            query,
        )
        self.assertIn("WHERE AMID = :amid", query)
        self.assertEqual(parametros, {"amid": "7500900"})
        self.assertTrue(resultado)

    def test_merge_conserva_columnas_binds_y_datos_faltantes_en_none(self):
        cursor = MagicMock()
        datos = {
            "AMID": "7500900",
            "NOMBRE": "Zona sintética",
            "VERSION_ZP": "V900",
        }

        ubicaciones_repository.upsert_vigente(cursor, datos)

        query, parametros = cursor.execute.call_args.args
        self.assertIn(
            "MERGE INTO USR_LAB.UBICACION_ESPERADA_VALIDADOR destino",
            query,
        )
        self.assertIn("SELECT :AMID AS AMID FROM DUAL", query)
        self.assertIn("WHEN MATCHED THEN", query)
        self.assertIn("WHEN NOT MATCHED THEN", query)
        self.assertEqual(set(parametros), set(ubicaciones_repository.COLUMNAS_ORACLE))
        self.assertEqual(parametros["AMID"], "7500900")
        self.assertEqual(parametros["NOMBRE"], "Zona sintética")
        self.assertEqual(parametros["VERSION_ZP"], "V900")
        self.assertIsNone(parametros["RADIO_METROS"])

    def test_historial_vigente_conserva_select_bind_orden_y_diccionario(self):
        cursor = MagicMock()
        cursor.description = [
            ("ID",),
            ("AMID",),
            ("NOMBRE",),
        ]
        cursor.fetchone.return_value = (9, "7500900", "Zona sintética")

        resultado = ubicaciones_repository.obtener_historial_vigente(
            cursor,
            "7500900",
        )

        query, parametros = cursor.execute.call_args.args
        self.assertIn(
            "FROM USR_LAB.HISTORIAL_UBICACION_ESPERADA",
            query,
        )
        self.assertIn("AND FECHA_FIN_VIGENCIA IS NULL", query)
        self.assertIn("ORDER BY FECHA_INICIO_VIGENCIA DESC", query)
        self.assertEqual(parametros, {"amid": "7500900"})
        self.assertEqual(
            resultado,
            {"ID": 9, "AMID": "7500900", "NOMBRE": "Zona sintética"},
        )

    def test_crear_historial_conserva_insert_binds_y_vigencia_abierta(self):
        cursor = MagicMock()

        ubicaciones_repository.crear_historial(
            cursor,
            {
                "AMID": "7500900",
                "NOMBRE": "Zona sintética",
                "ORIGEN_UBICACION": "excel",
            },
            self.FECHA_CARGA,
        )

        query, parametros = cursor.execute.call_args.args
        self.assertIn(
            "INSERT INTO USR_LAB.HISTORIAL_UBICACION_ESPERADA",
            query,
        )
        self.assertEqual(
            set(parametros),
            set(ubicaciones_repository.COLUMNAS_HISTORIAL),
        )
        self.assertEqual(
            parametros["FECHA_INICIO_VIGENCIA"],
            self.FECHA_CARGA,
        )
        self.assertIsNone(parametros["FECHA_FIN_VIGENCIA"])

    def test_reaparicion_desde_laboratorio_cierra_y_abre_historial_excel(self):
        cursor = MagicMock()
        datos_excel = {
            "AMID": "7500900",
            "NOMBRE": "Zona reactivada",
            "SERIE_VALIDADOR": "SERIE-900",
            "LATITUD_ESPERADA": -33.45,
            "LONGITUD_ESPERADA": -70.66,
            "RADIO_METROS": 150,
            "OPERATIVA": 1,
            "ORIGEN_UBICACION": "excel",
            "VERSION_ZP": "V900",
        }
        historial_laboratorio = {
            **datos_excel,
            "ID": 9,
            "NOMBRE": "Laboratorio Zonas Pagas",
            "OPERATIVA": 0,
            "ORIGEN_UBICACION": "laboratorio_default",
        }

        with patch.object(
            ubicaciones_repository,
            "obtener_historial_vigente",
            return_value=historial_laboratorio,
        ), patch.object(
            ubicaciones_repository,
            "crear_historial",
        ) as mock_crear:
            resultado = ubicaciones_repository.actualizar_historial(
                cursor,
                datos_excel,
                self.FECHA_CARGA,
            )

        query, parametros = cursor.execute.call_args.args
        self.assertIn("SET FECHA_FIN_VIGENCIA = :fecha_carga", query)
        self.assertEqual(
            parametros,
            {"fecha_carga": self.FECHA_CARGA, "id": 9},
        )
        mock_crear.assert_called_once_with(
            cursor,
            datos_excel,
            self.FECHA_CARGA,
        )
        self.assertEqual(resultado, "cerrado_y_nuevo")

    @patch(
        "apps.dashboard.repositories.ubicaciones_repository."
        "obtener_conexion_oracle"
    )
    def test_importacion_usa_una_conexion_cursor_commit_y_cierre(
        self,
        mock_conexion,
    ):
        contexto, conexion, cursor = self.preparar_oracle()
        mock_conexion.return_value = contexto
        datos = {"AMID": "7500900"}
        estadisticas = self.estadisticas()

        with patch.object(
            ubicaciones_repository,
            "existe_vigente",
            return_value=False,
        ) as mock_existe, patch.object(
            ubicaciones_repository,
            "upsert_vigente",
        ) as mock_upsert, patch.object(
            ubicaciones_repository,
            "actualizar_historial",
            return_value="nuevo",
        ) as mock_historial, patch.object(
            ubicaciones_repository,
            "mover_ausentes_a_laboratorio",
            return_value=(0, 0, 0),
        ) as mock_ausentes:
            resultado = ubicaciones_repository.persistir_importacion(
                filas_normalizadas=iter([datos]),
                fecha_carga=self.FECHA_CARGA,
                archivo_origen="ZONA PAGA V900.xlsx",
                version_zp="V900",
                referencia_laboratorio=self.referencia_laboratorio(),
                estadisticas=estadisticas,
            )

        mock_existe.assert_called_once_with(cursor, "7500900")
        mock_upsert.assert_called_once_with(cursor, datos)
        mock_historial.assert_called_once_with(
            cursor=cursor,
            datos=datos,
            fecha_carga=self.FECHA_CARGA,
        )
        mock_ausentes.assert_called_once_with(
            cursor=cursor,
            amids_excel={"7500900"},
            fecha_carga=self.FECHA_CARGA,
            archivo_origen="ZONA PAGA V900.xlsx",
            version_zp="V900",
            referencia_laboratorio=self.referencia_laboratorio(),
        )
        self.assertEqual(resultado["creados_vigente"], 1)
        self.assertEqual(resultado["nuevos_historial"], 1)
        conexion.commit.assert_called_once_with()
        conexion.rollback.assert_not_called()
        conexion.cursor.return_value.__exit__.assert_called_once()
        contexto.__exit__.assert_called_once()

    @patch(
        "apps.dashboard.repositories.ubicaciones_repository."
        "obtener_conexion_oracle"
    )
    def test_importacion_existente_sin_cambios_conserva_estadisticas(
        self,
        mock_conexion,
    ):
        contexto, conexion, _cursor = self.preparar_oracle()
        mock_conexion.return_value = contexto
        estadisticas = self.estadisticas()

        with patch.object(
            ubicaciones_repository,
            "existe_vigente",
            return_value=True,
        ), patch.object(
            ubicaciones_repository,
            "upsert_vigente",
        ), patch.object(
            ubicaciones_repository,
            "actualizar_historial",
            return_value="sin_cambios",
        ), patch.object(
            ubicaciones_repository,
            "mover_ausentes_a_laboratorio",
            return_value=(0, 0, 0),
        ):
            resultado = ubicaciones_repository.persistir_importacion(
                filas_normalizadas=iter([{"AMID": "7500900"}]),
                fecha_carga=self.FECHA_CARGA,
                archivo_origen="ZONA PAGA V900.xlsx",
                version_zp="V900",
                referencia_laboratorio=self.referencia_laboratorio(),
                estadisticas=estadisticas,
            )

        self.assertEqual(resultado["creados_vigente"], 0)
        self.assertEqual(resultado["actualizados_vigente"], 1)
        self.assertEqual(resultado["sin_cambios_historial"], 1)
        conexion.commit.assert_called_once_with()

    @patch(
        "apps.dashboard.repositories.ubicaciones_repository."
        "obtener_conexion_oracle"
    )
    def test_sincronizacion_conserva_procedure_salida_y_validacion(
        self,
        mock_conexion,
    ):
        contexto, conexion, cursor = self.preparar_oracle()
        mock_conexion.return_value = contexto
        ubicaciones_var = MagicMock()
        historiales_var = MagicMock()
        ubicaciones_var.getvalue.return_value = 2
        historiales_var.getvalue.return_value = 3
        cursor.var.side_effect = [ubicaciones_var, historiales_var]
        cursor.fetchone.return_value = (4, 5)

        resultado = ubicaciones_repository.sincronizar_amids_ubicaciones()

        self.assertEqual(cursor.var.call_args_list, [call(int), call(int)])
        cursor.callproc.assert_called_once_with(
            "USR_LAB.PRC_SINC_UBIC_AMID",
            [ubicaciones_var, historiales_var],
        )
        query_validacion = cursor.execute.call_args.args[0]
        self.assertIn("AMID_MAESTRO_ALERTAS", query_validacion)
        self.assertIn("sin_historial_abierto", query_validacion)
        self.assertEqual(
            resultado,
            {
                "ubicaciones_creadas": 2,
                "historiales_creados": 3,
                "sin_ubicacion": 4,
                "sin_historial_abierto": 5,
            },
        )
        conexion.commit.assert_not_called()
        conexion.rollback.assert_not_called()

    @patch(
        "apps.dashboard.repositories.ubicaciones_repository."
        "obtener_conexion_oracle"
    )
    def test_limpieza_conserva_procedure_parametros_y_retorno(
        self,
        mock_conexion,
    ):
        contexto, conexion, cursor = self.preparar_oracle()
        mock_conexion.return_value = contexto
        salida = MagicMock()
        salida.getvalue.return_value = 7
        cursor.var.return_value = salida

        resultado = ubicaciones_repository.limpiar_historial(16)

        cursor.var.assert_called_once_with(int)
        cursor.callproc.assert_called_once_with(
            "USR_LAB.PRC_LIMPIAR_HIST_UBICACION",
            [16, salida],
        )
        self.assertEqual(resultado, 7)
        conexion.commit.assert_not_called()
        conexion.rollback.assert_not_called()
