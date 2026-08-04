from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ingenieria', '0021_componente_presentacion_producto'),
    ]

    operations = [
        migrations.AddField(
            model_name='componentesubsistema',
            name='campo_presentacion_producto',
            field=models.CharField(
                blank=True,
                choices=[
                    ('CANTIDAD', 'Cantidad por presentación'),
                    ('ANCHO', 'Ancho'),
                    ('LARGO', 'Largo'),
                ],
                default='CANTIDAD',
                help_text=(
                    "Campo del producto cuyo valor se inyecta en la fórmula. "
                    "Solo aplica cuando 'requiere_presentacion_producto' está activo."
                ),
                max_length=10,
                verbose_name='Campo de presentación',
            ),
        ),
    ]
