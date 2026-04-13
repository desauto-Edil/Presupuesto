# Generated manually - Redesign: multi-unidad, versionamiento, archivos, logs
# 2026-03-25

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("comercial", "0001_initial"),
        ("configuracion", "0001_initial"),
    ]

    operations = [

        # ── 1. Cliente: eliminar creacion_Salesforce ────────────────────────────
        migrations.RemoveField(
            model_name="cliente",
            name="creacion_salesforce",
        ),

        # ── 2. Solicitud: agregar link_salesforce ───────────────────────────────
        migrations.AddField(
            model_name="solicitud",
            name="link_salesforce",
            field=models.URLField(
                verbose_name="Link de Salesforce",
                help_text="URL directa al registro en Salesforce",
                default="https://salesforce.example.com",
            ),
            preserve_default=False,
        ),

        # ── 3. Solicitud: actualizar verbose_name del consecutivo ────────────
        migrations.AlterField(
            model_name="solicitud",
            name="consecutivo",
            field=models.CharField(
                max_length=30,
                unique=True,
                verbose_name="Consecutivo de Salesforce",
                help_text="Número de consecutivo asignado en Salesforce",
            ),
        ),

        # ── 4. Proyecto: cambiar solicitud de OneToOneField a ForeignKey ─────
        migrations.AlterField(
            model_name="proyecto",
            name="solicitud",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="proyectos",
                to="comercial.solicitud",
            ),
        ),

        # ── 5. Proyecto: agregar campo version ───────────────────────────────
        migrations.AddField(
            model_name="proyecto",
            name="version",
            field=models.PositiveIntegerField(default=1, verbose_name="Versión"),
        ),

        # ── 6. Proyecto: agregar campo es_version_actual ─────────────────────
        migrations.AddField(
            model_name="proyecto",
            name="es_version_actual",
            field=models.BooleanField(default=True, verbose_name="Es versión actual"),
        ),

        # ── 7. Proyecto: actualizar Meta.ordering ─────────────────────────────
        migrations.AlterModelOptions(
            name="proyecto",
            options={"ordering": ["-version"]},
        ),

        # ── 8. Crear modelo ProyectoArchivo ──────────────────────────────────
        migrations.CreateModel(
            name="ProyectoArchivo",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("archivo", models.FileField(upload_to="proyectos/archivos/%Y/%m/", verbose_name="Archivo")),
                ("nombre", models.CharField(max_length=300, verbose_name="Nombre del archivo")),
                ("fecha_subida", models.DateTimeField(auto_now_add=True, verbose_name="Fecha de subida")),
                (
                    "proyecto",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="archivos",
                        to="comercial.proyecto",
                        verbose_name="Proyecto",
                    ),
                ),
                (
                    "usuario",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="archivos_subidos",
                        to="configuracion.usuariosistema",
                        verbose_name="Subido por",
                    ),
                ),
            ],
            options={
                "verbose_name": "Archivo de proyecto",
                "verbose_name_plural": "Archivos de proyecto",
                "db_table": "proyectos_archivos",
                "ordering": ["-fecha_subida"],
            },
        ),

        # ── 9. LogSistema: crear tabla (no fue creada en 0001) ───────────────
        # La tabla "comercial_logsistema" aparece en 0001_initial pero nunca
        # se creó físicamente en la BD. La creamos aquí con db_table="logs_sistema"
        # y todos los campos necesarios de una sola vez.
        migrations.RunSQL(
            sql="""
            CREATE TABLE IF NOT EXISTS logs_sistema (
                id          BIGSERIAL PRIMARY KEY,
                usuario_id  BIGINT NOT NULL
                            REFERENCES usuarios(id) ON DELETE CASCADE,
                unidad_negocio VARCHAR(20)  NOT NULL DEFAULT '',
                accion         VARCHAR(100) NOT NULL DEFAULT '',
                descripcion    TEXT         NOT NULL DEFAULT '',
                modelo_afectado VARCHAR(100) NOT NULL DEFAULT '',
                objeto_id      INTEGER,
                created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS logs_sistema_unidad_idx
                ON logs_sistema(unidad_negocio);
            """,
            reverse_sql="DROP TABLE IF EXISTS logs_sistema;",
        ),

        # ── 10. Registrar el modelo LogSistema en el estado Django ───────────
        # Usa SeparateDatabaseAndState: la BD ya tiene la tabla (paso 9),
        # aquí solo sincronizamos el estado de migraciones.
        migrations.SeparateDatabaseAndState(
            database_operations=[],   # nada: tabla ya existe
            state_operations=[
                migrations.CreateModel(
                    name="LogSistema",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        (
                            "usuario",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="logs",
                                to="configuracion.usuariosistema",
                            ),
                        ),
                        ("unidad_negocio", models.CharField(db_index=True, max_length=20, verbose_name="Unidad de negocio")),
                        ("accion", models.CharField(max_length=100, verbose_name="Acción")),
                        ("descripcion", models.TextField(blank=True, default="", verbose_name="Descripción")),
                        ("modelo_afectado", models.CharField(blank=True, max_length=100, verbose_name="Modelo afectado")),
                        ("objeto_id", models.PositiveIntegerField(blank=True, null=True, verbose_name="ID del objeto")),
                        ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Fecha")),
                    ],
                    options={
                        "verbose_name": "Log del sistema",
                        "verbose_name_plural": "Logs del sistema",
                        "db_table": "logs_sistema",
                        "ordering": ["-created_at"],
                    },
                ),
            ],
        ),
    ]
