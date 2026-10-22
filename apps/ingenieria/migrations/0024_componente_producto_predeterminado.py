from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('catalogos', '0007_producto_ancho_presentacion_and_more'),
        ('ingenieria', '0023_despiece_componentes_excluidos'),
    ]

    operations = [
        migrations.AddField(
            model_name='componentesubsistema',
            name='producto_predeterminado',
            field=models.ForeignKey(blank=True, help_text='Producto sugerido al calcular un despiece con esta plantilla. Debe pertenecer a la categoría del componente; el usuario puede cambiarlo.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='componentes_subsistema_predeterminado', to='catalogos.producto', verbose_name='Producto predeterminado'),
        ),
    ]
