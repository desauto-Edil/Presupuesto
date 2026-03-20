"""
apps/comercial/models.py 

Dominio: gestión de la relación con el cliente desde el primer contacto
hasta la creación del proyecto.

  Cliente → ContactoCliente
  Cliente → Solicitud → Proyecto

Dependencias:
  - apps.common.choices (EstadoSolicitud, EstadoProyecto, Moneda)
  - apps.usuarios (UsuarioSistema, vía FK de auditoría)
"""

from django.db import models
from django.utils import timezone
from apps.common.choices import EstadoSolicitud, EstadoProyecto, Moneda


# ---------------------------------------------------------------------------
# CLIENTES
# ---------------------------------------------------------------------------

class Cliente(models.Model):
    nit = models.CharField(max_length=50, unique=True)
    razon_social = models.CharField(max_length=300)
    ciudad = models.CharField(max_length=100, blank=True, null=True)
    direccion = models.TextField(blank=True, null=True)
    telefono_principal = models.CharField(max_length=30, blank=True, null=True)
    email_principal = models.EmailField(blank=True, null=True)
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
        db_table  = "tipos_proyecto"

    def __str__(self):
        return self.nombre


# ---------------------------------------------------------------------------
# SOLICITUDES
# ---------------------------------------------------------------------------

class Solicitud(models.Model):
    consecutivo = models.CharField(max_length=30, unique=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="solicitudes")
    contacto = models.ForeignKey(
        ContactoCliente, on_delete=models.SET_NULL,
        blank=True, null=True, related_name="solicitudes",
    )
    creado_por = models.ForeignKey(
        "usuarios.UsuarioSistema", on_delete=models.SET_NULL,
        blank=True, null=True, related_name="solicitudes_creadas",
    )
    nombre = models.CharField(max_length=300)
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
        """
        Campos controlados por el sistema — no editables por el usuario:
          · consecutivo : se genera automáticamente en creación (SLD-YYYY-NNNN).
          · estado      : solo cambia vía transiciones explícitas del negocio.
          · creado_por  : se asigna en la vista; nunca se expone en formularios.
        """
        # ── Consecutivo automático (solo en creación) ──────────────────────
        if not self.pk and not self.consecutivo:
            self.consecutivo = self.__class__.siguiente_consecutivo()
        # ── Contacto por defecto ───────────────────────────────────────────
        if not self.contacto_id and self.cliente_id:
            self.contacto = self.cliente.contacto_principal
        super().save(*args, **kwargs)

    @classmethod
    def siguiente_consecutivo(cls):
        """Genera el siguiente consecutivo SLD-YYYY-NNNN."""
        year = timezone.now().year
        prefix = f"SLD-{year}-"
        last = cls.objects.filter(consecutivo__startswith=prefix).order_by("-consecutivo").first()
        num = (int(last.consecutivo.split("-")[-1]) + 1) if last else 1
        return f"{prefix}{num:04d}"


# ---------------------------------------------------------------------------
# PROYECTOS
# ---------------------------------------------------------------------------

class Proyecto(models.Model):
    consecutivo = models.CharField(max_length=30, unique=True)
    solicitud = models.ForeignKey(
        Solicitud, on_delete=models.SET_NULL,
        blank=True, null=True, related_name="proyectos",
    )
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

    # Variables financieras (predeterminadas, editables)
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
    motivo_devolucion  = models.TextField(
        blank=True, null=True,
        help_text="Motivo de rechazo o devolución por parte del Administrador o Compras",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "comercial"
        db_table = "proyectos"

    def __str__(self):
        return f"{self.consecutivo} — {self.nombre}"

    def save(self, *args, **kwargs):
        """
        Campos controlados por el sistema — no editables por el usuario:
          · consecutivo : se genera automáticamente en creación (PRY-YYYY-NNNN).
          · estado      : solo cambia vía métodos de transición del modelo.
          · creado_por  : se asigna en la vista; nunca se expone en formularios.
        """
        if not self.pk and not self.consecutivo:
            self.consecutivo = self.__class__.siguiente_consecutivo()
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
        if self.estado == EstadoProyecto.SOLICITUD:
            self.estado = EstadoProyecto.DESPIECE
            self.save(update_fields=["estado", "updated_at"])
            
    def avanzar_a_despiece_validado(self):
        if self.estado in (EstadoProyecto.DESPIECE, EstadoProyecto.EN_REVISION_COMPRAS):
            self.estado = EstadoProyecto.DESPIECE_VALIDADO
            self.save(update_fields=["estado", "updated_at"])

    def avanzar_a_apu(self):
        if self.estado == EstadoProyecto.DESPIECE_VALIDADO:
            self.estado = EstadoProyecto.APU
            self.save(update_fields=["estado", "updated_at"])

    def avanzar_a_apu_generado(self):
        if self.estado == EstadoProyecto.APU:
            self.estado = EstadoProyecto.APU_GENERADO
            self.save(update_fields=["estado", "updated_at"])

    def aprobar_cotizacion(self):
        if self.estado == EstadoProyecto.APU_GENERADO:
            self.estado = EstadoProyecto.COTIZADO
            self.motivo_devolucion = None
            self.save(update_fields=["estado", "motivo_devolucion", "updated_at"])

    def rechazar_apu(self, motivo: str = ""):
        if self.estado == EstadoProyecto.APU_GENERADO:
            self.estado = EstadoProyecto.APU
            self.motivo_devolucion = motivo
            self.save(update_fields=["estado", "motivo_devolucion", "updated_at"])

    def avanzar_a_cotizado(self):
        if self.estado == EstadoProyecto.COTIZADO:
            self.estado = EstadoProyecto.APROBADO
            self.save(update_fields=["estado", "updated_at"])
