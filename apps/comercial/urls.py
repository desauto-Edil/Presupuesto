"""apps/comercial/urls.py"""

from django.urls import path
from . import views

app_name = "comercial"

urlpatterns = [

    # ── Clientes ──────────────────────────────────────────────────────────────
    path("clientes/", views.ClienteListView.as_view(),   name="cliente_list"),
    path("clientes/nuevo/", views.ClienteCreateView.as_view(), name="cliente_create"),
    path("clientes/<int:pk>/", views.ClienteDetailView.as_view(), name="cliente_detail"),
    path("clientes/<int:pk>/editar/", views.ClienteUpdateView.as_view(), name="cliente_update"),
    path("clientes/<int:pk>/eliminar/", views.ClienteDeleteView.as_view(), name="cliente_delete"),

    # ── Contactos ─────────────────────────────────────────────────────────────
    path("contactos/", views.ContactoListView.as_view(),   name="contacto_list"),
    path("contactos/nuevo/", views.ContactoCreateView.as_view(), name="contacto_create"),
    path("contactos/<int:pk>/editar/", views.ContactoUpdateView.as_view(), name="contacto_update"),
    path("contactos/<int:pk>/eliminar/", views.ContactoDeleteView.as_view(), name="contacto_delete"),

    # ── Solicitudes ───────────────────────────────────────────────────────────
    path("solicitudes/", views.SolicitudListView.as_view(),   name="solicitud_list"),
    path("solicitudes/nueva/", views.SolicitudCreateView.as_view(), name="solicitud_create"),
    path("solicitudes/<int:pk>/", views.SolicitudDetailView.as_view(), name="solicitud_detail"),
    path("solicitudes/<int:pk>/editar/", views.SolicitudUpdateView.as_view(), name="solicitud_update"),
    path("solicitudes/<int:pk>/eliminar/", views.SolicitudDeleteView.as_view(), name="solicitud_delete"),
    path("solicitudes/<int:pk>/crear-proyecto/", views.CrearProyectoDesdeSolicitudView.as_view(),
         name="crear_proyecto_desde_solicitud"),

    # ── Proyectos ─────────────────────────────────────────────────────────────
    path("proyectos/", views.ProyectoListView.as_view(),   name="proyecto_list"),
    path("proyectos/nuevo/", views.ProyectoCreateView.as_view(), name="proyecto_create"),
    path("proyectos/<int:pk>/", views.ProyectoDetailView.as_view(), name="proyecto_detail"),
    path("proyectos/<int:pk>/editar/", views.ProyectoUpdateView.as_view(), name="proyecto_update"),
    path("proyectos/<int:pk>/eliminar/", views.ProyectoDeleteView.as_view(), name="proyecto_delete"),

    # ── API interna ───────────────────────────────────────────────────────────
    path("api/contactos-por-cliente/<int:cliente_id>/",
         views.ContactosPorClienteView.as_view(),
         name="api_contactos_cliente"),
]
