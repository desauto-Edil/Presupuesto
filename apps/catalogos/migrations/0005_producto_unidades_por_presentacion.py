from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalogos", "0004_producto_ficha_tecnica"),
    ]

    operations = [
        migrations.AddField(
            model_name="producto",
            name="unidades_por_presentacion",
            field=models.PositiveIntegerField(
                default=1,
                verbose_name="Unidades por presentación",
                help_text=(
                    "Cantidad de unidades que trae la presentación de venta "
                    "(ej: 1000 para bolsa de 1000 und, 500 para bolsa de 500). "
                    "El precio se divide entre este valor para obtener el precio unitario real."
                ),
            ),
        ),
    ]
