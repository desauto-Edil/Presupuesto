"""
Migration comercial/0014 — Renombra la columna link_selford → link_salesforce
en la tabla solicitudes.

En BD existente: la columna tenía el typo 'link_selford' → se renombra aquí.
En BD nueva: 0002_redesign ya crea el campo como 'link_salesforce' (AddField),
  por lo que la columna nunca tuvo el nombre incorrecto → SQL es no-op.
El bloque DO $$ IF EXISTS garantiza idempotencia en ambos escenarios.
"""

from django.db import migrations


_RENAME_SQL = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'solicitudes' AND column_name = 'link_selford'
    ) THEN
        ALTER TABLE solicitudes RENAME COLUMN link_selford TO link_salesforce;
    END IF;
END $$;
"""

_REVERSE_SQL = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'solicitudes' AND column_name = 'link_salesforce'
    ) THEN
        ALTER TABLE solicitudes RENAME COLUMN link_salesforce TO link_selford;
    END IF;
END $$;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("comercial", "0013_add_unidad_negocio_to_cliente"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            # El estado de Django ya conoce el campo como 'link_salesforce' desde
            # 0002_redesign; aquí solo sincronizamos la columna física si es necesario.
            database_operations=[
                migrations.RunSQL(sql=_RENAME_SQL, reverse_sql=_REVERSE_SQL),
            ],
            state_operations=[],
        ),
    ]
