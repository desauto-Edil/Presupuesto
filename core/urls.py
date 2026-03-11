"""
core/urls.py — Rutas de la aplicación principal.

HTML views:
  /proyectos/                              → ProyectoListView
  /proyectos/<pk>/                         → ProyectoDetailView
  /proyectos/<pk>/variables/               → VariablesUpdateView (GET + POST)
  /proyectos/<pk>/apu/                     → APUFormView (GET + POST)
  /proyectos/<pk>/apu/detalle/             → APUDetailView
  /proyectos/<pk>/despiece/<lid>/ajustar/  → AjusteLineaView (POST)

API JSON:
  /api/proyectos/<pk>/despiece/            → APIEjecutarDespiece (POST)
  /api/proyectos/<pk>/apu/                 → APIGenerarAPU (POST)
  /api/proyectos/<pk>/resumen/             → APIResumenProyecto (GET)
"""

from django.urls import path
from . import views

urlpatterns = [
    # ── Vistas HTML ──────────────────────────────────────────────────────────
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
        "proyectos/<int:pk>/apu/",
        views.APUFormView.as_view(),
        name="proyecto_apu_form",
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

    # ── API JSON ─────────────────────────────────────────────────────────────
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
