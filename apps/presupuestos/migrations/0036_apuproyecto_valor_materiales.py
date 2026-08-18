from django.db import migrations, models
import decimal


class Migration(migrations.Migration):

    dependencies = [
        ("presupuestos", "0035_apu_cantidad_base"),
    ]

    operations = [
        migrations.AddField(
            model_name="apuproyecto",
            name="valor_materiales",
            field=models.DecimalField(
                decimal_places=4,
                default=decimal.Decimal("0"),
                help_text="Suma de valor_total de todas las líneas de MATERIALES (con margen de venta e IVA).",
                max_digits=18,
            ),
        ),
    ]
