from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("comercial", "0007_proyecto_solicitud_cascade"),
    ]

    operations = [
        migrations.AddField(
            model_name="proyecto",
            name="dias_duracion",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="Días de duración",
                help_text="Duración estimada del proyecto en días calendario",
            ),
        ),
    ]
