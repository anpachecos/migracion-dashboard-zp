from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0009_estatuszp_alter_logimportacion_options_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(
                    name="EstadoValidador",
                ),
                migrations.DeleteModel(
                    name="EstadoValidadorRaw",
                ),
                migrations.DeleteModel(
                    name="EstadoValidadorLimpio",
                ),
                migrations.DeleteModel(
                    name="UbicacionEsperadaValidador",
                ),
                migrations.DeleteModel(
                    name="HistorialUbicacionEsperadaValidador",
                ),
            ],
        ),
    ]