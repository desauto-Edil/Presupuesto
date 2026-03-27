"""
apps/comercial/models.py

Dominio: gestión de la relación con el cliente desde el primer contacto
hasta el seguimiento de solicitudes y proyectos de presupuesto.

  Cliente → ContactoCliente
  Cliente → Solicitud → SolicitudArchivo
  Solicitud → Proyecto (ForeignKey, versionado: N versiones por solicitud)

Flujo: Solicitud → crear Proyecto (versión) → seleccionar Sistema → Despiece

Dependencias:
  - apps.common.choices (EstadoSolicitud, EstadoProyecto, Moneda)
  - apps.usuarios (UsuarioSistema, vía FK de auditoría)
"""

from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# CLIENTES
# ---------------------------------------------------------------------------

class Cliente(models.Model):
    nit = models.CharField(max_length=50, unique=True)
    razon_social = models.CharField(max_length=300)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "comercial"
        db_table = "clientes"

    def __str__(self):
        return f"{self.razon_social} ({self.nit})"

    @property
    def contacto_principal(self):
        return self.contactos.filter(es_principal=True, activo=True).first()


class ContactoCliente(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name="contactos")
    nombre = models.CharField(max_length=200)
    cargo = models.CharField(max_length=120, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    telefono = models.CharField(max_length=30, blank=True, null=True)
    es_principal = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "comercial"
        db_table = "contactos_cliente"

    def __str__(self):
        return f"{self.nombre} — {self.cliente.razon_social}"


# ---------------------------------------------------------------------------
# TIPO DE PROYECTO
# ---------------------------------------------------------------------------

class TipoProyecto(models.Model):
    codigo = models.CharField(max_length=40, unique=True)
    nombre = models.CharField(max_length=120, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        app_label = "comercial"
        db_table = "tipos_proyecto"

    def __str__(self):
        return self.nombre


# ---------------------------------------------------------------------------
# SOLICITUDES
# ---------------------------------------------------------------------------

class Solicitud(models.Model):
    """
    Solicitud de presupuesto proveniente de Selford.
    El consecutivo es provisto por el usuario (no auto-generado).
    Los archivos asociados se gestionan en SolicitudArchivo.
    """
    from apps.common.choices import EstadoSolicitud

    consecutivo = models.CharField(
        max_length=30,
        unique=True,
        verbose_name="Consecutivo de Selford",
        help_text="Número de consecutivo asignado en Selford",
    )
    link_selford = models.URLField(
        verbose_name="Link de Selford",
        help_text="URL directa al registro en Selford",
    )
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="solicitudes")
    contacto = models.ForeignKey(
        ContactoCliente, on_delete=models.SET_NULL,
        blank=True, null=True, related_name="solicitudes",
    )
    creado_por = models.ForeignKey(
        "usuarios.UsuarioSistema", on_delete=models.SET_NULL,
        blank=True, null=True, related_name="solicitudes_creadas",
    )
    nombre = models.CharField(max_length=300, verbose_name="Nombre / descripción")
    descripcion = models.TextField(blank=True, null=True)
    fecha_entrega = models.DateField(null=True, blank=True)
    estado = models.CharField(
        max_length=20, choices=EstadoSolicitud.choices, default=EstadoSolicitud.EN_GESTION
    )
    observaciones = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "comercial"
        db_table = "solicitudes"

    def __str__(self):
        return f"{self.consecutivo} — {self.nombre}"

    def save(self, *args, **kwargs):
        # Asignar contacto principal del cliente si no se especificó
        if not self.contacto_id and self.cliente_id:
            self.contacto = self.cliente.contacto_principal
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# ARCHIVOS DE SOLICITUD
# ---------------------------------------------------------------------------

class SolicitudArchivo(models.Model):
    """
    Archivo adjunto a una Solicitud.
    Centraliza toda la documentación en la solicitud, sin depender de proyectos.
    """
    solicitud = models.ForeignKey(
        Solicitud, on_delete=models.CASCADE, related_name="archivos",
        verbose_name="Solicitud",
    )
    archivo = models.FileField(
        upload_to="solicitudes/archivos/%Y/%m/",
        verbose_name="Archivo",
    )
    nombre = models.CharField(max_length=300, verbose_name="Nombre del archivo")
    fecha_subida = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de subida")
    usuario = models.ForeignKey(
        "usuarios.UsuarioSistema", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="archivos_solicitud",
        verbose_name="Subido por",
    )

    class Meta:
        app_label = "comercial"
        db_table = "solicitudes_archivos"
        verbose_name = "Archivo de solicitud"
        verbose_name_plural = "Archivos de solicitud"
        ordering = ["-fecha_subida"]

    def __str__(self):
        return f"{self.nombre} — {self.solicitud.consecutivo}"

    @property
    def extension(self):
        import os
        _, ext = os.path.splitext(self.archivo.name)
        return ext.lower().lstrip(".")


# ---------------------------------------------------------------------------
# PROYECTOS
# ---------------------------------------------------------------------------

class Proyecto(models.Model):
    """
    Versión de presupuesto para una Solicitud.
    Una Solicitud puede tener N Proyectos (versiones); solo uno es el actual.

    Flujo: Solicitud → Proyecto → ProyectoSistema → Despiece → APU
    """
    from apps.common.choices import EstadoProyecto, Moneda

    consecutivo = models.CharField(max_length=30, unique=True)

    # ── Relación con solicitud (versionado) ──────────────────────────────────
    solicitud = models.ForeignKey(
        Solicitud,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="proyectos",          # solicitud.proyectos.all()
    )
    version = models.PositiveIntegerField(
        default=1,
        verbose_name="Versión",
        help_text="Número de versión dentro de la solicitud",
    )
    es_version_actual = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name="Es versión actual",
        help_text="Solo una versión por solicitud puede ser la actual",
    )

    # ── Datos del proyecto ───────────────────────────────────────────────────
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="proyectos")
    creado_por = models.ForeignKey(
        "usuarios.UsuarioSistema", on_delete=models.SET_NULL,
        blank=True, null=True, related_name="proyectos_creados",
    )
    tipo_proyecto = models.ForeignKey(
        TipoProyecto, on_delete=models.SET_NULL,
        blank=True, null=True, related_name="proyectos",
    )
    nombre = models.CharField(max_length=300)
    descripcion = models.TextField(blank=True, null=True)
    fecha_proyecto = models.DateField(auto_now_add=True)
    area_total_m2 = models.DecimalField(max_digits=14, decimal_places=4, blank=True, null=True)
    perimetro_ml = models.DecimalField(max_digits=14, decimal_places=4, blank=True, null=True)

    # ── Parámetros financieros ───────────────────────────────────────────────
    trm = models.DecimalField(max_digits=14, decimal_places=4, default=4200)
    margen_comercial_pct = models.DecimalField(max_digits=8, decimal_places=4, default=130)
    iva_pct = models.DecimalField(max_digits=8, decimal_places=4, default=19)
    aiu_pct = models.DecimalField(max_digits=8, decimal_places=4, default=130)
    moneda = models.CharField(max_length=3, choices=Moneda.choices, default=Moneda.COP)
    aplica_exencion_iva = models.BooleanField(default=False)
    observaciones = models.TextField(blank=True, null=True)

    estado = models.CharField(
        max_length=25, choices=EstadoProyecto.choices, default=EstadoProyecto.SOLICITUD
    )
    motivo_devolucion = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "comercial"
        db_table = "proyectos"
        ordering = ["-version"]

    def __str__(self):
        return f"{self.consecutivo} v{self.version} — {self.nombre}"

    def save(self, *args, **kwargs):
        if not self.pk and not self.consecutivo:
            self.consecutivo = self.__class__.siguiente_consecutivo()
        # Auto-versionado: solo cuando se crea un proyecto vinculado a solicitud
        if not self.pk and self.solicitud_id:
            ultimo = (
                Proyecto.objects.filter(solicitud_id=self.solicitud_id)
                .order_by("-version")
                .first()
            )
            self.version = (ultimo.version + 1) if ultimo else 1
            # Marcar todas las versiones anteriores como no actuales
            Proyecto.objects.filter(
                solicitud_id=self.solicitud_id
            ).update(es_version_actual=False)
            self.es_version_actual = True
        super().save(*args, **kwargs)

    @classmethod
    def siguiente_consecutivo(cls):
        year = timezone.now().year
        prefix = f"PRY-{year}-"
        last = cls.objects.filter(consecutivo__startswith=prefix).order_by("-consecutivo").first()
        num = (int(last.consecutivo.split("-")[-1]) + 1) if last else 1
        return f"{prefix}{num:04d}"

    # ── Transiciones de estado ────────────────────────────────────────────────

    def avanzar_a_despiece(self):
        """Avanza el estado a DESPIECE si el estado actual lo permite."""
        from apps.common.choices import EstadoProyecto
        permitidos = {
            EstadoProyecto.BORRADOR,
            EstadoProyecto.SOLICITUD,
            EstadoProyecto.DESPIECE,
            EstadoProyecto.EN_REVISION_COMPRAS,
        }
        if self.estado in permitidos:
            self.estado = EstadoProyecto.DESPIECE
            self.save(update_fields=["estado", "updated_at"])

    def avanzar_a_apu(self):
        """Avanza el estado a APU en proceso."""
        from apps.common.choices import EstadoProyecto
        self.estado = EstadoProyecto.APU
        self.save(update_fields=["estado", "updated_at"])


# ---------------------------------------------------------------------------
# LOG DEL SISTEMA
# ---------------------------------------------------------------------------

class LogSistema(models.Model):
    """
    Registro de auditoría de acciones importantes.
    Filtrado por unidad de negocio del usuario.
    """
    usuario = models.ForeignKey(
        "usuarios.UsuarioSistema", on_delete=models.CASCADE,
        related_name="logs",
    )
    unidad_negocio = models.CharField(
        max_length=20,
        verbose_name="Unidad de negocio",
        db_index=True,
    )
    accion = models.CharField(
        max_length=100,
        verbose_name="Acción",
        help_text="Código de acción: CREAR_SOLICITUD, SUBIR_ARCHIVO, etc.",
    )
    descripcion = models.TextField(
        blank=True,
        default="",
        verbose_name="Descripción",
    )
    modelo_afectado = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Modelo afectado",
    )
    objeto_id = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name="ID del objeto",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Fecha")

    class Meta:
        app_label = "comercial"
        db_table = "logs_sistema"
        verbose_name = "Log del sistema"
        verbose_name_plural = "Logs del sistema"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.unidad_negocio}] {self.accion} — {self.usuario} ({self.created_at:%d/%m/%Y %H:%M})"
