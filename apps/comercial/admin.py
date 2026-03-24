from django.contrib import admin
from .models import Cliente, ContactoCliente, TipoProyecto, Solicitud, Proyecto


class ContactoClienteInline(admin.TabularInline):
    model = ContactoCliente
    extra = 1
    fields = ("nombre", "cargo", "email", "telefono", "es_principal", "activo")


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nit", "razon_social", "creacion_selford", "activo")
    list_filter = ("activo", "creacion_selford")
    search_fields = ("nit", "razon_social")
    readonly_fields = ("created_at", "updated_at")
    inlines = [ContactoClienteInline]


@admin.register(TipoProyecto)
class TipoProyectoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "activo")
    list_filter = ("activo",)


@admin.register(Solicitud)
class SolicitudAdmin(admin.ModelAdmin):
    list_display  = ("consecutivo", "cliente", "nombre", "estado", "creado_por", "created_at")
    list_filter   = ("estado",)
    search_fields = ("consecutivo", "nombre", "cliente__razon_social")

    # Campos del sistema: visibles pero NO editables en el admin
    readonly_fields = ("consecutivo", "estado", "creado_por", "created_at", "updated_at")

    fieldsets = (
        ("🔒 Datos del sistema (solo lectura)", {
            "fields": ("consecutivo", "estado", "creado_por", "created_at", "updated_at"),
            "description": "Estos campos son controlados exclusivamente por el sistema.",
        }),
        ("Datos de la solicitud", {
            "fields": ("cliente", "contacto", "nombre", "descripcion", "fecha_entrega", "observaciones"),
        }),
    )


@admin.register(Proyecto)
class ProyectoAdmin(admin.ModelAdmin):
    list_display  = ("consecutivo", "cliente", "nombre", "estado", "creado_por", "created_at")
    list_filter   = ("estado", "tipo_proyecto")
    search_fields = ("consecutivo", "nombre", "cliente__razon_social")

    # Campos del sistema: visibles pero NO editables en el admin
    readonly_fields = ("consecutivo", "estado", "creado_por", "fecha_proyecto", "created_at", "updated_at")

    fieldsets = (
        ("🔒 Datos del sistema (solo lectura)", {
            "fields": ("consecutivo", "estado", "creado_por", "fecha_proyecto", "created_at", "updated_at"),
            "description": "Estos campos son controlados exclusivamente por el sistema.",
        }),
        ("Datos del proyecto", {
            "fields": (
                "solicitud", "cliente", "tipo_proyecto", "nombre", "descripcion",
                "area_total_m2", "perimetro_ml",
            ),
        }),
        ("Variables financieras", {
            "fields": ("trm", "margen_comercial_pct", "iva_pct", "aiu_pct", "moneda", "aplica_exencion_iva"),
        }),
        ("Observaciones", {
            "fields": ("observaciones", "motivo_devolucion"),
        }),
    )
