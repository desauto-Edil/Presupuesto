"""
core/urls.py — Rutas de la aplicación principal.

Flujo completo:
  ASESOR:
    /clientes/→ ClienteListView
    /clientes/nuevo/→ ClienteCreateView
    /clientes/<pk>/editar/→ ClienteEditView
    /solicitudes/→ SolicitudListView
    /solicitudes/nueva/→ SolicitudCreateView
    /solicitudes/<pk>/→ SolicitudDetailView
    /proyectos/<pk>/enviar-cotizacion/→ EnviarCotizacionView

  PRESUPUESTOS:
    /solicitudes/<pk>/crear-proyecto/→ ProyectoCrearView
    /proyectos/→ ProyectoListView
    /proyectos/<pk>/→ ProyectoDetailView
    /proyectos/<pk>/variables/→ VariablesUpdateView
    /proyectos/<pk>/validar-precios/→ ValidarPreciosView
    /proyectos/<pk>/apu/→ APUFormView
    /proyectos/<pk>/enviar-revision/→ EnviarRevisionAdminView
    /proyectos/<pk>/apu/detalle/→ APUDetailView
    /proyectos/<pk>/despiece/<lid>/ajustar/→ AjusteLineaView

  COMPRAS:
    /compras/→ ComprasDashboardView
    /compras/proyectos/<pk>/precios/→ ComprasActualizarPreciosView
    /compras/proyectos/<pk>/confirmar/→ ComprasConfirmarView

  ADMINISTRADOR:
    /admin-revision/→ AdminRevisionListView
    /admin-revision/proyectos/<pk>/→ AdminRevisionView

  API JSON:
    /api/proyectos/<pk>/despiece/→ APIEjecutarDespiece (POST)
    /api/proyectos/<pk>/apu/→ APIGenerarAPU (POST)
    /api/proyectos/<pk>/resumen/→ APIResumenProyecto (GET)
"""

from django.urls import path
from . import views

urlpatterns = [

    # ── ASESOR: Clientes ──────────────────────────────────────────────────────
    path(
        "clientes/",
        views.ClienteListView.as_view(),
        name="cliente_list",
    ),
    path(
        "clientes/nuevo/",
        views.ClienteCreateView.as_view(),
        name="cliente_create",
    ),
    path(
        "clientes/<int:pk>/editar/",
        views.ClienteEditView.as_view(),
        name="cliente_edit",
    ),

    # ── ASESOR: Solicitudes ───────────────────────────────────────────────────
    path(
        "solicitudes/",
        views.SolicitudListView.as_view(),
        name="solicitud_list",
    ),
    path(
        "solicitudes/nueva/",
        views.SolicitudCreateView.as_view(),
        name="solicitud_create",
    ),
    path(
        "solicitudes/<int:pk>/",
        views.SolicitudDetailView.as_view(),
        name="solicitud_detalle",
    ),

    # ── PRESUPUESTOS: Crear proyecto desde solicitud ──────────────────────────
    path(
        "solicitudes/<int:pk>/crear-proyecto/",
        views.ProyectoCrearView.as_view(),
        name="proyecto_crear",
    ),

    # ── PRESUPUESTOS: Proyectos ───────────────────────────────────────────────
    path(
        "proyectos/",
        views.ProyectoListView.as_view(),
        name="proyecto_list",
    ),
    path(
        "proyectos/<int:pk>/",
        views.ProyectoDetailView.as_view(),
        name="proyecto_detalle",
    ),
    path(
        "proyectos/<int:pk>/variables/",
        views.VariablesUpdateView.as_view(),
        name="proyecto_variables",
    ),
    path(
        "proyectos/<int:pk>/validar-precios/",
        views.ValidarPreciosView.as_view(),
        name="validar_precios",
    ),
    path(
        "proyectos/<int:pk>/apu/",
        views.APUFormView.as_view(),
        name="proyecto_apu_form",
    ),
    path(
        "proyectos/<int:pk>/enviar-revision/",
        views.EnviarRevisionAdminView.as_view(),
        name="enviar_revision_admin",
    ),
    path(
        "proyectos/<int:pk>/apu/detalle/",
        views.APUDetailView.as_view(),
        name="apu_detalle",
    ),
    path(
        "proyectos/<int:pk>/despiece/<int:linea_pk>/ajustar/",
        views.AjusteLineaView.as_view(),
        name="ajustar_linea",
    ),

    # ── ASESOR: Enviar cotización ─────────────────────────────────────────────
    path(
        "proyectos/<int:pk>/enviar-cotizacion/",
        views.EnviarCotizacionView.as_view(),
        name="enviar_cotizacion",
    ),

    # ── COMPRAS ───────────────────────────────────────────────────────────────
    path(
        "compras/",
        views.ComprasDashboardView.as_view(),
        name="compras_dashboard",
    ),
    path(
        "compras/proyectos/<int:pk>/precios/",
        views.ComprasActualizarPreciosView.as_view(),
        name="compras_actualizar_precios",
    ),
    path(
        "compras/proyectos/<int:pk>/confirmar/",
        views.ComprasConfirmarView.as_view(),
        name="compras_confirmar",
    ),

    # ── ADMINISTRADOR ─────────────────────────────────────────────────────────
    path(
        "admin-revision/",
        views.AdminRevisionListView.as_view(),
        name="admin_revision_list",
    ),
    path(
        "admin-revision/proyectos/<int:pk>/",
        views.AdminRevisionView.as_view(),
        name="admin_revision",
    ),

    # ── API JSON ──────────────────────────────────────────────────────────────
    path(
        "api/proyectos/<int:pk>/despiece/",
        views.APIEjecutarDespiece.as_view(),
        name="api_ejecutar_despiece",
    ),
    path(
        "api/proyectos/<int:pk>/apu/",
        views.APIGenerarAPU.as_view(),
        name="api_generar_apu",
    ),
    path(
        "api/proyectos/<int:pk>/resumen/",
        views.APIResumenProyecto.as_view(),
        name="api_resumen_proyecto",
    ),
]
