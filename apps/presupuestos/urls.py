"""apps/presupuestos/urls.py"""

from django.urls import path
from apps.presupuestos.views import (
    # ProyectoSistema
    ProyectoSistemaListView, ProyectoSistemaDetailView,
    ProyectoSistemaCreateView, ProyectoSistemaUpdateView, ProyectoSistemaDeleteView,
    # Despiece — módulo lista
    DespieceListView, DespieceCSVDownloadView, NuevoDespieceView,
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
    APUGenerarDesdeDespiece, APUArmarDesdeDespieceView,
    APUSeleccionarDespiecesView,
    APUManoObraView, APUHerramientasView, APUTransporteView, APUAdminView,
    APULineaUpdateView, APULineaDeleteView, APUArchivarView,
    APUPDFInternoView, APUPDFClienteView, APUEnviarRevisionView,
    CotizacionPDFInternoView, CotizacionPDFClienteView,
    APURevisarView, APUAprobarModalidadView, APUResetModalidadView,
    APUEditarGarantiaView,
    APUCotizacionFinalView,
    # APU consolidado (Fase 11.5)
    APUConsolidarSeleccionarView, APUConsolidarPreviewView, APUConsolidarConfirmarView,
    # Catálogo APU
    CatalogoAPUView,
    CategoriaItemAPUCreateView, CategoriaItemAPUUpdateView, CategoriaItemAPUDeleteView,
    ItemCatalogoAPUCreateView, ItemCatalogoAPUUpdateView, ItemCatalogoAPUDeleteView,
    # CuadrillaPresetCreateView, CuadrillaPresetUpdateView, CuadrillaPresetDeleteView,  # oculto
    ItemsCatalogoAPIView,
    # Consumo
    CalculoConsumoView, EjecutarCalculoConsumoView,
    AsignarProductoConsumoAPIView, ProductosPorCategoriaConsumoAPIView,
)

app_name = "presupuestos"

urlpatterns = [

    # ── ProyectoSistema ──────────────────────────────────────────────────────
    path("sistemas/",                    ProyectoSistemaListView.as_view(),   name="proyectosistema_list"),
    path("sistemas/nuevo/",              ProyectoSistemaCreateView.as_view(), name="proyectosistema_create"),
    path("sistemas/<int:pk>/",           ProyectoSistemaDetailView.as_view(), name="proyectosistema_detail"),
    path("sistemas/<int:pk>/editar/",    ProyectoSistemaUpdateView.as_view(), name="proyectosistema_update"),
    path("sistemas/<int:pk>/eliminar/",  ProyectoSistemaDeleteView.as_view(), name="proyectosistema_delete"),

    # ── Despiece — módulo lista ───────────────────────────────────────────────
    path("despiece/",                        DespieceListView.as_view(),           name="despiece_list"),
    path("despiece/nuevo/",                  NuevoDespieceView.as_view(),          name="despiece_nuevo"),
    path("despiece/<int:pk>/csv/",           DespieceCSVDownloadView.as_view(),    name="despiece_csv"),

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
    # Cuadrilla presets: ocultos de la interfaz (modelos conservados en BD)
    # path("catalogo-apu/cuadrilla/nueva/",              CuadrillaPresetCreateView.as_view(),  name="catalogo_cuadrilla_create"),
    # path("catalogo-apu/cuadrilla/<int:pk>/editar/",    CuadrillaPresetUpdateView.as_view(),  name="catalogo_cuadrilla_update"),
    # path("catalogo-apu/cuadrilla/<int:pk>/eliminar/",  CuadrillaPresetDeleteView.as_view(),  name="catalogo_cuadrilla_delete"),

    # ── Consumo ───────────────────────────────────────────────────────────────
    path("consumo/<int:pk>/",                           CalculoConsumoView.as_view(),                  name="consumo_maestro"),
    path("consumo/<int:pk>/ejecutar/",                  EjecutarCalculoConsumoView.as_view(),          name="consumo_ejecutar"),
    path("consumo/api/asignar-producto/<int:pk>/",      AsignarProductoConsumoAPIView.as_view(),       name="consumo_api_asignar_producto"),
    path("consumo/api/productos-linea/<int:pk>/",       ProductosPorCategoriaConsumoAPIView.as_view(), name="consumo_api_productos_linea"),

    # ── APU — proyectos ───────────────────────────────────────────────────────
    path("apu/",                         APUListView.as_view(),           name="apu_list"),
    path("apu/<int:pk>/",                APUProyectoDetailView.as_view(), name="apu_detail"),
    path("apu/<int:pk>/editar/",         APUProyectoUpdateView.as_view(), name="apu_update"),
    path("apu/generar/<int:pk>/",              APUGenerarView.as_view(),          name="apu_generar"),
    path("apu/generar-despiece/<int:pk>/",     APUGenerarDesdeDespiece.as_view(), name="apu_generar_despiece"),
    path("apu/seleccionar-despieces/<int:pk>/", APUSeleccionarDespiecesView.as_view(), name="apu_seleccionar_despieces"),
    path("apu/armar-desde-despiece/<int:pk>/", APUArmarDesdeDespieceView.as_view(), name="apu_armar_desde_despiece"),
    path("apu/<int:pk>/mano-obra/",      APUManoObraView.as_view(),       name="apu_mano_obra"),
    path("apu/<int:pk>/herramientas/",   APUHerramientasView.as_view(),   name="apu_herramientas"),
    path("apu/<int:pk>/transporte/",     APUTransporteView.as_view(),     name="apu_transporte"),
    path("apu/<int:pk>/administrativo/", APUAdminView.as_view(),          name="apu_admin"),
    path("apu/linea/<int:pk>/editar/",   APULineaUpdateView.as_view(),    name="apu_linea_update"),
    path("apu/linea/<int:pk>/eliminar/", APULineaDeleteView.as_view(),    name="apu_linea_delete"),
    path("apu/<int:pk>/archivar/",       APUArchivarView.as_view(),       name="apu_archivar"),
    path("apu/<int:pk>/pdf-interno/",    APUPDFInternoView.as_view(),     name="apu_pdf_interno"),
    path("apu/<int:pk>/pdf-cliente/",    APUPDFClienteView.as_view(),     name="apu_pdf_cliente"),
    path("apu/<int:pk>/enviar-revision/",    APUEnviarRevisionView.as_view(),    name="apu_enviar_revision"),
    path("apu/<int:pk>/revisar/",             APURevisarView.as_view(),           name="apu_revisar"),
    path("apu/<int:pk>/aprobar-modalidad/",   APUAprobarModalidadView.as_view(),  name="apu_aprobar_modalidad"),
    path("apu/<int:pk>/reset-modalidad/",     APUResetModalidadView.as_view(),    name="apu_reset_modalidad"),
    # Fase 9E — editar garantía del APU desde el detalle
    path("apu/<int:pk>/editar-garantia/",     APUEditarGarantiaView.as_view(),    name="apu_editar_garantia"),
    # Fase 11 — cotización final en pantalla
    path("apu/<int:pk>/cotizacion/",          APUCotizacionFinalView.as_view(),   name="apu_cotizacion_final"),

    # Fase 12 — PDFs desde snapshot inmutable (cotización aprobada)
    path("cotizacion/<int:pk>/pdf-interno/", CotizacionPDFInternoView.as_view(), name="cotizacion_pdf_interno"),
    path("cotizacion/<int:pk>/pdf-cliente/", CotizacionPDFClienteView.as_view(), name="cotizacion_pdf_cliente"),

    # Fase 11.5 — Consolidación opcional de APUs (por proyecto)
    path("proyectos/<int:pk>/apu/consolidar/",          APUConsolidarSeleccionarView.as_view(), name="apu_consolidar_seleccionar"),
    path("proyectos/<int:pk>/apu/consolidar/preview/",  APUConsolidarPreviewView.as_view(),     name="apu_consolidar_preview"),
    path("proyectos/<int:pk>/apu/consolidar/confirmar/", APUConsolidarConfirmarView.as_view(),  name="apu_consolidar_confirmar"),
]
