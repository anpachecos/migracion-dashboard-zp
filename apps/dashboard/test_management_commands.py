import importlib
import os
from datetime import datetime
from io import StringIO
from unittest.mock import MagicMock, call, patch

from django.core.management import get_commands
from django.db import OperationalError
from django.test import TestCase, override_settings

from apps.dashboard.apps import DashboardConfig
from apps.dashboard.management.commands.actualizar_validadores import (
    Command as ActualizarValidadoresCommand,
)
from apps.dashboard.management.commands.cargar_validadores_limpios import (
    Command as CargarValidadoresLimpiosCommand,
)
from apps.dashboard.management.commands.limpiar_historial_ubicacion_oracle import (
    Command as LimpiarHistorialOracleCommand,
)
from apps.dashboard.management.commands.limpiar_registros_antiguos import (
    Command as LimpiarRegistrosAntiguosCommand,
)
from apps.dashboard.management.commands.probar_oracle import Command as ProbarOracleCommand
from apps.dashboard.management.commands.registrar_estado_oracle import (
    Command as RegistrarEstadoOracleCommand,
)
from apps.dashboard.services import reglas_alertas_service, scheduler as scheduler_service


class ManagementCommandsSchedulerCaracterizacionTests(TestCase):
    AHORA = datetime(2026, 9, 11, 12, 0)

    def comando(self, clase):
        stdout = StringIO()
        stderr = StringIO()
        return clase(stdout=stdout, stderr=stderr), stdout, stderr

    def conexion_falsa(self):
        cursor = MagicMock(name="cursor_oracle_falso")
        conexion = MagicMock(name="conexion_oracle_falsa")
        conexion.cursor.return_value.__enter__.return_value = cursor
        contexto = MagicMock(name="contexto_oracle_falso")
        contexto.__enter__.return_value = conexion
        return contexto, conexion, cursor

    def restaurar_flags_scheduler(self):
        scheduler_service.scheduler_started = False
        scheduler_service.job_estado_oracle_running = False
        scheduler_service.job_limpieza_historial_ubicacion_running = False

    def setUp(self):
        self.restaurar_flags_scheduler()
        self.addCleanup(self.restaurar_flags_scheduler)

    def test_probar_oracle_registra_estado_ok_y_stdout(self):
        comando, stdout, stderr = self.comando(ProbarOracleCommand)

        with patch(
            "apps.dashboard.management.commands.probar_oracle."
            "operacion_oracle_repository.obtener_sysdate",
            return_value=(self.AHORA,),
        ) as mock_sysdate, patch(
            "apps.dashboard.management.commands.probar_oracle.registrar_log_importacion"
        ) as mock_log:
            comando.handle()

        mock_sysdate.assert_called_once_with()
        self.assertEqual(mock_log.call_args.kwargs["estado"], "OK")
        self.assertEqual(mock_log.call_args.kwargs["filas_obtenidas"], 1)
        self.assertIn("Conexión Oracle OK", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_probar_oracle_registra_error_sin_propagar_excepcion(self):
        comando, stdout, stderr = self.comando(ProbarOracleCommand)
        with patch(
            "apps.dashboard.management.commands.probar_oracle."
            "operacion_oracle_repository.obtener_sysdate",
            side_effect=RuntimeError("Oracle sintético no disponible"),
        ), patch(
            "apps.dashboard.management.commands.probar_oracle.registrar_log_importacion"
        ) as mock_log:
            resultado = comando.handle()

        self.assertIsNone(resultado)
        self.assertEqual(mock_log.call_args.kwargs["estado"], "ERROR")
        self.assertEqual(mock_log.call_args.kwargs["filas_obtenidas"], 0)
        self.assertIn("Error conectando a Oracle: Oracle sintético no disponible", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")

    def test_registrar_estado_oracle_resume_tres_fuentes_y_logs(self):
        comando, stdout, stderr = self.comando(RegistrarEstadoOracleCommand)
        filas = (
            (10, 8, self.AHORA, self.AHORA, self.AHORA),
            (5, self.AHORA),
            (4,),
        )

        with patch(
            "apps.dashboard.management.commands.registrar_estado_oracle."
            "operacion_oracle_repository.obtener_resumenes_estado",
            return_value=filas,
        ) as mock_resumenes, patch(
            "apps.dashboard.management.commands.registrar_estado_oracle.registrar_log_importacion"
        ) as mock_log:
            comando.handle()

        mock_resumenes.assert_called_once_with()
        self.assertEqual(
            [llamada.kwargs["origen"] for llamada in mock_log.call_args_list],
            ["BATERIA_BLOQUES_ORACLE", "UBICACIONES_ORACLE", "ESTADO_ORACLE"],
        )
        self.assertIn("Batería bloques: 10", stdout.getvalue())
        self.assertIn("Ubicaciones vigentes: 5", stdout.getvalue())
        self.assertIn("Historial vigente: 4", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_registrar_estado_oracle_captura_error_y_escribe_stderr(self):
        comando, stdout, stderr = self.comando(RegistrarEstadoOracleCommand)
        with patch(
            "apps.dashboard.management.commands.registrar_estado_oracle."
            "operacion_oracle_repository.obtener_resumenes_estado",
            side_effect=RuntimeError("fallo sintético"),
        ), patch(
            "apps.dashboard.management.commands.registrar_estado_oracle.registrar_log_importacion"
        ) as mock_log:
            resultado = comando.handle()

        self.assertIsNone(resultado)
        self.assertEqual(mock_log.call_args.kwargs["estado"], "ERROR")
        self.assertIn("Error registrando estado Oracle: fallo sintético", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")

    def test_comandos_sqlite_antiguos_informan_que_estan_deshabilitados(self):
        casos = (
            (ActualizarValidadoresCommand, "actualización antigua de validadores"),
            (CargarValidadoresLimpiosCommand, "flujo antiguo de carga"),
            (LimpiarRegistrosAntiguosCommand, "limpieza de EstadoValidadorLimpio"),
        )
        for clase, fragmento in casos:
            with self.subTest(command=clase.__module__):
                comando, stdout, stderr = self.comando(clase)
                resultado = comando.handle()
                self.assertIsNone(resultado)
                self.assertIn("Este comando está deshabilitado.", stdout.getvalue())
                self.assertIn(fragmento, stdout.getvalue())
                self.assertEqual(stderr.getvalue(), "")

    def test_importadores_obsoletos_ya_no_estan_disponibles(self):
        comandos_disponibles = get_commands()

        for nombre in (
            "importar_validadores_oracle",
            "importar_validadores_csv",
        ):
            with self.subTest(command=nombre):
                self.assertNotIn(nombre, comandos_disponibles)

    def test_limpieza_historial_rechaza_retencion_invalida_sin_oracle(self):
        comando, stdout, stderr = self.comando(LimpiarHistorialOracleCommand)
        with patch(
            "apps.dashboard.management.commands.limpiar_historial_ubicacion_oracle."
            "ubicaciones_repository.limpiar_historial"
        ) as mock_limpieza, patch(
            "apps.dashboard.management.commands.limpiar_historial_ubicacion_oracle.registrar_log_importacion"
        ) as mock_log:
            comando.handle(dias_retencion=0)

        mock_limpieza.assert_not_called()
        self.assertEqual(mock_log.call_args.kwargs["estado"], "ERROR")
        self.assertIn("Los días de retención deben ser mayores o iguales a 1", stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")

    def test_limpieza_historial_solo_invoca_procedure_en_cursor_falso(self):
        comando, stdout, stderr = self.comando(LimpiarHistorialOracleCommand)
        contexto, _, cursor = self.conexion_falsa()
        variable_salida = MagicMock()
        variable_salida.getvalue.return_value = 7
        cursor.var.return_value = variable_salida

        with patch(
            "apps.dashboard.repositories.ubicaciones_repository."
            "obtener_conexion_oracle",
            return_value=contexto,
        ), patch(
            "apps.dashboard.management.commands.limpiar_historial_ubicacion_oracle.registrar_log_importacion"
        ) as mock_log:
            comando.handle(dias_retencion=16)

        cursor.callproc.assert_called_once_with(
            "USR_LAB.PRC_LIMPIAR_HIST_UBICACION", [16, variable_salida]
        )
        self.assertEqual(mock_log.call_args.kwargs["filas_eliminadas"], 7)
        self.assertIn("Filas eliminadas: 7", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_scheduler_reintenta_database_locked_sin_sleep_real(self):
        with patch.object(
            scheduler_service,
            "call_command",
            side_effect=[OperationalError("database is locked"), None],
        ) as mock_command, patch.object(
            scheduler_service.time, "sleep"
        ) as mock_sleep:
            scheduler_service.ejecutar_comando_con_reintentos("comando_seguro")

        self.assertEqual(mock_command.call_count, 2)
        mock_sleep.assert_called_once_with(10)

    def test_scheduler_agota_tres_intentos_y_dos_esperas(self):
        error = OperationalError("database is locked")
        with patch.object(
            scheduler_service, "call_command", side_effect=error
        ) as mock_command, patch.object(
            scheduler_service.time, "sleep"
        ) as mock_sleep:
            with self.assertRaises(OperationalError):
                scheduler_service.ejecutar_comando_con_reintentos(
                    "comando_seguro", max_intentos=3, esperas=[1, 2, 3]
                )

        self.assertEqual(mock_command.call_count, 3)
        self.assertEqual(mock_sleep.call_args_list, [call(1), call(2)])

    def test_scheduler_no_reintenta_otros_errores(self):
        with patch.object(
            scheduler_service,
            "call_command",
            side_effect=OperationalError("otro error SQLite"),
        ) as mock_command, patch.object(
            scheduler_service.time, "sleep"
        ) as mock_sleep:
            with self.assertRaises(OperationalError):
                scheduler_service.ejecutar_comando_con_reintentos("comando_seguro")

        mock_command.assert_called_once_with("comando_seguro")
        mock_sleep.assert_not_called()

    def test_scheduler_registra_jobs_y_horarios_actuales_sin_iniciarlo_realmente(self):
        with patch.object(
            scheduler_service.scheduler, "add_job"
        ) as mock_add_job, patch.object(
            scheduler_service.scheduler, "start"
        ) as mock_start, patch.object(
            scheduler_service, "registrar_log_importacion"
        ):
            scheduler_service.iniciar_scheduler()

        self.assertEqual(mock_add_job.call_count, 2)
        estado, limpieza = mock_add_job.call_args_list
        self.assertEqual(estado.kwargs["id"], "registrar_estado_oracle_cada_30_min")
        self.assertEqual(estado.kwargs["minute"], "5,35")
        self.assertTrue(estado.kwargs["replace_existing"])
        self.assertEqual(estado.kwargs["max_instances"], 1)
        self.assertEqual(limpieza.kwargs["id"], "limpiar_historial_ubicacion_oracle_diario")
        self.assertEqual(limpieza.kwargs["hour"], 19)
        self.assertEqual(limpieza.kwargs["minute"], 10)
        mock_start.assert_called_once_with()
        self.assertTrue(scheduler_service.scheduler_started)

    def test_scheduler_no_duplica_jobs_si_ya_esta_iniciado(self):
        scheduler_service.scheduler_started = True
        with patch.object(
            scheduler_service.scheduler, "add_job"
        ) as mock_add_job, patch.object(
            scheduler_service.scheduler, "start"
        ) as mock_start:
            scheduler_service.iniciar_scheduler()

        mock_add_job.assert_not_called()
        mock_start.assert_not_called()

    @override_settings(DASHBOARD_SCHEDULER_ENABLED=False)
    def test_app_no_inicia_scheduler_si_esta_deshabilitado(self):
        modulo = importlib.import_module("apps.dashboard")
        configuracion = DashboardConfig("apps.dashboard", modulo)
        with patch.dict(os.environ, {"RUN_MAIN": "true"}), patch.object(
            scheduler_service, "iniciar_scheduler"
        ) as mock_iniciar:
            configuracion.ready()

        mock_iniciar.assert_not_called()

    def test_jobs_scheduler_delegan_en_commands_mockeados(self):
        with patch.object(
            scheduler_service, "ejecutar_comando_con_reintentos"
        ) as mock_ejecutar:
            scheduler_service.registrar_estado_oracle_job()
            scheduler_service.limpiar_historial_ubicacion_oracle_job()

        self.assertEqual(mock_ejecutar.call_args_list, [
            call("registrar_estado_oracle", max_intentos=3, esperas=[10, 20, 30]),
            call(
                "limpiar_historial_ubicacion_oracle",
                "--dias-retencion",
                "16",
                max_intentos=3,
                esperas=[10, 20, 30],
            ),
        ])
        self.assertFalse(scheduler_service.job_estado_oracle_running)
        self.assertFalse(scheduler_service.job_limpieza_historial_ubicacion_running)

    def test_job_scheduler_omite_ejecucion_duplicada_y_registra_advertencia(self):
        scheduler_service.job_estado_oracle_running = True
        with patch.object(
            scheduler_service, "ejecutar_comando_con_reintentos"
        ) as mock_ejecutar, patch.object(
            scheduler_service, "registrar_log_importacion"
        ) as mock_log:
            scheduler_service.registrar_estado_oracle_job()

        mock_ejecutar.assert_not_called()
        self.assertEqual(mock_log.call_args.kwargs["estado"], "ADVERTENCIA")
        self.assertIn("ya había una ejecución en curso", mock_log.call_args.kwargs["mensaje"])

    def test_job_scheduler_captura_error_y_restaurar_bandera(self):
        with patch.object(
            scheduler_service,
            "ejecutar_comando_con_reintentos",
            side_effect=RuntimeError("fallo sintético"),
        ), patch.object(
            scheduler_service, "registrar_log_importacion"
        ) as mock_log:
            scheduler_service.registrar_estado_oracle_job()

        self.assertFalse(scheduler_service.job_estado_oracle_running)
        self.assertEqual(mock_log.call_args.kwargs["estado"], "ERROR")
        self.assertIn("fallo sintético", mock_log.call_args.kwargs["mensaje"])

    def test_recalculo_segundo_plano_crea_thread_mock_sin_iniciarlo_real(self):
        if reglas_alertas_service._recalculo_lock.locked():
            reglas_alertas_service._recalculo_lock.release()

        hilo = MagicMock(name="thread_falso")
        with patch.object(
            reglas_alertas_service.threading, "Thread", return_value=hilo
        ) as mock_thread:
            resultado = reglas_alertas_service.iniciar_recalculo_en_segundo_plano(
                modo_recalculo="rapido",
                log_path="ruta-sintetica-no-utilizada.log",
            )

        self.assertIs(resultado, hilo)
        mock_thread.assert_called_once()
        self.assertEqual(mock_thread.call_args.kwargs["name"], "recalculo-alertas-rapido")
        self.assertTrue(mock_thread.call_args.kwargs["daemon"])
        hilo.start.assert_called_once_with()
        reglas_alertas_service._recalculo_lock.release()
