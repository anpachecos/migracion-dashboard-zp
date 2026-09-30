from unittest.mock import patch

from django.test import SimpleTestCase

from apps.dashboard import scheduler as scheduler_service


class SchedulerTests(SimpleTestCase):
    def test_no_programa_importacion_automatica_de_ubicaciones(self):
        scheduler_started_anterior = scheduler_service.scheduler_started
        scheduler_service.scheduler_started = False
        self.addCleanup(
            setattr,
            scheduler_service,
            "scheduler_started",
            scheduler_started_anterior,
        )

        with patch.object(
            scheduler_service.scheduler,
            "add_job",
        ) as mock_add_job, patch.object(
            scheduler_service.scheduler,
            "start",
        ) as mock_start, patch.object(
            scheduler_service,
            "registrar_log_importacion",
        ):
            scheduler_service.iniciar_scheduler()

        ids_programados = [
            llamada.kwargs["id"]
            for llamada in mock_add_job.call_args_list
        ]

        self.assertEqual(
            ids_programados,
            [
                "registrar_estado_oracle_cada_30_min",
                "limpiar_historial_ubicacion_oracle_diario",
            ],
        )
        self.assertNotIn(
            "importar_ubicaciones_esperadas_diario",
            ids_programados,
        )
        mock_start.assert_called_once_with()
