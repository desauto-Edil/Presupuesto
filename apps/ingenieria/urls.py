"""apps/ingenieria/urls.py"""

from django.urls import path
from apps.ingenieria.views import (
    SistemaListView, SistemaDetailView, SistemaCreateView, SistemaUpdateView, SistemaDeleteView,
    SubsistemaListView, SubsistemaDetailView, SubsistemaCreateView, SubsistemaUpdateView, SubsistemaDeleteView,
    ReglaListView, ReglaDetailView, ReglaCreateView, ReglaUpdateView, ReglaDeleteView,
    DependenciaListView, DependenciaCreateView, DependenciaUpdateView, DependenciaDeleteView,
)

app_name = "ingenieria"

urlpatterns = [
    # Sistemas
    path("sistemas/", SistemaListView.as_view(), name="sistema_list"),
    path("sistemas/nuevo/", SistemaCreateView.as_view(), name="sistema_create"),
    path("sistemas/<int:pk>/", SistemaDetailView.as_view(), name="sistema_detail"),
    path("sistemas/<int:pk>/editar/", SistemaUpdateView.as_view(), name="sistema_update"),
    path("sistemas/<int:pk>/eliminar/", SistemaDeleteView.as_view(), name="sistema_delete"),

    # Subsistemas
    path("subsistemas/", SubsistemaListView.as_view(), name="subsistema_list"),
    path("subsistemas/nuevo/", SubsistemaCreateView.as_view(), name="subsistema_create"),
    path("subsistemas/<int:pk>/", SubsistemaDetailView.as_view(), name="subsistema_detail"),
    path("subsistemas/<int:pk>/editar/", SubsistemaUpdateView.as_view(), name="subsistema_update"),
    path("subsistemas/<int:pk>/eliminar/", SubsistemaDeleteView.as_view(), name="subsistema_delete"),

    # Reglas de cálculo
    path("reglas/", ReglaListView.as_view(), name="regla_list"),
    path("reglas/nueva/", ReglaCreateView.as_view(), name="regla_create"),
    path("reglas/<int:pk>/", ReglaDetailView.as_view(), name="regla_detail"),
    path("reglas/<int:pk>/editar/", ReglaUpdateView.as_view(), name="regla_update"),
    path("reglas/<int:pk>/eliminar/", ReglaDeleteView.as_view(), name="regla_delete"),

    # Dependencias técnicas
    path("dependencias/", DependenciaListView.as_view(), name="dependencia_list"),
    path("dependencias/nueva/", DependenciaCreateView.as_view(), name="dependencia_create"),
    path("dependencias/<int:pk>/editar/", DependenciaUpdateView.as_view(), name="dependencia_update"),
    path("dependencias/<int:pk>/eliminar/", DependenciaDeleteView.as_view(), name="dependencia_delete"),
]
