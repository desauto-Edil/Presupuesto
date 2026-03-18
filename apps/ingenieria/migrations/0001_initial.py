"""
Migración inicial de la app ingenieria.
Crea las tablas de ingeniería (sistemas, subsistemas, reglas, dependencias).
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("catalogos", "0001_initial"),
        ("usuarios", "0001_initial"),
    ]

    operations = [
                migrations.CreateModel(
                    name="Sistema",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("codigo", models.CharField(max_length=50, unique=True)),
                        ("nombre", models.CharField(max_length=200)),
                        ("linea_negocio", models.CharField(
                            choices=[("CUBIERTAS", "Cubiertas"), ("FACHADAS", "Fachadas"), ("OTROS", "Otros")],
                            max_length=20,
                        )),
                        ("descripcion", models.TextField(blank=True, null=True)),
                        ("activo", models.BooleanField(default=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                    ],
                    options={"db_table": "sistemas"},
                ),
                migrations.CreateModel(
                    name="Subsistema",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("sistema", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="subsistemas", to="ingenieria.sistema")),
                        ("codigo", models.CharField(max_length=50, unique=True)),
                        ("nombre", models.CharField(max_length=200)),
                        ("descripcion", models.TextField(blank=True, null=True)),
                        ("activo", models.BooleanField(default=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                    ],
                    options={"db_table": "subsistemas"},
                ),
                migrations.CreateModel(
                    name="ReglaCalculo",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("subsistema", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reglas", to="ingenieria.subsistema")),
                        ("producto", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reglas_calculo", to="catalogos.producto")),
                        ("categoria_producto", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reglas_calculo", to="catalogos.categoriaproducto")),
                        ("codigo", models.CharField(max_length=60)),
                        ("nombre", models.CharField(max_length=200)),
                        ("variable_entrada", models.CharField(blank=True, max_length=80, null=True)),
                        ("coeficiente", models.DecimalField(blank=True, decimal_places=6, max_digits=18, null=True)),
                        ("divisor", models.DecimalField(blank=True, decimal_places=6, max_digits=18, null=True)),
                        ("factor_desperdicio", models.DecimalField(decimal_places=6, default=1.01, max_digits=12)),
                        ("formula_texto", models.TextField()),
                        ("formula_python", models.TextField(blank=True, null=True)),
                        ("tipo_regla", models.CharField(
                            choices=[
                                ("FIJA", "Fija"), ("VARIABLE_SISTEMA", "Variable sistema"),
                                ("VARIABLE_PROYECTO", "Variable proyecto"),
                                ("EDITABLE_USUARIO", "Editable usuario"),
                                ("DERIVADA", "Derivada de otro producto"),
                            ],
                            default="FIJA", max_length=30,
                        )),
                        ("orden_ejecucion", models.IntegerField(default=1)),
                        ("editable_por_proyecto", models.BooleanField(default=False)),
                        ("version", models.IntegerField(default=1)),
                        ("activa", models.BooleanField(default=True)),
                        ("obligatoria", models.BooleanField(default=True)),
                        ("variable_salida", models.CharField(blank=True, max_length=80)),
                        ("caso_prueba", models.TextField(blank=True, null=True)),
                        ("creada_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reglas_creadas", to="usuarios.usuariosistema")),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                    ],
                    options={
                        "db_table": "reglas_calculo",
                        "ordering": ["orden_ejecucion"],
                        "unique_together": {("subsistema", "codigo", "version")},
                    },
                ),
                migrations.CreateModel(
                    name="DependenciaTecnica",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("subsistema", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="dependencias", to="ingenieria.subsistema")),
                        ("producto_origen", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="dependencias_origen", to="catalogos.producto")),
                        ("producto_dependiente", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="dependencias_dependiente", to="catalogos.producto")),
                        ("categoria_producto", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="dependencias_tecnicas", to="catalogos.categoriaproducto")),
                        ("nombre", models.CharField(blank=True, max_length=200)),
                        ("variable_entrada", models.CharField(blank=True, max_length=80, null=True)),
                        ("condicion_texto", models.TextField(blank=True, null=True)),
                        ("obligatoria", models.BooleanField(default=True)),
                        ("orden", models.IntegerField(default=1)),
                        ("tipo_regla", models.CharField(
                            choices=[
                                ("FIJA", "Fija"), ("VARIABLE_SISTEMA", "Variable sistema"),
                                ("VARIABLE_PROYECTO", "Variable proyecto"),
                                ("EDITABLE_USUARIO", "Editable usuario"),
                                ("DERIVADA", "Derivada de otro producto"),
                            ],
                            default="FIJA", max_length=30,
                        )),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                    ],
                    options={"db_table": "dependencias_tecnicas", "ordering": ["orden"]},
                ),
    ]
