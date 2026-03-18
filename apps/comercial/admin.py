from django.contrib import admin
from .models import Cliente, ContactoCliente, TipoProyecto, Solicitud, Proyecto


class ContactoClienteInline(admin.TabularInline):
    model = ContactoCliente
    extra = 1
    fields = ("nombre", "cargo", "email", "telefono", "es_principal", "activo")


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nit", "razon_social", "ciudad", "activo")
    list_filter = ("activo",)
    search_fields = ("nit", "razon_social")
    readonly_fields = ("created_at", "updated_at")
    inlines = [ContactoClienteInline]


@admin.register(TipoProyecto)
class TipoProyectoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "activo")
    list_filter = ("activo",)


@admin.register(Solicitud)
class SolicitudAdmin(admin.ModelAdmin):
    list_display = ("consecutivo", "cliente", "nombre", "estado", "created_at")
    list_filter = ("estado",)
    search_fields = ("consecutivo", "nombre", "cliente__razon_social")
    readonly_fields = ("consecutivo", "created_at", "updated_at")


@admin.register(Proyecto)
class ProyectoAdmin(admin.ModelAdmin):
    list_display = ("consecutivo", "cliente", "nombre", "estado", "created_at")
    list_filter = ("estado", "tipo_proyecto")
    search_fields = ("consecutivo", "nombre", "cliente__razon_social")
    readonly_fields = ("consecutivo", "fecha_proyecto", "created_at", "updated_at")
