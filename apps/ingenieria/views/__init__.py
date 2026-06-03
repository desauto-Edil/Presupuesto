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
from apps.common.mixins import WithCreateFormMixin


# ── Sistemas ──────────────────────────────────────────────────────────────────

class SistemaListView(WithCreateFormMixin, ListView):
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


class SistemaDetailView(DetailView):
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


class SistemaCreateView(CreateView):
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


class SistemaUpdateView(UpdateView):
    model = Sistema
    form_class = SistemaForm
    template_name = "ingenieria/sistema_form.html"
    success_url = reverse_lazy("ingenieria:sistema_list")


class SistemaDeleteView(DeleteView):
    model = Sistema
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("ingenieria:sistema_list")


# ── Subsistemas ───────────────────────────────────────────────────────────────

class SubsistemaListView(WithCreateFormMixin, ListView):
    model = Subsistema
    form_class = SubsistemaForm
    template_name = "ingenieria/subsistema_list.html"
    context_object_name = "subsistemas"
    ordering = ["sistema__codigo", "codigo"]


class SubsistemaDetailView(DetailView):
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


# ── Helpers de guardado ───────────────────────────────────────────────────────

def _guardar_reglas_apu(subsistema, post):
    """
    Procesa las reglas APU enviadas desde el form del subsistema.
    Reemplaza todos los registros existentes con los nuevos valores.
    POST arrays: regla_tipo_apu[], regla_formula[]
    """
    from apps.presupuestos.models import ReglaAPUSubsistema

    tipos    = post.getlist("regla_tipo_apu[]")
    formulas = post.getlist("regla_formula[]")

    ReglaAPUSubsistema.objects.filter(subsistema=subsistema).delete()
    for idx, (tipo, formula) in enumerate(zip(tipos, formulas)):
        tipo    = tipo.strip()
        formula = formula.strip()
        if tipo and formula:
            ReglaAPUSubsistema.objects.create(
                subsistema=subsistema,
                tipo_apu=tipo,
                formula_costo_unitario=formula,
                orden=idx + 1,
            )


def _parsear_opciones(raw: str) -> list:
    """
    Parsea un string de opciones separadas por punto y coma.
    Ej: "4; 6"  →  ["4", "6"]
    Limpia espacios y filtra entradas vacías.
    """
    if not raw:
        return []
    return [o.strip() for o in raw.split(";") if o.strip()]


def _guardar_variables(subsistema, post):
    """
    Guarda las variables de entrada del subsistema desde arrays POST.
    POST arrays: var_variable[], var_label[], var_unidad[], var_default[],
                 var_tipo[], var_opciones[]

    - tipo_entrada: NUMERO | TEXTO | OPCION_UNICA (default: NUMERO)
    - opciones: string "4; 6" → lista ["4", "6"] (solo para OPCION_UNICA)
    - valor_default: se guarda siempre; debe ser numérico para NUMERO/OPCION_UNICA
    """
    var_variables = post.getlist("var_variable[]")
    var_labels    = post.getlist("var_label[]")
    var_unidades  = post.getlist("var_unidad[]")
    var_defaults  = post.getlist("var_default[]")
    var_tipos     = post.getlist("var_tipo[]")
    var_opciones  = post.getlist("var_opciones[]")

    VariableSubsistema.objects.filter(subsistema=subsistema).delete()
    for idx, (variable, label) in enumerate(zip(var_variables, var_labels)):
        variable = variable.strip()
        label    = label.strip()
        if not (variable and label):
            continue
        raw_default = var_defaults[idx].strip() if idx < len(var_defaults) else ""
        try:
            default_val = float(raw_default) if raw_default else 0
        except ValueError:
            default_val = 0

        tipo = (var_tipos[idx].strip() if idx < len(var_tipos) else "").upper()
        if tipo not in ("NUMERO", "TEXTO", "OPCION_UNICA"):
            tipo = VariableSubsistema.NUMERO

        raw_ops = var_opciones[idx].strip() if idx < len(var_opciones) else ""
        opciones = _parsear_opciones(raw_ops) if tipo == VariableSubsistema.OPCION_UNICA else []

        VariableSubsistema.objects.create(
            subsistema=subsistema,
            variable=variable,
            label=label,
            unidad=var_unidades[idx].strip() if idx < len(var_unidades) else "",
            valor_default=default_val,
            tipo_entrada=tipo,
            opciones=opciones,
            orden=idx + 1,
        )


def _guardar_subconjuntos_componentes(subsistema, post):
    """
    Guarda los subconjuntos de receta técnica y sus componentes.

    Espera el campo POST 'subconjuntos_json' con estructura JSON:
    [
      {
        "nombre": "Estructura metálica",
        "descripcion": "Descripción opcional",
        "componentes": [
          {
            "codigo": "viga",
            "nombre": "Viga principal",
            "categoria_id": 3,          // null si sin categoría
            "formula_texto": "longitud * 1.05",
            "variable_salida": "",
            "unidad": "ml",
            "variable_referencia_apu": "",
            "unidad_apu": ""
          }
        ]
      }
    ]

    Si el JSON está vacío o ausente, no modifica los componentes existentes.
    Compatibilidad: si un subsistema antiguo tiene componentes sin subconjunto,
    se eliminan también al guardar con la nueva estructura.
    """
    from apps.catalogos.models import CategoriaProducto

    raw = post.get("subconjuntos_json", "").strip()
    if not raw:
        return

    try:
        subconjuntos_data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return

    if not isinstance(subconjuntos_data, list):
        return

    # Eliminar todos los subconjuntos y componentes existentes (incluye legacy)
    SubconjuntoRecetaTecnica.objects.filter(subsistema=subsistema).delete()
    ComponenteSubsistema.objects.filter(subsistema=subsistema, subconjunto__isnull=True).delete()

    # Set acumulativo de códigos ya asignados en este subsistema (defensa backend
    # ante un código vacío o duplicado proveniente del frontend).
    codigos_en_uso: set[str] = set()

    for sq_idx, sq_data in enumerate(subconjuntos_data):
        nombre_sq = str(sq_data.get("nombre", "")).strip()
        if not nombre_sq:
            continue

        subconjunto = SubconjuntoRecetaTecnica.objects.create(
            subsistema=subsistema,
            nombre=nombre_sq,
            descripcion=str(sq_data.get("descripcion", "")).strip(),
            orden=sq_idx + 1,
            activo=True,
        )

        componentes = sq_data.get("componentes", [])
        if not isinstance(componentes, list):
            continue

        for comp_idx, comp_data in enumerate(componentes):
            codigo  = str(comp_data.get("codigo", "")).strip()
            nombre  = str(comp_data.get("nombre", "")).strip()
            formula = str(comp_data.get("formula_texto", "")).strip()
            if not (nombre and formula):
                continue
            # Red de seguridad: si no llegó código, o si colisiona con otro
            # componente del mismo subsistema (unique_together), asignar el
            # próximo entero libre.
            if not codigo or codigo in codigos_en_uso:
                codigo = _proximo_codigo_numerico(codigos_en_uso)
            codigos_en_uso.add(codigo)

            cat_id = comp_data.get("categoria_id")
            categoria = None
            if cat_id:
                try:
                    categoria = CategoriaProducto.objects.get(pk=int(cat_id))
                except (CategoriaProducto.DoesNotExist, ValueError, TypeError):
                    pass

            ComponenteSubsistema.objects.create(
                subsistema=subsistema,
                subconjunto=subconjunto,
                codigo=codigo,
                nombre=nombre,
                categoria=categoria,
                formula_texto=formula,
                variable_salida=str(comp_data.get("variable_salida", "")).strip(),
                unidad=str(comp_data.get("unidad", "")).strip(),
                variable_referencia_apu=str(comp_data.get("variable_referencia_apu", "")).strip(),
                unidad_apu=str(comp_data.get("unidad_apu", "")).strip(),
                orden=comp_idx + 1,
            )


def _guardar_m2m_consumo(subsistema, post):
    """
    Guarda los M2M de catálogo consumo: funciones, problemas_resuelve, superficies_compatibles.
    Los checkboxes llegan como: funciones[], problemas_resuelve[], superficies_compatibles[]
    con los PKs seleccionados.
    """
    funciones_pks   = [int(pk) for pk in post.getlist("funciones[]") if pk.strip().isdigit()]
    problemas_pks   = [int(pk) for pk in post.getlist("problemas_resuelve[]") if pk.strip().isdigit()]
    superficies_pks = [int(pk) for pk in post.getlist("superficies_compatibles[]") if pk.strip().isdigit()]

    subsistema.funciones.set(funciones_pks)
    subsistema.problemas_resuelve.set(problemas_pks)
    subsistema.superficies_compatibles.set(superficies_pks)


def _guardar_productos_tecnicos_componentes_quimicos(subsistema, post):
    """
    Procesa ProductoTecnicoAsociado y ComponenteQuimico desde el form del subsistema.

    POST arrays para productos técnicos:
        pt_nombre[], pt_estado_fisico[], pt_consumo_min[], pt_consumo_max[], pt_unidad[]

    POST arrays para componentes químicos:
        cq_nombre[], cq_porcentaje[], cq_estado_fisico[], cq_categoria[]
    """
    from apps.catalogos.models import CategoriaProducto

    # ── Productos técnicos asociados ──────────────────────────────────────────
    pt_nombres        = post.getlist("pt_nombre[]")
    pt_estados_fisico = post.getlist("pt_estado_fisico[]")
    pt_consumos_min   = post.getlist("pt_consumo_min[]")
    pt_consumos_max   = post.getlist("pt_consumo_max[]")
    pt_unidades       = post.getlist("pt_unidad[]")

    ProductoTecnicoAsociado.objects.filter(subsistema=subsistema).delete()
    for idx, nombre in enumerate(pt_nombres):
        nombre = nombre.strip()
        if not nombre:
            continue

        def _decimal_or_none(lst, i):
            try:
                v = lst[i].strip() if i < len(lst) else ""
                return float(v) if v else None
            except ValueError:
                return None

        ProductoTecnicoAsociado.objects.create(
            subsistema=subsistema,
            nombre=nombre,
            estado_fisico=pt_estados_fisico[idx].strip() if idx < len(pt_estados_fisico) else "",
            consumo_min_g_m2=_decimal_or_none(pt_consumos_min, idx),
            consumo_max_g_m2=_decimal_or_none(pt_consumos_max, idx),
            unidad=pt_unidades[idx].strip() if idx < len(pt_unidades) else "kg",
            orden=idx + 1,
        )

    # ── Componentes químicos ──────────────────────────────────────────────────
    cq_nombres        = post.getlist("cq_nombre[]")
    cq_porcentajes    = post.getlist("cq_porcentaje[]")
    cq_estados_fisico = post.getlist("cq_estado_fisico[]")
    cq_categorias     = post.getlist("cq_categoria[]")

    ComponenteQuimico.objects.filter(subsistema=subsistema).delete()
    for idx, nombre in enumerate(cq_nombres):
        nombre = nombre.strip()
        if not nombre:
            continue
        try:
            porcentaje = float(cq_porcentajes[idx].strip()) if idx < len(cq_porcentajes) and cq_porcentajes[idx].strip() else 0
        except ValueError:
            porcentaje = 0
        cat_pk = cq_categorias[idx].strip() if idx < len(cq_categorias) else ""
        categoria = None
        if cat_pk:
            try:
                categoria = CategoriaProducto.objects.get(pk=int(cat_pk))
            except (CategoriaProducto.DoesNotExist, ValueError):
                pass
        ComponenteQuimico.objects.create(
            subsistema=subsistema,
            nombre=nombre,
            porcentaje=porcentaje,
            estado_fisico=cq_estados_fisico[idx].strip() if idx < len(cq_estados_fisico) else "",
            categoria=categoria,
            orden=idx + 1,
        )


def _tipo_apu_choices_sin_materiales():
    from apps.common.choices import TipoAPU
    return [(v, l) for v, l in TipoAPU.choices if v != TipoAPU.MATERIALES]


def _proximo_codigo_numerico(en_uso: set) -> str:
    """Devuelve el menor entero positivo (como string) que NO esté en `en_uso`.
    Replica el comportamiento del helper JS `generarCodigoComponente` del template.
    Códigos alfanuméricos legacy (ej. "fijaciones_plus") se consideran ocupados
    como string pero no afectan la numeración: se busca el primer hueco numérico
    libre desde 1.
    """
    n = 1
    while str(n) in en_uso:
        n += 1
    return str(n)


def _build_unidades_medida_json():
    """Catálogo de unidades de medida para selects del subsistema_form."""
    from apps.catalogos.models import UnidadMedida
    return json.dumps([
        {"abrev": u.abreviatura, "nombre": u.nombre}
        for u in UnidadMedida.objects.order_by("nombre")
    ])


def _sistemas_tipos_json():
    """Devuelve un dict {pk: tipo_sistema} de todos los sistemas."""
    return json.dumps({
        str(s.pk): s.tipo_sistema
        for s in Sistema.objects.only("pk", "tipo_sistema")
    })


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


class SubsistemaCreateView(CreateView):
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
        from apps.catalogos.models import CategoriaProducto
        ctx["categorias_producto"] = CategoriaProducto.objects.filter(activa=True).order_by("nombre")
        ctx["unidades_medida_json"] = _build_unidades_medida_json()
        ctx["tipo_apu_choices"] = _tipo_apu_choices_sin_materiales()
        ctx["reglas_apu_existentes"] = []
        ctx["productos_tecnicos_existentes"] = []
        ctx["componentes_quimicos_existentes"] = []
        ctx["variables_existentes"] = []
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
        return ctx

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method in ("POST", "PUT"):
            kwargs["files"] = self.request.FILES
        return kwargs

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)
            _guardar_variables(self.object, self.request.POST)
            _guardar_subconjuntos_componentes(self.object, self.request.POST)
            _guardar_reglas_apu(self.object, self.request.POST)
            _guardar_m2m_consumo(self.object, self.request.POST)
            _guardar_productos_tecnicos_componentes_quimicos(self.object, self.request.POST)
        return response


class SubsistemaUpdateView(UpdateView):
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
        from apps.catalogos.models import CategoriaProducto
        from apps.presupuestos.models import ReglaAPUSubsistema

        ctx["categorias_producto"] = CategoriaProducto.objects.filter(activa=True).order_by("nombre")
        ctx["unidades_medida_json"] = _build_unidades_medida_json()

        # Variables de entrada (incluye tipo_entrada y opciones para el template)
        ctx["variables_existentes"] = list(
            VariableSubsistema.objects.filter(subsistema=self.object).order_by("orden")
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
        return ctx

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method in ("POST", "PUT"):
            kwargs["files"] = self.request.FILES
        return kwargs

    def form_valid(self, form):
        with transaction.atomic():
            response = super().form_valid(form)
            _guardar_variables(self.object, self.request.POST)
            _guardar_subconjuntos_componentes(self.object, self.request.POST)
            _guardar_reglas_apu(self.object, self.request.POST)
            _guardar_m2m_consumo(self.object, self.request.POST)
            _guardar_productos_tecnicos_componentes_quimicos(self.object, self.request.POST)
        return response


class SubsistemaDeleteView(DeleteView):
    model = Subsistema
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("ingenieria:subsistema_list")


# ── Catálogos de consumo (FuncionConsumo, ProblemaResuelto, SuperficieCompatible) ─

class FuncionConsumoCreateView(CreateView):
    model = FuncionConsumo
    fields = ["nombre", "descripcion", "activo"]
    success_url = reverse_lazy("ingenieria:sistema_list")

    def get(self, request, *args, **kwargs):
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(["POST"])


class FuncionConsumoDeleteView(DeleteView):
    model = FuncionConsumo
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("ingenieria:sistema_list")


class ProblemaResueltoCreateView(CreateView):
    model = ProblemaResuelto
    fields = ["nombre", "descripcion", "activo"]
    success_url = reverse_lazy("ingenieria:sistema_list")

    def get(self, request, *args, **kwargs):
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(["POST"])


class ProblemaResueltoDeleteView(DeleteView):
    model = ProblemaResuelto
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("ingenieria:sistema_list")


class SuperficieCompatibleCreateView(CreateView):
    model = SuperficieCompatible
    fields = ["nombre", "descripcion", "activo"]
    success_url = reverse_lazy("ingenieria:sistema_list")

    def get(self, request, *args, **kwargs):
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(["POST"])


class SuperficieCompatibleDeleteView(DeleteView):
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
