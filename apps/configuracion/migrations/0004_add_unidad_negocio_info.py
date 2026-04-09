"""
Migration 0004 — Crea tabla configuracion_unidades para UnidadNegocioInfo.

Usa SeparateDatabaseAndState para crear solo la tabla en BD sin intentar
reconciliar el estado del modelo (la app tuvo un renombre de UsuarioSistema
→ ConfiguracionSistema que no está reflejado en las migraciones previas).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('configuracion', '0003_rename_app_from_usuarios_to_configuracion'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                    CREATE TABLE IF NOT EXISTS configuracion_unidades (
                        id          BIGSERIAL PRIMARY KEY,
                        codigo      VARCHAR(20)  NOT NULL UNIQUE,
                        razon_social VARCHAR(200) NOT NULL DEFAULT '',
                        nit         VARCHAR(30)  NOT NULL DEFAULT '',
                        ciudad      VARCHAR(100) NOT NULL DEFAULT '',
                        direccion   VARCHAR(300) NOT NULL DEFAULT '',
                        telefono    VARCHAR(50)  NOT NULL DEFAULT '',
                        email       VARCHAR(254) NOT NULL DEFAULT '',
                        descripcion TEXT         NOT NULL DEFAULT '',
                        activa      BOOLEAN      NOT NULL DEFAULT TRUE,
                        created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                        updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
                    );
                    """,
                    reverse_sql="DROP TABLE IF EXISTS configuracion_unidades;",
                ),
            ],
            state_operations=[
                migrations.CreateModel(
                    name='UnidadNegocioInfo',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                        ('codigo', models.CharField(max_length=20, unique=True,
                            choices=[('IMPERANDINA', 'Imperandina'), ('SOLARANDINA', 'Solarandina'), ('IMPERTIENDA', 'Impertienda')])),
                        ('razon_social', models.CharField(max_length=200, verbose_name='Razón social')),
                        ('nit', models.CharField(max_length=30, blank=True)),
                        ('ciudad', models.CharField(max_length=100, blank=True, default='')),
                        ('direccion', models.CharField(max_length=300, blank=True, default='')),
                        ('telefono', models.CharField(max_length=50, blank=True, default='')),
                        ('email', models.EmailField(blank=True, default='')),
                        ('descripcion', models.TextField(blank=True, default='')),
                        ('activa', models.BooleanField(default=True)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                    ],
                    options={
                        'verbose_name': 'Unidad de negocio',
                        'verbose_name_plural': 'Unidades de negocio',
                        'db_table': 'configuracion_unidades',
                        'ordering': ['codigo'],
                        'app_label': 'configuracion',
                    },
                ),
            ],
        ),
    ]
