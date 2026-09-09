"""Alinea los márgenes del Proyecto con el vocabulario del APU.

    margen_comercial_pct  →  margen_material_pct
    aiu_pct               →  aiu_contratista_pct
    (nuevo)                  margen_mano_obra_pct

Los tres campos eran hasta ahora informativos: el APU sembraba sus márgenes
desde ConfiguracionAPU y nunca leía los del proyecto. Al conectarlos
(APUService.__init__) los valores heredados dejan de ser inocuos, y los 130 %
que traían todos los proyectos por defecto producirían márgenes absurdos.
Por eso el paso de datos los normaliza a los mismos valores que la
configuración global (20 / 20 / 30).
"""
from decimal import Decimal

from django.db import migrations, models


def normalizar_porcentajes(apps, schema_editor):
    Proyecto = apps.get_model("comercial", "Proyecto")
    Proyecto.objects.filter(margen_material_pct=Decimal("130")).update(
        margen_material_pct=Decimal("20")
    )
    Proyecto.objects.filter(aiu_contratista_pct=Decimal("130")).update(
        aiu_contratista_pct=Decimal("30")
    )


def revertir_porcentajes(apps, schema_editor):
    """No se restauran los 130 %: eran el default inservible, no un dato."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("comercial", "0022_proyecto_trm_nullable"),
    ]

    operations = [
        migrations.RenameField(
            model_name="proyecto",
            old_name="margen_comercial_pct",
            new_name="margen_material_pct",
        ),
        migrations.RenameField(
            model_name="proyecto",
            old_name="aiu_pct",
            new_name="aiu_contratista_pct",
        ),
        migrations.AddField(
            model_name="proyecto",
            name="margen_mano_obra_pct",
            field=models.DecimalField(
                decimal_places=4, default=Decimal("20"),
                help_text="Margen de mano de obra (%) del proyecto. Siembra el mismo campo del APU, donde queda disponible como variable «margen_mano_obra» en las fórmulas de ReglaAPUSubsistema. No se aplica solo.",
                max_digits=8, verbose_name="Margen de mano de obra (%)",
            ),
        ),
        migrations.AlterField(
            model_name="proyecto",
            name="margen_material_pct",
            field=models.DecimalField(
                decimal_places=4, default=Decimal("20"),
                help_text="Margen de material (%) del proyecto. Siembra el mismo campo del APU, donde se aplica automáticamente al valor unitario de las líneas de MATERIALES. Ej: 20 → × 1.20.",
                max_digits=8, verbose_name="Margen de material (%)",
            ),
        ),
        migrations.AlterField(
            model_name="proyecto",
            name="aiu_contratista_pct",
            field=models.DecimalField(
                decimal_places=4, default=Decimal("30"),
                help_text="AIU del contratista (%) del proyecto. Siembra el mismo campo del APU, donde queda disponible como variable «aiu» en las fórmulas.",
                max_digits=8, verbose_name="AIU contratista (%)",
            ),
        ),
        migrations.RunPython(normalizar_porcentajes, revertir_porcentajes),
    ]
