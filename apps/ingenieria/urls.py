"""apps/ingenieria/urls.py"""

from django.urls import path
from apps.ingenieria.views import (
    SistemaListView, SistemaDetailView,
    SistemaCreateView, SistemaUpdateView, SistemaDeleteView,
    SubsistemaListView, SubsistemaDetailView,
    SubsistemaCreateView, SubsistemaUpdateView, SubsistemaDeleteView,
)

app_name = "ingenieria"

urlpatterns = [
    # Sistemas
    path("sistemas/",                   SistemaListView.as_view(),   name="sistema_list"),
    path("sistemas/nuevo/",             SistemaCreateView.as_view(), name="sistema_create"),
    path("sistemas/<int:pk>/",          SistemaDetailView.as_view(), name="sistema_detail"),
    path("sistemas/<int:pk>/editar/",   SistemaUpdateView.as_view(), name="sistema_update"),
    path("sistemas/<int:pk>/eliminar/", SistemaDeleteView.as_view(), name="sistema_delete"),

    # Subsistemas
    path("subsistemas/",                   SubsistemaListView.as_view(),   name="subsistema_list"),
    path("subsistemas/nuevo/",             SubsistemaCreateView.as_view(), name="subsistema_create"),
    path("subsistemas/<int:pk>/",          SubsistemaDetailView.as_view(), name="subsistema_detail"),
    path("subsistemas/<int:pk>/editar/",   SubsistemaUpdateView.as_view(), name="subsistema_update"),
    path("subsistemas/<int:pk>/eliminar/", SubsistemaDeleteView.as_view(), name="subsistema_delete"),
]
