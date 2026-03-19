"""
0006 — Pone DEFAULT NOW() en las columnas de timestamp legadas.

'created_at' y 'updated_at' son columnas del schema original que no están
en el modelo Django nuevo. Sin DEFAULT, PostgreSQL falla el INSERT porque
Django no las incluye en el statement. Se asigna NOW() como valor por defecto.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("presupuestos", "0005_fix_legacy_notnull_columns"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE proyecto_sistemas
                    ALTER COLUMN created_at SET DEFAULT NOW(),
                    ALTER COLUMN updated_at SET DEFAULT NOW();
            """,
            reverse_sql="""
                ALTER TABLE proyecto_sistemas
                    ALTER COLUMN created_at DROP DEFAULT,
                    ALTER COLUMN updated_at DROP DEFAULT;
            """,
        ),
    ]
