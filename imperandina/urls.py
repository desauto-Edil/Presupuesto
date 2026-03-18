"""
URL configuration for imperandina project.
"""

from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", RedirectView.as_view(url="/comercial/proyectos/"), name="home"),

    path("catalogos/", include("apps.catalogos.urls")),
    path("comercial/", include("apps.comercial.urls")),
    path("ingenieria/", include("apps.ingenieria.urls")),
    path("presupuestos/", include("apps.presupuestos.urls")),
    path("usuarios/", include("apps.usuarios.urls")),
]
