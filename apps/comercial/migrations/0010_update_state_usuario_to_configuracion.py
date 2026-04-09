"""
Migration comercial/0010 — Actualiza el estado de Django para reflejar el renombre
UsuarioSistema → ConfiguracionSistema y los campos usuario → configuracion.

La BD NO cambia: las columnas 'usuario_id' y 'creado_por_id' ya existen con los
datos correctos apuntando a la tabla 'usuarios' (= ConfiguracionSistema).
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('configuracion', '0005_rename_usuariosistema_to_configuracionsistema'),
        ('comercial', '0009_proyecto_num_personas'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],  # ningún cambio en BD
            state_operations=[
                # ── SolicitudArchivo: campo 'usuario' → 'configuracion' ──────────
                migrations.RemoveField(
                    model_name='solicitudarchivo',
                    name='usuario',
                ),
                migrations.AddField(
                    model_name='solicitudarchivo',
                    name='configuracion',
                    field=models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='archivos_solicitud',
                        to='configuracion.configuracionsistema',
                        verbose_name='Subido por',
                        db_column='usuario_id',   # columna real en BD
                    ),
                ),

                # ── LogSistema: campo 'usuario' → 'configuracion' ────────────────
                migrations.RemoveField(
                    model_name='logsistema',
                    name='usuario',
                ),
                migrations.AddField(
                    model_name='logsistema',
                    name='configuracion',
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='logs',
                        to='configuracion.configuracionsistema',
                        db_column='usuario_id',   # columna real en BD
                    ),
                ),

                # ── Solicitud.creado_por: actualizar target del FK ───────────────
                migrations.AlterField(
                    model_name='solicitud',
                    name='creado_por',
                    field=models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='solicitudes_creadas',
                        to='configuracion.configuracionsistema',
                    ),
                ),

                # ── Proyecto.creado_por: actualizar target del FK ────────────────
                migrations.AlterField(
                    model_name='proyecto',
                    name='creado_por',
                    field=models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='proyectos_creados',
                        to='configuracion.configuracionsistema',
                    ),
                ),
            ],
        ),
    ]
