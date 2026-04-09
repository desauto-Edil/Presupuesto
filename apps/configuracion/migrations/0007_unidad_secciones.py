"""
Migration 0007 — Agrega columnas nuevas a configuracion_unidades
y crea las tablas configuracion_politicas, configuracion_clausulas,
configuracion_alianzas.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('configuracion', '0006_alter_configuracionsistema_id_and_more'),
    ]

    operations = [
        # ── Nuevas columnas en configuracion_unidades ──────────────────────────
        migrations.AddField(
            model_name='unidadnegocioinfo',
            name='quienes_somos',
            field=models.TextField(blank=True, default='', verbose_name='Quiénes somos'),
        ),
        migrations.AddField(
            model_name='unidadnegocioinfo',
            name='mision',
            field=models.TextField(blank=True, default='', verbose_name='Misión'),
        ),
        migrations.AddField(
            model_name='unidadnegocioinfo',
            name='vision',
            field=models.TextField(blank=True, default='', verbose_name='Visión'),
        ),
        migrations.AddField(
            model_name='unidadnegocioinfo',
            name='sitio_web',
            field=models.URLField(blank=True, default='', verbose_name='Sitio web'),
        ),
        # Quitar descripcion (reemplazada por quienes_somos/mision/vision)
        migrations.RemoveField(
            model_name='unidadnegocioinfo',
            name='descripcion',
        ),

        # ── Tabla políticas ────────────────────────────────────────────────────
        migrations.CreateModel(
            name='UnidadPolitica',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('titulo', models.CharField(max_length=200, verbose_name='Título')),
                ('descripcion', models.TextField(verbose_name='Descripción')),
                ('orden', models.PositiveIntegerField(default=0)),
                ('unidad', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='politicas', to='configuracion.unidadnegocioinfo')),
            ],
            options={
                'verbose_name': 'Política',
                'verbose_name_plural': 'Políticas',
                'db_table': 'configuracion_politicas',
                'ordering': ['orden', 'titulo'],
                'app_label': 'configuracion',
            },
        ),

        # ── Tabla cláusulas ────────────────────────────────────────────────────
        migrations.CreateModel(
            name='UnidadClausula',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('titulo', models.CharField(max_length=200, verbose_name='Título')),
                ('descripcion', models.TextField(verbose_name='Descripción')),
                ('orden', models.PositiveIntegerField(default=0)),
                ('unidad', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='clausulas', to='configuracion.unidadnegocioinfo')),
            ],
            options={
                'verbose_name': 'Cláusula',
                'verbose_name_plural': 'Cláusulas',
                'db_table': 'configuracion_clausulas',
                'ordering': ['orden', 'titulo'],
                'app_label': 'configuracion',
            },
        ),

        # ── Tabla alianzas ─────────────────────────────────────────────────────
        migrations.CreateModel(
            name='UnidadAlianza',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('nombre', models.CharField(max_length=200, verbose_name='Nombre del aliado')),
                ('descripcion', models.TextField(blank=True, default='', verbose_name='Descripción')),
                ('url', models.URLField(blank=True, default='', verbose_name='Sitio web')),
                ('orden', models.PositiveIntegerField(default=0)),
                ('unidad', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='alianzas', to='configuracion.unidadnegocioinfo')),
            ],
            options={
                'verbose_name': 'Alianza',
                'verbose_name_plural': 'Alianzas',
                'db_table': 'configuracion_alianzas',
                'ordering': ['orden', 'nombre'],
                'app_label': 'configuracion',
            },
        ),
    ]
