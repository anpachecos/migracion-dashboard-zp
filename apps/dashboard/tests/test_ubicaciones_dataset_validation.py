from unittest import TestCase

from apps.dashboard.services.ubicaciones_dataset_validation import (
    CAMPO_FILA_ORIGEN,
    formatear_reporte_validacion,
    validar_dataset_ubicaciones,
)


class UbicacionesDatasetValidationTests(TestCase):
    LABORATORIO = {
        "NOMBRE": "Laboratorio Zonas Pagas",
        "LATITUD_ESPERADA": -33.437191,
        "LONGITUD_ESPERADA": -70.656102,
        "RADIO_METROS": 150,
    }

    def fila(self, **cambios):
        datos = {
            CAMPO_FILA_ORIGEN: 2,
            "IDDS": 7500001,
            "NOMBRE": "Zona sintética",
            "OPERATIVA": "SI",
            "LATITUD_ESPERADA": -33.45,
            "LONGITUD_ESPERADA": -70.66,
            "RADIO_METROS": 150,
            "SERIE_VALIDADOR": "SERIE-1",
        }
        datos.update(cambios)
        return datos

    def validar(self, *filas):
        return validar_dataset_ubicaciones(list(filas), self.LABORATORIO)

    def incidencia(self, **cambios):
        resultado = self.validar(self.fila(**cambios))
        self.assertFalse(resultado.es_valido)
        return resultado.incidencias

    def test_dataset_totalmente_valido_se_materializa(self):
        resultado = self.validar(
            self.fila(),
            self.fila(IDDS=7500002, **{CAMPO_FILA_ORIGEN: 3}),
        )
        self.assertTrue(resultado.es_valido)
        self.assertIsInstance(resultado.registros, tuple)
        self.assertEqual(len(resultado.registros), 2)

    def test_nombre_vacio_es_critico(self):
        incidencia = self.incidencia(NOMBRE="   ")[0]
        self.assertEqual((incidencia.campo, incidencia.codigo), ("NOMBRE", "required"))

    def test_nombre_vacio_tambien_es_critico_para_operativa_no(self):
        incidencia = self.incidencia(NOMBRE="", OPERATIVA="NO")[0]
        self.assertEqual(incidencia.campo, "NOMBRE")

    def test_idds_null_es_critico(self):
        self.assertEqual(self.incidencia(IDDS=None)[0].codigo, "required")

    def test_idds_vacio_es_critico(self):
        self.assertEqual(self.incidencia(IDDS="  ")[0].codigo, "required")

    def test_idds_texto_arbitrario_es_critico(self):
        self.assertEqual(self.incidencia(IDDS="ABC")[0].codigo, "invalid_integer")

    def test_idds_decimal_no_entero_no_se_trunca(self):
        self.assertEqual(self.incidencia(IDDS=7500001.7)[0].codigo, "invalid_integer")

    def test_idds_float_entero_es_valido(self):
        resultado = self.validar(self.fila(IDDS=7500001.0))
        self.assertEqual(resultado.registros[0]["IDDS"], "7500001")

    def test_idds_string_numerico_es_valido_y_determinista(self):
        resultado = self.validar(self.fila(IDDS=" 07500001 "))
        self.assertEqual(resultado.registros[0]["AMID"], "7500001")

    def test_idds_negativo_es_critico(self):
        self.assertEqual(self.incidencia(IDDS=-1)[0].codigo, "not_positive")

    def test_idds_cero_es_critico(self):
        self.assertEqual(self.incidencia(IDDS=0)[0].codigo, "not_positive")

    def test_idds_infinito_es_critico(self):
        self.assertEqual(self.incidencia(IDDS=float("inf"))[0].codigo, "invalid_integer")

    def test_idds_nan_es_critico(self):
        self.assertEqual(self.incidencia(IDDS=float("nan"))[0].codigo, "invalid_integer")

    def test_idds_notacion_cientifica_textual_es_critico(self):
        self.assertEqual(self.incidencia(IDDS="7.5e6")[0].codigo, "invalid_integer")

    def test_idds_duplicado_marca_todas_las_filas(self):
        resultado = self.validar(
            self.fila(**{CAMPO_FILA_ORIGEN: 34}),
            self.fila(**{CAMPO_FILA_ORIGEN: 201}),
        )
        duplicados = [i for i in resultado.incidencias if i.codigo == "duplicate"]
        self.assertEqual([i.fila_origen for i in duplicados], [34, 201])
        self.assertIn("filas 34 y 201", duplicados[0].mensaje)

    def test_duplicado_identico_tambien_falla(self):
        resultado = self.validar(self.fila(), self.fila(**{CAMPO_FILA_ORIGEN: 3}))
        self.assertFalse(resultado.es_valido)

    def test_duplicado_conflictivo_tambien_falla(self):
        resultado = self.validar(
            self.fila(), self.fila(NOMBRE="Otra", **{CAMPO_FILA_ORIGEN: 3})
        )
        self.assertFalse(resultado.es_valido)

    def test_operativa_vacia_es_critica(self):
        self.assertEqual(self.incidencia(OPERATIVA="")[0].campo, "OPERATIVA")

    def test_operativa_invalida_es_critica(self):
        self.assertEqual(self.incidencia(OPERATIVA="YES")[0].codigo, "invalid_choice")

    def test_si_y_si_con_tilde_son_aceptados(self):
        for valor in ("SI", "SÍ"):
            with self.subTest(valor=valor):
                self.assertEqual(self.validar(self.fila(OPERATIVA=valor)).registros[0]["OPERATIVA"], 1)

    def test_no_es_aceptado(self):
        self.assertEqual(self.validar(self.fila(OPERATIVA="NO")).registros[0]["OPERATIVA"], 0)

    def test_operativa_es_case_insensitive_y_tolera_espacios(self):
        resultado = self.validar(self.fila(OPERATIVA="  sí "))
        self.assertTrue(resultado.es_valido)

    def test_si_sin_latitud_es_critico(self):
        self.assertEqual(self.incidencia(LATITUD_ESPERADA=None)[0].campo, "LATITUD_ESPERADA")

    def test_si_sin_longitud_es_critico(self):
        self.assertEqual(self.incidencia(LONGITUD_ESPERADA=None)[0].campo, "LONGITUD_ESPERADA")

    def test_si_sin_radio_es_critico(self):
        self.assertEqual(self.incidencia(RADIO_METROS=None)[0].campo, "RADIO_METROS")

    def test_latitud_fuera_de_rango_es_critica(self):
        self.assertEqual(self.incidencia(LATITUD_ESPERADA=91)[0].codigo, "out_of_range")

    def test_longitud_fuera_de_rango_es_critica(self):
        self.assertEqual(self.incidencia(LONGITUD_ESPERADA=-181)[0].codigo, "out_of_range")

    def test_coordenada_nan_es_critica(self):
        self.assertEqual(self.incidencia(LATITUD_ESPERADA=float("nan"))[0].codigo, "invalid_number")

    def test_coordenada_infinita_es_critica(self):
        self.assertEqual(self.incidencia(LONGITUD_ESPERADA=float("inf"))[0].codigo, "invalid_number")

    def test_pareja_cero_cero_es_critica(self):
        incidencias = self.incidencia(LATITUD_ESPERADA=0, LONGITUD_ESPERADA=0)
        self.assertEqual(incidencias[0].codigo, "zero_pair")

    def test_radio_cero_es_critico(self):
        self.assertEqual(self.incidencia(RADIO_METROS=0)[0].codigo, "not_positive")

    def test_radio_negativo_es_critico(self):
        self.assertEqual(self.incidencia(RADIO_METROS=-1)[0].codigo, "not_positive")

    def test_radio_infinito_es_critico(self):
        self.assertEqual(self.incidencia(RADIO_METROS=float("inf"))[0].codigo, "invalid_number")

    def test_no_sin_coordenadas_ni_radio_sigue_valido_y_usa_laboratorio(self):
        resultado = self.validar(self.fila(
            OPERATIVA="NO", LATITUD_ESPERADA=None,
            LONGITUD_ESPERADA=None, RADIO_METROS=None,
        ))
        registro = resultado.registros[0]
        self.assertTrue(resultado.es_valido)
        self.assertEqual(registro["NOMBRE"], self.LABORATORIO["NOMBRE"])
        self.assertEqual(registro["ORIGEN_UBICACION"], "laboratorio")

    def test_serie_ausente_es_valida(self):
        resultado = self.validar(self.fila(SERIE_VALIDADOR=None))
        self.assertIsNone(resultado.registros[0]["SERIE_VALIDADOR"])

    def test_serie_duplicada_esta_permitida(self):
        resultado = self.validar(
            self.fila(),
            self.fila(IDDS=7500002, **{CAMPO_FILA_ORIGEN: 3}),
        )
        self.assertTrue(resultado.es_valido)

    def test_multiples_errores_de_una_fila_se_recopilan(self):
        resultado = self.validar(self.fila(
            IDDS=None, NOMBRE="", OPERATIVA="S",
        ))
        self.assertEqual(len(resultado.incidencias), 3)
        self.assertEqual(resultado.total_filas_con_error, 1)

    def test_errores_de_multiples_filas_se_recopilan(self):
        resultado = self.validar(
            self.fila(IDDS=None),
            self.fila(IDDS=7500002, NOMBRE="", **{CAMPO_FILA_ORIGEN: 3}),
        )
        self.assertEqual(resultado.total_filas_con_error, 2)
        self.assertEqual(len(resultado.incidencias), 2)

    def test_reporte_contiene_fila_campo_valor_motivo_y_no_persistencia(self):
        resultado = self.validar(self.fila(OPERATIVA="S", **{CAMPO_FILA_ORIGEN: 28}))
        reporte = formatear_reporte_validacion(resultado)
        self.assertIn("Fila 28 | IDDS 7500001 | OPERATIVA", reporte)
        self.assertIn('Valor "S"', reporte)
        self.assertIn("Use SI, SÍ o NO", reporte)
        self.assertIn("Oracle no fue modificado", reporte)

    def test_reporte_no_inyecta_saltos_desde_valor(self):
        resultado = self.validar(self.fila(OPERATIVA="S\nvalor inyectado"))
        reporte = formatear_reporte_validacion(resultado)
        self.assertIn('Valor "S valor inyectado"', reporte)

    def test_dataset_invalido_no_expone_registros_ni_amids_parciales(self):
        resultado = self.validar(
            self.fila(),
            self.fila(IDDS=None, **{CAMPO_FILA_ORIGEN: 3}),
        )
        self.assertEqual(resultado.registros, ())
        self.assertEqual(resultado.amids_presentes, frozenset())

    def test_amids_confiables_contienen_todos_los_idds_validos(self):
        resultado = self.validar(
            self.fila(),
            self.fila(IDDS="7500002", **{CAMPO_FILA_ORIGEN: 3}),
        )
        self.assertEqual(resultado.amids_presentes, {"7500001", "7500002"})

    def test_validacion_funciona_con_mappings_sinteticos_sin_pandas(self):
        fila = dict(self.fila())
        fila.pop(CAMPO_FILA_ORIGEN)
        resultado = validar_dataset_ubicaciones([fila], self.LABORATORIO)
        self.assertTrue(resultado.es_valido)
        self.assertEqual(resultado.registros[0]["AMID"], "7500001")
