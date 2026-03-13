"""
URL configuration for imperandina project.
"""

from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", RedirectView.as_view(url="/proyectos/", permanent=False)),
    path("", include("core.urls")),
]
