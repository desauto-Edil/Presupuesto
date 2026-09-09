"""
Renombra los dos márgenes del APU para que el código coincida con las etiquetas:

    factor_venta_pct    → margen_material_pct
    margen_ganancia_pct → margen_mano_obra_pct

RenameField conserva los datos: los porcentajes ya configurados siguen intactos.

Cambio de comportamiento asociado (en APULinea.calcular): el margen de material
pasa a aplicarse SOLO a las líneas de MATERIALES. En las demás categorías el
margen debe venir de la fórmula de ReglaAPUSubsistema.
"""

from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('presupuestos', '0038_apuproyecto_enviado_por_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='configuracionapu',
            old_name='factor_venta_pct',
            new_name='margen_material_pct',
        ),
        migrations.RenameField(
            model_name='configuracionapu',
            old_name='margen_ganancia_pct',
            new_name='margen_mano_obra_pct',
        ),
        migrations.RenameField(
            model_name='apuproyecto',
            old_name='factor_venta_pct',
            new_name='margen_material_pct',
        ),
        migrations.RenameField(
            model_name='apuproyecto',
            old_name='margen_ganancia_pct',
            new_name='margen_mano_obra_pct',
        ),

        migrations.AlterField(
            model_name='apulinea',
            name='valor_unitario',
            field=models.DecimalField(decimal_places=6, default=Decimal('0'), help_text='costo_unitario × (1 + margen_material_pct / 100) en MATERIALES; igual a costo_unitario en las demás categorías, donde el margen lo aporta la fórmula del subsistema.', max_digits=18),
        ),
        migrations.AlterField(
            model_name='apuproyecto',
            name='margen_mano_obra_pct',
            field=models.DecimalField(decimal_places=4, default=Decimal('20'), help_text='Margen de mano de obra (%). Sólo se aplica donde la fórmula del subsistema lo invoque como «margen_mano_obra».', max_digits=8),
        ),
        migrations.AlterField(
            model_name='apuproyecto',
            name='margen_material_pct',
            field=models.DecimalField(decimal_places=4, default=Decimal('20'), help_text='Margen de material (%). Se aplica automáticamente a las líneas de MATERIALES: valor unit = costo unit × (1 + margen/100). Ej: 20 → × 1.20. También está disponible como variable «margen_material» en las fórmulas.', max_digits=8),
        ),
        migrations.AlterField(
            model_name='configuracionapu',
            name='margen_mano_obra_pct',
            field=models.DecimalField(decimal_places=4, default=Decimal('20'), help_text='Margen de mano de obra (%). No se aplica solo: queda disponible como variable «margen_mano_obra» en las fórmulas de ReglaAPUSubsistema.', max_digits=8),
        ),
        migrations.AlterField(
            model_name='configuracionapu',
            name='margen_material_pct',
            field=models.DecimalField(decimal_places=4, default=Decimal('20'), help_text='Margen de material (%). Se aplica automáticamente al valor unitario de las líneas de MATERIALES, que no pasan por ReglaAPUSubsistema. Ej: 20 → multiplica × 1.20.', max_digits=8),
        ),
        migrations.AlterField(
            model_name='reglaapusubsistema',
            name='formula_costo_unitario',
            field=models.TextField(help_text='Expresión Python que devuelve el costo unitario de la categoría. Variables: suma, aiu, margen_mano_obra, margen_material, dias, tp, personas, trm. Alias antiguos: margen, factor_venta. Ej (herramientas): suma * aiu * margen_mano_obra * dias / tp'),
        ),
    ]
