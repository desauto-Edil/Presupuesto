"""apps/presupuestos/urls.py"""

from django.urls import path
from apps.presupuestos.views import (
    ProyectoSistemaListView, ProyectoSistemaDetailView,
    ProyectoSistemaCreateView, ProyectoSistemaUpdateView, ProyectoSistemaDeleteView,
    DespieceProyectoView, DespieceEjecutarView, DespieceLineaAjusteView,
    SubsistemaVariablesView, DespieceLineaAjusteAPIView, CalcularDespiecePSView,
    ConfiguracionAPUListView, ConfiguracionAPUCreateView, ConfiguracionAPUUpdateView,
    APUProyectoDetailView, APUProyectoUpdateView, APUGenerarView,
)

app_name = "presupuestos"

urlpatterns = [
    # ProyectoSistema
    path("sistemas/", ProyectoSistemaListView.as_view(), name="proyectosistema_list"),
    path("sistemas/nuevo/", ProyectoSistemaCreateView.as_view(), name="proyectosistema_create"),
    path("sistemas/<int:pk>/", ProyectoSistemaDetailView.as_view(), name="proyectosistema_detail"),
    path("sistemas/<int:pk>/editar/", ProyectoSistemaUpdateView.as_view(), name="proyectosistema_update"),
    path("sistemas/<int:pk>/eliminar/", ProyectoSistemaDeleteView.as_view(), name="proyectosistema_delete"),

    # Despiece — workbench
    path("despiece/proyecto/<int:pk>/", DespieceProyectoView.as_view(), name="despiece_proyecto"),

    # Despiece — acciones de cálculo
    path("despiece/calcular/<int:pk>/", CalcularDespiecePSView.as_view(), name="despiece_calcular"),
    path("despiece/ejecutar/<int:pk>/", DespieceEjecutarView.as_view(), name="despiece_ejecutar"),

    # Despiece — ajuste de línea (formulario clásico)
    path("despiece/ajuste/<int:pk>/", DespieceLineaAjusteView.as_view(), name="despiece_ajuste"),

    # Despiece — API AJAX
    path("despiece/api/variables/<int:pk>/", SubsistemaVariablesView.as_view(), name="despiece_api_variables"),
    path("despiece/api/ajuste/<int:pk>/", DespieceLineaAjusteAPIView.as_view(), name="despiece_api_ajuste"),

    # Configuración APU
    path("config-apu/", ConfiguracionAPUListView.as_view(), name="configapu_list"),
    path("config-apu/nueva/", ConfiguracionAPUCreateView.as_view(), name="configapu_create"),
    path("config-apu/<int:pk>/editar/", ConfiguracionAPUUpdateView.as_view(), name="configapu_update"),

    # APU
    path("apu/<int:pk>/", APUProyectoDetailView.as_view(), name="apu_detail"),
    path("apu/<int:pk>/editar/", APUProyectoUpdateView.as_view(), name="apu_update"),
    path("apu/generar/<int:pk>/", APUGenerarView.as_view(), name="apu_generar"),
]
