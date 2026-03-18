"""
Migración inicial de la app usuarios.
Crea la tabla 'usuarios' directamente (sin dependencia de core).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="UsuarioSistema",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("nombre_completo", models.CharField(max_length=200)),
                ("password_hash", models.TextField()),
                ("rol", models.CharField(
                    choices=[
                        ("ADMINISTRADOR", "Administrador"),
                        ("PRESUPUESTOS", "Presupuestos"),
                        ("COMPRAS", "Compras"),
                        ("ASESOR_COMERCIAL", "Asesor comercial"),
                        ("SOLO_LECTURA", "Solo lectura"),
                    ],
                    default="SOLO_LECTURA",
                    max_length=30,
                )),
                ("activo", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "usuarios"},
        ),
    ]
