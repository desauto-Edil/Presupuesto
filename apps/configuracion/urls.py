"""apps/configuracion/urls.py"""

from django.urls import path
from . import views

app_name = "configuracion"

urlpatterns = [
    # ── Página principal (usuarios + unidades) ──────────────────────────────
    path("", views.ConfiguracionView.as_view(), name="configuracion"),

    # ── CRUD usuarios ───────────────────────────────────────────────────────
    path("nuevo/",             views.ConfiguracionCreateView.as_view(), name="configuracion_create"),
    path("<int:pk>/",          views.ConfiguracionDetailView.as_view(), name="configuracion_detail"),
    path("<int:pk>/editar/",   views.ConfiguracionUpdateView.as_view(), name="configuracion_update"),
    path("<int:pk>/eliminar/", views.ConfiguracionDeleteView.as_view(), name="configuracion_delete"),

    # ── CRUD unidades de negocio ────────────────────────────────────────────
    path("unidades/nueva/",             views.UnidadCreateView.as_view(),  name="unidad_create"),
    path("unidades/<int:pk>/editar/",   views.UnidadUpdateView.as_view(),  name="unidad_update"),
    path("unidades/<int:pk>/eliminar/", views.UnidadDeleteView.as_view(),  name="unidad_delete"),

    # ── CRUD políticas ──────────────────────────────────────────────────────
    path("unidades/<int:unidad_pk>/politicas/nueva/",         views.PoliticaCreateView.as_view(),  name="politica_create"),
    path("unidades/politicas/<int:pk>/editar/",               views.PoliticaUpdateView.as_view(),  name="politica_update"),
    path("unidades/politicas/<int:pk>/eliminar/",             views.PoliticaDeleteView.as_view(),  name="politica_delete"),

    # ── CRUD cláusulas ──────────────────────────────────────────────────────
    path("unidades/<int:unidad_pk>/clausulas/nueva/",         views.ClausulaCreateView.as_view(),  name="clausula_create"),
    path("unidades/clausulas/<int:pk>/editar/",               views.ClausulaUpdateView.as_view(),  name="clausula_update"),
    path("unidades/clausulas/<int:pk>/eliminar/",             views.ClausulaDeleteView.as_view(),  name="clausula_delete"),

    # ── CRUD alianzas ───────────────────────────────────────────────────────
    path("unidades/<int:unidad_pk>/alianzas/nueva/",          views.AlianzaCreateView.as_view(),   name="alianza_create"),
    path("unidades/alianzas/<int:pk>/editar/",                views.AlianzaUpdateView.as_view(),   name="alianza_update"),
    path("unidades/alianzas/<int:pk>/eliminar/",              views.AlianzaDeleteView.as_view(),   name="alianza_delete"),

    # ── Auth ────────────────────────────────────────────────────────────────
    path("login/",  views.LoginConfiguracionView.as_view(), name="login"),
    path("logout/", views.logout_configuracion,             name="logout"),
]
