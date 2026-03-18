from django.contrib import admin
from .models import UsuarioSistema


@admin.register(UsuarioSistema)
class UsuarioSistemaAdmin(admin.ModelAdmin):
    list_display = ("email", "nombre_completo", "rol", "activo", "created_at")
    list_filter = ("rol", "activo")
    search_fields = ("email", "nombre_completo")
    readonly_fields = ("created_at", "updated_at")
