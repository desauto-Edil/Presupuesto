"""apps/ingenieria/views — Vistas CRUD para catálogo de ingeniería.

Solo Sistema y Subsistema tienen vistas operativas.
Reglas y Dependencias ya no tienen CRUD en la interfaz —
las recetas técnicas se definen en apps/ingenieria/system_defs/.
"""

import json
from django.db import transaction
from django.db.models import Prefetch
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.views import View
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from apps.ingenieria.models import (
    Sistema, Subsistema, ComponenteSubsistema, VariableSubsistema,
    SubconjuntoRecetaTecnica,
    CapaConsumo, ComponenteQuimico,
    FuncionConsumo, ProblemaResuelto, SuperficieCompatible,
    ProductoTecnicoAsociado,
)
from apps.ingenieria.forms import SistemaForm, SubsistemaForm
from apps.common.mixins import WithCreateFormMixin, GestionIngenieriaMixin, APUSistemaAccesoMixin
from apps.ingenieria.services.subsistema_service import (
    guardar_variables,
    guardar_subconjuntos_componentes,
    guardar_reglas_apu,
    guardar_items_apu_subsistema,
    guardar_m2m_consumo,
    guardar_productos_tecnicos_componentes_quimicos,
    guardar_dependencias_variables,
)


# ── Sistemas ──────────────────────────────────────────────────────────────────

class SistemaListView(APUSistemaAccesoMixin, WithCreateFormMixin, ListView):
    model = Sistema
    form_class = SistemaForm
    template_name = "ingenieria/sistema_list.html"
    context_object_name = "sistemas"
    ordering = ["codigo"]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["subsistemas"] = (
            Subsistema.objects
            .select_related("sistema")
            .order_by("sistema__codigo", "codigo")
        )
        ctx["create_subsistema_form"] = SubsistemaForm()
        ctx["funciones_catalogo"] = FuncionConsumo.objects.order_by("nombre")
        ctx["problemas_catalogo"] = ProblemaResuelto.objects.order_by("nombre")
        ctx["superficies_catalogo"] = SuperficieCompatible.objects.order_by("nombre")
        return ctx


class SistemaDetailView(APUSistemaAccesoMixin, DetailView):
    model = Sistema
    template_name = "ingenieria/sistema_detail.html"
    context_object_name = "sistema"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["subsistemas"] = self.object.subsistemas.filter(activo=True).order_by("codigo")

        # Mostrar definición backend si existe
        from apps.ingenieria.system_defs.registry import get_sistema_def, sistema_tiene_def
        ctx["tiene_def_backend"] = sistema_tiene_def(self.object.codigo)
        ctx["subsistemas_def"] = get_sistema_def(self.object.codigo)
        return ctx


class SistemaCreateView(APUSistemaAccesoMixin, CreateView):
    model = Sistema
    form_class = SistemaForm
    template_name = "ingenieria/sistema_form.html"
    success_url = reverse_lazy("ingenieria:sistema_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        # Crear subsistemas inline si se enviaron
        codigos  = self.request.POST.getlist("sub_codigo[]")
        nombres  = self.request.POST.getlist("sub_nombre[]")
        descrips = self.request.POST.getlist("sub_descripcion[]")
        for codigo, nombre, descripcion in zip(codigos, nombres, descrips):
            codigo  = codigo.strip()
            nombre  = nombre.strip()
            if codigo and nombre:
                Subsistema.objects.get_or_create(
                    sistema=self.object,
                    codigo=codigo,
                    defaults={"nombre": nombre, "descripcion": descripcion.strip(), "activo": True},
                )
        return response


class SistemaUpdateView(APUSistemaAccesoMixin, UpdateView):
    model = Sistema
    form_class = SistemaForm
    template_name = "ingenieria/sistema_form.html"
    success_url = reverse_lazy("ingenieria:sistema_list")


class SistemaDeleteView(APUSistemaAccesoMixin, DeleteView):
    model = Sistema
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("ingenieria:sistema_list")


# ── Subsistemas ───────────────────────────────────────────────────────────────

class SubsistemaDetailView(APUSistemaAccesoMixin, DetailView):
    model = Subsistema
    template_name = "ingenieria/subsistema_detail.html"
    context_object_name = "subsistema"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # DB componentes y variables (prioridad)
        ctx["componentes_db"] = list(
            ComponenteSubsistema.objects.filter(subsistema=self.object)
            .select_related("categoria")
            .order_by("orden")
        )
        ctx["variables_db"] = list(
            VariableSubsistema.objects.filter(subsistema=self.object).order_by("orden")
        )

        # Registro Python (fallback / comparación)
        from apps.ingenieria.system_defs.registry import get_subsistema_def
        ctx["sub_def"] = get_subsistema_def(self.object.sistema.codigo, self.object.codigo)
        return ctx


# ── Helpers de guardado ──────────────────────────────────────────────────────
# Movidos a apps/ingenieria/services/subsistema_service.py (Fase 2 — Lote D).
# Las funciones se importan al inicio del módulo.
def _tipo_apu_choices_sin_materiales():
    from apps.common.choices import TipoAPU
    return [(v, l) for v, l in TipoAPU.choices if v != TipoAPU.MATERIALES]


def _build_unidades_medida_json():
    """Catálogo de unidades de medida para selects del subsistema_form.

    Usa cache (Fase 5B). Shape emitido al JS preservada: {"abrev", "nombre"}.
    Invalidación: signals post_save/post_delete sobre UnidadMedida
    (apps/catalogos/signals.py).
    """
    from apps.common.cache import get_cached_unidades
    return json.dumps([
        {"abrev": u["abreviatura"], "nombre": u["nombre"]}
        for u in get_cached_unidades()
    ])


def _categorias_producto_para_template():
    """Lista de categorías activas (cache-aside) en forma compatible con el
    template subsistema_form.html, que consume cat.pk y cat.nombre.

    Devuelve dicts con claves: pk, id, codigo, nombre. La clave 'pk' es alias
    de 'id' para no romper {{ cat.pk }} en el template.
    Invalidación: signals post_save/post_delete sobre CategoriaProducto
    (apps/catalogos/signals.py).
    """
    from apps.common.cache import get_cached_categorias
    return [
        {"pk": c["id"], "id": c["id"], "codigo": c["codigo"], "nombre": c["nombre"]}
        for c in get_cached_categorias()
    ]


def _sistemas_tipos_json():
    """Devuelve un dict {pk: tipo_sistema} de todos los sistemas."""
    return json.dumps({
        str(s.pk): s.tipo_sistema
        for s in Sistema.objects.only("pk", "tipo_sistema")
    })


def _items_apu_subsistema_context(subsistema=None):
    """Context para la sección 'Configuración APU del subsistema' (Fase 6L-C).

    Devuelve, por tipo APU (no-Materiales), la lista completa del catálogo
    activo agrupada por categoría y el conjunto de PKs ya seleccionados
    para el subsistema actual (vacío si es Create). El template usa esto
    para renderizar 4 bloques (Herramientas, Transporte, Mano de obra,
    Administración) con checkboxes + cantidad + búsqueda frontend.

    Estructura de salida:
        {
          "sia_tipos": [
              {"tipo": "HERRAMIENTAS_EQUIPOS", "label": "Herramientas",
               "icon": "bi-tools", "color": "#e07d10",
               "items_por_categoria": [
                   {"categoria": "Eléctrica",
                    "items": [ItemCatalogoAPU, ...]},
                   ...
               ]},
              ...
          ],
          "sia_seleccion": {
              "HERRAMIENTAS_EQUIPOS": {item_id: cantidad, ...},
              ...
          },
        }
    """
    from apps.common.choices import TipoAPU
    from apps.presupuestos.models import ItemCatalogoAPU, SubsistemaItemAPU
    from collections import OrderedDict

    TIPOS_INFO = [
        {"tipo": TipoAPU.HERRAMIENTAS_EQUIPOS, "label": "Herramientas",
         "icon": "bi-tools",     "color": "#e07d10"},
        {"tipo": TipoAPU.TRANSPORTE,           "label": "Transporte",
         "icon": "bi-truck",     "color": "#7048d0"},
        {"tipo": TipoAPU.MANO_DE_OBRA,         "label": "Mano de obra",
         "icon": "bi-people",    "color": "#17a85e"},
        {"tipo": TipoAPU.ADMINISTRACION,       "label": "Administración",
         "icon": "bi-briefcase", "color": "#64748b"},
    ]

    # Pre-cargar todo el catálogo activo en una sola query y agrupar en Python
    items_all = list(
        ItemCatalogoAPU.objects.filter(activo=True)
        .select_related("categoria")
        .order_by("categoria__tipo_apu", "categoria__nombre", "nombre")
    )

    # Selección actual (solo si Update, no Create)
    seleccion: dict = {info["tipo"]: {} for info in TIPOS_INFO}
    rendimientos_seleccion: dict = {info["tipo"]: {} for info in TIPOS_INFO}
    if subsistema is not None and getattr(subsistema, "pk", None):
        for sia in SubsistemaItemAPU.objects.filter(
            subsistema=subsistema, activo=True
        ).only("item_catalogo_id", "tipo", "cantidad", "rendimiento_override"):
            seleccion.setdefault(sia.tipo, {})[sia.item_catalogo_id] = sia.cantidad
            rendimientos_seleccion.setdefault(sia.tipo, {})[sia.item_catalogo_id] = sia.rendimiento_override

    sia_tipos = []
    for info in TIPOS_INFO:
        seleccion_tipo = seleccion.get(info["tipo"], {})
        rend_tipo = rendimientos_seleccion.get(info["tipo"], {})
        items_tipo = [
            it for it in items_all
            if it.categoria and it.categoria.tipo_apu == info["tipo"]
        ]
        # Anotar en runtime cada ítem con su estado de selección para no
        # requerir custom template filters en subsistema_form.html.
        for it in items_tipo:
            cant = seleccion_tipo.get(it.pk)
            it.sia_checked = cant is not None
            it.sia_cantidad = cant if cant is not None else 1
            # Porcentaje de aplicación para ADMINISTRACIÓN (factor → %).
            # None si no está guardado (el template muestra placeholder 100).
            rend = rend_tipo.get(it.pk)
            it.sia_rendimiento_pct = float(rend) * 100 if rend is not None else ""
        # Agrupar por categoría (preservando orden)
        por_cat: "OrderedDict[str, list]" = OrderedDict()
        for it in items_tipo:
            nombre_cat = it.categoria.nombre
            por_cat.setdefault(nombre_cat, []).append(it)
        items_por_categoria = [
            {"categoria": nombre, "items": lista}
            for nombre, lista in por_cat.items()
        ]
        sia_tipos.append({
            **info,
            "items_por_categoria": items_por_categoria,
            "total_items": len(items_tipo),
            "total_seleccionados": len(seleccion_tipo),
        })

    return {
        "sia_tipos": sia_tipos,
        "sia_seleccion": seleccion,
    }


def _catalogo_consumo_context():
    """Context dict con los catálogos M2M y choices para el form de subsistema de consumo."""
    from apps.common.choices import EstadoFisicoProducto
    return {
        "funciones_catalogo": FuncionConsumo.objects.filter(activo=True).order_by("nombre"),
        "problemas_catalogo": ProblemaResuelto.objects.filter(activo=True).order_by("nombre"),
        "superficies_catalogo": SuperficieCompatible.objects.filter(activo=True).order_by("nombre"),
        "estado_fisico_choices": EstadoFisicoProducto.choices,
    }


def _build_subconjuntos_json(subconjuntos, componentes_legacy):
    """
    Serializa subconjuntos (con sus componentes) y componentes legacy a JSON
    para inicializar el editor JS del template.
    Los legacy se agrupan en un bloque 'General' si existen.
    """
    data = []
    for sq in subconjuntos:
        data.append({
            "nombre": sq.nombre,
            "descripcion": sq.descripcion,
            "componentes": [
                {
                    "codigo": c.codigo,
                    "nombre": c.nombre,
                    "categoria_id": c.categoria_id,
                    "formula_texto": c.formula_texto,
                    "variable_salida": c.variable_salida,
                    "unidad": c.unidad,
                    "variable_referencia_apu": c.variable_referencia_apu,
                    "unidad_apu": c.unidad_apu,
                    "requiere_presentacion_producto": c.requiere_presentacion_producto,
                    "variable_presentacion_producto": c.variable_presentacion_producto,
                    "campo_presentacion_producto": c.campo_presentacion_producto or "CANTIDAD",
                }
                for c in sq.componentes.all()
            ],
        })
    if componentes_legacy:
        data.append({
            "nombre": "General",
            "descripcion": "Componentes migrados de versión anterior (puedes renombrar este subconjunto)",
            "componentes": [
                {
                    "codigo": c.codigo,
                    "nombre": c.nombre,
                    "categoria_id": c.categoria_id,
                    "formula_texto": c.formula_texto,
                    "variable_salida": c.variable_salida,
                    "unidad": c.unidad,
                    "variable_referencia_apu": c.variable_referencia_apu,
                    "unidad_apu": c.unidad_apu,
                    "requiere_presentacion_producto": c.requiere_presentacion_producto,
                    "variable_presentacion_producto": c.variable_presentacion_producto,
                    "campo_presentacion_producto": c.campo_presentacion_producto or "CANTIDAD",
                }
                for c in componentes_legacy
            ],
        })
    return json.dumps(data, ensure_ascii=False)


def _subconjuntos_context(subsistema):
    """
    Carga los subconjuntos de receta técnica con sus componentes (prefetch optimizado).
    También detecta componentes legacy (sin subconjunto asignado).
    """
    subconjuntos = list(
        SubconjuntoRecetaTecnica.objects.filter(subsistema=subsistema)
        .prefetch_related(
            Prefetch(
                "componentes",
                queryset=ComponenteSubsistema.objects.select_related("categoria").order_by("orden"),
            )
        )
        .order_by("orden", "id")
    )
    # Componentes legacy: creados antes de la versión con subconjuntos
    componentes_legacy = list(
        ComponenteSubsistema.objects.filter(subsistema=subsistema, subconjunto__isnull=True)
        .select_related("categoria")
        .order_by("orden")
    )
    return subconjuntos, componentes_legacy


class SubsistemaCreateView(APUSistemaAccesoMixin, CreateView):
    model = Subsistema
    form_class = SubsistemaForm
    template_name = "ingenieria/subsistema_form.html"
    success_url = reverse_lazy("ingenieria:sistema_list")

    def get_initial(self):
        initial = super().get_initial()
        sistema_pk = self.request.GET.get("sistema")
        if sistema_pk:
            initial["sistema"] = sistema_pk
        return initial

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["categorias_producto"] = _categorias_producto_para_template()
        ctx["unidades_medida_json"] = _build_unidades_medida_json()
        ctx["tipo_apu_choices"] = _tipo_apu_choices_sin_materiales()
        ctx["reglas_apu_existentes"] = []
        ctx["productos_tecnicos_existentes"] = []
        ctx["componentes_quimicos_existentes"] = []
        ctx["variables_existentes"] = []
        ctx["dependencias_existentes"] = []
        # Solo NUMERO y OPCION_UNICA disponibles en el formulario (TEXTO se conserva
        # en el modelo por compatibilidad con datos existentes, pero no se ofrece).
        ctx["tipo_entrada_choices"] = [
            (val, lbl) for val, lbl in VariableSubsistema.TIPO_ENTRADA_CHOICES
            if val != VariableSubsistema.TEXTO
        ]
        ctx["subconjuntos_receta"] = []
        ctx["componentes_legacy"] = []
        ctx["subconjuntos_json"] = "[]"
        ctx["sistemas_tipos_json"] = _sistemas_tipos_json()
        # Tipo del sistema pre-seleccionado (para JS)
        sistema_pk = self.request.GET.get("sistema")
        if sistema_pk:
            try:
                sis = Sistema.objects.get(pk=int(sistema_pk))
                ctx["sistema_actual_tipo"] = sis.tipo_sistema
            except (Sistema.DoesNotExist, ValueError):
                pass
        # M2M catálogos
        ctx.update(_catalogo_consumo_context())
        ctx["funciones_seleccionadas"] = []
        ctx["problemas_seleccionados"] = []
        ctx["superficies_seleccionadas"] = []
        # Fase 6L-C: configuración APU del subsistema (vacía en Create)
        ctx.update(_items_apu_subsistema_context(None))
        return ctx

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method in ("POST", "PUT"):
            kwargs["files"] = self.request.FILES
        return kwargs

    def form_valid(self, form):
        errores_comps = []
        errores_dep = []
        with transaction.atomic():
            response = super().form_valid(form)
            guardar_variables(self.object, self.request.POST)
            errores_comps = guardar_subconjuntos_componentes(self.object, self.request.POST)
            guardar_reglas_apu(self.object, self.request.POST)
            # Fase 6L-2: la configuración APU ya no viaja en este POST
            # (vive en el modal #modalConfigApu que tiene su propio form).
            guardar_m2m_consumo(self.object, self.request.POST)
            guardar_productos_tecnicos_componentes_quimicos(self.object, self.request.POST)
            errores_dep = guardar_dependencias_variables(self.object, self.request.POST)
        from django.contrib import messages
        for e in errores_comps:
            messages.warning(self.request, e)
        for e in errores_dep:
            messages.warning(self.request, e)
        return response

    def get_success_url(self):
        # Fase 6L-5: tras "Guardar y continuar" se abre el modal de config APU
        # en la vista de edición del subsistema recién creado.
        return (
            reverse_lazy("ingenieria:subsistema_update", args=[self.object.pk])
            + "?abrir_modal_apu=1"
        )


class SubsistemaUpdateView(APUSistemaAccesoMixin, UpdateView):
    model = Subsistema
    form_class = SubsistemaForm
    template_name = "ingenieria/subsistema_form.html"
    success_url = reverse_lazy("ingenieria:sistema_list")

    def get_queryset(self):
        return (
            super().get_queryset()
            .select_related("sistema")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.presupuestos.models import ReglaAPUSubsistema

        ctx["categorias_producto"] = _categorias_producto_para_template()
        ctx["unidades_medida_json"] = _build_unidades_medida_json()

        # Variables de entrada (incluye tipo_entrada y opciones para el template)
        ctx["variables_existentes"] = list(
            VariableSubsistema.objects.filter(subsistema=self.object).order_by("orden")
        )
        # Fase 2B — Dependencias entre variables del subsistema.
        from apps.ingenieria.models import VariableDependenciaSubsistema
        ctx["dependencias_existentes"] = list(
            VariableDependenciaSubsistema.objects
            .filter(subsistema=self.object)
            .select_related("variable_origen", "variable_destino")
            .order_by("orden", "id")
        )
        # Solo NUMERO y OPCION_UNICA disponibles en el formulario (TEXTO se conserva
        # en el modelo por compatibilidad con datos existentes, pero no se ofrece).
        ctx["tipo_entrada_choices"] = [
            (val, lbl) for val, lbl in VariableSubsistema.TIPO_ENTRADA_CHOICES
            if val != VariableSubsistema.TEXTO
        ]

        # Subconjuntos con componentes (estructura nueva) + legacy
        subconjuntos, componentes_legacy = _subconjuntos_context(self.object)
        ctx["subconjuntos_receta"] = subconjuntos
        ctx["componentes_legacy"] = componentes_legacy
        ctx["subconjuntos_json"] = _build_subconjuntos_json(subconjuntos, componentes_legacy)

        ctx["tipo_apu_choices"] = _tipo_apu_choices_sin_materiales()
        ctx["reglas_apu_existentes"] = list(
            ReglaAPUSubsistema.objects.filter(subsistema=self.object)
            .order_by("orden")
            .values("tipo_apu", "formula_costo_unitario", "orden")
        )
        ctx["productos_tecnicos_existentes"] = list(
            ProductoTecnicoAsociado.objects.filter(subsistema=self.object)
            .order_by("orden")
            .values("id", "nombre", "estado_fisico", "consumo_min_g_m2", "consumo_max_g_m2", "unidad", "orden")
        )
        ctx["componentes_quimicos_existentes"] = list(
            ComponenteQuimico.objects.filter(subsistema=self.object)
            .select_related("categoria")
            .order_by("orden")
            .values("id", "nombre", "porcentaje", "estado_fisico", "categoria_id", "orden")
        )
        ctx["sistemas_tipos_json"] = _sistemas_tipos_json()
        ctx["sistema_actual_tipo"] = self.object.sistema.tipo_sistema
        # M2M catálogos
        ctx.update(_catalogo_consumo_context())
        ctx["funciones_seleccionadas"] = list(self.object.funciones.values_list("pk", flat=True))
        ctx["problemas_seleccionados"] = list(self.object.problemas_resuelve.values_list("pk", flat=True))
        ctx["superficies_seleccionadas"] = list(self.object.superficies_compatibles.values_list("pk", flat=True))
        # Fase 6L-C: configuración APU del subsistema (con selección actual)
        ctx.update(_items_apu_subsistema_context(self.object))
        return ctx

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method in ("POST", "PUT"):
            kwargs["files"] = self.request.FILES
        return kwargs

    def form_valid(self, form):
        errores_comps = []
        errores_dep = []
        with transaction.atomic():
            response = super().form_valid(form)
            guardar_variables(self.object, self.request.POST)
            errores_comps = guardar_subconjuntos_componentes(self.object, self.request.POST)
            guardar_reglas_apu(self.object, self.request.POST)
            # Fase 6L-2: la configuración APU ya no viaja en este POST
            # (vive en el modal #modalConfigApu).
            guardar_m2m_consumo(self.object, self.request.POST)
            guardar_productos_tecnicos_componentes_quimicos(self.object, self.request.POST)
            errores_dep = guardar_dependencias_variables(self.object, self.request.POST)
        from django.contrib import messages
        for e in errores_comps:
            messages.warning(self.request, e)
        for e in errores_dep:
            messages.warning(self.request, e)
        return response

    def get_success_url(self):
        # Fase 6L-5: tras "Guardar y continuar" abrir el modal de config APU.
        return (
            reverse_lazy("ingenieria:subsistema_update", args=[self.object.pk])
            + "?abrir_modal_apu=1"
        )


class SubsistemaConfigApuGuardarView(APUSistemaAccesoMixin, View):
    """
    Fase 6L-4: vista POST-only que recibe la configuración APU del subsistema
    enviada desde el modal `#modalConfigApu`. Reutiliza el servicio
    `guardar_items_apu_subsistema`. Tras guardar redirige al **detalle** del
    subsistema (no al edit) para que el usuario perciba claramente que la
    configuración quedó guardada y salga del modo edición.
    """
    http_method_names = ["post"]

    def post(self, request, pk, *args, **kwargs):
        from django.shortcuts import get_object_or_404, redirect
        from django.contrib import messages
        subsistema = get_object_or_404(Subsistema, pk=pk)
        with transaction.atomic():
            guardar_items_apu_subsistema(subsistema, request.POST)
        messages.success(request, "Configuración APU del subsistema guardada.")
        return redirect("ingenieria:sistema_list")


class SubsistemaDeleteView(APUSistemaAccesoMixin, DeleteView):
    model = Subsistema
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("ingenieria:sistema_list")


# ── Catálogos de consumo (FuncionConsumo, ProblemaResuelto, SuperficieCompatible) ─

class FuncionConsumoCreateView(APUSistemaAccesoMixin, CreateView):
    model = FuncionConsumo
    fields = ["nombre", "descripcion", "activo"]
    success_url = reverse_lazy("ingenieria:sistema_list")

    def get(self, request, *args, **kwargs):
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(["POST"])


class FuncionConsumoDeleteView(APUSistemaAccesoMixin, DeleteView):
    model = FuncionConsumo
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("ingenieria:sistema_list")


class ProblemaResueltoCreateView(APUSistemaAccesoMixin, CreateView):
    model = ProblemaResuelto
    fields = ["nombre", "descripcion", "activo"]
    success_url = reverse_lazy("ingenieria:sistema_list")

    def get(self, request, *args, **kwargs):
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(["POST"])


class ProblemaResueltoDeleteView(APUSistemaAccesoMixin, DeleteView):
    model = ProblemaResuelto
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("ingenieria:sistema_list")


class SuperficieCompatibleCreateView(APUSistemaAccesoMixin, CreateView):
    model = SuperficieCompatible
    fields = ["nombre", "descripcion", "activo"]
    success_url = reverse_lazy("ingenieria:sistema_list")

    def get(self, request, *args, **kwargs):
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(["POST"])


class SuperficieCompatibleDeleteView(APUSistemaAccesoMixin, DeleteView):
    model = SuperficieCompatible
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("ingenieria:sistema_list")


# ── Calculadora de consumo ─────────────────────────────────────────────────────

class CalculadoraConsumoView(DetailView):
    """
    Calculadora interactiva para sistemas de CONSUMO.
    El usuario ingresa áreas por tipo y la página calcula el consumo de productos.
    """
    model = Sistema
    template_name = "ingenieria/calculadora_consumo.html"
    context_object_name = "sistema"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        subsistemas = list(
            self.object.subsistemas.filter(activo=True).order_by("codigo")
            .prefetch_related("funciones", "superficies_compatibles", "productos_tecnicos")
        )
        subs_data = []
        for s in subsistemas:
            consumo_min = float(s.consumo_min_g_m2) if s.consumo_min_g_m2 else None
            consumo_max = float(s.consumo_max_g_m2) if s.consumo_max_g_m2 else None
            subs_data.append({
                "pk": s.pk,
                "codigo": s.codigo,
                "nombre": s.nombre,
                "funciones": [f.nombre for f in s.funciones.all()],
                "tipo_producto": s.get_tipo_producto_display() if s.tipo_producto else "",
                "resistencia_quimica": s.resistencia_quimica,
                "temperatura_min": float(s.temperatura_min) if s.temperatura_min else None,
                "temperatura_max": float(s.temperatura_max) if s.temperatura_max else None,
                "interior_exterior": s.get_interior_exterior_display() if s.interior_exterior else "",
                "consumo_min_g_m2": consumo_min,
                "consumo_max_g_m2": consumo_max,
            })
        ctx["subsistemas"] = subsistemas
        ctx["subsistemas_json"] = json.dumps(subs_data)
        return ctx
