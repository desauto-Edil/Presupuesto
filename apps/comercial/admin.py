from django.contrib import admin
from .models import Cliente, ContactoCliente, Solicitud, SolicitudArchivo, LogSistema


class ContactoClienteInline(admin.TabularInline):
    model = ContactoCliente
    extra = 1
    fields = ("nombre", "cargo", "email", "telefono", "es_principal", "activo")


class SolicitudArchivoInline(admin.TabularInline):
    model = SolicitudArchivo
    extra = 0
    fields = ("nombre", "archivo", "usuario", "fecha_subida")
    readonly_fields = ("fecha_subida",)


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nit", "razon_social", "activo")
    list_filter = ("activo",)
    search_fields = ("nit", "razon_social")
    readonly_fields = ("created_at", "updated_at")
    inlines = [ContactoClienteInline]


@admin.register(Solicitud)
class SolicitudAdmin(admin.ModelAdmin):
    list_display = ("consecutivo", "cliente", "nombre", "estado", "creado_por", "created_at")
    list_filter = ("estado",)
    search_fields = ("consecutivo", "nombre", "cliente__razon_social")
    readonly_fields = ("estado", "creado_por", "created_at", "updated_at")
    inlines = [SolicitudArchivoInline]

    fieldsets = (
        ("Datos de Selford", {
            "fields": ("consecutivo", "link_selford"),
            "description": "Consecutivo y link provienen del sistema Selford.",
        }),
        ("Datos de la solicitud", {
            "fields": ("cliente", "contacto", "nombre", "descripcion", "fecha_entrega", "observaciones"),
        }),
        ("Sistema (solo lectura)", {
            "fields": ("estado", "creado_por", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


@admin.register(SolicitudArchivo)
class SolicitudArchivoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "solicitud", "usuario", "fecha_subida")
    list_filter = ("fecha_subida",)
    search_fields = ("nombre", "solicitud__consecutivo")
    readonly_fields = ("fecha_subida",)


@admin.register(LogSistema)
class LogSistemaAdmin(admin.ModelAdmin):
    list_display = ("created_at", "unidad_negocio", "accion", "usuario", "modelo_afectado", "objeto_id")
    list_filter = ("unidad_negocio", "accion", "modelo_afectado")
    search_fields = ("accion", "descripcion", "usuario__nombre_completo")
    readonly_fields = (
        "created_at", "unidad_negocio", "usuario",
        "accion", "descripcion", "modelo_afectado", "objeto_id",
    )
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
