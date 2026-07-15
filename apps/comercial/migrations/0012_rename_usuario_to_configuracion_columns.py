"""
Migration comercial/0012 — Renombra columnas usuario_id → configuracion_id en BD.

Contexto:
  - En una BD existente (creada antes de 0011), 0011 solo actualizó el estado Django
    sin tocar las columnas físicas, por lo que aún se llaman usuario_id → necesita
    el RENAME explícito aquí.
  - En una BD nueva (desde cero), 0011 aplica AlterField que implícitamente le hace
    a Django renombrar la columna a configuracion_id, así que al llegar aquí ya
    tiene el nombre correcto y no hay nada que hacer.

Por eso los SQL usan bloques DO $$ IF EXISTS para ser idempotentes en ambos escenarios.
"""

from django.db import migrations


_RENAME_SOLICITUDES = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'solicitudes_archivos' AND column_name = 'usuario_id'
    ) THEN
        ALTER TABLE solicitudes_archivos RENAME COLUMN usuario_id TO configuracion_id;
    END IF;
END $$;
"""

_RENAME_LOGS = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'logs_sistema' AND column_name = 'usuario_id'
    ) THEN
        ALTER TABLE logs_sistema RENAME COLUMN usuario_id TO configuracion_id;
    END IF;
END $$;
"""

_REVERSE_SOLICITUDES = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'solicitudes_archivos' AND column_name = 'configuracion_id'
    ) THEN
        ALTER TABLE solicitudes_archivos RENAME COLUMN configuracion_id TO usuario_id;
    END IF;
END $$;
"""

_REVERSE_LOGS = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'logs_sistema' AND column_name = 'configuracion_id'
    ) THEN
        ALTER TABLE logs_sistema RENAME COLUMN configuracion_id TO usuario_id;
    END IF;
END $$;
"""


class Migration(migrations.Migration):

    dependencies = [
        ('comercial', '0011_alter_logsistema_configuracion_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(sql=_RENAME_SOLICITUDES, reverse_sql=_REVERSE_SOLICITUDES),
                migrations.RunSQL(sql=_RENAME_LOGS,        reverse_sql=_REVERSE_LOGS),
            ],
            state_operations=[],  # El estado Django ya está correcto desde 0011
        ),
    ]
