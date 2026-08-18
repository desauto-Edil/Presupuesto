"""
Migration 0035 — Agrega cantidad_base_apu y unidad_base_apu a APUProyecto.

Estos campos almacenan la cantidad de referencia del APU (m², ml, etc.) para
calcular el valor total del proyecto = cantidad_base_apu × total_valor_venta.
Se rellenan automáticamente al hacer «Guardar APU» desde el panel confirmado.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("presupuestos", "0034_apu_poliza_bases_calculo_jsonfield"),
    ]

    operations = [
        migrations.AddField(
            model_name="apuproyecto",
            name="cantidad_base_apu",
            field=models.DecimalField(
                blank=True, null=True,
                max_digits=18, decimal_places=4,
                help_text=(
                    "Cantidad de referencia del APU (p. ej. m², ml). "
                    "Se calcula automáticamente al ejecutar «Guardar APU»."
                ),
            ),
        ),
        migrations.AddField(
            model_name="apuproyecto",
            name="unidad_base_apu",
            field=models.CharField(
                blank=True, default="", max_length=30,
                help_text="Unidad de medida de la base APU (m², ml, und, …).",
            ),
        ),
    ]
