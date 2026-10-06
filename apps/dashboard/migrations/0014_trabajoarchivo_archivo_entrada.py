import apps.dashboard.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0013_trabajoarchivo"),
    ]

    operations = [
        migrations.AddField(
            model_name="trabajoarchivo",
            name="archivo_entrada",
            field=models.FileField(
                blank=True,
                upload_to=apps.dashboard.models.trabajo_archivo_upload_to,
            ),
        ),
    ]
