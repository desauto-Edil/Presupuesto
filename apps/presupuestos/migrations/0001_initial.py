"""
Migración inicial de la app presupuestos.
SeparateDatabaseAndState: las tablas ya existen, solo registramos el estado.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("catalogos", "0001_initial"),
        ("ingenieria", "0001_initial"),
        ("comercial", "0001_initial"),
        ("usuarios", "0001_initial"),
    ]

    operations = [
                migrations.CreateModel(
                    name="ProyectoSistema",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("proyecto", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="proyecto_sistemas", to="comercial.proyecto")),
                        ("sistema", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="proyecto_sistemas", to="ingenieria.sistema")),
                        ("subsistema", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="proyecto_sistemas", to="ingenieria.subsistema")),
                        ("orden", models.IntegerField(default=1)),
                        ("total_powergip", models.DecimalField(blank=True, decimal_places=4, max_digits=14, null=True)),
                        ("cuadrilla_personas", models.IntegerField(blank=True, null=True)),
                        ("variables_extra", models.JSONField(blank=True, default=dict)),
                        ("observaciones", models.TextField(blank=True, null=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                    ],
                    options={
                        "db_table": "proyecto_sistemas",
                        "unique_together": {("proyecto", "sistema", "subsistema")},
                    },
                ),
                migrations.CreateModel(
                    name="DespieceLinea",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("proyecto", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="despiece_lineas", to="comercial.proyecto")),
                        ("proyecto_sistema", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="despiece_lineas", to="presupuestos.proyectoSistema")),
                        ("producto", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="despiece_lineas", to="catalogos.producto")),
                        ("categoria_producto", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="despiece_lineas", to="catalogos.categoriaproducto")),
                        ("dependencia_tecnica", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="despiece_lineas", to="ingenieria.dependenciatecnica")),
                        ("regla", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="despiece_lineas", to="ingenieria.reglacalculo")),
                        ("cantidad_calculada", models.DecimalField(decimal_places=6, max_digits=18)),
                        ("cantidad_ajustada", models.DecimalField(blank=True, decimal_places=6, max_digits=18, null=True)),
                        ("motivo_ajuste", models.TextField(blank=True, null=True)),
                        ("precio_snapshot", models.DecimalField(blank=True, decimal_places=6, max_digits=18, null=True)),
                        ("es_dependencia_automatica", models.BooleanField(default=False)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                    ],
                    options={"db_table": "despiece_lineas"},
                ),
                migrations.CreateModel(
                    name="ConfiguracionAPU",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("nombre", models.CharField(default="Configuración global", max_length=100)),
                        ("porcentaje_ganancia", models.DecimalField(decimal_places=4, default=20, max_digits=8)),
                        ("aiu_contratista", models.DecimalField(decimal_places=4, default=30, max_digits=8)),
                        ("desperdicio", models.DecimalField(decimal_places=4, default=3, max_digits=8)),
                        ("margen_ganancia_contratista", models.DecimalField(decimal_places=4, default=30, max_digits=8)),
                        ("activa", models.BooleanField(default=True)),
                        ("modificado_por", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="configs_apu", to="usuarios.usuariosistema")),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                    ],
                    options={"db_table": "configuracion_apu"},
                ),
                migrations.CreateModel(
                    name="APUProyecto",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("proyecto_sistema", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="apu", to="presupuestos.proyectoSistema")),
                        ("factor_venta_pct", models.DecimalField(decimal_places=4, default=20, max_digits=8)),
                        ("iva_pct", models.DecimalField(decimal_places=4, default=19, max_digits=8)),
                        ("aplica_iva", models.BooleanField(default=True)),
                        ("aiu_contratista_pct", models.DecimalField(decimal_places=4, default=30, max_digits=8)),
                        ("margen_contratista_pct", models.DecimalField(decimal_places=4, default=30, max_digits=8)),
                        ("dias_trabajo", models.DecimalField(blank=True, decimal_places=4, max_digits=10, null=True)),
                        ("tiempo_estimado_meses", models.DecimalField(blank=True, decimal_places=4, max_digits=10, null=True)),
                        ("rendimiento_und_dia", models.DecimalField(blank=True, decimal_places=6, max_digits=14, null=True)),
                        ("subtotal_materiales", models.DecimalField(decimal_places=4, default=0, max_digits=18)),
                        ("subtotal_herramientas", models.DecimalField(decimal_places=4, default=0, max_digits=18)),
                        ("subtotal_transporte", models.DecimalField(decimal_places=4, default=0, max_digits=18)),
                        ("subtotal_mano_obra", models.DecimalField(decimal_places=4, default=0, max_digits=18)),
                        ("subtotal_administracion", models.DecimalField(decimal_places=4, default=0, max_digits=18)),
                        ("total_costo", models.DecimalField(decimal_places=4, default=0, max_digits=18)),
                        ("total_valor_venta", models.DecimalField(decimal_places=4, default=0, max_digits=18)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                    ],
                    options={"db_table": "apu_proyectos"},
                ),
                migrations.CreateModel(
                    name="APULinea",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("apu", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lineas", to="presupuestos.apuproyecto")),
                        ("tipo", models.CharField(
                            choices=[
                                ("MATERIALES", "Materiales"),
                                ("HERRAMIENTAS_EQUIPOS", "Herramientas y equipos"),
                                ("TRANSPORTE", "Transporte"),
                                ("MANO_DE_OBRA", "Mano de obra"),
                                ("ADMINISTRACION", "Administración"),
                            ],
                            max_length=30,
                        )),
                        ("descripcion", models.CharField(max_length=300)),
                        ("despiece_linea", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="apu_lineas", to="presupuestos.despiecelinea")),
                        ("rendimiento", models.DecimalField(decimal_places=6, default=1, max_digits=14)),
                        ("precio_referencia", models.DecimalField(decimal_places=6, default=0, max_digits=18)),
                        ("iva_aplicado", models.BooleanField(default=True)),
                        ("costo_unitario", models.DecimalField(decimal_places=6, default=0, max_digits=18)),
                        ("costo_total", models.DecimalField(decimal_places=6, default=0, max_digits=18)),
                        ("valor_unitario", models.DecimalField(decimal_places=6, default=0, max_digits=18)),
                        ("valor_total", models.DecimalField(decimal_places=6, default=0, max_digits=18)),
                        ("editable", models.BooleanField(default=False)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                    ],
                    options={"db_table": "apu_lineas", "ordering": ["tipo", "descripcion"]},
                ),
    ]
