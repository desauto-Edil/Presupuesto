"""
0004 — Agrega columnas faltantes a proyecto_sistemas.

La tabla existía con el schema viejo (variables_extra, total_powergip, etc.)
y la migración 0001 fue fake-applied. Esta migración agrega las columnas
que el modelo actual necesita y que no estaban en la BD:
  - solicitud_id  (FK nullable a comercial_solicitudes)
  - parametros_entrada  (JSONField)

Las columnas viejas (orden, total_powergip, cuadrilla_personas, variables_extra,
observaciones) se dejan intactas — Django las ignora.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("presupuestos", "0003_alter_despiecelinea_options_and_more"),
        ("comercial", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="proyectosistema",
            name="solicitud",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="proyecto_sistemas",
                to="comercial.solicitud",
            ),
        ),
        migrations.AddField(
            model_name="proyectosistema",
            name="parametros_entrada",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Variables de entrada específicas de este sistema. "
                    "Ej: {'total_powergrip': 2883, 'tornilleria_u7': 8, 'desperdicio': 1.01}"
                ),
            ),
        ),
    ]
