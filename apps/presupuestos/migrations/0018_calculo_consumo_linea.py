"""
Migration 0018 — presupuestos
Agrega:
  - calculo_consumo_lineas (CalculoConsumoLinea)

Tabla completamente nueva — no reemplaza ni modifica despiece_lineas.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("presupuestos", "0017_alter_proyectosistema_subsistema"),
        ("catalogos", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CalculoConsumoLinea",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("capa_nombre", models.CharField(help_text="Nombre de la capa o componente.", max_length=200)),
                ("area_m2", models.DecimalField(decimal_places=4, help_text="Área usada en el cálculo.", max_digits=14)),
                ("consumo_m2", models.DecimalField(decimal_places=4, help_text="Consumo unitario de la capa (kg/m², gal/m², etc.)", max_digits=10)),
                ("num_capas", models.PositiveSmallIntegerField(default=1)),
                ("desperdicio_pct", models.DecimalField(decimal_places=2, default=0, max_digits=5)),
                ("cantidad_calculada", models.DecimalField(decimal_places=6, help_text="Cantidad calculada automáticamente.", max_digits=18)),
                ("cantidad_ajustada", models.DecimalField(blank=True, decimal_places=6, help_text="Ajuste manual del usuario; reemplaza la cantidad calculada.", max_digits=18, null=True)),
                ("motivo_ajuste", models.TextField(blank=True, null=True)),
                ("unidad", models.CharField(default="kg", max_length=40)),
                ("precio_snapshot", models.DecimalField(blank=True, decimal_places=6, help_text="Precio unitario capturado en el momento del cálculo.", max_digits=18, null=True)),
                ("es_componente_quimico", models.BooleanField(default=False, help_text="True para líneas generadas por ComponenteQuimico (bicomponente).")),
                ("porcentaje_componente", models.DecimalField(blank=True, decimal_places=2, help_text="Porcentaje del componente dentro de la mezcla (sólo bicomponente).", max_digits=5, null=True)),
                ("orden", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "proyecto_sistema",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="calculo_consumo_lineas",
                        to="presupuestos.proyectosistema",
                    ),
                ),
                (
                    "producto",
                    models.ForeignKey(
                        blank=True,
                        help_text="Producto concreto; NULL mientras no se haya seleccionado.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="calculo_consumo_lineas",
                        to="catalogos.producto",
                    ),
                ),
                (
                    "categoria_producto",
                    models.ForeignKey(
                        blank=True,
                        help_text="Categoría para selección del producto cuando aún no está resuelto.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="calculo_consumo_lineas",
                        to="catalogos.categoriaproducto",
                    ),
                ),
                (
                    "linea_padre",
                    models.ForeignKey(
                        blank=True,
                        help_text="Si es componente químico, apunta a la línea de capa principal.",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="componentes_quimicos",
                        to="presupuestos.calculoconsumolinea",
                    ),
                ),
            ],
            options={
                "verbose_name": "Línea de Cálculo Consumo",
                "verbose_name_plural": "Líneas de Cálculo Consumo",
                "db_table": "calculo_consumo_lineas",
                "ordering": ["orden", "id"],
            },
        ),
    ]
