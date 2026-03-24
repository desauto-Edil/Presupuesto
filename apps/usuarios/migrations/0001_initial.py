from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='UsuarioSistema',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.EmailField(unique=True, max_length=254)),
                ('nombre_completo', models.CharField(max_length=200)),
                ('password_hash', models.TextField()),
                ('unidad_negocio', models.CharField(choices=[('IMPERANDINA', 'Imperandina'), ('SOLARANDINA', 'Solarandina'), ('IMPERTIENDA', 'Impertienda')], default='IMPERANDINA', max_length=20)),
                ('rol', models.CharField(choices=[('ADMINISTRADOR', 'Administrador'), ('PRESUPUESTOS', 'Presupuestos'), ('COMPRAS', 'Compras'), ('ASESOR_COMERCIAL', 'Asesor comercial'), ('SOLO_LECTURA', 'Solo lectura')], default='SOLO_LECTURA', max_length=30)),
                ('activo', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'usuarios',
            },
        ),
    ]
