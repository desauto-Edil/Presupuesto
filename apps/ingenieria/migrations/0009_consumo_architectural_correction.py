"""
Migration 0009 — ingenieria
Corrección arquitectónica de sistemas de CONSUMO:

ELIMINA de subsistemas (campos planos reemplazados por M2M o campos mejores):
  - funcion, estado_producto, categoria_consumo
  - temperatura, superficie
  - capas_parqueo, capas_transitable, capas_rampa
  - consumo_por_capa, consumo_prueba_transitable

AGREGA a subsistemas:
  - temperatura_min, temperatura_max  (Decimal, null)
  - interior_exterior                 (CharField)

AGREGA tablas catálogo nuevas:
  - funciones_consumo       (FuncionConsumo)
  - problemas_resueltos     (ProblemaResuelto)
  - superficies_compatibles (SuperficieCompatible)

AGREGA tabla de producto de referencia:
  - productos_tecnicos_asociados (ProductoTecnicoAsociado)

AGREGA M2M en subsistemas:
  - subsistema ↔ FuncionConsumo
  - subsistema ↔ ProblemaResuelto
  - subsistema ↔ SuperficieCompatible

AGREGA a componentes_quimicos:
  - estado_fisico (CharField)
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("ingenieria", "0008_capas_consumo_componentes_quimicos"),
    ]

    operations = [

        # ── 1. Nuevas tablas catálogo ─────────────────────────────────────────

        migrations.CreateModel(
            name="FuncionConsumo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(help_text="Ej: Imprimación, Impermeabilización, Capa intermedia", max_length=200, unique=True)),
                ("descripcion", models.TextField(blank=True)),
                ("activo", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "Función de consumo",
                "verbose_name_plural": "Funciones de consumo",
                "db_table": "funciones_consumo",
                "ordering": ["nombre"],
                "app_label": "ingenieria",
            },
        ),

        migrations.CreateModel(
            name="ProblemaResuelto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(help_text="Ej: Filtraciones, Carbonatación, Fisuras", max_length=200, unique=True)),
                ("descripcion", models.TextField(blank=True)),
                ("activo", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "Problema resuelto",
                "verbose_name_plural": "Problemas resueltos",
                "db_table": "problemas_resueltos",
                "ordering": ["nombre"],
                "app_label": "ingenieria",
            },
        ),

        migrations.CreateModel(
            name="SuperficieCompatible",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(help_text="Ej: Concreto, Metal, Madera, Ladrillo", max_length=200, unique=True)),
                ("descripcion", models.TextField(blank=True)),
                ("activo", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "Superficie compatible",
                "verbose_name_plural": "Superficies compatibles",
                "db_table": "superficies_compatibles",
                "ordering": ["nombre"],
                "app_label": "ingenieria",
            },
        ),

        # ── 2. Tabla ProductoTecnicoAsociado ──────────────────────────────────

        migrations.CreateModel(
            name="ProductoTecnicoAsociado",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(help_text="Nombre comercial del producto. Ej: KÖSTER KB-Pox 008", max_length=300)),
                ("descripcion", models.TextField(blank=True)),
                ("estado_fisico", models.CharField(
                    blank=True, default="",
                    choices=[
                        ("LIQUIDO", "Líquido"),
                        ("SOLIDO", "Sólido"),
                        ("PASTOSO", "Pastoso"),
                        ("POLVO", "Polvo"),
                        ("ROLLO_PREFORMADO", "Rollo preformado"),
                        ("MIXTO", "Mixto"),
                    ],
                    max_length=20,
                    verbose_name="Estado físico",
                )),
                ("consumo_min_g_m2", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name="Consumo mínimo (g/m²)")),
                ("consumo_max_g_m2", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name="Consumo máximo (g/m²)")),
                ("unidad", models.CharField(default="kg", max_length=40)),
                ("orden", models.PositiveIntegerField(default=1)),
                (
                    "subsistema",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="productos_tecnicos",
                        to="ingenieria.subsistema",
                    ),
                ),
            ],
            options={
                "verbose_name": "Producto técnico asociado",
                "verbose_name_plural": "Productos técnicos asociados",
                "db_table": "productos_tecnicos_asociados",
                "ordering": ["orden"],
                "app_label": "ingenieria",
            },
        ),

        # ── 3. M2M en Subsistema ──────────────────────────────────────────────

        migrations.AddField(
            model_name="subsistema",
            name="funciones",
            field=models.ManyToManyField(
                blank=True,
                help_text="Funciones técnicas que cumple este sistema (ej: Imprimación, Impermeabilización)",
                related_name="subsistemas",
                to="ingenieria.funcionconsumo",
                verbose_name="Funciones",
            ),
        ),

        migrations.AddField(
            model_name="subsistema",
            name="problemas_resuelve",
            field=models.ManyToManyField(
                blank=True,
                related_name="subsistemas",
                to="ingenieria.problemaresuelto",
                verbose_name="Problemas que resuelve",
            ),
        ),

        migrations.AddField(
            model_name="subsistema",
            name="superficies_compatibles",
            field=models.ManyToManyField(
                blank=True,
                related_name="subsistemas",
                to="ingenieria.superficiecompatible",
                verbose_name="Superficies compatibles",
            ),
        ),

        # ── 4. Nuevas columnas en Subsistema ─────────────────────────────────

        migrations.AddField(
            model_name="subsistema",
            name="temperatura_min",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=6, null=True, verbose_name="Temperatura mínima de aplicación (°C)"),
        ),
        migrations.AddField(
            model_name="subsistema",
            name="temperatura_max",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=6, null=True, verbose_name="Temperatura máxima de aplicación (°C)"),
        ),
        migrations.AddField(
            model_name="subsistema",
            name="interior_exterior",
            field=models.CharField(
                blank=True, default="",
                choices=[
                    ("INTERIOR", "Interior"),
                    ("EXTERIOR", "Exterior"),
                    ("AMBOS", "Interior y exterior"),
                ],
                max_length=20,
                verbose_name="Interior / Exterior",
            ),
        ),

        # ── 5. Actualizar choices de tipo_producto (agrega MULTICOMPONENTE) ──

        migrations.AlterField(
            model_name="subsistema",
            name="tipo_producto",
            field=models.CharField(
                blank=True, default="",
                choices=[
                    ("MONOCOMPONENTE", "Monocomponente"),
                    ("BICOMPONENTE", "Bicomponente"),
                    ("MULTICOMPONENTE", "Multicomponente"),
                ],
                max_length=20,
                verbose_name="Tipo de producto",
                help_text="Monocomponente, Bicomponente o Multicomponente",
            ),
        ),

        # ── 6. Agregar estado_fisico a ComponenteQuimico ──────────────────────

        migrations.AddField(
            model_name="componentequimico",
            name="estado_fisico",
            field=models.CharField(
                blank=True, default="",
                choices=[
                    ("LIQUIDO", "Líquido"),
                    ("SOLIDO", "Sólido"),
                    ("PASTOSO", "Pastoso"),
                    ("POLVO", "Polvo"),
                    ("ROLLO_PREFORMADO", "Rollo preformado"),
                    ("MIXTO", "Mixto"),
                ],
                max_length=20,
                verbose_name="Estado físico",
            ),
        ),

        # ── 7. Eliminar campos obsoletos de Subsistema ────────────────────────

        migrations.RemoveField(model_name="subsistema", name="funcion"),
        migrations.RemoveField(model_name="subsistema", name="estado_producto"),
        migrations.RemoveField(model_name="subsistema", name="categoria_consumo"),
        migrations.RemoveField(model_name="subsistema", name="temperatura"),
        migrations.RemoveField(model_name="subsistema", name="superficie"),
        migrations.RemoveField(model_name="subsistema", name="capas_parqueo"),
        migrations.RemoveField(model_name="subsistema", name="capas_transitable"),
        migrations.RemoveField(model_name="subsistema", name="capas_rampa"),
        migrations.RemoveField(model_name="subsistema", name="consumo_por_capa"),
        migrations.RemoveField(model_name="subsistema", name="consumo_prueba_transitable"),
    ]
