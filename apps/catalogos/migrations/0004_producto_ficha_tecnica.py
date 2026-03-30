from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalogos', '0003_alter_producto_fecha_actualizacion_precio_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='producto',
            name='ficha_tecnica',
            field=models.FileField(
                blank=True,
                help_text='PDF o imagen con las especificaciones técnicas del producto (opcional).',
                null=True,
                upload_to='fichas_tecnicas/',
                verbose_name='Ficha técnica',
            ),
        ),
    ]
