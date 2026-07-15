"""
Migración 0017 — Agrega tipo_entrada y opciones a VariableSubsistema.

- tipo_entrada: CharField con opciones NUMERO / TEXTO / OPCION_UNICA, default NUMERO.
  Las variables existentes quedan como NUMERO (comportamiento idéntico al anterior).
- opciones: JSONField con lista vacía por defecto.
  Solo se usa cuando tipo_entrada = OPCION_UNICA.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ingenieria", "0016_consolidacion_despiece"),
    ]

    operations = [
        migrations.AddField(
            model_name="variablesubsistema",
            name="tipo_entrada",
            field=models.CharField(
                choices=[
                    ("NUMERO", "Número"),
                    ("TEXTO", "Texto"),
                    ("OPCION_UNICA", "Opción única"),
                ],
                default="NUMERO",
                help_text="NUMERO: campo numérico libre. TEXTO: campo texto libre. OPCION_UNICA: lista de opciones.",
                max_length=20,
                verbose_name="Tipo de entrada",
            ),
        ),
        migrations.AddField(
            model_name="variablesubsistema",
            name="opciones",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Lista de valores permitidos para OPCION_UNICA. Ej: ["4", "6"]',
                verbose_name="Opciones",
            ),
        ),
    ]
