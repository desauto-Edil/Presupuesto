"""
0005 — Hace nullable las columnas legadas NOT NULL en proyecto_sistemas.

Las columnas 'orden' y 'variables_extra' son del schema original y tienen
NOT NULL sin default, lo que impide crear nuevas filas con el modelo actual
(que ya no incluye esos campos). Se hacen nullables para compatibilidad.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("presupuestos", "0004_add_missing_columns_proyecto_sistemas"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE proyecto_sistemas
                    ALTER COLUMN orden        DROP NOT NULL,
                    ALTER COLUMN variables_extra DROP NOT NULL;
            """,
            reverse_sql="""
                UPDATE proyecto_sistemas SET orden = 0 WHERE orden IS NULL;
                UPDATE proyecto_sistemas SET variables_extra = '{}' WHERE variables_extra IS NULL;
                ALTER TABLE proyecto_sistemas
                    ALTER COLUMN orden        SET NOT NULL,
                    ALTER COLUMN variables_extra SET NOT NULL;
            """,
        ),
    ]
