"""
Migration configuracion/0009 — Agrega campo imagen a UnidadAlianza
y elimina el campo url (queda solo en BD para no perder datos existentes,
se oculta del estado de Django mediante SeparateDatabaseAndState).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("configuracion", "0008_alter_unidadalianza_id_alter_unidadclausula_id_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="unidadalianza",
            name="imagen",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to="configuracion/alianzas/",
                verbose_name="Logo / imagen",
            ),
        ),
        # Quitar 'url' del estado de Django (la columna en BD se preserva)
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RemoveField(
                    model_name="unidadalianza",
                    name="url",
                ),
            ],
        ),
    ]
