from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ingenieria", "0002_componentes_variables_subsistema"),
    ]

    operations = [
        migrations.AddField(
            model_name="subsistema",
            name="variable_referencia_apu",
            field=models.CharField(
                blank=True,
                default="",
                max_length=80,
                verbose_name="Variable de referencia APU",
                help_text=(
                    "Nombre de la variable de entrada que representa la cantidad "
                    "principal del sistema para el APU. Ej: 'total_powergrip'."
                ),
            ),
        ),
        migrations.AddField(
            model_name="subsistema",
            name="unidad_apu",
            field=models.CharField(
                blank=True,
                default="und",
                max_length=40,
                verbose_name="Unidad del APU",
                help_text="Unidad de la referencia. Ej: 'soporte', 'm²', 'ml'.",
            ),
        ),
    ]
