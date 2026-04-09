"""
0003 — Refactor completo del módulo APU.

Cambios:
  - APUProyecto → APU (rename modelo + tabla apu_proyectos → apus)
  - APU: add nombre/descripcion, remove campos legacy, proyecto_sistema nullable
  - APULinea: add item_catalogo, unidad, vida_util_dias, costo_por_dia, salario_base, prestaciones
  - ConfiguracionAPU: replace campos legacy por nuevos (factor_venta_pct, iva_pct, aiu_pct, …)
  - ItemCatalogoAPU: add salario_base, prestaciones; update unidad choices
"""

from decimal import Decimal
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('presupuestos', '0002_catalogo_apu'),
        ('configuracion', '0001_initial'),
    ]

    operations = [

        # ── 1. Renombrar modelo APUProyecto → APU ───────────────────────────
        migrations.RenameModel(
            old_name='APUProyecto',
            new_name='APU',
        ),

        # ── 2. Renombrar tabla apu_proyectos → apus ─────────────────────────
        migrations.AlterModelTable(
            name='apu',
            table='apus',
        ),

        # ── 3. APU — agregar campos nuevos ───────────────────────────────────
        migrations.AddField(
            model_name='apu',
            name='nombre',
            field=models.CharField(
                default='',
                max_length=200,
                help_text="Nombre del APU, p. ej. 'APU Cubierta TPO — Edificio Central'.",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='apu',
            name='descripcion',
            field=models.TextField(blank=True, default=''),
            preserve_default=False,
        ),

        # ── 4. APU — hacer proyecto_sistema nullable ──────────────────────────
        migrations.AlterField(
            model_name='apu',
            name='proyecto_sistema',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='apu',
                to='presupuestos.proyectosistema',
                help_text='ProyectoSistema al que pertenece este APU (si aplica).',
            ),
        ),

        # ── 5. APU — eliminar campos legacy ──────────────────────────────────
        migrations.RemoveField(model_name='apu', name='aiu_contratista_pct'),
        migrations.RemoveField(model_name='apu', name='cuadrilla_personas'),
        migrations.RemoveField(model_name='apu', name='dias_trabajo'),
        migrations.RemoveField(model_name='apu', name='margen_contratista_pct'),
        migrations.RemoveField(model_name='apu', name='rendimiento_und_dia'),
        migrations.RemoveField(model_name='apu', name='tiempo_estimado_meses'),

        # ── 6. APU — ajustar metadatos ───────────────────────────────────────
        migrations.AlterModelOptions(
            name='apu',
            options={
                'verbose_name': 'APU',
                'verbose_name_plural': 'APUs',
            },
        ),

        # ── 7. APULinea — agregar campos del catálogo ────────────────────────
        migrations.AddField(
            model_name='apulinea',
            name='item_catalogo',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='apu_lineas',
                to='presupuestos.itemcatalogoapu',
                help_text='Ítem del catálogo APU del que proviene esta línea.',
            ),
        ),
        migrations.AddField(
            model_name='apulinea',
            name='unidad',
            field=models.CharField(
                choices=[
                    ('und', 'Unidad'), ('m2', 'Metro cuadrado'), ('ml', 'Metro lineal'),
                    ('mts', 'Metros'), ('kg', 'Kilogramo'), ('galon', 'Galón'),
                    ('kilo', 'Kilo'), ('cartucho', 'Cartucho'), ('dia', 'Día'),
                    ('mes', 'Mes'), ('hora', 'Hora'), ('global', 'Global'),
                ],
                default='und',
                max_length=20,
                help_text='Unidad de medida del rendimiento.',
            ),
        ),
        migrations.AddField(
            model_name='apulinea',
            name='vida_util_dias',
            field=models.PositiveIntegerField(
                blank=True, null=True,
                help_text='Vida útil en días (herramientas/dotación).',
            ),
        ),
        migrations.AddField(
            model_name='apulinea',
            name='costo_por_dia',
            field=models.DecimalField(
                default=Decimal('0'),
                decimal_places=6, max_digits=18,
                help_text='precio_referencia / vida_util_dias. Calculado automáticamente.',
            ),
        ),
        migrations.AddField(
            model_name='apulinea',
            name='salario_base',
            field=models.DecimalField(
                blank=True, default=Decimal('0'),
                decimal_places=4, max_digits=18,
                help_text='Salario base mensual (solo personal).',
            ),
        ),
        migrations.AddField(
            model_name='apulinea',
            name='prestaciones',
            field=models.DecimalField(
                blank=True, default=Decimal('0'),
                decimal_places=4, max_digits=18,
                help_text='Prestaciones sociales mensuales (solo personal).',
            ),
        ),

        # ── 8. APULinea — ajustar metadatos ──────────────────────────────────
        migrations.AlterModelOptions(
            name='apulinea',
            options={
                'ordering': ['tipo', 'descripcion'],
                'verbose_name': 'Línea APU',
                'verbose_name_plural': 'Líneas APU',
            },
        ),

        # ── 9. ConfiguracionAPU — eliminar campos legacy ─────────────────────
        migrations.RemoveField(model_name='configuracionapu', name='porcentaje_ganancia'),
        migrations.RemoveField(model_name='configuracionapu', name='aiu_contratista'),
        migrations.RemoveField(model_name='configuracionapu', name='desperdicio'),
        migrations.RemoveField(model_name='configuracionapu', name='margen_ganancia_contratista'),

        # ── 10. ConfiguracionAPU — agregar campos nuevos ─────────────────────
        migrations.AddField(
            model_name='configuracionapu',
            name='factor_venta_pct',
            field=models.DecimalField(
                decimal_places=4, default=Decimal('20'), max_digits=8,
                help_text='% de margen sobre costo unitario para obtener valor unitario.',
            ),
        ),
        migrations.AddField(
            model_name='configuracionapu',
            name='iva_pct',
            field=models.DecimalField(
                decimal_places=4, default=Decimal('19'), max_digits=8,
                help_text='Porcentaje de IVA aplicado a materiales cuando corresponda.',
            ),
        ),
        migrations.AddField(
            model_name='configuracionapu',
            name='aiu_contratista_pct',
            field=models.DecimalField(
                decimal_places=4, default=Decimal('30'), max_digits=8,
                help_text='AIU del contratista (%).',
            ),
        ),
        migrations.AddField(
            model_name='configuracionapu',
            name='margen_ganancia_pct',
            field=models.DecimalField(
                decimal_places=4, default=Decimal('20'), max_digits=8,
                help_text='Margen de ganancia general (%).',
            ),
        ),
        migrations.AddField(
            model_name='configuracionapu',
            name='desperdicio_pct',
            field=models.DecimalField(
                decimal_places=4, default=Decimal('3'), max_digits=8,
                help_text='Porcentaje de desperdicio sobre materiales.',
            ),
        ),

        # ── 11. ConfiguracionAPU — ajustar metadatos ─────────────────────────
        migrations.AlterModelOptions(
            name='configuracionapu',
            options={
                'verbose_name': 'Configuración APU',
                'verbose_name_plural': 'Configuraciones APU',
            },
        ),

        # ── 12. ItemCatalogoAPU — agregar salario_base + prestaciones ─────────
        migrations.AddField(
            model_name='itemcatalogoapu',
            name='salario_base',
            field=models.DecimalField(
                blank=True, default=Decimal('0'),
                decimal_places=4, max_digits=18,
                help_text='Salario base mensual del cargo (solo personal).',
            ),
        ),
        migrations.AddField(
            model_name='itemcatalogoapu',
            name='prestaciones',
            field=models.DecimalField(
                blank=True, default=Decimal('0'),
                decimal_places=4, max_digits=18,
                help_text='Valor de prestaciones sociales mensuales (solo personal).',
            ),
        ),

        # ── 13. ItemCatalogoAPU — actualizar choices de unidad ───────────────
        migrations.AlterField(
            model_name='itemcatalogoapu',
            name='unidad',
            field=models.CharField(
                choices=[
                    ('dia', 'Día'), ('mes', 'Mes'), ('hora', 'Hora'),
                    ('und', 'Unidad'), ('mts', 'Metros'), ('global', 'Global'),
                ],
                default='und',
                max_length=20,
                help_text='Unidad sobre la que aplica el precio base.',
            ),
        ),
    ]
