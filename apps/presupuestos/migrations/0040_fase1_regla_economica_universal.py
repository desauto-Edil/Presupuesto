"""
Fase 1 APU — Regla económica universal del catálogo y retiro de cuadrillas.

Orden de operaciones:
  1. ItemCatalogoAPU.precio_base → valor_base (RenameField, conserva datos).
  2. Datos: ítems con salario_base > 0 o prestaciones > 0 (misma condición que
     usaba el motor para "personal") pasan a valor_base = salario_base +
     prestaciones. Es el valor económico que el motor usaba hasta ahora.
     vida_util_dias NO se toca: queda como esté (NULL = pendiente de
     configuración manual; no se inventa ningún valor).
  3. Se eliminan salario_base / prestaciones del catálogo y
     aplica_dias_mensuales de la categoría (todas estaban en False).
  4. APULinea gana `cantidad` y `precio_personalizado`.
  5. Restricciones: valor_base >= 0 y vida_util_dias NULL o > 0.
  6. Se eliminan CuadrillaPresetItem y CuadrillaPreset (y sus datos).

Reversión: el esquema es reversible, pero la fusión salario + prestaciones y
el borrado de cuadrillas no se pueden deshacer con datos exactos. Para volver
atrás con datos, restaurar el respaldo tomado antes de aplicar la migración.
"""

from django.db import migrations, models


def fusionar_salario_prestaciones(apps, schema_editor):
    ItemCatalogoAPU = apps.get_model("presupuestos", "ItemCatalogoAPU")
    qs = ItemCatalogoAPU.objects.filter(
        models.Q(salario_base__gt=0) | models.Q(prestaciones__gt=0)
    )
    for item in qs:
        item.valor_base = (item.salario_base or 0) + (item.prestaciones or 0)
        item.save(update_fields=["valor_base"])


class Migration(migrations.Migration):

    dependencies = [
        ("presupuestos", "0039_rename_margenes_material_mano_obra"),
    ]

    operations = [
        # 1. precio_base → valor_base
        migrations.RenameField(
            model_name="itemcatalogoapu",
            old_name="precio_base",
            new_name="valor_base",
        ),
        # 2. Traslado económico de personal
        migrations.RunPython(fusionar_salario_prestaciones, migrations.RunPython.noop),
        # 3. Campos retirados
        migrations.RemoveField(model_name="itemcatalogoapu", name="salario_base"),
        migrations.RemoveField(model_name="itemcatalogoapu", name="prestaciones"),
        migrations.RemoveField(model_name="categoriaitemapu", name="aplica_dias_mensuales"),
        migrations.AlterField(
            model_name="itemcatalogoapu",
            name="valor_base",
            field=models.DecimalField(
                decimal_places=4, default=0, max_digits=18,
                help_text="Valor base del ítem. valor_diario = valor_base / vida_util_dias.",
            ),
        ),
        migrations.AlterField(
            model_name="itemcatalogoapu",
            name="vida_util_dias",
            field=models.PositiveIntegerField(
                blank=True, null=True,
                help_text=(
                    "Vida útil en días (dato manual del ítem). Obligatoria para calcular "
                    "el valor diario; vacía = ítem pendiente de configuración."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="itemcatalogoapu",
            name="tienda_referencia",
            field=models.CharField(
                blank=True, default="", max_length=200,
                help_text="Proveedor o tienda donde se cotizó el valor base.",
                verbose_name="Tienda de referencia",
            ),
        ),
        # 4. APULinea: cantidad + override explícito; salario/prestaciones históricos
        migrations.AddField(
            model_name="apulinea",
            name="cantidad",
            field=models.DecimalField(
                blank=True, null=True, max_digits=14, decimal_places=4,
                help_text=(
                    "Cantidad del ítem de catálogo seleccionada para este APU. "
                    "aporte a suma = precio_referencia (valor diario) × cantidad. "
                    "NULL en líneas resumen, materiales y líneas anteriores a la Fase 1."
                ),
            ),
        ),
        migrations.AddField(
            model_name="apulinea",
            name="precio_personalizado",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "True si precio_referencia es un valor diario escrito por el usuario "
                    "para este APU (override); False si proviene del catálogo."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="apulinea",
            name="salario_base",
            field=models.DecimalField(
                blank=True, decimal_places=4, default=0, max_digits=18,
                help_text="HISTÓRICO. Salario copiado en líneas anteriores a la Fase 1.",
            ),
        ),
        migrations.AlterField(
            model_name="apulinea",
            name="prestaciones",
            field=models.DecimalField(
                blank=True, decimal_places=4, default=0, max_digits=18,
                help_text="HISTÓRICO. Prestaciones copiadas en líneas anteriores a la Fase 1.",
            ),
        ),
        # 5. Restricciones de integridad económica
        migrations.AddConstraint(
            model_name="itemcatalogoapu",
            constraint=models.CheckConstraint(
                check=models.Q(valor_base__gte=0),
                name="item_apu_valor_base_no_negativo",
            ),
        ),
        migrations.AddConstraint(
            model_name="itemcatalogoapu",
            constraint=models.CheckConstraint(
                check=models.Q(vida_util_dias__isnull=True) | models.Q(vida_util_dias__gt=0),
                name="item_apu_vida_util_positiva",
            ),
        ),
        # 6. Cuadrillas / presets legacy
        migrations.DeleteModel(name="CuadrillaPresetItem"),
        migrations.DeleteModel(name="CuadrillaPreset"),
    ]
