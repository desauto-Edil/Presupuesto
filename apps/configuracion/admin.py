from django.contrib import admin
from .models import ConfiguracionSistema


@admin.register(ConfiguracionSistema)
class ConfiguracionSistemaAdmin(admin.ModelAdmin):
    list_display = ("email", "nombre_completo", "unidad_negocio", "rol", "activo", "created_at")
    list_filter = ("unidad_negocio", "rol", "activo")
    search_fields = ("email", "nombre_completo")
    readonly_fields = ("created_at", "updated_at")

fieldsets = (
        (None, {
            "fields": ("nombre_completo", "email", "password_hash")
        }),
        ("Organización", {
            "fields": ("unidad_negocio", "rol", "activo")
        }),
        ("Metadatos", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )