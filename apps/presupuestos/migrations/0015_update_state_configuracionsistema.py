"""
Migration presupuestos/0015 — Actualiza el estado de Django para:
- ConfiguracionAPU.modificado_por: apunta ahora a configuracion.ConfiguracionSistema
- APULinea.editable: actualiza help_text

La BD no cambia (FK ya apunta a la tabla 'usuarios' = ConfiguracionSistema).
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('configuracion', '0005_rename_usuariosistema_to_configuracionsistema'),
        ('presupuestos', '0014_alter_apuproyecto_factor_venta_pct_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],  # ningún cambio en BD
            state_operations=[
                # ConfiguracionAPU.modificado_por apunta a la nueva clase
                migrations.AlterField(
                    model_name='configuracionapu',
                    name='modificado_por',
                    field=models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='configs_apu',
                        to='configuracion.configuracionsistema',
                    ),
                ),
                # APULinea.editable — actualizar help_text
                migrations.AlterField(
                    model_name='apulinea',
                    name='editable',
                    field=models.BooleanField(
                        default=False,
                        help_text='Si True, el usuario puede modificar precio_referencia y rendimiento.',
                    ),
                ),
            ],
        ),
    ]
