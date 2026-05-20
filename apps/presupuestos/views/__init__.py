"""apps/presupuestos/views — Vistas del módulo de presupuestos."""

import csv
import io
import json
import logging
from datetime import date
from decimal import Decimal

from django.db.models import Prefetch, Count, Q
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.views import View
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string

from apps.presupuestos.models import (
    ProyectoSistema, DespieceLinea,
    ConfiguracionAPU,
    APU, APUProyecto, APULinea,
    CategoriaItemAPU, CuadrillaPreset, CuadrillaPresetItem, ItemCatalogoAPU,
)
from apps.comercial.models import Proyecto
from apps.comercial.views import registrar_log
from apps.ingenieria.models import Sistema, Subsistema
from apps.common.choices import TipoAPU
from apps.presupuestos.forms import (
    ProyectoSistemaForm, DespieceLineaAjusteForm,
    ConfiguracionAPUForm, APUProyectoForm,
    CategoriaItemAPUForm, ItemCatalogoAPUForm,
    CuadrillaPresetForm, CuadrillaPresetItemFormSet,
)
from apps.comercial.forms import SolicitudForm
from apps.common.mixins import UnidadFilterMixin, WithCreateFormMixin

logger = logging.getLogger(__name__)


# ── ProyectoSistema ───────────────────────────────────────────────────────────

class ProyectoSistemaListView(ListView):
    model = ProyectoSistema
    template_name = "presupuestos/proyectosistema_list.html"
    context_object_name = "proyecto_sistemas"
    ordering = ["proyecto__consecutivo", "sistema__nombre"]


class ProyectoSistemaDetailView(DetailView):
    model = ProyectoSistema
    template_name = "presupuestos/proyectosistema_detail.html"
    context_object_name = "ps"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["despiece_lineas"] = self.object.despiece_lineas.select_related(
            "producto", "categoria_producto", "regla"
        ).order_by("id")
        return ctx


class ProyectoSistemaCreateView(CreateView):
    model = ProyectoSistema
    form_class = ProyectoSistemaForm
    template_name = "presupuestos/proyectosistema_form.html"
    success_url = reverse_lazy("presupuestos:proyectosistema_list")


class ProyectoSistemaUpdateView(UpdateView):
    model = ProyectoSistema
    form_class = ProyectoSistemaForm
    template_name = "presupuestos/proyectosistema_form.html"
    success_url = reverse_lazy("presupuestos:proyectosistema_list")


class ProyectoSistemaDeleteView(DeleteView):
    model = ProyectoSistema
    template_name = "confirm_delete.html"

    def get_success_url(self):
        return reverse("ingenieria:despiece_list") + f"?proyecto_pk={self.object.proyecto_id}"


# ── Despiece — Módulo lista ───────────────────────────────────────────────────

class DespieceListView(UnidadFilterMixin, ListView):
    """Módulo Despiece — lista proyectos con despieces. Visible para todas las unidades."""
    model = Proyecto
    template_name = "presupuestos/proyecto_despiece_dashboard.html"
    context_object_name = "proyectos"
    unidad_field = "creado_por__unidad_negocio"

    def get_queryset(self):
        qs = super().get_queryset()
        return (
            qs
            .filter(es_version_actual=True)
            .select_related("cliente", "solicitud", "creado_por")
            .annotate(
                num_sistemas=Count("proyecto_sistemas", distinct=True),
                num_lineas=Count("proyecto_sistemas__despiece_lineas", distinct=True),
            )
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs)


class NuevoDespieceView(View):
    """POST — redirige al nuevo calculador de sistemas."""

    def post(self, request):
        return redirect("ingenieria:calculador_sistemas")


class DespieceCSVDownloadView(View):
    """GET /presupuestos/despiece/<pk>/csv/ — descarga CSV de DespieceLineas del proyecto."""

    def get(self, request, pk):
        proyecto = get_object_or_404(Proyecto, pk=pk)

        unidad = request.session.get("unidad_negocio", "") or ""
        if unidad and proyecto.creado_por and proyecto.creado_por.unidad_negocio != unidad:
            messages.error(request, "No tiene acceso a este proyecto.")
            return redirect("presupuestos:despiece_list")

        lineas = (
            DespieceLinea.objects
            .filter(proyecto=proyecto)
            .select_related(
                "proyecto_sistema__sistema",
                "proyecto_sistema__subsistema",
                "categoria_producto",
                "producto",
            )
            .order_by(
                "proyecto_sistema__sistema__nombre",
                "proyecto_sistema__subsistema__nombre",
                "componente_codigo",
            )
        )

        filename = f"despiece_{proyecto.consecutivo}.csv"
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response.write("\ufeff")  # BOM para Excel en Windows

        writer = csv.writer(response)
        writer.writerow([
            "Sistema", "Subsistema", "Componente", "Categoría",
            "Producto asignado", "Cantidad final", "Unidad",
            "Precio unitario (COP)", "Subtotal (COP)",
        ])

        for linea in lineas:
            ps = linea.proyecto_sistema
            sistema = ps.sistema.nombre if ps and ps.sistema_id else "—"
            subsistema = ps.subsistema.nombre if ps and ps.subsistema_id else "—"
            categoria = linea.categoria_producto.nombre if linea.categoria_producto_id else "—"
            producto = linea.producto.nombre if linea.producto_id else "Sin asignar"
            cantidad = linea.cantidad_final
            precio = linea.precio_snapshot or 0
            subtotal = round(float(cantidad) * float(precio), 2) if precio else 0

            writer.writerow([
                sistema, subsistema, linea.componente_codigo or "—",
                categoria, producto, cantidad, "und",
                precio, subtotal,
            ])

        registrar_log(
            request,
            accion="DESCARGAR_DESPIECE_CSV",
            descripcion=f"CSV despiece — {proyecto.consecutivo}",
            modelo_afectado="Proyecto",
            objeto_id=proyecto.pk,
        )
        return response


# ── Despiece — Vista principal ─────────────────────────────────────────────────

class DespieceProyectoView(View):
    """Redirige al nuevo calculador — reemplazado por DespieceMaestro en ingenieria."""

    def get(self, request, pk):
        url = reverse("ingenieria:despiece_list") + f"?proyecto_pk={pk}"
        return redirect(url)


# ── Despiece — AJAX: variables requeridas por subsistema ──────────────────────

class SubsistemaVariablesView(View):
    """
    GET /despiece/api/variables/<pk>/
    Devuelve las variables que el subsistema del ProyectoSistema <pk> necesita,
    incluyendo el valor actual guardado en parametros_entrada.
    """
    def get(self, request, pk):
        ps = get_object_or_404(ProyectoSistema, pk=pk)
        variables = ps.get_variables_requeridas()
        return JsonResponse({"variables": variables})


# ── Despiece — POST: calcular (crea/actualiza PS + ejecuta despiece) ──────────

class CalcularDespiecePSView(View):
    """
    POST /despiece/calcular/<proyecto_pk>/
    Body JSON: {sistema_id, subsistema_id (opt), parametros: {k: v, ...}}

    Crea o actualiza el ProyectoSistema, guarda los parámetros de entrada,
    inyecta dependencias y ejecuta el motor de cálculo.
    Redirige de vuelta al workbench del proyecto.
    """
    def post(self, request, pk):
        proyecto = get_object_or_404(Proyecto, pk=pk)

        # Soporta tanto JSON body como form POST con campos parametros[variable]
        try:
            body = json.loads(request.body)
            sistema_id = body.get("sistema_id")
            subsistema_id = body.get("subsistema_id") or None
            parametros = body.get("parametros", {})
        except (json.JSONDecodeError, ValueError):
            post = request.POST
            sistema_id    = post.get("sistema_id")
            subsistema_id = post.get("subsistema_id") or None
            # Parsear claves tipo "parametros[total_powergrip]" → {"total_powergrip": "2883"}
            parametros = {}
            for key, val in post.items():
                if key.startswith("parametros[") and key.endswith("]") and val != "":
                    var_name = key[len("parametros["):-1]
                    parametros[var_name] = val

        if not sistema_id:
            messages.error(request, "Debe indicar un sistema.")
            return redirect(reverse("ingenieria:despiece_list") + f"?proyecto_pk={pk}")

        try:
            sistema    = Sistema.objects.get(pk=sistema_id)
            subsistema = Subsistema.objects.get(pk=subsistema_id) if subsistema_id else None

            ps, _ = ProyectoSistema.objects.get_or_create(
                proyecto=proyecto,
                sistema=sistema,
                subsistema=subsistema,
            )
            ps.parametros_entrada = parametros
            ps.save(update_fields=["parametros_entrada"])

            # ── Routing por tipo de sistema ───────────────────────────────────
            from apps.common.choices import TipoSistema
            if sistema.tipo_sistema == TipoSistema.CONSUMO:
                # Para sistemas de CONSUMO: redirigir al panel de consumo.
                # El usuario ejecuta el cálculo explícitamente desde allí.
                messages.info(
                    request,
                    f"Sistema de consumo «{sistema.nombre}» agregado. "
                    "Usa el panel de consumo para calcular cantidades.",
                )
                return redirect(reverse("presupuestos:consumo_maestro", args=[ps.pk]))

            from apps.presupuestos.services.despiece_service import DespieceService

            lineas = DespieceService(ps).ejecutar()
            messages.success(request, f"Despiece calculado: {len(lineas)} líneas generadas.")
            registrar_log(
                request,
                accion="CALCULAR_DESPIECE",
                descripcion=(
                    f"Despiece calculado para {proyecto.consecutivo} — {proyecto.nombre}: "
                    f"sistema {sistema.nombre}"
                    + (f" / {subsistema.nombre}" if subsistema else "")
                    + f" · {len(lineas)} líneas generadas"
                ),
                modelo_afectado="Proyecto",
                objeto_id=proyecto.pk,
            )
        except Exception as exc:
            messages.error(request, f"Error al calcular despiece: {exc}")

        return redirect(reverse("ingenieria:despiece_list") + f"?proyecto_pk={pk}")


# ── Despiece — POST clásico: re-ejecutar cálculo de un PS existente ───────────

class DespieceEjecutarView(View):
    """Ejecuta el cálculo del despiece para un ProyectoSistema existente."""
    def post(self, request, pk):
        ps = get_object_or_404(ProyectoSistema, pk=pk)
        try:
            from apps.presupuestos.services.despiece_service import DespieceService

            lineas = DespieceService(ps).ejecutar()
            messages.success(request, f"Despiece ejecutado: {len(lineas)} líneas calculadas.")
            registrar_log(
                request,
                accion="RECALCULAR_DESPIECE",
                descripcion=(
                    f"Re-ejecución despiece — {ps.proyecto.consecutivo}: "
                    f"sistema {ps.sistema.nombre}"
                    + (f" / {ps.subsistema.nombre}" if ps.subsistema_id else "")
                    + f" · {len(lineas)} líneas"
                ),
                modelo_afectado="Proyecto",
                objeto_id=ps.proyecto_id,
            )
        except Exception as exc:
            messages.error(request, f"Error al ejecutar despiece: {exc}")
        return redirect(reverse("ingenieria:despiece_list") + f"?proyecto_pk={ps.proyecto_id}")


# ── Despiece — AJAX: ajuste de cantidad ───────────────────────────────────────

class DespieceLineaAjusteAPIView(View):
    """
    POST /despiece/api/ajuste/<linea_pk>/
    Body JSON: {cantidad_ajustada, motivo_ajuste (opt)}
    Devuelve JSON con la línea actualizada para que el JS actualice la fila.
    """
    def post(self, request, pk):
        linea = get_object_or_404(DespieceLinea, pk=pk)
        try:
            body = json.loads(request.body)
            valor = body.get("cantidad_ajustada")
            motivo = body.get("motivo_ajuste", "")

            if valor is None:
                return JsonResponse({"error": "cantidad_ajustada requerida."}, status=400)

            from decimal import Decimal, InvalidOperation
            try:
                linea.cantidad_ajustada = Decimal(str(valor))
            except InvalidOperation:
                return JsonResponse({"error": "Valor numérico inválido."}, status=400)

            linea.motivo_ajuste = motivo or None
            linea.save(update_fields=["cantidad_ajustada", "motivo_ajuste", "updated_at"])

            return JsonResponse({
                "ok": True,
                "linea_pk": linea.pk,
                "cantidad_calculada": str(linea.cantidad_calculada),
                "cantidad_ajustada": str(linea.cantidad_ajustada),
                "cantidad_final": str(linea.cantidad_final),
                "motivo_ajuste": linea.motivo_ajuste or "",
            })
        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=500)


class DespieceLineaAjusteView(UpdateView):
    """Ajuste manual de cantidad en una línea de despiece (formulario clásico)."""
    model = DespieceLinea
    form_class = DespieceLineaAjusteForm
    template_name = "presupuestos/despiece_ajuste_form.html"

    def get_success_url(self):
        return reverse("ingenieria:despiece_list") + f"?proyecto_pk={self.object.proyecto_id}"


class AsignarProductoLineaAPIView(View):
    """
    POST /presupuestos/despiece/api/asignar-producto/<linea_pk>/
    Body JSON: {"producto_id": int}
    Asigna un producto concreto a una línea de despiece y captura el precio.
    """
    def post(self, request, pk):
        linea = get_object_or_404(DespieceLinea, pk=pk)
        try:
            data = json.loads(request.body)
            producto_id = int(data.get("producto_id", 0))
        except (json.JSONDecodeError, ValueError, TypeError):
            return JsonResponse({"error": "Datos inválidos."}, status=400)

        if not producto_id:
            return JsonResponse({"error": "Debe indicar un producto."}, status=400)

        from apps.catalogos.models import Producto
        producto = get_object_or_404(Producto, pk=producto_id, activo=True)

        linea.producto = producto
        linea.categoria_producto = producto.categoria
        linea.save(update_fields=["producto", "categoria_producto"])
        linea.capturar_precio()
        linea.refresh_from_db()

        moneda = producto.moneda or "COP"
        fecha_act = (
            producto.fecha_actualizacion_precio.strftime("%d/%m/%Y")
            if producto.fecha_actualizacion_precio else "—"
        )
        return JsonResponse({
            "ok": True,
            "producto_nombre": producto.nombre,
            "producto_codigo": producto.codigo,
            "moneda": moneda,
            "precio_snapshot": float(linea.precio_snapshot or 0),
            "fecha_actualizacion": fecha_act,
        })


class ProductosPorCategoriaLineaAPIView(View):
    """
    GET /presupuestos/despiece/api/productos-linea/<linea_pk>/
    Devuelve productos activos de la misma categoría que la línea.
    """
    def get(self, request, pk):
        linea = get_object_or_404(DespieceLinea, pk=pk)
        cat = linea.categoria_producto or (linea.producto.categoria if linea.producto else None)
        if not cat:
            return JsonResponse({"productos": [], "categoria": ""})
        from apps.catalogos.models import Producto
        productos = list(
            Producto.objects.filter(categoria=cat, activo=True)
            .order_by("nombre")
            .values("pk", "nombre", "codigo", "precio_actual", "moneda", "unidades_por_presentacion")
        )
        return JsonResponse({"productos": productos, "categoria": cat.nombre})


# ── Configuración APU ─────────────────────────────────────────────────────────

class ConfiguracionAPUListView(ListView):
    model = ConfiguracionAPU
    template_name = "presupuestos/configapu_list.html"
    context_object_name = "configs"
    ordering = ["-activa", "nombre"]


class ConfiguracionAPUCreateView(CreateView):
    model = ConfiguracionAPU
    form_class = ConfiguracionAPUForm
    template_name = "presupuestos/configapu_form.html"
    success_url = reverse_lazy("presupuestos:configapu_list")


class ConfiguracionAPUUpdateView(UpdateView):
    model = ConfiguracionAPU
    form_class = ConfiguracionAPUForm
    template_name = "presupuestos/configapu_form.html"
    success_url = reverse_lazy("presupuestos:configapu_list")


# ── APU ───────────────────────────────────────────────────────────────────────

class APUListView(ListView):
    """Lista todos los APUProyecto que tienen al menos una línea registrada."""
    model = APUProyecto
    template_name = "presupuestos/apu_list.html"
    context_object_name = "apus"

    def get_queryset(self):
        qs = (
            APUProyecto.objects
            .select_related(
                "proyecto_sistema__proyecto__cliente",
                "proyecto_sistema__sistema",
                "proyecto_sistema__subsistema",
                "revisor",
            )
            .annotate(
                total_lineas=Count("lineas"),
                lineas_mat=Count("lineas", filter=Q(lineas__tipo="MATERIALES")),
                lineas_herr=Count("lineas", filter=Q(lineas__tipo="HERRAMIENTAS_EQUIPOS")),
                lineas_transp=Count("lineas", filter=Q(lineas__tipo="TRANSPORTE")),
                lineas_mo=Count("lineas", filter=Q(lineas__tipo="MANO_DE_OBRA")),
                lineas_admin=Count("lineas", filter=Q(lineas__tipo="ADMINISTRACION")),
            )
            .filter(total_lineas__gt=0)
            .order_by("-updated_at")
        )
        if self.request.GET.get("revision") == "pendiente":
            qs = qs.filter(fecha_envio_revision__isnull=False, modalidad_aiu_seleccionada__isnull=True)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["filtro_revision"] = self.request.GET.get("revision", "")
        return ctx


def _build_categorias_context(apu) -> list:
    """
    Construye la estructura de categorías para la vista de detalle del APU.

    Para cada TipoAPU devuelve un dict con:
      - tipo, label, icon, color, tab_id
      - subtotal_costo, subtotal_valor, count
      - grupos: lista de grupos (uno por CategoriaItemAPU o "flat" para MATERIALES)
        Cada grupo contiene:
          - descripcion: nombre del grupo
          - linea_resumen: APULinea resumen (o None para MATERIALES)
          - lineas_detalle: lista de APULineas de detalle
          - subtotal_costo, subtotal_valor

    Patrón de identificación:
      - MATERIALES: todas las líneas son detalle (despiece_linea set o item_catalogo=None sin resumen).
      - No-MATERIALES: líneas resumen = item_catalogo__isnull=True AND despiece_linea__isnull=True.
                       líneas detalle = item_catalogo__isnull=False.
    """
    from apps.common.choices import TipoAPU
    from decimal import Decimal

    TIPO_INFO = [
        {"tipo": TipoAPU.MATERIALES,          "label": "Materiales",     "icon": "bi-box-seam",  "color": "#1470e6", "tab_id": "tab-materiales"},
        {"tipo": TipoAPU.HERRAMIENTAS_EQUIPOS, "label": "Herramientas",   "icon": "bi-tools",     "color": "#e07d10", "tab_id": "tab-herramientas"},
        {"tipo": TipoAPU.TRANSPORTE,           "label": "Transporte",     "icon": "bi-truck",     "color": "#7048d0", "tab_id": "tab-transporte"},
        {"tipo": TipoAPU.MANO_DE_OBRA,         "label": "Mano de Obra",   "icon": "bi-people",    "color": "#17a85e", "tab_id": "tab-manoobra"},
        {"tipo": TipoAPU.ADMINISTRACION,       "label": "Administración", "icon": "bi-briefcase", "color": "#64748b", "tab_id": "tab-admin"},
    ]

    # Cargar todas las líneas del APU de una sola vez
    all_lineas = list(
        apu.lineas.select_related(
            "item_catalogo__categoria", "despiece_linea__producto"
        ).order_by("descripcion")
    )

    categorias = []
    for info in TIPO_INFO:
        tipo = info["tipo"]
        lineas_tipo = [l for l in all_lineas if l.tipo == tipo]

        if tipo == TipoAPU.MATERIALES:
            # Todos los materiales se muestran en tabla plana
            grupos = []
            if lineas_tipo:
                subtotal_c = sum(l.costo_total for l in lineas_tipo)
                subtotal_v = sum(l.valor_total  for l in lineas_tipo)
                grupos = [{
                    "descripcion": "Materiales",
                    "linea_resumen": None,
                    "lineas_detalle": lineas_tipo,
                    "subtotal_costo": subtotal_c,
                    "subtotal_valor": subtotal_v,
                }]
            subtotal_costo = sum(l.costo_total for l in lineas_tipo)
            subtotal_valor = sum(l.valor_total  for l in lineas_tipo)

        else:
            # Líneas resumen (item_catalogo=None, despiece_linea=None)
            resumen_lines = [l for l in lineas_tipo if not l.item_catalogo_id and not l.despiece_linea_id]
            # Líneas detalle (item_catalogo set, solo referencia)
            detalle_lines = [l for l in lineas_tipo if l.item_catalogo_id]

            grupos = []
            if resumen_lines:
                # Agrupar líneas detalle por nombre de categoría (coincide con descripcion de la resumen)
                for lr in resumen_lines:
                    # Las líneas detalle de esta resumen comparten el nombre de categoría
                    detalle_para_lr = [
                        l for l in detalle_lines
                        if l.item_catalogo
                        and l.item_catalogo.categoria
                        and l.item_catalogo.categoria.nombre == lr.descripcion.replace(" — Dotación", "").replace(" — Personal", "").strip()
                    ]
                    grupos.append({
                        "descripcion": lr.descripcion,
                        "linea_resumen": lr,
                        "lineas_detalle": detalle_para_lr,
                        "subtotal_costo": lr.costo_total,
                        "subtotal_valor": lr.valor_total,
                    })
            elif lineas_tipo:
                # Formato antiguo: sin líneas resumen → mostrar todas en tabla plana
                subtotal_c = sum(l.costo_total for l in lineas_tipo)
                subtotal_v = sum(l.valor_total  for l in lineas_tipo)
                grupos = [{
                    "descripcion": info["label"],
                    "linea_resumen": None,
                    "lineas_detalle": lineas_tipo,
                    "subtotal_costo": subtotal_c,
                    "subtotal_valor": subtotal_v,
                }]

            subtotal_costo = sum(g["subtotal_costo"] for g in grupos)
            subtotal_valor = sum(g["subtotal_valor"] for g in grupos)

        categorias.append({
            **info,
            "grupos": grupos,
            "subtotal_costo": subtotal_costo,
            "subtotal_valor": subtotal_valor,
            "count": len(lineas_tipo),
        })

    return categorias


class APUProyectoDetailView(DetailView):
    model = APUProyecto
    template_name = "presupuestos/apu_detail.html"
    context_object_name = "apu"

    def get_context_data(self, **kwargs):
        from django.db.models import Sum as _Sum

        ctx = super().get_context_data(**kwargs)

        # Contexto estructurado por categoría (Session 4)
        ctx["categorias_apu"] = _build_categorias_context(self.object)

        # Mantener lineas y subtotales para compatibilidad con otras partes del template
        ctx["lineas"] = self.object.lineas.select_related(
            "item_catalogo__categoria"
        ).order_by("tipo", "item_catalogo__categoria__nombre", "descripcion")

        # Subtotales de costo_total, valor_total y costo_por_dia por tipo
        valor_subs: dict = {}
        costo_subs: dict = {}
        dia_subs: dict = {}
        for agg in self.object.lineas.values("tipo").annotate(
            valor=_Sum("valor_total"),
            costo=_Sum("costo_total"),
            dia=_Sum("costo_por_dia"),
        ):
            valor_subs[agg["tipo"]] = float(agg["valor"] or 0)
            costo_subs[agg["tipo"]] = float(agg["costo"] or 0)
            dia_subs[agg["tipo"]] = float(agg["dia"] or 0)
        ctx["valor_subtotales"] = valor_subs
        ctx["costo_subtotales"] = costo_subs
        ctx["dia_subtotales"] = dia_subs
        ctx["total_dia"] = sum(dia_subs.values())

        # Datos del proyecto vinculado
        proyecto = None
        if self.object.proyecto_sistema_id:
            proyecto = getattr(self.object.proyecto_sistema, "proyecto", None)
        ctx["proyecto_num_personas"] = getattr(proyecto, "num_personas", None)

        # Catálogo para los modales de selección
        ctx["presets"] = (
            CuadrillaPreset.objects
            .filter(activo=True)
            .prefetch_related("items__item")
        )
        ctx["items_mo"] = (
            ItemCatalogoAPU.objects
            .filter(activo=True, categoria__tipo_apu="MANO_DE_OBRA")
            .select_related("categoria").order_by("categoria__nombre", "nombre")
        )
        ctx["items_herr"] = (
            ItemCatalogoAPU.objects
            .filter(activo=True, categoria__tipo_apu="HERRAMIENTAS_EQUIPOS")
            .select_related("categoria").order_by("categoria__nombre", "nombre")
        )
        ctx["items_transp"] = (
            ItemCatalogoAPU.objects
            .filter(activo=True, categoria__tipo_apu="TRANSPORTE")
            .select_related("categoria").order_by("categoria__nombre", "nombre")
        )
        ctx["items_admin"] = (
            ItemCatalogoAPU.objects
            .filter(activo=True, categoria__tipo_apu="ADMINISTRACION")
            .select_related("categoria").order_by("categoria__nombre", "nombre")
        )
        # PKs de ítems ya usados en este APU (para pre-marcar checkboxes)
        ctx["lineas_item_ids"] = set(
            self.object.lineas
            .exclude(item_catalogo=None)
            .values_list("item_catalogo_id", flat=True)
        )
        # Modalidades AIU del proyecto
        ctx["modalidades_aiu"] = self.object.calcular_modalidades_aiu()

        # Revisores disponibles (usuarios del sistema excepto el actual)
        from apps.configuracion.models import ConfiguracionSistema
        ctx["revisores"] = ConfiguracionSistema.objects.filter(activo=True).order_by("nombre_completo")
        ctx["ya_en_revision"] = bool(self.object.fecha_envio_revision)
        return ctx


class APUProyectoUpdateView(UpdateView):
    model = APUProyecto
    form_class = APUProyectoForm
    template_name = "presupuestos/apu_form.html"

    def get_success_url(self):
        return reverse("presupuestos:apu_detail", args=[self.object.pk])

    def form_valid(self, form):
        # Snapshot config fields before save to detect changes
        old = APUProyecto.objects.get(pk=self.object.pk)
        old_aiu  = old.aiu_contratista_pct
        old_mg   = old.margen_ganancia_pct
        old_dias = old.dias_duracion
        old_fv   = old.factor_venta_pct

        response = super().form_valid(form)

        # If any calc-affecting field changed, regenerate non-MATERIALES lines
        new = self.object
        parametros_cambiaron = (
            new.aiu_contratista_pct != old_aiu
            or new.margen_ganancia_pct != old_mg
            or new.dias_duracion != old_dias
            or new.factor_venta_pct != old_fv
        )
        if parametros_cambiaron:
            try:
                from apps.presupuestos.services.apu_service import APUService
                from apps.presupuestos.models import ItemCatalogoAPU

                svc = APUService.for_apu(new)
                tipos = [
                    TipoAPU.HERRAMIENTAS_EQUIPOS,
                    TipoAPU.MANO_DE_OBRA,
                    TipoAPU.TRANSPORTE,
                    TipoAPU.ADMINISTRACION,
                ]
                regenerado = False
                for tipo in tipos:
                    items = list(ItemCatalogoAPU.objects.filter(
                        activo=True, categoria__tipo_apu=tipo
                    ))
                    if items:
                        svc._generar_categoria_desde_catalogo(
                            tipo,
                            [{"item_id": i.pk, "cantidad": 1} for i in items],
                        )
                        regenerado = True
                if regenerado:
                    new.recalcular()
                    messages.success(
                        self.request,
                        "Parámetros guardados y líneas recalculadas con los nuevos valores.",
                    )
            except Exception as exc:
                messages.warning(
                    self.request,
                    f"Parámetros guardados, pero error al recalcular líneas: {exc}",
                )

        # Registrar log de actualización de parámetros APU
        try:
            proyecto_id = new.proyecto_sistema.proyecto_id if new.proyecto_sistema_id else None
            proyecto_nombre = (
                f"{new.proyecto_sistema.proyecto.consecutivo} — {new.proyecto_sistema.proyecto.nombre}"
                if new.proyecto_sistema_id else "—"
            )
            registrar_log(
                self.request,
                accion="ACTUALIZAR_APU",
                descripcion=(
                    f"Parámetros APU actualizados — {proyecto_nombre}: "
                    f"AIU {new.aiu_contratista_pct}%, margen {new.margen_ganancia_pct}%, "
                    f"días {new.dias_duracion}, factor venta {new.factor_venta_pct}%"
                    + (" · líneas recalculadas" if parametros_cambiaron else "")
                ),
                modelo_afectado="Proyecto",
                objeto_id=proyecto_id,
            )
        except Exception:
            pass

        return response


class APUGenerarView(View):
    """Genera el APU para un ProyectoSistema dado."""
    def post(self, request, pk):
        ps = get_object_or_404(ProyectoSistema, pk=pk)
        try:
            from apps.presupuestos.services.apu_service import APUService
            apu = APUService.generar(ps)
            messages.success(request, "APU generado correctamente.")
            registrar_log(
                request,
                accion="GENERAR_APU",
                descripcion=(
                    f"APU generado para {ps.proyecto.consecutivo} — {ps.proyecto.nombre}: "
                    f"sistema {ps.sistema.nombre}"
                    + (f" / {ps.subsistema.nombre}" if ps.subsistema_id else "")
                ),
                modelo_afectado="Proyecto",
                objeto_id=ps.proyecto_id,
            )
            return redirect(reverse("presupuestos:apu_detail", args=[apu.pk]))
        except Exception as exc:
            messages.error(request, f"Error al generar APU: {exc}")
            return redirect(reverse("ingenieria:despiece_list") + f"?proyecto_pk={ps.proyecto_id}")


class APUGenerarDesdeDespiece(View):
    """
    POST: genera o actualiza el APU a partir de un DespieceMaestro asociado a proyecto.

    Flujo:
      1. Valida que el despiece esté guardado, tenga proyecto y tenga líneas.
      2. Obtiene o crea el ProyectoSistema (proyecto × sistema × subsistema).
      3. Sincroniza variables_entrada del DespieceMaestro → parametros_entrada del PS.
      4. Sincroniza DespieceMaestroLinea → DespieceLinea del PS (upsert por componente).
      5. Llama a APUService.generar(ps) — internamente hace get_or_create del APU.
      6. Redirige a apu_detail con mensaje de éxito (creado vs. actualizado).
    """
    def post(self, request, pk):
        from apps.ingenieria.models import DespieceMaestro
        from django.db import transaction as db_transaction

        dm = get_object_or_404(DespieceMaestro, pk=pk)

        # ── Validaciones ──────────────────────────────────────────────────────
        if not dm.esta_guardado:
            messages.error(request, "El despiece debe estar guardado antes de generar el APU.")
            return redirect("ingenieria:despiece_maestro", pk=dm.pk)
        if not dm.proyecto_id:
            messages.error(request, "Solo los despieces asociados a un proyecto pueden generar APU.")
            return redirect("ingenieria:despiece_maestro", pk=dm.pk)
        lineas_dm = list(dm.lineas.select_related("producto", "producto__unidad"))
        if not lineas_dm:
            messages.error(request, "El despiece no tiene líneas calculadas. Calcula y guarda primero.")
            return redirect("ingenieria:despiece_maestro", pk=dm.pk)

        try:
            with db_transaction.atomic():
                # ── 1. Obtener o crear ProyectoSistema ────────────────────────
                ps, _ = ProyectoSistema.objects.get_or_create(
                    proyecto=dm.proyecto,
                    sistema=dm.subsistema.sistema,
                    subsistema=dm.subsistema,
                )

                # ── 2. Sincronizar variables_entrada → parametros_entrada ──────
                # Esto permite que APUService._get_total_unidades() calcule bien
                # el denominador (ej: total_powergrip) usando los valores reales
                # que el usuario ingresó en el DespieceMaestro.
                if dm.variables_entrada:
                    ps.parametros_entrada = {
                        **(ps.parametros_entrada or {}),
                        **dm.variables_entrada,
                    }
                    ps.save(update_fields=["parametros_entrada"])

                # ── 3. Consolidar TODOS los despieces guardados del proyecto ──
                # Tarea 9: recoge líneas de TODOS los DespieceMaestro guardados
                # del mismo proyecto (no sólo el que disparó el POST) y suma
                # cantidades cuando el mismo producto aparece en varios despieces.
                todos_dm = DespieceMaestro.objects.filter(
                    proyecto=dm.proyecto,
                    estado=DespieceMaestro.GUARDADO,
                ).prefetch_related("lineas__producto__unidad", "consolidaciones__producto__unidad")

                # Dict: clave → {datos acumulados}
                # Para líneas individuales (sin consolidar): clave = componente_codigo
                # Para líneas consolidadas: clave = "CONS_{producto_id}" para agrupar
                # mismo producto en distintos despieces.
                consolidado: dict = {}
                for dm_iter in todos_dm:
                    # PKs de líneas incluidas en alguna consolidación → se saltan abajo
                    pks_consolidados: set = set()
                    for c in dm_iter.consolidaciones.all():
                        pks_consolidados.update(c.lineas_ids or [])

                    # ── Líneas técnicas individuales (no consolidadas) ──────────
                    for dml in dm_iter.lineas.select_related("producto", "producto__unidad"):
                        if dml.pk in pks_consolidados:
                            continue  # manejada por consolidación
                        if dml.producto_id is None:
                            continue
                        clave = dml.componente_codigo
                        if clave in consolidado:
                            consolidado[clave]["cantidad"] += (dml.cantidad_calculada or 0)
                        else:
                            precio_snapshot = (
                                dml.producto.precio_unitario_real
                                if dml.producto_id and dml.producto
                                else dml.precio_unitario
                            )
                            consolidado[clave] = {
                                "cantidad": dml.cantidad_calculada or 0,
                                "precio_snapshot": precio_snapshot,
                                "producto": dml.producto,
                            }

                    # ── Líneas consolidadas ────────────────────────────────────
                    for c in dm_iter.consolidaciones.select_related("producto", "producto__unidad"):
                        if c.producto_id is None:
                            continue
                        # Mismo producto en varios despieces → suma bajo la misma clave
                        clave = f"CONS_{c.producto_id}"
                        precio_snapshot = (
                            c.precio_unitario
                            or (c.producto.precio_unitario_real if c.producto else None)
                        )
                        if clave in consolidado:
                            consolidado[clave]["cantidad"] += (c.cantidad_total or 0)
                        else:
                            consolidado[clave] = {
                                "cantidad": c.cantidad_total or 0,
                                "precio_snapshot": precio_snapshot,
                                "producto": c.producto,
                            }

                # Sync consolidado → DespieceLinea del ProyectoSistema
                for codigo, datos in consolidado.items():
                    DespieceLinea.objects.update_or_create(
                        proyecto_sistema=ps,
                        componente_codigo=codigo,
                        defaults={
                            "proyecto": dm.proyecto,
                            "cantidad_calculada": datos["cantidad"],
                            "precio_snapshot": datos["precio_snapshot"],
                            "producto": datos["producto"],
                        },
                    )

                # Eliminar líneas obsoletas (productos que ya no están en ningún despiece)
                DespieceLinea.objects.filter(
                    proyecto_sistema=ps
                ).exclude(componente_codigo__in=consolidado.keys()).delete()

                # ── 4. Detectar creación vs. actualización ────────────────────
                apu_existia = APUProyecto.objects.filter(proyecto_sistema=ps).exists()

                # ── 5. Generar APU ────────────────────────────────────────────
                from apps.presupuestos.services.apu_service import APUService
                apu = APUService.generar(ps)

        except Exception as exc:
            messages.error(request, f"Error al generar APU: {exc}")
            return redirect("ingenieria:despiece_maestro", pk=dm.pk)

        if apu_existia:
            messages.success(request, "APU actualizado correctamente.")
        else:
            messages.success(request, "APU generado correctamente.")

        registrar_log(
            request,
            accion="GENERAR_APU",
            descripcion=(
                f"APU {'actualizado' if apu_existia else 'generado'} desde despiece maestro "
                f"#{dm.pk} — {ps.proyecto.consecutivo} / {ps.sistema.nombre}"
                + (f" / {ps.subsistema.nombre}" if ps.subsistema_id else "")
            ),
            modelo_afectado="Proyecto",
            objeto_id=ps.proyecto_id,
        )
        return redirect(reverse("presupuestos:apu_detail", args=[apu.pk]))


# Stubs de compatibilidad para imports históricos
class PowerGripWizardView(View):
    """Redirige al calculador de sistemas."""
    def get(self, request, pk):
        return redirect(reverse("ingenieria:despiece_list") + f"?proyecto_pk={pk}")


class CalcularPowerGripView(View):
    """Redirige al calculador de sistemas."""
    def post(self, request, pk):
        return redirect(reverse("ingenieria:despiece_list") + f"?proyecto_pk={pk}")


# ── API: productos por categoría (para el wizard) ──────────────────────────

class ProductosPorCategoriaAPIView(View):
    """
    GET /presupuestos/api/productos/<categoria_slug>/
    Devuelve productos activos de esa categoría (por nombre).
    """
    def get(self, request, slug):
        from apps.catalogos.models import Producto
        productos = list(
            Producto.objects.filter(
                categoria__nombre__iexact=slug, activo=True
            ).values("pk", "nombre", "codigo")
        )
        return JsonResponse({"productos": productos, "categoria": slug})


# ── API: definición de subsistema (variables + categorías) ─────────────────

class SubsistemaDefAPIView(View):
    """
    GET /presupuestos/api/subsistema-def/<subsistema_pk>/
    Devuelve las variables y categorías requeridas para el subsistema.
    Prioridad: variables DB > registry Python.
    Usado por el despiece modal cuando el usuario selecciona un subsistema.
    """
    def get(self, request, pk):
        sub = get_object_or_404(Subsistema, pk=pk)
        VARS_PROYECTO = {"area_m2", "perimetro_ml"}

        # ── Prioridad 1: variables definidas en DB ────────────────────────────
        from apps.ingenieria.models import VariableSubsistema, ComponenteSubsistema
        vars_db = list(
            VariableSubsistema.objects.filter(subsistema=sub).order_by("orden")
        )
        comps_db = list(
            ComponenteSubsistema.objects.filter(subsistema=sub)
            .select_related("categoria").order_by("orden")
        )
        if vars_db or comps_db:
            return JsonResponse({
                "subsistema_pk":  sub.pk,
                "subsistema_cod": sub.codigo,
                "variables": [
                    {
                        "variable": v.variable,
                        "label": v.label,
                        "unidad": v.unidad,
                        "default": float(v.valor_default),
                        "opciones": [],
                        "descripcion": "",
                    }
                    for v in vars_db
                    if v.variable not in VARS_PROYECTO
                ],
                "categorias": [
                    {
                        "codigo": c.codigo,
                        "nombre": c.nombre,
                        "categoria_slug": c.categoria.nombre if c.categoria else "",
                    }
                    for c in comps_db
                ],
            })

        # ── Prioridad 2: registry Python ──────────────────────────────────────
        from apps.ingenieria.system_defs.registry import get_subsistema_def
        sub_def = get_subsistema_def(sub.sistema.codigo, sub.codigo)
        if not sub_def:
            return JsonResponse({
                "subsistema_pk": sub.pk,
                "subsistema_cod": sub.codigo,
                "variables": [],
                "categorias": [],
            })

        return JsonResponse({
            "subsistema_pk":  sub.pk,
            "subsistema_cod": sub.codigo,
            "variables": [
                {
                    "variable": v.variable,
                    "label": v.label,
                    "unidad": v.unidad,
                    "default": v.default,
                    "opciones": v.opciones,
                    "descripcion": v.descripcion,
                }
                for v in sub_def.variables
                if v.variable not in VARS_PROYECTO
            ],
            "categorias": [
                {"codigo": c.codigo, "nombre": c.nombre, "categoria_slug": c.categoria_slug}
                for c in sub_def.componentes
            ],
        })


# ── APU Mano de Obra ────────────────────────────────────────────────────────

class APUManoObraView(View):
    """
    POST /presupuestos/apu/<pk>/mano-obra/

    Registra mano de obra desde catálogo.
    Acepta:
      - preset_id: carga todos los ítems del preset seleccionado
      - item_id[] + cantidad[]: selección manual ítem a ítem
    Borra líneas MANO_DE_OBRA previas antes de guardar (reemplaza).
    """
    def post(self, request, pk):
        apu = get_object_or_404(APUProyecto, pk=pk)
        try:
            from apps.presupuestos.services.apu_service import APUService

            preset_id = request.POST.get("preset_id", "").strip()
            if preset_id:
                preset = get_object_or_404(
                    CuadrillaPreset.objects.prefetch_related("items__item"),
                    pk=preset_id, activo=True,
                )
                items_data = [
                    {"item_id": pi.item_id, "cantidad": pi.cantidad}
                    for pi in preset.items.all()
                ]
            else:
                item_ids  = request.POST.getlist("item_id[]")
                cantidades = request.POST.getlist("cantidad[]")
                items_data = [
                    {"item_id": int(iid), "cantidad": max(int(cant or 1), 1)}
                    for iid, cant in zip(item_ids, cantidades) if iid
                ]

            if not items_data:
                messages.warning(request, "Seleccione al menos un ítem de mano de obra.")
                return redirect(reverse("presupuestos:apu_detail", args=[apu.pk]))

            apu.lineas.filter(tipo="MANO_DE_OBRA").delete()
            svc = APUService.for_apu(apu)
            svc.generar_mano_obra_desde_catalogo(items_data)
            svc.finalizar()
            messages.success(request, f"Mano de obra registrada: {len(items_data)} cargo(s).")
        except Exception as exc:
            messages.error(request, f"Error al registrar mano de obra: {exc}")
            logger.exception("[APUManoObraView] Error APU %s", pk)

        return redirect(reverse("presupuestos:apu_detail", args=[apu.pk]))


class APUHerramientasView(View):
    """
    POST /presupuestos/apu/<pk>/herramientas/

    Registra herramientas/equipos desde catálogo.
    Acepta item_id[] + cantidad[].
    Borra líneas HERRAMIENTAS_EQUIPOS previas antes de guardar (reemplaza).
    """
    def post(self, request, pk):
        apu = get_object_or_404(APUProyecto, pk=pk)
        try:
            from apps.presupuestos.services.apu_service import APUService

            item_ids   = request.POST.getlist("item_id[]")
            cantidades = request.POST.getlist("cantidad[]")
            items_data = [
                {"item_id": int(iid), "cantidad": max(int(cant or 1), 1)}
                for iid, cant in zip(item_ids, cantidades) if iid
            ]

            if not items_data:
                messages.warning(request, "No se seleccionaron herramientas del catálogo.")
                return redirect(reverse("presupuestos:apu_detail", args=[apu.pk]))

            apu.lineas.filter(tipo="HERRAMIENTAS_EQUIPOS").delete()
            svc = APUService.for_apu(apu)
            svc.generar_herramientas_desde_catalogo(items_data)
            svc.finalizar()
            messages.success(request, f"{len(items_data)} herramienta(s) registrada(s).")
        except Exception as exc:
            messages.error(request, f"Error al registrar herramientas: {exc}")
            logger.exception("[APUHerramientasView] Error APU %s", pk)

        return redirect(reverse("presupuestos:apu_detail", args=[apu.pk]))


class APUTransporteView(View):
    """
    POST /presupuestos/apu/<pk>/transporte/

    Registra ítems de transporte del APU (retiro, envío, flete, etc.).
    El form envía múltiples filas: descripcion[] y precio_total[].
    Borra las líneas TRANSPORTE previas antes de crear las nuevas (reemplaza).
    """
    def post(self, request, pk):
        apu = get_object_or_404(APUProyecto, pk=pk)
        try:
            descripciones   = request.POST.getlist("descripcion[]")
            precios_totales = request.POST.getlist("precio_total[]")

            items = []
            for desc, precio_str in zip(descripciones, precios_totales):
                desc = desc.strip()
                if not desc or not precio_str:
                    continue
                try:
                    precio = float(precio_str)
                    if precio > 0:
                        items.append({"descripcion": desc, "precio_total": precio})
                except (ValueError, TypeError):
                    pass

            if not items:
                messages.warning(request, "No se ingresaron ítems de transporte válidos.")
                return redirect(reverse("presupuestos:apu_detail", args=[apu.pk]))

            # Reemplazar líneas previas de transporte
            apu.lineas.filter(tipo="TRANSPORTE").delete()

            from apps.presupuestos.services.apu_service import APUService
            svc = APUService.for_apu(apu)
            svc.generar_transporte_items(items)
            svc.finalizar()
            messages.success(request, f"{len(items)} ítem(s) de transporte registrados.")
        except Exception as exc:
            messages.error(request, f"Error al registrar transporte: {exc}")
            logger.exception("[APUTransporteView] Error APU %s", pk)

        return redirect(reverse("presupuestos:apu_detail", args=[apu.pk]))


class APULineaUpdateView(View):
    """
    POST /presupuestos/apu/linea/<pk>/editar/

    Actualiza rendimiento y precio_referencia de una APULinea editable,
    recalcula la línea y los totales del APU padre.
    Solo acepta líneas marcadas como editable=True.
    """
    def post(self, request, pk):
        from apps.presupuestos.models import APULinea
        from decimal import Decimal
        linea = get_object_or_404(APULinea, pk=pk, editable=True)
        try:
            rend_str   = request.POST.get("rendimiento", "").strip()
            precio_str = request.POST.get("precio_referencia", "").strip()

            if rend_str:
                linea.rendimiento = Decimal(str(float(rend_str)))
            if precio_str:
                linea.precio_referencia = Decimal(str(float(precio_str)))

            linea.save(update_fields=["rendimiento", "precio_referencia", "updated_at"])
            linea.calcular()
            linea.apu.recalcular()
            messages.success(request, f"Línea «{linea.descripcion}» actualizada.")
        except Exception as exc:
            messages.error(request, f"Error al actualizar línea: {exc}")
            logger.exception("[APULineaUpdateView] Error línea %s", pk)

        return redirect(reverse("presupuestos:apu_detail", args=[linea.apu.pk]))


class APULineaDeleteView(View):
    """
    POST /presupuestos/apu/linea/<pk>/eliminar/

    Elimina una APULinea individual de tipo no-MATERIALES.
    El signal post_delete dispara apu.recalcular() automáticamente.
    """
    def post(self, request, pk):
        from apps.presupuestos.models import APULinea
        linea = get_object_or_404(APULinea, pk=pk)
        if linea.tipo == "MATERIALES":
            messages.error(request, "Las líneas de materiales se regeneran desde el despiece.")
            return redirect(reverse("presupuestos:apu_detail", args=[linea.apu_id]))
        apu_pk = linea.apu_id
        desc = linea.descripcion
        linea.delete()
        messages.success(request, f"Línea «{desc}» eliminada.")
        return redirect(reverse("presupuestos:apu_detail", args=[apu_pk]))


class APUAdminView(View):
    """
    POST /presupuestos/apu/<pk>/administrativo/

    Acepta ítems del catálogo como descripcion[] + precio_total[].
    Reemplaza todas las líneas ADMINISTRACION previas.
    """
    def post(self, request, pk):
        apu = get_object_or_404(APUProyecto, pk=pk)
        try:
            from apps.presupuestos.services.apu_service import APUService

            descripciones   = request.POST.getlist("descripcion[]")
            precios_totales = request.POST.getlist("precio_total[]")

            items = []
            for desc, precio_str in zip(descripciones, precios_totales):
                desc = (desc or "").strip()
                if not desc or not precio_str:
                    continue
                try:
                    precio = float(precio_str)
                    if precio >= 0:
                        items.append({"descripcion": desc, "precio_total": precio})
                except (ValueError, TypeError):
                    pass

            if not items:
                messages.warning(request, "No se ingresaron ítems de administración válidos.")
                return redirect(reverse("presupuestos:apu_detail", args=[apu.pk]))

            apu.lineas.filter(tipo="ADMINISTRACION").delete()
            svc = APUService.for_apu(apu)
            for item in items:
                svc.generar_administracion_item(item["descripcion"], item["precio_total"])
            svc.finalizar()
            messages.success(request, f"{len(items)} ítem(s) de administración registrados.")
        except Exception as exc:
            messages.error(request, f"Error al registrar administrativo: {exc}")
            logger.exception("[APUAdminView] Error APU %s", pk)

        return redirect(reverse("presupuestos:apu_detail", args=[apu.pk]))


# ══════════════════════════════════════════════════════════════════════════════
# CATÁLOGO APU — Vista principal + CRUD
# ══════════════════════════════════════════════════════════════════════════════

class CatalogoAPUView(ListView):
    """
    Página principal del catálogo APU.
    Muestra las CategoriaItemAPU agrupadas por TipoAPU,
    cada una con sus ítems. Funciona como la vista de catalogos.
    """
    model = CategoriaItemAPU
    template_name = "presupuestos/catalogo_apu.html"
    context_object_name = "categorias"

    def get_queryset(self):
        return (
            CategoriaItemAPU.objects
            .prefetch_related("items")
            .order_by("tipo_apu", "orden", "nombre")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from collections import defaultdict
        grupos = defaultdict(list)
        for cat in ctx["categorias"]:
            grupos[cat.tipo_apu].append(cat)
        orden_tipos = [
            TipoAPU.MANO_DE_OBRA,
            TipoAPU.HERRAMIENTAS_EQUIPOS,
            TipoAPU.TRANSPORTE,
            TipoAPU.ADMINISTRACION,
            TipoAPU.MATERIALES,
        ]
        ctx["grupos"] = [
            {
                "tipo": tipo,
                "label": dict(TipoAPU.choices)[tipo],
                "categorias": grupos.get(tipo, []),
            }
            for tipo in orden_tipos
            if tipo in grupos
        ]
        ctx["presets"] = (
            CuadrillaPreset.objects
            .filter(activo=True)
            .prefetch_related("items__item")
        )
        ctx["tipo_choices"] = TipoAPU.choices
        return ctx


# ── CategoriaItemAPU CRUD ─────────────────────────────────────────────────────

class CategoriaItemAPUCreateView(CreateView):
    model = CategoriaItemAPU
    form_class = CategoriaItemAPUForm
    template_name = "presupuestos/catalogo_apu_categoria_form.html"
    success_url = reverse_lazy("presupuestos:catalogo_apu")


class CategoriaItemAPUUpdateView(UpdateView):
    model = CategoriaItemAPU
    form_class = CategoriaItemAPUForm
    template_name = "presupuestos/catalogo_apu_categoria_form.html"
    success_url = reverse_lazy("presupuestos:catalogo_apu")


class CategoriaItemAPUDeleteView(DeleteView):
    model = CategoriaItemAPU
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("presupuestos:catalogo_apu")


# ── ItemCatalogoAPU CRUD ──────────────────────────────────────────────────────

class ItemCatalogoAPUCreateView(CreateView):
    model = ItemCatalogoAPU
    form_class = ItemCatalogoAPUForm
    template_name = "presupuestos/catalogo_apu_item_form.html"
    success_url = reverse_lazy("presupuestos:catalogo_apu")

    def get_initial(self):
        initial = super().get_initial()
        cat_pk = self.request.GET.get("categoria")
        if cat_pk:
            initial["categoria"] = cat_pk
        return initial


class ItemCatalogoAPUUpdateView(UpdateView):
    model = ItemCatalogoAPU
    form_class = ItemCatalogoAPUForm
    template_name = "presupuestos/catalogo_apu_item_form.html"
    success_url = reverse_lazy("presupuestos:catalogo_apu")


class ItemCatalogoAPUDeleteView(DeleteView):
    model = ItemCatalogoAPU
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("presupuestos:catalogo_apu")


# ── CuadrillaPreset CRUD ──────────────────────────────────────────────────────

class CuadrillaPresetCreateView(CreateView):
    model = CuadrillaPreset
    form_class = CuadrillaPresetForm
    template_name = "presupuestos/cuadrilla_preset_form.html"
    success_url = reverse_lazy("presupuestos:catalogo_apu")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx["formset"] = CuadrillaPresetItemFormSet(self.request.POST)
        else:
            ctx["formset"] = CuadrillaPresetItemFormSet()
        return ctx

    def form_valid(self, form):
        ctx = self.get_context_data()
        formset = ctx["formset"]
        if formset.is_valid():
            self.object = form.save()
            formset.instance = self.object
            formset.save()
            messages.success(self.request, f"Cuadrilla «{self.object.nombre}» creada.")
            return redirect(self.success_url)
        return self.form_invalid(form)


class CuadrillaPresetUpdateView(UpdateView):
    model = CuadrillaPreset
    form_class = CuadrillaPresetForm
    template_name = "presupuestos/cuadrilla_preset_form.html"
    success_url = reverse_lazy("presupuestos:catalogo_apu")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if self.request.POST:
            ctx["formset"] = CuadrillaPresetItemFormSet(self.request.POST, instance=self.object)
        else:
            ctx["formset"] = CuadrillaPresetItemFormSet(instance=self.object)
        return ctx

    def form_valid(self, form):
        ctx = self.get_context_data()
        formset = ctx["formset"]
        if formset.is_valid():
            self.object = form.save()
            formset.instance = self.object
            formset.save()
            messages.success(self.request, f"Cuadrilla «{self.object.nombre}» actualizada.")
            return redirect(self.success_url)
        return self.form_invalid(form)


class CuadrillaPresetDeleteView(DeleteView):
    model = CuadrillaPreset
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("presupuestos:catalogo_apu")


# ── API: ítems del catálogo por tipo APU ─────────────────────────────────────

class ItemsCatalogoAPIView(View):
    """
    GET /presupuestos/api/catalogo/<tipo_apu>/
    Devuelve ítems activos del catálogo filtrados por TipoAPU.
    """
    def get(self, request, tipo_apu):
        items = list(
            ItemCatalogoAPU.objects
            .filter(activo=True, categoria__tipo_apu=tipo_apu)
            .select_related("categoria")
            .values("pk", "nombre", "precio_base", "unidad",
                    "salario_base", "prestaciones", "vida_util_dias",
                    "categoria__nombre")
        )
        return JsonResponse({"items": items, "tipo_apu": tipo_apu})


# ══════════════════════════════════════════════════════════════════════════════
# APU — PDF GENERACIÓN (WeasyPrint)
# ══════════════════════════════════════════════════════════════════════════════

def _render_apu_pdf(apu, template_name: str) -> bytes:
    """Renderiza un template HTML a PDF con WeasyPrint."""
    from weasyprint import HTML, CSS
    from django.templatetags.static import static

    lineas = apu.lineas.order_by("tipo", "descripcion")
    html_str = render_to_string(template_name, {
        "apu": apu,
        "lineas": lineas,
        "fecha_generacion": date.today().strftime("%d/%m/%Y"),
    })
    return HTML(string=html_str, base_url="/").write_pdf()


class APUPDFInternoView(View):
    """
    GET /presupuestos/apu/<pk>/pdf-interno/
    Renderiza una página HTML imprimible con todos los datos internos (costos, márgenes, etc.).
    Solo para uso interno de la empresa.
    """
    def get(self, request, pk):
        apu = get_object_or_404(APUProyecto, pk=pk)
        lineas = apu.lineas.order_by("tipo", "descripcion").select_related(
            "despiece_linea__producto", "item_catalogo",
        )
        html = render_to_string("presupuestos/apu_pdf_interno.html", {
            "apu": apu,
            "lineas": lineas,
            "fecha_generacion": date.today().strftime("%d/%m/%Y"),
            "request": request,
        })
        return HttpResponse(html)


class APUPDFClienteView(View):
    """
    GET /presupuestos/apu/<pk>/pdf-cliente/
    Renderiza cotización comercial simplificada para el cliente.
    Muestra filas consolidadas por sección (Suministro / Instalación / etc.)
    con cantidad, precio unitario de venta y total. Sin desglose interno de costos.
    """
    def get(self, request, pk):
        from decimal import Decimal
        apu = get_object_or_404(APUProyecto, pk=pk)
        ps = apu.proyecto_sistema
        lineas_qs = list(apu.lineas.order_by("tipo", "descripcion").select_related(
            "despiece_linea__producto__unidad", "item_catalogo",
        ))

        # ── Obtener cantidad principal del proyecto ──────────────────────────
        qty_principal = Decimal("1")
        unidad_principal = "und"
        moneda_principal = "COP"
        desc_sistema = apu.nombre or "Sistema"

        if ps:
            params = ps.parametros_entrada or {}
            for key in ("total_powergrip", "cantidad", "area_m2"):
                if key in params:
                    try:
                        qty_principal = Decimal(str(params[key]))
                    except Exception:
                        pass
                    break
            if qty_principal == Decimal("1") and ps.proyecto:
                if ps.proyecto.area_total_m2:
                    qty_principal = Decimal(str(ps.proyecto.area_total_m2))
                    unidad_principal = "m²"
            # Detectar moneda y unidad principal desde primera línea de materiales
            for linea in lineas_qs:
                if linea.tipo == "MATERIALES" and linea.despiece_linea and linea.despiece_linea.producto:
                    prod = linea.despiece_linea.producto
                    moneda_principal = prod.moneda or "COP"
                    if prod.unidad:
                        unidad_principal = str(prod.unidad)
                    break
            desc_sistema = (
                f"{ps.sistema.nombre}"
                + (f" / {ps.subsistema.nombre}" if ps.subsistema else "")
            )

        # ── Construir secciones consolidadas ─────────────────────────────────
        SECCIONES_CONFIG = [
            ("MATERIALES",          "Suministro",                 moneda_principal),
            ("MANO_DE_OBRA",        "Mano de Obra / Instalación", "COP"),
            ("HERRAMIENTAS_EQUIPOS","Herramientas y Equipos",      "COP"),
            ("TRANSPORTE",          "Transporte y Logística",      "COP"),
            ("ADMINISTRACION",      "Administración",              "COP"),
        ]
        secciones = []
        for tipo_key, tipo_label, moneda_sec in SECCIONES_CONFIG:
            lineas_tipo = [l for l in lineas_qs if l.tipo == tipo_key]
            if not lineas_tipo:
                continue
            valor_subtotal = sum(Decimal(str(l.valor_total or 0)) for l in lineas_tipo)
            if valor_subtotal <= 0:
                continue
            # Calcular precio unitario de venta como subtotal / qty_principal
            qty = qty_principal if qty_principal > 0 else Decimal("1")
            valor_unitario = (valor_subtotal / qty).quantize(Decimal("0.1"))
            iva_factor = Decimal(str(apu.iva_pct or 0)) / Decimal("100")
            iva_monto = (valor_subtotal * iva_factor).quantize(Decimal("0.1")) if apu.aplica_iva else Decimal("0")
            total_con_iva = valor_subtotal + iva_monto
            secciones.append({
                "tipo": tipo_key,
                "label": tipo_label,
                "descripcion": f"{tipo_label} — {desc_sistema}",
                "unidad": unidad_principal,
                "cantidad": qty,
                "valor_unitario": valor_unitario,
                "subtotal": valor_subtotal,
                "iva_monto": iva_monto,
                "total_con_iva": total_con_iva,
                "moneda": moneda_sec,
                "aplica_iva": apu.aplica_iva,
                "iva_pct": apu.iva_pct,
            })

        # ── Fichas técnicas ───────────────────────────────────────────────────
        productos_con_ficha = []
        vistos = set()
        for linea in lineas_qs:
            if linea.despiece_linea and linea.despiece_linea.producto:
                prod = linea.despiece_linea.producto
                if prod.pk not in vistos and prod.ficha_tecnica:
                    productos_con_ficha.append(prod)
                    vistos.add(prod.pk)

        html = render_to_string("presupuestos/apu_pdf_cliente.html", {
            "apu": apu,
            "ps": ps,
            "secciones": secciones,
            "productos_con_ficha": productos_con_ficha,
            "fecha_generacion": date.today().strftime("%d/%m/%Y"),
            "request": request,
        })
        return HttpResponse(html, content_type="text/html; charset=utf-8")


class APUEnviarRevisionView(View):
    """
    POST /presupuestos/apu/<pk>/enviar-revision/
    Asigna revisor, marca el APU como enviado a revisión y avanza el estado del proyecto.
    """
    def post(self, request, pk):
        from django.utils import timezone as tz
        from apps.configuracion.models import ConfiguracionSistema
        apu = get_object_or_404(APUProyecto, pk=pk)
        try:
            revisor_pk = request.POST.get("revisor_id", "").strip()
            revisor = None
            if revisor_pk:
                revisor = ConfiguracionSistema.objects.filter(pk=revisor_pk).first()

            update_fields = ["fecha_envio_revision", "updated_at"]
            apu.fecha_envio_revision = tz.now()
            if revisor:
                apu.revisor = revisor
                update_fields.append("revisor")
            apu.save(update_fields=update_fields)

            if apu.proyecto_sistema:
                proyecto = apu.proyecto_sistema.proyecto
                from apps.common.choices import EstadoProyecto, EstadoSolicitud
                proyecto.estado = EstadoProyecto.APU_GENERADO
                proyecto.save(update_fields=["estado"])
                # Avanzar estado de la solicitud si existe
                if proyecto.solicitud_id:
                    proyecto.solicitud.estado = EstadoSolicitud.EN_REVISION
                    proyecto.solicitud.save(update_fields=["estado"])

            revisor_txt = f" Revisor: {revisor}." if revisor else ""
            messages.success(
                request,
                f"APU «{apu.nombre}» enviado a revisión.{revisor_txt}",
            )
        except Exception as exc:
            messages.error(request, f"Error al enviar a revisión: {exc}")
            logger.exception("[APUEnviarRevisionView] Error APU %s", pk)

        return redirect(reverse("presupuestos:apu_detail", args=[pk]))


class APURevisarView(View):
    """
    GET /presupuestos/apu/<pk>/revisar/
    Vista del revisor asignado: muestra el APU y permite seleccionar la modalidad AIU oficial.
    Solo accesible si el APU tiene fecha_envio_revision asignada.
    """
    template_name = "presupuestos/apu_revisar.html"

    def get(self, request, pk):
        apu = get_object_or_404(APUProyecto, pk=pk)
        if not apu.fecha_envio_revision:
            messages.warning(request, "Este APU aún no ha sido enviado a revisión.")
            return redirect(reverse("presupuestos:apu_detail", args=[pk]))
        from apps.configuracion.models import ConfiguracionSistema
        ctx = {
            "apu": apu,
            "modalidades_aiu": apu.calcular_modalidades_aiu(),
            "revisores": ConfiguracionSistema.objects.filter(activo=True).order_by("nombre_completo"),
            "ya_aprobado": bool(apu.modalidad_aiu_seleccionada),
        }
        return render(request, self.template_name, ctx)


class APUAprobarModalidadView(View):
    """
    POST /presupuestos/apu/<pk>/aprobar-modalidad/
    Guarda la modalidad AIU seleccionada por el revisor y avanza el estado del proyecto a COTIZADO.
    """
    def post(self, request, pk):
        from django.utils import timezone as tz
        from apps.configuracion.models import ConfiguracionSistema
        from apps.common.choices import EstadoProyecto, EstadoSolicitud
        apu = get_object_or_404(APUProyecto, pk=pk)
        try:
            modalidad = request.POST.get("modalidad_aiu", "").strip()
            if modalidad not in ("1", "2"):
                messages.error(request, "Seleccione una modalidad AIU válida (1 o 2).")
                return redirect(reverse("presupuestos:apu_revisar", args=[pk]))

            aprobador_pk = request.POST.get("aprobado_por_id", "").strip()
            aprobador = None
            if aprobador_pk:
                aprobador = ConfiguracionSistema.objects.filter(pk=aprobador_pk).first()

            apu.modalidad_aiu_seleccionada = modalidad
            apu.fecha_aprobacion = tz.now()
            update_fields = ["modalidad_aiu_seleccionada", "fecha_aprobacion", "updated_at"]
            if aprobador:
                apu.aprobado_por = aprobador
                update_fields.append("aprobado_por")
            apu.save(update_fields=update_fields)

            # Avanzar estado proyecto → COTIZADO y solicitud → APROBADA
            if apu.proyecto_sistema:
                proyecto = apu.proyecto_sistema.proyecto
                proyecto.estado = EstadoProyecto.COTIZADO
                proyecto.save(update_fields=["estado"])
                if proyecto.solicitud_id:
                    proyecto.solicitud.estado = EstadoSolicitud.APROBADA
                    proyecto.solicitud.save(update_fields=["estado"])

            messages.success(
                request,
                f"Modalidad AIU {modalidad} aprobada para el APU «{apu.nombre}».",
            )
        except Exception as exc:
            messages.error(request, f"Error al aprobar modalidad: {exc}")
            logger.exception("[APUAprobarModalidadView] Error APU %s", pk)

        return redirect(reverse("presupuestos:apu_revisar", args=[pk]))


# ═══════════════════════════════════════════════════════════════════════════════
# MÓDULO CONSUMO — Calculadora técnica para sistemas de CONSUMO
# ═══════════════════════════════════════════════════════════════════════════════

class CalculoConsumoView(View):
    """
    GET /presupuestos/consumo/<pk>/ — Panel de cálculo de consumo para un ProyectoSistema.

    Muestra:
    - Definición del sistema (capas, tipo_producto)
    - Parámetros de entrada (area_m2 del proyecto)
    - Resultados existentes (CalculoConsumoLinea)
    - Botón para recalcular
    """

    template_name = "presupuestos/consumo_maestro.html"

    def get(self, request, pk):
        from apps.presupuestos.models import CalculoConsumoLinea
        from apps.ingenieria.models import CapaConsumo, ComponenteQuimico
        from apps.common.choices import TipoSistema

        ps = get_object_or_404(
            ProyectoSistema.objects.select_related(
                "proyecto", "sistema", "subsistema"
            ),
            pk=pk,
        )

        if ps.sistema.tipo_sistema != TipoSistema.CONSUMO:
            messages.error(
                request,
                f"El sistema «{ps.sistema.nombre}» es CONSTRUCTIVO. "
                "Use el módulo de Despiece.",
            )
            return redirect(reverse("ingenieria:despiece_list") + f"?proyecto_pk={ps.proyecto_id}")

        capas = list(
            CapaConsumo.objects.filter(subsistema=ps.subsistema)
            .select_related("categoria")
            .order_by("orden")
        ) if ps.subsistema else []

        componentes_quimicos = list(
            ComponenteQuimico.objects.filter(subsistema=ps.subsistema).order_by("orden")
        ) if ps.subsistema else []

        lineas = list(
            CalculoConsumoLinea.objects
            .filter(proyecto_sistema=ps, es_componente_quimico=False)
            .select_related("producto", "categoria_producto")
            .prefetch_related(
                "componentes_quimicos__producto",
                "componentes_quimicos__categoria_producto",
            )
            .order_by("orden")
        )

        from apps.catalogos.models import CategoriaProducto
        categorias_disponibles = CategoriaProducto.objects.filter(activa=True).order_by("nombre")

        ctx = {
            "ps": ps,
            "proyecto": ps.proyecto,
            "capas": capas,
            "componentes_quimicos": componentes_quimicos,
            "lineas": lineas,
            "categorias_disponibles": categorias_disponibles,
            "area_m2": ps.proyecto.area_total_m2,
            "tiene_resultados": bool(lineas),
            "sin_capas_definidas": not capas,
        }
        return render(request, self.template_name, ctx)


class EjecutarCalculoConsumoView(View):
    """
    POST /presupuestos/consumo/<pk>/ejecutar/ — Ejecuta ConsumoService.
    """

    def post(self, request, pk):
        from apps.presupuestos.services import ConsumoService
        from apps.common.choices import TipoSistema

        ps = get_object_or_404(ProyectoSistema, pk=pk)

        if ps.sistema.tipo_sistema != TipoSistema.CONSUMO:
            messages.error(request, "Solo se puede calcular consumo en sistemas de tipo CONSUMO.")
            return redirect(reverse("ingenieria:despiece_list") + f"?proyecto_pk={ps.proyecto_id}")

        try:
            servicio = ConsumoService(ps)
            resultados = servicio.ejecutar()
            messages.success(
                request,
                f"Cálculo completado: {len(resultados)} capa(s) procesada(s).",
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        except Exception as exc:
            messages.error(request, f"Error en el cálculo: {exc}")
            logger.exception("[EjecutarCalculoConsumoView] Error PS %s", pk)

        return redirect("presupuestos:consumo_maestro", pk=pk)


class AsignarProductoConsumoAPIView(View):
    """
    POST JSON /presupuestos/consumo/api/asignar-producto/<pk>/
    Body: { "producto_pk": 123 }
    Asigna un producto a una CalculoConsumoLinea.
    """

    def post(self, request, pk):
        from apps.presupuestos.models import CalculoConsumoLinea
        from apps.catalogos.models import Producto
        from django.core.exceptions import ValidationError

        try:
            data = json.loads(request.body)
            producto_pk = int(data.get("producto_pk", 0))
        except (json.JSONDecodeError, ValueError, TypeError):
            return JsonResponse({"ok": False, "error": "Datos inválidos."}, status=400)

        try:
            linea = get_object_or_404(CalculoConsumoLinea, pk=pk)
            producto = get_object_or_404(Producto, pk=producto_pk, activo=True)
            linea.resolver_producto(producto)
            return JsonResponse({
                "ok": True,
                "producto_nombre": producto.nombre,
                "precio_snapshot": float(linea.precio_snapshot) if linea.precio_snapshot else None,
            })
        except ValidationError as exc:
            return JsonResponse({"ok": False, "error": exc.message}, status=400)
        except Exception as exc:
            logger.exception("[AsignarProductoConsumoAPIView] Línea %s", pk)
            return JsonResponse({"ok": False, "error": str(exc)}, status=500)


class ProductosPorCategoriaConsumoAPIView(View):
    """
    GET /presupuestos/consumo/api/productos-linea/<pk>/
    Retorna productos de la categoría de la línea dada.
    """

    def get(self, request, pk):
        from apps.presupuestos.models import CalculoConsumoLinea
        from apps.catalogos.models import Producto

        linea = get_object_or_404(CalculoConsumoLinea, pk=pk)
        if not linea.categoria_producto_id:
            return JsonResponse({"productos": []})

        productos = (
            Producto.objects
            .filter(categoria=linea.categoria_producto, activo=True)
            .order_by("nombre")
            .values("pk", "nombre", "precio_actual", "moneda", "unidad__abreviatura")
        )
        return JsonResponse({"productos": list(productos)})
