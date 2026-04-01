"""apps/presupuestos/urls.py"""

from django.urls import path
from apps.presupuestos.views import (
    # ProyectoSistema
    ProyectoSistemaListView, ProyectoSistemaDetailView,
    ProyectoSistemaCreateView, ProyectoSistemaUpdateView, ProyectoSistemaDeleteView,
    # Despiece
    DespieceProyectoView, DespieceEjecutarView, DespieceLineaAjusteView,
    SubsistemaVariablesView, DespieceLineaAjusteAPIView, CalcularDespiecePSView,
    AsignarProductoLineaAPIView, ProductosPorCategoriaLineaAPIView,
    # APIs helpers
    ProductosPorCategoriaAPIView, SubsistemaDefAPIView,
    # Config APU
    ConfiguracionAPUListView, ConfiguracionAPUCreateView, ConfiguracionAPUUpdateView,
    # APU — proyectos
    APUListView, APUProyectoDetailView, APUProyectoUpdateView, APUGenerarView,
    APUManoObraView, APUHerramientasView, APUTransporteView, APUAdminView,
    APULineaUpdateView,
    APUPDFInternoView, APUPDFClienteView, APUEnviarRevisionView,
    # Catálogo APU
    CatalogoAPUView,
    CategoriaItemAPUCreateView, CategoriaItemAPUUpdateView, CategoriaItemAPUDeleteView,
    ItemCatalogoAPUCreateView, ItemCatalogoAPUUpdateView, ItemCatalogoAPUDeleteView,
    CuadrillaPresetCreateView, CuadrillaPresetUpdateView, CuadrillaPresetDeleteView,
    ItemsCatalogoAPIView,
)

app_name = "presupuestos"

urlpatterns = [

    # ── ProyectoSistema ──────────────────────────────────────────────────────
    path("sistemas/",                    ProyectoSistemaListView.as_view(),   name="proyectosistema_list"),
    path("sistemas/nuevo/",              ProyectoSistemaCreateView.as_view(), name="proyectosistema_create"),
    path("sistemas/<int:pk>/",           ProyectoSistemaDetailView.as_view(), name="proyectosistema_detail"),
    path("sistemas/<int:pk>/editar/",    ProyectoSistemaUpdateView.as_view(), name="proyectosistema_update"),
    path("sistemas/<int:pk>/eliminar/",  ProyectoSistemaDeleteView.as_view(), name="proyectosistema_delete"),

    # ── Despiece ─────────────────────────────────────────────────────────────
    path("despiece/proyecto/<int:pk>/",      DespieceProyectoView.as_view(),       name="despiece_proyecto"),
    path("despiece/calcular/<int:pk>/",      CalcularDespiecePSView.as_view(),     name="despiece_calcular"),
    path("despiece/ejecutar/<int:pk>/",      DespieceEjecutarView.as_view(),       name="despiece_ejecutar"),
    path("despiece/ajuste/<int:pk>/",        DespieceLineaAjusteView.as_view(),    name="despiece_ajuste"),
    path("despiece/api/variables/<int:pk>/",          SubsistemaVariablesView.as_view(),          name="despiece_api_variables"),
    path("despiece/api/ajuste/<int:pk>/",             DespieceLineaAjusteAPIView.as_view(),       name="despiece_api_ajuste"),
    path("despiece/api/asignar-producto/<int:pk>/",   AsignarProductoLineaAPIView.as_view(),      name="despiece_api_asignar_producto"),
    path("despiece/api/productos-linea/<int:pk>/",    ProductosPorCategoriaLineaAPIView.as_view(), name="despiece_api_productos_linea"),

    # ── APIs helpers ──────────────────────────────────────────────────────────
    path("api/productos-categoria/<slug:slug>/", ProductosPorCategoriaAPIView.as_view(), name="api_productos_categoria"),
    path("api/subsistema-def/<int:pk>/",         SubsistemaDefAPIView.as_view(),         name="api_subsistema_def"),
    path("api/catalogo/<str:tipo_apu>/",         ItemsCatalogoAPIView.as_view(),         name="api_catalogo_items"),

    # ── Configuración APU ─────────────────────────────────────────────────────
    path("config-apu/",                 ConfiguracionAPUListView.as_view(),   name="configapu_list"),
    path("config-apu/nueva/",           ConfiguracionAPUCreateView.as_view(), name="configapu_create"),
    path("config-apu/<int:pk>/editar/", ConfiguracionAPUUpdateView.as_view(), name="configapu_update"),

    # ── Catálogo APU ──────────────────────────────────────────────────────────
    path("catalogo-apu/",                              CatalogoAPUView.as_view(),            name="catalogo_apu"),
    path("catalogo-apu/categoria/nueva/",              CategoriaItemAPUCreateView.as_view(), name="catalogo_categoria_create"),
    path("catalogo-apu/categoria/<int:pk>/editar/",    CategoriaItemAPUUpdateView.as_view(), name="catalogo_categoria_update"),
    path("catalogo-apu/categoria/<int:pk>/eliminar/",  CategoriaItemAPUDeleteView.as_view(), name="catalogo_categoria_delete"),
    path("catalogo-apu/item/nuevo/",                   ItemCatalogoAPUCreateView.as_view(),  name="catalogo_item_create"),
    path("catalogo-apu/item/<int:pk>/editar/",         ItemCatalogoAPUUpdateView.as_view(),  name="catalogo_item_update"),
    path("catalogo-apu/item/<int:pk>/eliminar/",       ItemCatalogoAPUDeleteView.as_view(),  name="catalogo_item_delete"),
    path("catalogo-apu/cuadrilla/nueva/",              CuadrillaPresetCreateView.as_view(),  name="catalogo_cuadrilla_create"),
    path("catalogo-apu/cuadrilla/<int:pk>/editar/",    CuadrillaPresetUpdateView.as_view(),  name="catalogo_cuadrilla_update"),
    path("catalogo-apu/cuadrilla/<int:pk>/eliminar/",  CuadrillaPresetDeleteView.as_view(),  name="catalogo_cuadrilla_delete"),

    # ── APU — proyectos ───────────────────────────────────────────────────────
    path("apu/",                         APUListView.as_view(),           name="apu_list"),
    path("apu/<int:pk>/",                APUProyectoDetailView.as_view(), name="apu_detail"),
    path("apu/<int:pk>/editar/",         APUProyectoUpdateView.as_view(), name="apu_update"),
    path("apu/generar/<int:pk>/",        APUGenerarView.as_view(),        name="apu_generar"),
    path("apu/<int:pk>/mano-obra/",      APUManoObraView.as_view(),       name="apu_mano_obra"),
    path("apu/<int:pk>/herramientas/",   APUHerramientasView.as_view(),   name="apu_herramientas"),
    path("apu/<int:pk>/transporte/",     APUTransporteView.as_view(),     name="apu_transporte"),
    path("apu/<int:pk>/administrativo/", APUAdminView.as_view(),          name="apu_admin"),
    path("apu/linea/<int:pk>/editar/",   APULineaUpdateView.as_view(),    name="apu_linea_update"),
    path("apu/<int:pk>/pdf-interno/",    APUPDFInternoView.as_view(),     name="apu_pdf_interno"),
    path("apu/<int:pk>/pdf-cliente/",    APUPDFClienteView.as_view(),     name="apu_pdf_cliente"),
    path("apu/<int:pk>/enviar-revision/", APUEnviarRevisionView.as_view(), name="apu_enviar_revision"),
]
