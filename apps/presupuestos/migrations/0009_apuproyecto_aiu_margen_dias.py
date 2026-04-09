from django.db import migrations, models
import decimal


class Migration(migrations.Migration):

    dependencies = [
        ("presupuestos", "0008_add_costo_por_dia_field"),
    ]

    operations = [
        migrations.AddField(
            model_name="apuproyecto",
            name="aiu_contratista_pct",
            field=models.DecimalField(
                decimal_places=4,
                default=decimal.Decimal("30"),
                help_text="AIU del contratista (%).",
                max_digits=8,
            ),
        ),
        migrations.AddField(
            model_name="apuproyecto",
            name="margen_ganancia_pct",
            field=models.DecimalField(
                decimal_places=4,
                default=decimal.Decimal("20"),
                help_text="Margen de ganancia (%).",
                max_digits=8,
            ),
        ),
        migrations.AddField(
            model_name="apuproyecto",
            name="dias_duracion",
            field=models.PositiveIntegerField(
                default=30,
                help_text="Días de duración del proyecto para el cálculo de costos.",
            ),
        ),
    ]
