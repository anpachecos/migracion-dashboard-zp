"""
Pruebas del service común de TRX.

Se prueba sin Oracle: se ejercita la normalización de filas, los agregados y la
validación de filtros. Cuando `TRX_ORACLE_HABILITADO` está apagado (que es el
valor por defecto), `obtener_dataset_base` no debe tocar la conexión.
"""

import ast
import datetime
import re
from pathlib import Path
from unittest import mock

from django.conf import settings as django_settings
from django.test import RequestFactory, SimpleTestCase

from apps.transacciones.services import trx_reglas, trx_service


def fila_cruda(
    fec_trx,
    fec_bd,
    nid_contexto_opte="1",
    amid=7_500_001,
    nombre_entidad="Operador Uno",
    nombre_sitio="Sitio Uno",
):
    return {
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


class NormalizacionTests(SimpleTestCase):
    def test_normaliza_una_trx_valida(self):
        fila = fila_cruda(
            datetime.datetime(2026, 8, 27, 10, 0, 0),
            datetime.datetime(2026, 8, 27, 10, 16, 30),
        )

        trx = trx_service.normalizar_fila(fila)

        self.assertTrue(trx["datos_validos"])
        self.assertFalse(trx["desfase_reloj"])
        self.assertEqual(trx["duracion_segundos"], 990)
        self.assertEqual(trx["duracion_texto"], "00:16:30")
        self.assertEqual(trx["duracion_minutos"], 16.5)
        self.assertTrue(trx["es_mismo_dia"])
        self.assertFalse(trx["es_rezagada"])
        self.assertTrue(trx["es_mayor_15"])
        self.assertEqual(trx["dias_rezago"], 0)
        self.assertEqual(trx["tramo_clave"], "15_a_30")

    def test_exclusividad_entre_rezagada_y_mayor_15(self):
        combos = [
            (
                datetime.datetime(2026, 8, 27, 23, 50, 0),
                datetime.datetime(2026, 8, 28, 0, 20, 0),
            ),
            (
                datetime.datetime(2026, 8, 27, 10, 0, 0),
                datetime.datetime(2026, 8, 27, 10, 20, 0),
            ),
            (
                datetime.datetime(2026, 8, 27, 10, 0, 0),
                datetime.datetime(2026, 8, 27, 10, 0, 1),
            ),
        ]

        for fec_trx, fec_bd in combos:
            with self.subTest(trx=f"{fec_trx} -> {fec_bd}"):
                trx = trx_service.normalizar_fila(fila_cruda(fec_trx, fec_bd))
                self.assertFalse(
                    trx["es_rezagada"] and trx["es_mayor_15"],
                    "Una TRX no puede ser rezagada y mayor a 15 min a la vez.",
                )

    def test_fechas_ausentes_no_inventan_duracion(self):
        trx = trx_service.normalizar_fila(fila_cruda(None, None))

        self.assertFalse(trx["datos_validos"])
        self.assertIsNone(trx["duracion_segundos"])
        self.assertEqual(trx["duracion_texto"], "Sin dato")
        self.assertEqual(trx["clasificacion"], trx_reglas.CLASIFICACION_SIN_DATO)
        self.assertEqual(trx["tramo_clave"], "")
        self.assertFalse(trx["es_mayor_15"])
        self.assertFalse(trx["es_rezagada"])

    def test_desfase_de_reloj_se_marca_sin_generar_duracion(self):
        trx = trx_service.normalizar_fila(
            fila_cruda(
                datetime.datetime(2026, 8, 27, 12, 0, 0),
                datetime.datetime(2026, 8, 27, 10, 0, 0),
            )
        )

        self.assertTrue(trx["desfase_reloj"])
        self.assertFalse(trx["datos_validos"])
        self.assertIsNone(trx["duracion_segundos"])
        self.assertFalse(trx["es_mayor_15"])

    def test_textos_vacios_caen_en_defecto(self):
        fila = fila_cruda(
            datetime.datetime(2026, 8, 27, 10, 0, 0),
            datetime.datetime(2026, 8, 27, 10, 0, 1),
        )
        fila["nombre_entidad"] = None
        fila["nombre_sitio"] = "   "

        trx = trx_service.normalizar_fila(fila)

        self.assertEqual(trx["nombre_entidad"], "Sin operador")
        self.assertEqual(trx["nombre_sitio"], "Sin sitio")

    def test_un_join_sin_coincidencia_no_deja_identificadores_vacios(self):
        fila = fila_cruda(
            datetime.datetime(2026, 8, 27, 10, 0, 0),
            datetime.datetime(2026, 8, 27, 10, 0, 1),
        )
        fila["nombre_entidad"] = None
        fila["nombre_sitio"] = None

        trx = trx_service.normalizar_fila(fila)

        self.assertEqual(trx["nombre_entidad"], "Sin operador")
        self.assertEqual(trx["nombre_sitio"], "Sin sitio")

    def test_identificadores_numericos_llegan_como_texto(self):
        trx = trx_service.normalizar_fila(
            fila_cruda(
                datetime.datetime(2026, 8, 27, 10, 0, 0),
                datetime.datetime(2026, 8, 27, 10, 0, 1),
                amid=7500001,
            )
        )

        self.assertEqual(trx["amid"], "7500001")
        self.assertEqual(trx["nid_sitio"], "1234")


class PrecedenciaDeEstadoTests(SimpleTestCase):
    """
    La columna `Estado` es un resumen de las dos reglas, no una tercera.

    El orden importa: sin datos no se afirma nada, el cambio de día calendario
    manda sobre la duración, y "dentro de rango" es el residuo.
    """

    def _estado(self, mayor_15, rezagada, datos_validos):
        return trx_service._estado_texto(mayor_15, rezagada, datos_validos)

    def test_sin_datos_tiene_prioridad_sobre_todo(self):
        self.assertEqual(
            self._estado(mayor_15=False, rezagada=False, datos_validos=False),
            trx_service.ESTADO_SIN_DATO,
        )
        # Aunque las otras dos banderas vinieran encendidas por un error.
        self.assertEqual(
            self._estado(mayor_15=True, rezagada=True, datos_validos=False),
            trx_service.ESTADO_SIN_DATO,
        )

    def test_rezagada_tiene_prioridad_sobre_el_umbral(self):
        self.assertEqual(
            self._estado(mayor_15=True, rezagada=True, datos_validos=True),
            trx_service.ESTADO_REZAGADA,
        )

    def test_cada_estado_es_exclusivo(self):
        casos = {
            (False, False, False): trx_service.ESTADO_SIN_DATO,
            (True, True, True): trx_service.ESTADO_REZAGADA,
            (True, False, True): trx_service.ESTADO_MAYOR_15,
            (False, False, True): trx_service.ESTADO_DENTRO_DE_RANGO,
        }

        for (mayor_15, rezagada, valido), esperado in casos.items():
            with self.subTest(mayor_15=mayor_15, rezagada=rezagada, valido=valido):
                self.assertEqual(
                    self._estado(mayor_15, rezagada, valido),
                    esperado,
                )

    def test_el_orden_publicado_coincide_con_la_implementacion(self):
        self.assertEqual(
            trx_reglas.PRECEDENCIA_ESTADOS,
            (
                trx_service.ESTADO_SIN_DATO,
                trx_service.ESTADO_REZAGADA,
                trx_service.ESTADO_MAYOR_15,
                trx_service.ESTADO_DENTRO_DE_RANGO,
            ),
        )

    def test_la_clase_css_corresponde_al_estado(self):
        esperado = {
            trx_service.ESTADO_SIN_DATO: "trx-clase-sin-dato",
            trx_service.ESTADO_REZAGADA: "trx-clase-rezagada",
            trx_service.ESTADO_MAYOR_15: "trx-clase-alto",
            trx_service.ESTADO_DENTRO_DE_RANGO: "trx-clase-ok",
        }

        for (mayor_15, rezagada, valido), (estado, clase) in zip(
            [
                (False, False, False),
                (True, True, True),
                (True, False, True),
                (False, False, True),
            ],
            esperado.items(),
        ):
            with self.subTest(estado=estado):
                self.assertEqual(
                    trx_service._clase_estado(mayor_15, rezagada, valido),
                    clase,
                )

    def test_el_estado_real_de_una_rezagada_corta_no_es_verde(self):
        # El caso que motiva la columna: 2 minutos de diferencia, otro día.
        trx = trx_service.normalizar_fila(
            fila_cruda(
                datetime.datetime(2026, 8, 26, 23, 59, 0),
                datetime.datetime(2026, 8, 27, 0, 1, 0),
            )
        )

        self.assertEqual(trx["clasificacion"], trx_reglas.CLASIFICACION_HASTA_5)
        self.assertEqual(trx["estado_texto"], trx_service.ESTADO_REZAGADA)


class EtiquetasDerivadasDelUmbralTests(SimpleTestCase):
    """
    El texto visible tiene que seguir al umbral, no a una copia del número.

    Si alguien sube `UMBRAL_CORTE_MINUTOS` a 10, la regla cambia; si las
    etiquetas tuvieran "15" escrito a mano, la pantalla empezaría a mentir.
    """

    def test_el_estado_deriva_del_umbral(self):
        self.assertEqual(
            trx_service.ESTADO_MAYOR_15,
            trx_reglas.ETIQUETA_ESTADO_UMBRAL,
        )
        self.assertIn(
            str(trx_reglas.UMBRAL_CORTE_MINUTOS),
            trx_service.ESTADO_MAYOR_15,
        )

    def test_todas_las_etiquetas_mencionan_el_umbral(self):
        etiquetas = {
            nombre: getattr(trx_reglas, nombre)
            for nombre in (
                "ETIQUETA_ESTADO_UMBRAL",
                "ETIQUETA_KPI_MAYOR",
                "ETIQUETA_MISMO_DIA_MAYOR",
                "ETIQUETA_DIAS_MAYOR",
                "ETIQUETA_COMPARATIVO_MENSUAL",
                "ETIQUETA_DETALLE_MAYOR",
                "ETIQUETA_ARIA_MAYOR",
            )
        }

        for nombre, texto in etiquetas.items():
            with self.subTest(etiqueta=nombre):
                self.assertIn(
                    str(trx_reglas.UMBRAL_CORTE_MINUTOS),
                    texto,
                    f"{nombre} no menciona el umbral vigente.",
                )

    def test_los_textos_visibles_no_reescriben_el_numero_del_corte(self):
        """
        Barre la app buscando el umbral escrito a mano.

        Solo se revisan literales de cadena que llegan a la pantalla y literales
        numéricos. Se ignoran a propósito:

        - `trx_reglas`, que es la fuente.
        - Docstrings y comentarios, que no son salida visible.
        - Identificadores como `mayor_15` o `es_mayor_15`, que contienen los
          dígitos pero no son un número mágico.

        Un "15" suelto en un string de etiqueta o en un cálculo es exactamente
        el defecto que esta prueba existe para evitar.
        """

        raiz = Path(trx_service.__file__).resolve().parent.parent
        umbral = trx_reglas.UMBRAL_CORTE_MINUTOS
        # El umbral no puede quedar pegado a una letra ni a otro dígito: así
        # "mayor_15" y "115" no cuentan, pero "> 15 min" sí.
        #
        # El guion también queda como carácter pegado a la izquierda porque una
        # fecha ISO no es el umbral: "2026-08-15" es el día quince del mes, no
        # un número mágico escrito a mano. Sin esta salvedad los datos de
        # referencia del monitor no podrían existir en los archivos js.
        patron_umbral = re.compile(rf"(?<![\w.,-]){umbral}(?![\w.,])")
        excluidos = {Path(trx_reglas.__file__).resolve()}
        infracciones = []

        for patron in ("services/*.py", "repositories/*.py", "views.py"):
            for ruta in sorted(raiz.glob(patron)):
                if ruta.resolve() in excluidos or "__pycache__" in ruta.parts:
                    continue
                for linea, literales in self._literales_visibles(ruta):
                    for texto in literales:
                        if isinstance(texto, str) and patron_umbral.search(texto):
                            infracciones.append(
                                f"{ruta.relative_to(raiz)}:{linea} (cadena {texto!r})"
                            )
                        elif isinstance(texto, (int, float)) and texto == umbral:
                            infracciones.append(
                                f"{ruta.relative_to(raiz)}:{linea} (numero {texto!r})"
                            )

        for patron in (
            "templates/transacciones/*.html",
            "templates/transacciones/partials/*.html",
            "static/transacciones/js/*.js",
        ):
            for ruta in sorted(raiz.glob(patron)):
                for numero_linea, texto in self._sin_comentarios(ruta):
                    if patron_umbral.search(texto):
                        infracciones.append(
                            f"{ruta.relative_to(raiz)}:{numero_linea}"
                        )

        self.assertEqual(
            infracciones,
            [],
            "El umbral aparece escrito a mano fuera de trx_reglas:\n  - "
            + "\n  - ".join(infracciones),
        )

    def test_el_guardian_permite_las_fechas_iso(self):
        """La salvedad del guion no relaja lo que tiene que seguir saltando.

        Se prueban los dos lados a la vez. Solo la fecha ISO queda cubierta,
        porque es la única forma en que el umbral aparece precedido por un
        guion; un "15" suelto seguido de coma, punto o letra tampoco es el
        número mágico que se busca. Lo que tiene que seguir saltando es el 15
        que funciona como cantidad.
        """

        umbral = trx_reglas.UMBRAL_CORTE_MINUTOS
        patron = re.compile(rf"(?<![\w.,-]){umbral}(?![\w.,])")

        # El día quince escrito como fecha no es el umbral a mano.
        for texto in (
            "2026-08-15",
            "2026-{:02d}-01".format(umbral),
            "2026-08-{:02d}T00:00".format(umbral),
        ):
            with self.subTest(texto=texto):
                self.assertIsNone(patron.search(texto))

        # Números pegados, decimales e identificadores tampoco son el umbral.
        for texto in (
            "mayor_15",
            "115",
            "015",
            "1,15",
            "1.15",
        ):
            with self.subTest(texto=texto):
                self.assertIsNone(patron.search(texto))

        # Y esto sí: el umbral escrito como cantidad, que es el defecto real.
        for texto in (
            "> 15 min",
            "15 minutos",
            "promedio de 15",
            "15 o más",
            "umbral 15",
            "15%",
        ):
            with self.subTest(texto=texto):
                self.assertIsNotNone(patron.search(texto))

    @staticmethod
    def _literales_visibles(ruta):
        """
        Devuelve (linea, literales) de un .py, saltando docstrings.

        Se usa el AST: los comentarios ni siquiera llegan al árbol y las
        docstrings se descartan por ser el primer statement de su modulo, clase
        o funcion.
        """

        arbol = ast.parse(ruta.read_text(encoding="utf-8"))

        docstrings = set()
        for nodo in ast.walk(arbol):
            if isinstance(
                nodo,
                (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
            ):
                doc = ast.get_docstring(nodo, clean=False)
                if doc is not None:
                    docstrings.add(doc)

        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Constant) and nodo.value not in docstrings:
                yield nodo.lineno, (nodo.value,)

    @staticmethod
    def _sin_comentarios(ruta):
        """Quita bloques de comentario de Django y comentarios de una linea."""

        texto = ruta.read_text(encoding="utf-8")

        texto = re.sub(
            r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}",
            "",
            texto,
            flags=re.DOTALL,
        )
        texto = re.sub(r"\{#.*?#\}", "", texto, flags=re.DOTALL)
        texto = re.sub(r"<!--.*?-->", "", texto, flags=re.DOTALL)
        texto = re.sub(r"(?m)//.*$", "", texto)
        texto = re.sub(r"(?m)^\s*#.*$", "", texto)

        for numero_linea, linea in enumerate(texto.splitlines(), start=1):
            yield numero_linea, linea


class EstadoTests(SimpleTestCase):
    """
    El estado resume las dos reglas del modulo.

    Sin el, una rezagada de dos minutos aparece como "<= 5 min" en verde, lo
    que no describe su problema real.
    """

    def estado(self, fec_trx, fec_bd):
        return trx_service.normalizar_fila(fila_cruda(fec_trx, fec_bd))

    def test_rezagada_corta_no_se_muestra_como_dentro_de_rango(self):
        trx = self.estado(
            datetime.datetime(2026, 8, 26, 23, 59, 0),
            datetime.datetime(2026, 8, 27, 0, 1, 0),
        )

        self.assertEqual(trx["duracion_segundos"], 120)
        self.assertEqual(trx["estado_texto"], trx_service.ESTADO_REZAGADA)
        self.assertEqual(trx["clase_estado"], "trx-clase-rezagada")

    def test_mismo_dia_sobre_quince_min(self):
        trx = self.estado(
            datetime.datetime(2026, 8, 27, 10, 0, 0),
            datetime.datetime(2026, 8, 27, 10, 20, 0),
        )

        self.assertEqual(trx["estado_texto"], trx_service.ESTADO_MAYOR_15)
        self.assertEqual(trx["clase_estado"], "trx-clase-alto")

    def test_mismo_dia_dentro_de_rango(self):
        trx = self.estado(
            datetime.datetime(2026, 8, 27, 10, 0, 0),
            datetime.datetime(2026, 8, 27, 10, 0, 30),
        )

        self.assertEqual(trx["estado_texto"], trx_service.ESTADO_DENTRO_DE_RANGO)
        self.assertEqual(trx["clase_estado"], "trx-clase-ok")

    def test_quince_min_exactos_no_es_mayor_15(self):
        trx = self.estado(
            datetime.datetime(2026, 8, 27, 10, 0, 0),
            datetime.datetime(2026, 8, 27, 10, 15, 0),
        )

        self.assertEqual(trx["estado_texto"], trx_service.ESTADO_DENTRO_DE_RANGO)

    def test_sin_datos_utiles(self):
        trx = self.estado(None, None)

        self.assertEqual(trx["estado_texto"], trx_service.ESTADO_SIN_DATO)
        self.assertEqual(trx["clase_estado"], "trx-clase-sin-dato")

    def test_desfase_de_reloj_no_se_reporta_como_dentro_de_rango(self):
        trx = self.estado(
            datetime.datetime(2026, 8, 27, 12, 0, 0),
            datetime.datetime(2026, 8, 27, 10, 0, 0),
        )

        self.assertEqual(trx["estado_texto"], trx_service.ESTADO_SIN_DATO)


class AgregadosTests(SimpleTestCase):
    def setUp(self):
        self.dataset = [
            trx_service.normalizar_fila(
                fila_cruda(
                    datetime.datetime(2026, 8, 27, 10, 0, 0),
                    datetime.datetime(2026, 8, 27, 10, 0, 30),
                )
            ),
            trx_service.normalizar_fila(
                fila_cruda(
                    datetime.datetime(2026, 8, 27, 11, 0, 0),
                    datetime.datetime(2026, 8, 27, 11, 20, 0),
                    nid_contexto_opte="2",
                )
            ),
            trx_service.normalizar_fila(
                fila_cruda(
                    datetime.datetime(2026, 8, 26, 23, 59, 0),
                    datetime.datetime(2026, 8, 27, 0, 1, 0),
                    nid_contexto_opte="3",
                )
            ),
        ]

    def test_conteos_y_porcentuales(self):
        agregados = trx_service.resumir_dataset(self.dataset)

        self.assertEqual(agregados["total_trx"], 3)
        self.assertEqual(agregados["total_mayor_15"], 1)
        self.assertEqual(agregados["total_rezagadas"], 1)
        self.assertEqual(agregados["dias_problematicos"], 1)
        self.assertEqual(agregados["maximo_dias_rezago"], 1)
        self.assertEqual(agregados["porcentual_mayor_15"], 33.33)
        self.assertEqual(agregados["porcentual_rezagadas"], 33.33)

    def test_dataset_vacio_no_divide_entre_cero(self):
        agregados = trx_service.resumir_dataset([])

        self.assertEqual(agregados["total_trx"], 0)
        self.assertEqual(agregados["porcentual_mayor_15"], 0.0)
        self.assertEqual(agregados["porcentual_rezagadas"], 0.0)
        self.assertEqual(agregados["maximo_dias_rezago"], 0)

    def test_porcentual_de_cero(self):
        self.assertEqual(trx_service.calcular_porcentual(0, 0), 0.0)
        self.assertEqual(trx_service.calcular_porcentual(1, 4), 25.0)


class FiltrosTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.hoy = datetime.date(2026, 8, 27)

    def obtener(self, **params):
        request = self.factory.get("/transacciones/informe-interno/", params)
        return trx_service.obtener_filtros_trx(request, hoy=self.hoy)

    def test_sin_parametros_usa_el_dia_de_hoy(self):
        filtros = self.obtener()

        self.assertEqual(filtros["fecha_desde"], self.hoy)
        self.assertEqual(filtros["fecha_hasta"], self.hoy)
        self.assertEqual(filtros["dias_rango"], 1)
        self.assertEqual(filtros["fecha_hasta_exclusiva"], datetime.date(2026, 8, 28))

    def test_fecha_suelta_cubre_ese_dia(self):
        filtros = self.obtener(fecha="2026-08-20")

        self.assertEqual(filtros["fecha_desde"], datetime.date(2026, 8, 20))
        self.assertEqual(filtros["fecha_hasta"], datetime.date(2026, 8, 20))

    def test_rango_inclusive_de_ambos_extremos(self):
        filtros = self.obtener(fecha_desde="2026-08-24", fecha_hasta="2026-08-26")

        self.assertEqual(filtros["dias_rango"], 3)
        self.assertEqual(filtros["fecha_hasta_exclusiva"], datetime.date(2026, 8, 27))

    def test_rango_maximo_se_respeta(self):
        with self.assertRaises(ValueError):
            self.obtener(fecha_desde="2026-08-01", fecha_hasta="2026-08-27")

    def test_rango_invertido_falla(self):
        with self.assertRaises(ValueError):
            self.obtener(fecha_desde="2026-08-26", fecha_hasta="2026-08-24")

    def test_fecha_inexistente_falla(self):
        with self.assertRaises(ValueError):
            self.obtener(fecha="27-08-2026")

    def test_amid_no_numerico_falla(self):
        with self.assertRaises(ValueError):
            self.obtener(amid="7.500.001")

    def test_amid_con_demasiados_digitos_falla(self):
        with self.assertRaises(ValueError):
            self.obtener(amid="12345678")

    def test_origen_invalido_cae_en_el_default(self):
        filtros = self.obtener(origen="otro")

        self.assertEqual(filtros["origen"], trx_service.ORIGEN_TRX)

    def test_origen_bd_se_acepta(self):
        filtros = self.obtener(origen="bd")

        self.assertEqual(filtros["origen"], trx_service.ORIGEN_BD)

    def test_solo_mismo_dia_solo_acepta_el_valor_explicito(self):
        self.assertTrue(self.obtener(solo_mismo_dia="1")["solo_mismo_dia"])
        self.assertFalse(self.obtener(solo_mismo_dia="0")["solo_mismo_dia"])


class FeatureFlagTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.hoy = datetime.date(2026, 8, 27)

    def test_con_oracle_apagado_no_se_consulta(self):
        request = self.factory.get("/transacciones/informe-interno/")
        filtros = trx_service.obtener_filtros_trx(request, hoy=self.hoy)

        with self.settings(TRX_ORACLE_HABILITADO=False):
            resultado = trx_service.obtener_dataset_base(filtros)

        self.assertFalse(resultado["consultado"])
        self.assertEqual(resultado["dataset"], [])
        self.assertEqual(resultado["total"], 0)
        self.assertEqual(resultado["mensaje"], trx_service.MENSAJE_ORACLE_DESHABILITADO)

    def test_oracle_apagado_es_el_default_del_proyecto(self):
        self.assertFalse(
            getattr(django_settings, "TRX_ORACLE_HABILITADO", False),
            "El módulo debe seguir apagado por defecto.",
        )

    def test_fallo_de_oracle_no_rompe_la_pantalla(self):
        request = self.factory.get("/transacciones/informe-interno/")

        with mock.patch(
            "apps.transacciones.services.trx_service.obtener_dataset_base",
            side_effect=RuntimeError("ORA-03113"),
        ):
            contexto = trx_service.construir_contexto_comun(
                request,
                pestana_activa="informe_interno",
                titulo="Informe Interno",
                descripcion="",
                hoy=self.hoy,
            )

        self.assertIn("No fue posible consultar", contexto["mensaje"])
        self.assertEqual(contexto["dataset"], [])
        self.assertFalse(contexto["consultado"])
        self.assertEqual(contexto["agregados"]["total_trx"], 0)


class ContextoComunTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.hoy = datetime.date(2026, 8, 27)

    def test_error_de_validacion_no_rompe_la_pantalla(self):
        request = self.factory.get(
            "/transacciones/informe-interno/",
            {"fecha_desde": "2026-08-01", "fecha_hasta": "2026-08-27"},
        )

        contexto = trx_service.construir_contexto_comun(
            request,
            pestana_activa="informe_interno",
            titulo="Informe Interno",
            descripcion="",
            hoy=self.hoy,
        )

        self.assertIn("rango máximo", contexto["mensaje"].lower())
        self.assertEqual(contexto["dataset"], [])
        self.assertEqual(contexto["filtros"]["fecha_desde"], self.hoy)

    def test_consultas_validadas_sigue_en_falso(self):
        self.assertFalse(trx_service.CONSULTAS_VALIDADAS)

    def test_rangos_sugeridos_son_cortos(self):
        rangos = trx_service.construir_rangos_sugeridos(self.hoy)

        for rango in rangos:
            with self.subTest(rango=rango["clave"]):
                dias = (rango["fecha_hasta"] - rango["fecha_desde"]).days + 1
                self.assertLessEqual(dias, 7)


class QuerystringTests(SimpleTestCase):
    def test_conserva_los_filtros_al_cambiar_de_pestana(self):
        filtros = {
            "fecha_desde": datetime.date(2026, 8, 27),
            "fecha_hasta": datetime.date(2026, 8, 27),
            "amid": "7500001",
            "nidsitio": "1234",
            "nmodo": "4",
            "origen": "trx",
            "solo_mismo_dia": False,
        }

        query = trx_service.construir_querystring(filtros)

        self.assertIn("fecha_desde=2026-08-27", query)
        self.assertIn("amid=7500001", query)
        self.assertNotIn("solo_mismo_dia", query)

    def test_activa_solo_mismo_dia(self):
        query = trx_service.construir_querystring({}, solo_mismo_dia="1")

        self.assertEqual(query, "solo_mismo_dia=1")

    def test_valor_vacio_omite_el_parametro(self):
        query = trx_service.construir_querystring({"amid": "7500001"}, amid=None)

        self.assertEqual(query, "")
