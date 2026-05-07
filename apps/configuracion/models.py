"""
apps/configuracion/models.py — Modelo de configuración del sistema.

Dominio: gestión de identidad y roles internos.
No usa django.contrib.auth; es un modelo propio mientras el sistema
escale hacia auth completo.
"""

from django.db import models
from apps.common.choices import UnidadNegocio, RolSistema


class UnidadNegocioInfo(models.Model):
    """
    Ficha completa de cada unidad de negocio.
    Secciones: Quiénes somos · Contacto · Políticas · Cláusulas · Alianzas.
    """
    codigo = models.CharField(
        max_length=20, choices=UnidadNegocio.choices, unique=True,
        help_text="Identificador de la unidad de negocio.",
    )
    razon_social = models.CharField(max_length=200, verbose_name="Razón social")
    nit = models.CharField(max_length=30, blank=True, verbose_name="NIT")

    # ── Quiénes somos ──────────────────────────────────────────────────────────
    quienes_somos = models.TextField(
        blank=True, default="",
        verbose_name="Quiénes somos",
        help_text="Texto de presentación de la unidad de negocio.",
    )
    mision = models.TextField(blank=True, default="", verbose_name="Misión")
    vision  = models.TextField(blank=True, default="", verbose_name="Visión")

    # ── Contacto ───────────────────────────────────────────────────────────────
    ciudad    = models.CharField(max_length=100, blank=True, default="")
    direccion = models.CharField(max_length=300, blank=True, default="")
    telefono  = models.CharField(max_length=50,  blank=True, default="")
    email     = models.EmailField(blank=True, default="")
    sitio_web = models.URLField(blank=True, default="", verbose_name="Sitio web")

    activa     = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "configuracion"
        db_table = "configuracion_unidades"
        ordering = ["codigo"]
        verbose_name = "Unidad de negocio"
        verbose_name_plural = "Unidades de negocio"

    def __str__(self):
        return f"{self.get_codigo_display()} — {self.razon_social}"


class UnidadPolitica(models.Model):
    """Política de la unidad de negocio (varias por unidad)."""
    unidad      = models.ForeignKey(UnidadNegocioInfo, on_delete=models.CASCADE, related_name="politicas")
    titulo      = models.CharField(max_length=200, verbose_name="Título")
    descripcion = models.TextField(verbose_name="Descripción")
    orden       = models.PositiveIntegerField(default=0)

    class Meta:
        app_label = "configuracion"
        db_table = "configuracion_politicas"
        ordering = ["orden", "titulo"]
        verbose_name = "Política"
        verbose_name_plural = "Políticas"

    def __str__(self):
        return f"{self.unidad.get_codigo_display()} — {self.titulo}"


class UnidadClausula(models.Model):
    """Cláusula contractual de la unidad de negocio (varias por unidad)."""
    unidad      = models.ForeignKey(UnidadNegocioInfo, on_delete=models.CASCADE, related_name="clausulas")
    titulo      = models.CharField(max_length=200, verbose_name="Título")
    descripcion = models.TextField(verbose_name="Descripción")
    orden       = models.PositiveIntegerField(default=0)

    class Meta:
        app_label = "configuracion"
        db_table = "configuracion_clausulas"
        ordering = ["orden", "titulo"]
        verbose_name = "Cláusula"
        verbose_name_plural = "Cláusulas"

    def __str__(self):
        return f"{self.unidad.get_codigo_display()} — {self.titulo}"


class UnidadAlianza(models.Model):
    """Alianza estratégica de la unidad de negocio (varias por unidad)."""
    unidad      = models.ForeignKey(UnidadNegocioInfo, on_delete=models.CASCADE, related_name="alianzas")
    nombre      = models.CharField(max_length=200, verbose_name="Nombre del aliado")
    descripcion = models.TextField(blank=True, default="", verbose_name="Descripción")
    imagen      = models.ImageField(
        upload_to="configuracion/alianzas/",
        blank=True, null=True,
        verbose_name="Logo / imagen",
    )
    orden       = models.PositiveIntegerField(default=0)

    class Meta:
        app_label = "configuracion"
        db_table = "configuracion_alianzas"
        ordering = ["orden", "nombre"]
        verbose_name = "Alianza"
        verbose_name_plural = "Alianzas"

    def __str__(self):
        return f"{self.unidad.get_codigo_display()} — {self.nombre}"


class ConfiguracionSistema(models.Model):
    email = models.EmailField(unique=True)
    nombre_completo = models.CharField(max_length=200)
    password_hash = models.TextField()
    unidad_negocio = models.CharField(
        max_length=20,
        choices=UnidadNegocio.choices,
        help_text="Unidad de negocio a la que pertenece la configuración"
    )
    rol = models.CharField(
        max_length=30,
        choices=RolSistema.choices,
        default=RolSistema.SOLO_LECTURA,
        help_text="Rol de la configuración en el sistema"
    )
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "configuracion"
        db_table = "usuarios"
        verbose_name = "Usuario del sistema"
        verbose_name_plural = "Usuarios del sistema"

    def __str__(self):
        return f"{self.nombre_completo} ({self.unidad_negocio})"
