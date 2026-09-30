"""Pruebas de `oracle_cursor`.

El punto de estas pruebas es fijar la convencion de nombres de columna. El
parametro `minusculas` existe porque los repositorios no coinciden: la mayoria
trabaja en minusculas, pero el flujo GPS y las tablas de validadores dependen de
las columnas de Oracle tal cual, en mayusculas. Si alguien normalizara GPS a
minusculas, el fallo apareceria lejos de aqui, como un KeyError en la vista.
"""

from django.test import SimpleTestCase

from apps.core.oracle import cursor as oracle_cursor


class CursorFalso:
    """Cursor minimo: solo description, fetchone y fetchall."""

    def __init__(self, description, filas):
        self.description = description
        self._filas = filas

    def fetchone(self):
        return self._filas[0] if self._filas else None

    def fetchall(self):
        return self._filas


class ConvencionDeColumnasTests(SimpleTestCase):
    def test_minusculas_true_normaliza_los_nombres(self):
        cursor = CursorFalso([("AMID",), ("NIVEL_ALERTA_GLOBAL",)], [("7500001", "1")])

        resultado = oracle_cursor.mapear_filas(cursor, minusculas=True)

        self.assertEqual(resultado, [{"amid": "7500001", "nivel_alerta_global": "1"}])

    def test_minusculas_false_conserva_los_nombres_de_oracle(self):
        cursor = CursorFalso([("AMID",), ("DRIVERID",)], [("7500001", "999")])

        resultado = oracle_cursor.mapear_filas(cursor, minusculas=False)

        self.assertEqual(resultado, [{"AMID": "7500001", "DRIVERID": "999"}])

    def test_la_convencion_es_obligatoria(self):
        # Sin `minusculas` el helper no deduce nada: la eleccion es de quien
        # llama, para que no se pierda por descuido.
        with self.assertRaises(TypeError):
            oracle_cursor.mapear_filas(CursorFalso([], []), {})

    def test_una_description_malformada_falla_en_vez_de_desalinear(self):
        # Si se filtrara la entrada invalida, `zip` correria los valores un
        # lugar y devolveria datos de la columna equivocada sin avisar.
        cursor = CursorFalso([("AMID",), None], [("7500001", "2")])

        with self.assertRaises(TypeError):
            oracle_cursor.mapear_filas(cursor, minusculas=True)


class MapearUnaFilaTests(SimpleTestCase):
    def test_devuelve_none_sin_filas(self):
        self.assertIsNone(
            oracle_cursor.mapear_fila(CursorFalso([("AMID",)], []), minusculas=True)
        )

    def test_mapea_la_primera_fila(self):
        cursor = CursorFalso([("AMID",), ("NIVEL",)], [("7500001", "2")])

        resultado = oracle_cursor.mapear_fila(cursor, minusculas=True)

        self.assertEqual(resultado, {"amid": "7500001", "nivel": "2"})

    def test_solo_consume_una_fila(self):
        cursor = CursorFalso([("AMID",)], [("7500001",), ("7500002",)])

        resultado = oracle_cursor.mapear_fila(cursor, minusculas=False)

        self.assertEqual(resultado, {"AMID": "7500001"})


class MapearRegistroTests(SimpleTestCase):
    def test_mapea_una_fila_ya_traida_sin_volver_a_leer_el_cursor(self):
        cursor = CursorFalso([("AMID",), ("SERIE_VALIDADOR",)], [])

        resultado = oracle_cursor.mapear_registro(
            cursor, ("7500001", "SER-9"), minusculas=False
        )

        self.assertEqual(resultado, {"AMID": "7500001", "SERIE_VALIDADOR": "SER-9"})

    def test_description_vacio_produce_un_dict_vacio(self):
        resultado = oracle_cursor.mapear_registro(
            CursorFalso([], ("7500001",)), ("7500001",), minusculas=True
        )

        self.assertEqual(resultado, {})
