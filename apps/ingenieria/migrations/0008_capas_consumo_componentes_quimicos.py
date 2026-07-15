"""
Migration 0008 — ingenieria
Agrega:
  - capas_consumo (CapaConsumo)
  - componentes_quimicos (ComponenteQuimico)

Estas tablas son completamente nuevas — no hay estado previo que preservar.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("ingenieria", "0007_subsistema_consumo_numerico"),
        ("catalogos", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CapaConsumo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(help_text="Ej: Imprimación, Capa impermeabilizante, Refuerzo, Accesorios", max_length=200)),
                ("consumo_m2", models.DecimalField(decimal_places=4, help_text="Consumo unitario por m² por mano. Ej: 0.35 (kg/m²), 0.15 (gal/m²)", max_digits=10)),
                ("num_capas", models.PositiveSmallIntegerField(default=1, help_text="Número de manos o capas a aplicar")),
                ("unidad", models.CharField(default="kg", help_text="Unidad del consumo: kg, g, gal, L, m², und", max_length=40)),
                ("desperdicio_pct", models.DecimalField(decimal_places=2, default=0, help_text="% de desperdicio adicional. Ej: 5 → multiplica por 1.05", max_digits=5)),
                ("requiere_accesorio", models.BooleanField(default=False, help_text="Si es True, indica que esta capa incluye o requiere accesorios")),
                ("orden", models.PositiveIntegerField(default=1)),
                (
                    "subsistema",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="capas",
                        to="ingenieria.subsistema",
                    ),
                ),
                (
                    "categoria",
                    models.ForeignKey(
                        blank=True,
                        help_text="Categoría de producto que aplica en esta capa",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="capas_consumo",
                        to="catalogos.categoriaproducto",
                    ),
                ),
            ],
            options={
                "verbose_name": "Capa de Consumo",
                "verbose_name_plural": "Capas de Consumo",
                "db_table": "capas_consumo",
                "ordering": ["orden"],
            },
        ),
        migrations.CreateModel(
            name="ComponenteQuimico",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(help_text="Ej: Componente A (Base), Componente B (Endurecedor)", max_length=200)),
                ("porcentaje", models.DecimalField(decimal_places=2, help_text="% dentro de la mezcla total. Todos los componentes deben sumar 100.", max_digits=5)),
                ("orden", models.PositiveIntegerField(default=1)),
                (
                    "subsistema",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="componentes_quimicos",
                        to="ingenieria.subsistema",
                    ),
                ),
                (
                    "categoria",
                    models.ForeignKey(
                        blank=True,
                        help_text="Categoría de producto para este componente",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="componentes_quimicos",
                        to="catalogos.categoriaproducto",
                    ),
                ),
            ],
            options={
                "verbose_name": "Componente Químico",
                "verbose_name_plural": "Componentes Químicos",
                "db_table": "componentes_quimicos",
                "ordering": ["orden"],
            },
        ),
    ]
