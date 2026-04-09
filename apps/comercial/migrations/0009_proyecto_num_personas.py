from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("comercial", "0008_proyecto_dias_duracion"),
    ]

    operations = [
        migrations.AddField(
            model_name="proyecto",
            name="num_personas",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="Número de personas",
                help_text="Personas en el equipo de trabajo. Si es 7 se usa la cuadrilla de instalación estándar.",
            ),
        ),
    ]
