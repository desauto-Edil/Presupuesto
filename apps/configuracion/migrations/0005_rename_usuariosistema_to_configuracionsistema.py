"""
Migration 0005 — Renombra UsuarioSistema → ConfiguracionSistema en el estado de Django.

La tabla en BD sigue siendo 'usuarios' (db_table explícito en el modelo).
No se toca ninguna columna ni tabla real.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('configuracion', '0004_add_unidad_negocio_info'),
    ]

    operations = [
        # Solo actualiza el estado de Django; la BD no cambia.
        migrations.SeparateDatabaseAndState(
            database_operations=[],   # nada en la BD
            state_operations=[
                # 1. Eliminar el modelo UsuarioSistema del estado
                migrations.DeleteModel(name='UsuarioSistema'),
                # 2. Crear ConfiguracionSistema en el estado
                #    (db_table='usuarios' → misma tabla que UsuarioSistema)
                migrations.CreateModel(
                    name='ConfiguracionSistema',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                        ('email', models.EmailField(max_length=254, unique=True)),
                        ('nombre_completo', models.CharField(max_length=200)),
                        ('password_hash', models.TextField()),
                        ('unidad_negocio', models.CharField(
                            choices=[('IMPERANDINA', 'Imperandina'), ('SOLARANDINA', 'Solarandina'), ('IMPERTIENDA', 'Impertienda')],
                            max_length=20,
                        )),
                        ('rol', models.CharField(
                            choices=[('ADMINISTRADOR', 'Administrador'), ('PRESUPUESTOS', 'Presupuestos'),
                                     ('COMPRAS', 'Compras'), ('ASESOR_COMERCIAL', 'Asesor comercial'), ('SOLO_LECTURA', 'Solo lectura')],
                            default='SOLO_LECTURA', max_length=30,
                        )),
                        ('activo', models.BooleanField(default=True)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                    ],
                    options={
                        'verbose_name': 'Usuario del sistema',
                        'verbose_name_plural': 'Usuarios del sistema',
                        'db_table': 'usuarios',
                        'app_label': 'configuracion',
                    },
                ),
            ],
        ),
    ]
