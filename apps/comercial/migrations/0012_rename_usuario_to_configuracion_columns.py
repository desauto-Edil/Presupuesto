"""
Migration comercial/0012 — Renombra columnas usuario_id → configuracion_id en BD.

La migración 0011 actualizó el estado Django (sin db_column), pero no renombró
las columnas físicas. Esta migración ejecuta los RENAME COLUMN reales.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('comercial', '0011_alter_logsistema_configuracion_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE solicitudes_archivos RENAME COLUMN usuario_id TO configuracion_id;",
                    reverse_sql="ALTER TABLE solicitudes_archivos RENAME COLUMN configuracion_id TO usuario_id;",
                ),
                migrations.RunSQL(
                    sql="ALTER TABLE logs_sistema RENAME COLUMN usuario_id TO configuracion_id;",
                    reverse_sql="ALTER TABLE logs_sistema RENAME COLUMN configuracion_id TO usuario_id;",
                ),
            ],
            state_operations=[],  # El estado Django ya está correcto desde 0011
        ),
    ]
