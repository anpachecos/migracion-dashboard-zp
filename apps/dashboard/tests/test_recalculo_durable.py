import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from apps.dashboard.repositories import reglas_alertas_repository
from apps.dashboard.services import reglas_alertas_service


class RecalculoDurableSettingsTests(SimpleTestCase):
    RAIZ_PROYECTO = Path(__file__).resolve().parents[3]
    AUSENTE = object()
    SCRIPT_CARGA_SETTINGS = r"""
import json
from unittest.mock import patch

with patch("dotenv.load_dotenv", return_value=False):
    import config.settings as project_settings

print(json.dumps({
    "durable_enabled": project_settings.ALERTAS_RECALCULO_DURABLE_ENABLED,
}))
"""

    def cargar_flag(self, valor=AUSENTE):
        entorno = os.environ.copy()
        entorno["SECRET_KEY"] = "clave-sintetica-exclusiva-para-tests-1234567890"
        entorno.pop("ALERTAS_RECALCULO_DURABLE_ENABLED", None)
        if valor is not self.AUSENTE:
            entorno["ALERTAS_RECALCULO_DURABLE_ENABLED"] = valor

        proceso = subprocess.run(
            [sys.executable, "-c", self.SCRIPT_CARGA_SETTINGS],
            cwd=self.RAIZ_PROYECTO,
            env=entorno,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        salida = proceso.stdout.strip().splitlines()
        datos = json.loads(salida[-1]) if salida else {}
        self.assertEqual(proceso.returncode, 0, proceso.stderr)
        return datos["durable_enabled"]

    def test_flag_ausente_usa_false_por_default(self):
        self.assertIs(self.cargar_flag(), False)

    def test_flag_false_es_false(self):
        self.assertIs(self.cargar_flag("False"), False)

    def test_flag_true_es_true(self):
        self.assertIs(self.cargar_flag("True"), True)


class SolicitudRecalculoRepositoryTests(SimpleTestCase):
    def preparar_oracle(self):
        conexion = MagicMock(name="conexion_oracle_falsa")
        cursor = MagicMock(name="cursor_oracle_falso")
        conexion.cursor.return_value.__enter__.return_value = cursor
        contexto = MagicMock(name="contexto_oracle_falso")
        contexto.__enter__.return_value = conexion
        return contexto, conexion, cursor

    @patch(
        "apps.dashboard.repositories.reglas_alertas_repository.uuid.uuid4"
    )
    @patch(
        "apps.dashboard.services.oracle_connection.obtener_conexion_oracle"
    )
    def test_crear_solicitud_durable_pendiente_confirma(
        self,
        mock_conexion,
        mock_uuid,
    ):
        contexto, conexion, cursor = self.preparar_oracle()
        mock_conexion.return_value = contexto
        mock_uuid.return_value.hex = "a" * 32

        resultado = reglas_alertas_repository.crear_solicitud_recalculo(
            "rapido",
            "admin",
        )

        query, parametros = cursor.execute.call_args.args
        self.assertIn("ALERTA_RECALCULO_SOLICITUD", query)
        self.assertNotIn("PRC_RECLASIFICAR_ALERTAS", query)
        self.assertEqual(parametros["solicitud_id"], "A" * 32)
        self.assertEqual(parametros["modo"], "RAPIDO")
        self.assertEqual(parametros["usuario_solicitante"], "admin")
        self.assertEqual(resultado["estado"], "PENDIENTE")
        conexion.commit.assert_called_once_with()
        conexion.rollback.assert_not_called()

    @patch(
        "apps.dashboard.services.oracle_connection.obtener_conexion_oracle"
    )
    def test_crear_solicitud_revierte_si_oracle_falla(self, mock_conexion):
        contexto, conexion, cursor = self.preparar_oracle()
        cursor.execute.side_effect = RuntimeError("fallo sintético")
        mock_conexion.return_value = contexto

        with self.assertRaisesRegex(RuntimeError, "fallo sintético"):
            reglas_alertas_repository.crear_solicitud_recalculo(
                "completo",
                "admin",
            )

        conexion.commit.assert_not_called()
        conexion.rollback.assert_called_once_with()

    @patch(
        "apps.dashboard.services.oracle_connection.obtener_conexion_oracle"
    )
    def test_consultar_solicitud_no_encontrada_retorna_none(self, mock_conexion):
        contexto, _conexion, cursor = self.preparar_oracle()
        cursor.fetchone.return_value = None
        mock_conexion.return_value = contexto

        resultado = reglas_alertas_repository.obtener_estado_solicitud_recalculo(
            "F" * 32
        )

        self.assertIsNone(resultado)
        self.assertEqual(
            cursor.execute.call_args.args[1],
            {"solicitud_id": "F" * 32},
        )


class RecalculoDurableFeatureFlagTests(SimpleTestCase):
    @override_settings(ALERTAS_RECALCULO_DURABLE_ENABLED=True)
    @patch.object(reglas_alertas_service.threading, "Thread")
    @patch.object(
        reglas_alertas_service.reglas_alertas_repository,
        "crear_solicitud_recalculo",
    )
    def test_flag_activa_encola_sin_crear_thread(self, mock_crear, mock_thread):
        mock_crear.return_value = {
            "solicitud_id": "A" * 32,
            "origen": "DJANGO_PANEL",
            "modo": "RAPIDO",
            "estado": "PENDIENTE",
            "usuario_solicitante": "admin",
        }

        resultado = reglas_alertas_service.iniciar_recalculo_en_segundo_plano(
            modo_recalculo="rapido",
            usuario_solicitante="admin",
        )

        self.assertEqual(resultado["tipo"], "durable")
        self.assertEqual(resultado["estado"], "PENDIENTE")
        mock_crear.assert_called_once_with(
            modo_recalculo="rapido",
            usuario_solicitante="admin",
        )
        mock_thread.assert_not_called()

    @override_settings(ALERTAS_RECALCULO_DURABLE_ENABLED=False)
    @patch.object(reglas_alertas_service.threading, "Thread")
    def test_flag_inactiva_conserva_thread_daemon(self, mock_thread):
        if reglas_alertas_service._recalculo_lock.locked():
            reglas_alertas_service._recalculo_lock.release()
        hilo = MagicMock(name="thread_falso")
        mock_thread.return_value = hilo

        resultado = reglas_alertas_service.iniciar_recalculo_en_segundo_plano(
            modo_recalculo="rapido",
            log_path="ruta-sintetica.log",
            usuario_solicitante="admin",
        )

        self.assertIs(resultado, hilo)
        self.assertTrue(mock_thread.call_args.kwargs["daemon"])
        hilo.start.assert_called_once_with()
        reglas_alertas_service._recalculo_lock.release()


class RecalculoDurableSqlArtifactsTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.carpeta = (
            Path(__file__).resolve().parents[3]
            / "oracle"
            / "pending"
            / "bkl-002c"
        )

    def leer_sql(self, nombre):
        return (self.carpeta / nombre).read_text(encoding="utf-8")

    def test_scripts_operativos_son_compatibles_con_oracle_11g(self):
        for ruta in self.carpeta.glob("*.sql"):
            contenido = ruta.read_text(encoding="utf-8").upper()
            self.assertNotIn("FETCH FIRST", contenido, ruta.name)

    def test_no_existe_takeover_automatico_por_expiracion(self):
        package = self.leer_sql("02_create_pkg_alerta_lease.sql").upper()
        self.assertNotIn("OR FECHA_EXPIRACION <= SYSTIMESTAMP", package)
        self.assertIn("C_ERR_SOSPECHOSO", package)
        self.assertIn("LEASE_VERSION = LEASE_VERSION + 1", package)

    def test_jobs_nuevos_quedan_deshabilitados(self):
        jobs = self.leer_sql("04_create_jobs_disabled.sql").upper()
        self.assertEqual(jobs.count("ENABLED         => FALSE"), 2)
        self.assertNotIn("DBMS_SCHEDULER.ENABLE", jobs)

    def test_rollback_preserva_tablas_y_restaura_ambos_procedures(self):
        rollback = self.leer_sql("10_rollback.sql").upper()
        self.assertNotIn("DROP TABLE", rollback)
        self.assertIn("CREATE OR REPLACE PROCEDURE         PRC_UPD_ALERTAS_VAL", rollback)
        self.assertIn(
            "CREATE OR REPLACE PROCEDURE         PRC_APLICAR_REGLAS_ALERTA",
            rollback,
        )

    def test_patches_declaran_hashes_del_baseline_real(self):
        upd = self.leer_sql("05_patch_prc_upd_alertas_val.sql")
        aplicar = self.leer_sql("06_patch_prc_aplicar_reglas_alerta.sql")
        self.assertIn(
            "e770b0d949573a8aca29aabb00bd89d418c432f6a6b3903fb934d98e2568505a",
            upd,
        )
        self.assertIn(
            "a7c98788a7b0d80103466b1a631dd0e0ce55f98c1b34556acabf5056e58c6b50",
            aplicar,
        )


class RecalculoDurableProcessorSafetyTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ruta = (
            Path(__file__).resolve().parents[3]
            / "oracle"
            / "pending"
            / "bkl-002c"
            / "03_create_processor.sql"
        )
        cls.processor = ruta.read_text(encoding="utf-8")
        cls.acquire = cls.processor.index("PKG_ALERTA_LEASE.ADQUIRIR;")
        cls.lease_true = cls.processor.index(
            "v_lease_adquirido := TRUE;",
            cls.acquire,
        )
        cls.protected = cls.processor.index(
            "Todo lo posterior al acquire queda cubierto"
        )
        cls.handler = cls.processor.index(
            "    EXCEPTION\n        WHEN OTHERS THEN",
            cls.protected,
        )
        cls.reraise = cls.processor.index("            RAISE;", cls.handler)
        cls.normal_cleanup = cls.processor.index(
            "    IF v_lease_adquirido THEN",
            cls.reraise,
        )

    def assert_en_bloque_protegido(self, texto):
        posicion = self.processor.index(texto, self.protected)
        self.assertLess(posicion, self.handler)

    def test_fallo_select_for_update_converge_en_cleanup(self):
        self.assert_en_bloque_protegido("            FOR UPDATE;")
        self.assertIn(
            "IF v_lease_adquirido THEN",
            self.processor[self.handler:self.reraise],
        )

    def test_fallo_al_marcar_ejecutando_converge_en_cleanup(self):
        self.assert_en_bloque_protegido("SET ESTADO = 'EJECUTANDO'")

    def test_fallo_commit_ejecutando_converge_en_cleanup(self):
        comentario = self.processor.index("Hace durable EJECUTANDO", self.protected)
        commit = self.processor.index("COMMIT;", comentario)
        self.assertLess(commit, self.handler)

    def test_fallo_recalculo_rapido_converge_en_cleanup(self):
        self.assert_en_bloque_protegido("USR_LAB.PRC_RECLASIFICAR_ALERTAS;")

    def test_fallo_recalculo_completo_converge_en_cleanup(self):
        self.assert_en_bloque_protegido("USR_LAB.PRC_RECALCULAR_ALERTAS_SEGURO;")

    def test_fallo_guardando_ok_converge_en_cleanup(self):
        self.assert_en_bloque_protegido("SET ESTADO = 'OK'")
        posicion_ok = self.processor.index("SET ESTADO = 'OK'", self.protected)
        commit_ok = self.processor.index("COMMIT;", posicion_ok)
        self.assertLess(commit_ok, self.handler)

    def test_fallo_guardando_error_no_impide_intentar_liberar(self):
        guardar_error = self.processor.index("SET ESTADO = 'ERROR'", self.handler)
        handler_guardar = self.processor.index(
            "Error guardando estado ERROR:",
            guardar_error,
        )
        liberar = self.processor.index("PKG_ALERTA_LEASE.LIBERAR;", handler_guardar)
        self.assertLess(handler_guardar, liberar)
        self.assertIn(
            "ROLLBACK_SIN_PROPAGAR('estado ERROR');",
            self.processor[handler_guardar:liberar],
        )

    def test_fallo_liberar_en_camino_normal_es_visible(self):
        segmento = self.processor[self.normal_cleanup:]
        liberar = segmento.index("PKG_ALERTA_LEASE.LIBERAR;")
        marcar_false = segmento.index("v_lease_adquirido := FALSE;")
        self.assertLess(liberar, marcar_false)
        self.assertNotIn("EXCEPTION", segmento[:marcar_false])

    def test_error_original_se_preserva_si_liberar_tambien_falla(self):
        segmento = self.processor[self.handler:self.reraise + len("            RAISE;")]
        self.assertIn("v_error_codigo := SQLCODE;", segmento)
        self.assertIn("v_error_mensaje := SUBSTR(SQLERRM, 1, 2000);", segmento)
        self.assertIn("DBMS_UTILITY.FORMAT_ERROR_BACKTRACE", segmento)
        self.assertIn("ROLLBACK_SIN_PROPAGAR('error original');", segmento)
        self.assertIn("Error secundario liberando lease:", segmento)
        self.assertIn("Error original ", segmento)
        self.assertTrue(segmento.rstrip().endswith("RAISE;"))

    def test_contencion_no_libera_lease_no_adquirido(self):
        bloque_adquisicion = self.processor[self.acquire:self.protected]
        self.assertIn("C_ERR_ACTIVO", bloque_adquisicion)
        self.assertIn("C_ERR_SOSPECHOSO", bloque_adquisicion)
        self.assertIn("RETURN;", bloque_adquisicion)
        self.assertNotIn("PKG_ALERTA_LEASE.LIBERAR", bloque_adquisicion)
        self.assertLess(self.acquire, self.lease_true)
