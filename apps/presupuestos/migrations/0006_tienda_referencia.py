from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("presupuestos", "0005_alter_apuproyecto_factor_venta_pct_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="itemcatalogoapu",
            name="tienda_referencia",
            field=models.CharField(
                blank=True,
                default="",
                max_length=200,
                verbose_name="Tienda de referencia",
                help_text="Proveedor o tienda donde se cotizó el precio base.",
            ),
        ),
        migrations.AddField(
            model_name="apulinea",
            name="tienda_referencia",
            field=models.CharField(
                blank=True,
                default="",
                max_length=200,
                verbose_name="Tienda de referencia",
                help_text="Proveedor o tienda de referencia (copiado del catálogo).",
            ),
        ),
    ]
