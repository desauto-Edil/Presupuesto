"""
Migración inicial de ingeniería.
Las tablas ya existían en DB — aplicar con --fake-initial.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('catalogos', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Sistema',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo', models.CharField(max_length=50, unique=True)),
                ('nombre', models.CharField(max_length=200)),
                ('linea_negocio', models.CharField(choices=[('CUBIERTAS', 'Cubiertas'), ('FACHADAS', 'Fachadas'), ('OTROS', 'Otros')], max_length=20)),
                ('descripcion', models.TextField(blank=True, null=True)),
                ('activo', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Sistema',
                'verbose_name_plural': 'Sistemas',
                'db_table': 'sistemas',
                'app_label': 'ingenieria',
            },
        ),
        migrations.CreateModel(
            name='Subsistema',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo', models.CharField(max_length=50, unique=True)),
                ('nombre', models.CharField(max_length=200)),
                ('descripcion', models.TextField(blank=True, null=True)),
                ('activo', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('sistema', models.ForeignKey(help_text='Sistema padre al que pertenece esta variante técnica', on_delete=django.db.models.deletion.CASCADE, related_name='subsistemas', to='ingenieria.sistema')),
            ],
            options={
                'verbose_name': 'Subsistema (Receta Técnica)',
                'verbose_name_plural': 'Subsistemas (Recetas)',
                'db_table': 'subsistemas',
                'app_label': 'ingenieria',
            },
        ),
        migrations.AlterUniqueTogether(
            name='subsistema',
            unique_together={('sistema', 'codigo')},
        ),
        migrations.CreateModel(
            name='ReglaCalculo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo', models.CharField(max_length=100, unique=True)),
                ('nombre', models.CharField(max_length=200)),
                ('variable_entrada', models.CharField(blank=True, max_length=100, null=True)),
                ('coeficiente', models.DecimalField(decimal_places=6, default=1, max_digits=18)),
                ('divisor', models.DecimalField(decimal_places=6, default=1, max_digits=18)),
                ('factor_desperdicio', models.DecimalField(decimal_places=6, default=1, max_digits=18)),
                ('formula_texto', models.TextField(blank=True, null=True)),
                ('formula_python', models.TextField(blank=True, null=True)),
                ('tipo_regla', models.CharField(blank=True, max_length=100, null=True)),
                ('orden_ejecucion', models.IntegerField(default=0)),
                ('variable_salida', models.CharField(blank=True, max_length=100, null=True)),
                ('activa', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('subsistema', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reglas_calculo', to='ingenieria.subsistema')),
                ('producto', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reglas_calculo', to='catalogos.producto')),
                ('categoria_producto', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reglas_calculo', to='catalogos.categoriaproducto')),
            ],
            options={
                'app_label': 'ingenieria',
                'ordering': ['subsistema', 'orden_ejecucion'],
            },
        ),
        migrations.CreateModel(
            name='DependenciaTecnica',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(blank=True, max_length=200, null=True)),
                ('obligatoria', models.BooleanField(default=False)),
                ('orden', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('subsistema', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='dependencias_tecnicas', to='ingenieria.subsistema')),
                ('producto_origen', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='dependencias_origen', to='catalogos.producto')),
                ('producto_dependiente', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='dependencias_dependiente', to='catalogos.producto')),
                ('categoria_producto', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='dependencias_tecnicas', to='catalogos.categoriaproducto')),
            ],
            options={
                'app_label': 'ingenieria',
            },
        ),
    ]
