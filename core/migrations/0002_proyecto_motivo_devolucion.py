"""
0002_proyecto_motivo_devolucion.py

Agrega el campo `motivo_devolucion` al modelo Proyecto.
El nuevo estado `EN_REVISION_COMPRAS` no requiere migración ya que es
un TextChoices sobre un CharField existente.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="proyecto",
            name="motivo_devolucion",
            field=models.TextField(
                blank=True,
                null=True,
                help_text="Motivo de rechazo o devolución por parte del Administrador o Compras",
            ),
        ),
    ]
