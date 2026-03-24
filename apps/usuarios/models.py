"""
apps/usuarios/models.py — Modelo de usuario del sistema.

Dominio: gestión de identidad y roles internos.
No usa django.contrib.auth; es un modelo propio mientras el sistema
escale hacia auth completo.
"""

from django.db import models
from apps.common.choices import UnidadNegocio, RolSistema


class UsuarioSistema(models.Model):
    email = models.EmailField(unique=True)
    nombre_completo = models.CharField(max_length=200)
    password_hash = models.TextField()
    unidad_negocio = models.CharField(
        max_length=20,
        choices=UnidadNegocio.choices,
        help_text="Unidad de negocio a la que pertenece el usuario"
    )
    rol = models.CharField(
        max_length=30,
        choices=RolSistema.choices,
        default=RolSistema.SOLO_LECTURA,
        help_text="Rol del usuario en el sistema"
    )
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "usuarios"
        db_table = "usuarios"

    def __str__(self):
        return f"{self.nombre_completo} ({self.unidad_negocio})"
