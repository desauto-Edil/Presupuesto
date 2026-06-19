"""apps/ingenieria/urls.py"""

from django.urls import path
from apps.ingenieria.views import (
    SistemaListView, SistemaDetailView,
    SistemaCreateView, SistemaUpdateView, SistemaDeleteView,
    SubsistemaDetailView,
    SubsistemaCreateView, SubsistemaUpdateView, SubsistemaDeleteView,
    SubsistemaConfigApuGuardarView,
    CalculadoraConsumoView,
    FuncionConsumoCreateView, FuncionConsumoDeleteView,
    ProblemaResueltoCreateView, ProblemaResueltoDeleteView,
    SuperficieCompatibleCreateView, SuperficieCompatibleDeleteView,
)
from apps.ingenieria.views.calculador import (
    CalculadorSistemaView,
    CalculadorSeleccionarView,
    DespieceMaestroView,
    CalcularDespieceMaestroView,
    GuardarDespieceMaestroView,
    DespiecesGuardadosView,
    EliminarDespieceMaestroView,
    APUDespieceMaestroView,
    BuscarProductosView,
)

app_name = "ingenieria"

urlpatterns = [
    # Sistemas
    path("sistemas/", SistemaListView.as_view(),   name="sistema_list"),
    path("sistemas/nuevo/", SistemaCreateView.as_view(), name="sistema_create"),
    path("sistemas/<int:pk>/", SistemaDetailView.as_view(), name="sistema_detail"),
    path("sistemas/<int:pk>/editar/", SistemaUpdateView.as_view(), name="sistema_update"),
    path("sistemas/<int:pk>/eliminar/", SistemaDeleteView.as_view(), name="sistema_delete"),

    # Calculadora
    path("sistemas/<int:pk>/calcular/", CalculadoraConsumoView.as_view(), name="calculadora_consumo"),

    # Subsistemas
    path("subsistemas/nuevo/", SubsistemaCreateView.as_view(), name="subsistema_create"),
    path("subsistemas/<int:pk>/", SubsistemaDetailView.as_view(), name="subsistema_detail"),
    path("subsistemas/<int:pk>/editar/", SubsistemaUpdateView.as_view(), name="subsistema_update"),
    path("subsistemas/<int:pk>/eliminar/", SubsistemaDeleteView.as_view(), name="subsistema_delete"),
    # Fase 6L-4: guardado del modal "Configurar APU del subsistema"
    path("subsistemas/<int:pk>/config-apu/guardar/",
         SubsistemaConfigApuGuardarView.as_view(),
         name="subsistema_config_apu_guardar"),

    # Catálogos de consumo
    path("catalogo/funciones/nueva/", FuncionConsumoCreateView.as_view(), name="funcion_consumo_create"),
    path("catalogo/funciones/<int:pk>/eliminar/", FuncionConsumoDeleteView.as_view(), name="funcion_consumo_delete"),
    path("catalogo/problemas/nuevo/", ProblemaResueltoCreateView.as_view(), name="problema_resuelto_create"),
    path("catalogo/problemas/<int:pk>/eliminar/", ProblemaResueltoDeleteView.as_view(), name="problema_resuelto_delete"),
    path("catalogo/superficies/nueva/", SuperficieCompatibleCreateView.as_view(), name="superficie_compatible_create"),
    path("catalogo/superficies/<int:pk>/eliminar/", SuperficieCompatibleDeleteView.as_view(), name="superficie_compatible_delete"),

    # ── Calculador de sistemas (standalone) ───────────────────────────────────
    path("calculador/", CalculadorSistemaView.as_view(), name="calculador_sistemas"),
    # Flujo rápido (sin proyecto) y flujo de proyecto (con proyecto_pk en GET/POST)
    path("calculador/<int:sistema_pk>/nuevo/", CalculadorSeleccionarView.as_view(), name="calculador_seleccionar"),
    path("calculador/despieces/", DespiecesGuardadosView.as_view(), name="despiece_list"),
    # Alias de compatibilidad (redirige a la misma vista)
    path("calculador/guardados/", DespiecesGuardadosView.as_view(), name="despieces_guardados"),
    path("calculador/despiece/<int:pk>/", DespieceMaestroView.as_view(), name="despiece_maestro"),
    path("calculador/despiece/<int:pk>/calcular/", CalcularDespieceMaestroView.as_view(), name="despiece_calcular"),
    path("calculador/despiece/<int:pk>/guardar/", GuardarDespieceMaestroView.as_view(), name="despiece_guardar"),
    path("calculador/despiece/<int:pk>/eliminar/", EliminarDespieceMaestroView.as_view(), name="despiece_delete"),
    # APU: redirige al módulo presupuestos (apu_despiece_maestro obsoleto)
    path("calculador/despiece/<int:pk>/apu/", APUDespieceMaestroView.as_view(), name="apu_despiece_maestro"),
    path("calculador/productos/buscar/", BuscarProductosView.as_view(), name="buscar_productos"),
]
