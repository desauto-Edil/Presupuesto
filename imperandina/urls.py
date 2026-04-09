"""
URL configuration for imperandina project.
"""

from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    
    path("", RedirectView.as_view(pattern_name="configuracion:login"), name="home"),

    path("catalogos/", include("apps.catalogos.urls")),
    path("comercial/", include("apps.comercial.urls")),
    path("ingenieria/", include("apps.ingenieria.urls")),
    path("presupuestos/", include("apps.presupuestos.urls")),
    path("configuracion/", include("apps.configuracion.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
