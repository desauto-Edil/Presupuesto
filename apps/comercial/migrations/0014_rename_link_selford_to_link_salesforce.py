"""
Migration comercial/0014 — Renombra la columna link_selford → link_salesforce
en la tabla solicitudes.

La BD tiene la columna con el nombre incorrecto 'link_selford'; el modelo
y el resto del código ya usan 'link_salesforce'. Esta migración sincroniza la BD.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("comercial", "0013_add_unidad_negocio_to_cliente"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            # Solo renombramos en BD (ALTER TABLE); el estado de Django
            # ya conoce el campo como 'link_salesforce' desde 0002_redesign.
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE solicitudes RENAME COLUMN link_selford TO link_salesforce;",
                    reverse_sql="ALTER TABLE solicitudes RENAME COLUMN link_salesforce TO link_selford;",
                ),
            ],
            state_operations=[],
        ),
    ]
