"""
apps/ingenieria/views/calculador.py — Calculador de sistemas constructivos.


Flujo completo (independiente de proyectos):
  1. CalculadorSistemaView       → catálogo de sistemas con búsqueda/filtros
  2. CalculadorSeleccionarView   → elegir subsistema + subconjuntos a incluir
  3. DespieceMaestroView         → workbench: variables, cálculo, guardado, APU
  4. CalcularDespieceMaestroView → endpoint AJAX que ejecuta el cálculo sin guardar
  5. GuardarDespieceMaestroView  → guarda el resultado y marca estado=GUARDADO
  6. DespiecesGuardadosView      → lista de despieces guardados
  7. EliminarDespieceMaestroView → elimina un despiece en borrador o guardado
"""

import json

from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from apps.ingenieria.models import (
    Sistema,
    Subsistema,
    SubconjuntoRecetaTecnica,
    VariableSubsistema,
    DespieceMaestro,
    DespieceMaestroLinea,
)
from apps.ingenieria.services.despiece_maestro_service import DespieceMaestroService
from apps.common.choices import TipoSistema, LineaNegocio


# ── 1. Catálogo de sistemas ───────────────────────────────────────────────────

class CalculadorSistemaView(TemplateView):
    """
    Vista catálogo: muestra los sistemas constructivos disponibles.
    Permite buscar por nombre/código, filtrar por línea de negocio.
    """
    template_name = "ingenieria/calculador_sistemas.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # Solo sistemas constructivos activos
        qs = (
            Sistema.objects
            .filter(activo=True, tipo_sistema=TipoSistema.CONSTRUCTIVO)
            .prefetch_related("subsistemas")
            .order_by("linea_negocio", "codigo")
        )

        q        = self.request.GET.get("q", "").strip()
        linea    = self.request.GET.get("linea", "").strip()

        if q:
            qs = qs.filter(
                nombre__icontains=q
            ) | Sistema.objects.filter(
                activo=True, tipo_sistema=TipoSistema.CONSTRUCTIVO, codigo__icontains=q
            )
            qs = qs.distinct()

        if linea:
            qs = qs.filter(linea_negocio=linea)

        ctx["sistemas"]          = list(qs)
        ctx["q"]                 = q
        ctx["linea_activa"]      = linea
        ctx["linea_choices"]     = LineaNegocio.choices
        ctx["total_guardados"]   = DespieceMaestro.objects.filter(estado=DespieceMaestro.GUARDADO).count()
        ctx["total_borradores"]  = DespieceMaestro.objects.filter(estado=DespieceMaestro.BORRADOR).count()
        return ctx


# ── 2. Seleccionar subsistema + subconjuntos ──────────────────────────────────

class CalculadorSeleccionarView(View):
    """
    GET:  Muestra los subsistemas del sistema y los subconjuntos de cada uno.
    POST: Crea un DespieceMaestro en estado BORRADOR y redirige al workbench.
    """
    template_name = "ingenieria/calculador_seleccionar.html"

    def get(self, request, sistema_pk):
        from django.shortcuts import render
        sistema = get_object_or_404(Sistema, pk=sistema_pk, tipo_sistema=TipoSistema.CONSTRUCTIVO)
        subsistemas = (
            Subsistema.objects
            .filter(sistema=sistema, activo=True)
            .prefetch_related("subconjuntos_receta", "variables_db")
            .order_by("codigo")
        )
        return render(request, self.template_name, {
            "sistema":     sistema,
            "subsistemas": subsistemas,
        })

    def post(self, request, sistema_pk):
        sistema = get_object_or_404(Sistema, pk=sistema_pk, tipo_sistema=TipoSistema.CONSTRUCTIVO)

        subsistema_pk = request.POST.get("subsistema_pk", "").strip()
        if not subsistema_pk:
            messages.error(request, "Debes seleccionar un subsistema.")
            return redirect("ingenieria:calculador_seleccionar", sistema_pk=sistema_pk)

        subsistema = get_object_or_404(Subsistema, pk=subsistema_pk, sistema=sistema, activo=True)

        subconjuntos_pks = [
            int(pk) for pk in request.POST.getlist("subconjuntos[]")
            if str(pk).isdigit()
        ]

        # Validación: si el subsistema tiene subconjuntos, obligar a elegir al menos uno
        tiene_subconjuntos = SubconjuntoRecetaTecnica.objects.filter(
            subsistema=subsistema, activo=True
        ).exists()

        if tiene_subconjuntos and not subconjuntos_pks:
            messages.error(request, "Selecciona al menos un subconjunto de la receta técnica.")
            return redirect("ingenieria:calculador_seleccionar", sistema_pk=sistema_pk)

        nombre = request.POST.get("nombre", "").strip()

        with transaction.atomic():
            dm = DespieceMaestro.objects.create(
                subsistema=subsistema,
                nombre=nombre,
                estado=DespieceMaestro.BORRADOR,
                variables_entrada={},
            )
            if subconjuntos_pks:
                subconjuntos = SubconjuntoRecetaTecnica.objects.filter(
                    pk__in=subconjuntos_pks,
                    subsistema=subsistema,
                )
                dm.subconjuntos.set(subconjuntos)

        return redirect("ingenieria:despiece_maestro", pk=dm.pk)


# ── 3. Workbench: Despiece Maestro ────────────────────────────────────────────

class DespieceMaestroView(DetailView):
    """
    Vista principal del Despiece Maestro.

    Muestra:
      - Variables de entrada del subsistema (formulario dinámico)
      - Resultado del cálculo agrupado por subconjunto (si ya fue calculado)
      - Botón Calcular (AJAX, no guarda)
      - Botón Guardar (guarda y marca GUARDADO)
      - Botón Generar APU (solo si estado=GUARDADO)
    """
    model = DespieceMaestro
    template_name = "ingenieria/despiece_maestro_nuevo.html"
    context_object_name = "despiece"

    def get_queryset(self):
        return (
            super().get_queryset()
            .select_related("subsistema__sistema")
            .prefetch_related("subconjuntos", "lineas__subconjunto")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        dm = self.object
        svc = DespieceMaestroService(dm)

        # Variables de entrada para el formulario
        ctx["variables_requeridas"] = svc.get_variables_requeridas()

        # Líneas agrupadas por subconjunto (si ya fue guardado)
        ctx["lineas_por_subconjunto"] = _agrupar_lineas(dm.lineas.all())

        # Subconjuntos seleccionados para mostrar cuáles se incluyen
        ctx["subconjuntos_seleccionados"] = list(
            dm.subconjuntos.order_by("orden", "id")
        )

        # Serialización JSON de líneas guardadas para inicializar la tabla en JS
        lineas_data = []
        for linea in dm.lineas.order_by("orden"):
            lineas_data.append({
                "subconjunto_nombre":    linea.subconjunto_nombre,
                "componente_codigo":     linea.componente_codigo,
                "componente_nombre":     linea.componente_nombre,
                "cantidad_calculada":    float(linea.cantidad_calculada),
                "unidad":                linea.unidad,
                "categoria_nombre":      linea.categoria_nombre,
                "formula_texto":         linea.formula_texto,
                "variable_salida":       linea.variable_salida,
                "variable_referencia_apu": linea.variable_referencia_apu,
                "unidad_apu":            linea.unidad_apu,
                "subconjunto_id":        linea.subconjunto_id,
                # Snapshot de producto guardado (puede ser null)
                "producto_id":           linea.producto_id,
                "producto_codigo":       linea.producto_codigo,
                "producto_nombre":       linea.producto_nombre,
                "precio_unitario": (
                    float(linea.precio_unitario) if linea.precio_unitario is not None else None
                ),
                "precio_total": (
                    float(linea.precio_total) if linea.precio_total is not None else None
                ),
                "moneda":      linea.moneda,
                "fecha_precio": (
                    linea.fecha_precio.strftime("%Y-%m-%d") if linea.fecha_precio else None
                ),
            })
        ctx["lineas_json"] = json.dumps(lineas_data, ensure_ascii=False)

        return ctx


def _agrupar_lineas(lineas_qs):
    """Agrupa las líneas del despiece por subconjunto para el template."""
    grupos: dict[str, dict] = {}
    for linea in lineas_qs.order_by("orden"):
        key = linea.subconjunto_nombre or "General"
        if key not in grupos:
            grupos[key] = {"nombre": key, "lineas": []}
        grupos[key]["lineas"].append(linea)
    return list(grupos.values())


# ── 4. Calcular (AJAX, sin guardar) ──────────────────────────────────────────

class CalcularDespieceMaestroView(View):
    """
    POST endpoint AJAX.

    Body JSON esperado:
      {
        "variables_entrada": {"total_powergrip": 2000, "desperdicio": 1.05}
      }

    Respuesta JSON:
      {
        "ok": true,
        "subconjuntos": [
          {
            "nombre": "Estructura metálica",
            "lineas": [
              { "componente_codigo": "...", "componente_nombre": "...",
                "cantidad_calculada": 42.0, "unidad": "und", ... }
            ]
          }
        ],
        "total_lineas": 5,
        "errores": []
      }

    No modifica la base de datos.
    """

    def post(self, request, pk):
        dm = get_object_or_404(DespieceMaestro, pk=pk)

        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, TypeError):
            body = {}

        variables_entrada = body.get("variables_entrada", {})
        if not isinstance(variables_entrada, dict):
            variables_entrada = {}

        # Actualizar variables_entrada en el objeto en memoria (sin guardar)
        dm.variables_entrada = variables_entrada

        svc = DespieceMaestroService(dm)
        try:
            resultados = svc.calcular()
        except Exception as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)

        errores = [r for r in resultados if r.get("error")]
        subconjuntos_resp = _agrupar_resultados(resultados)

        return JsonResponse({
            "ok": True,
            "subconjuntos": subconjuntos_resp,
            "total_lineas": len(resultados),
            "errores": [{"codigo": e["componente_codigo"], "msg": e["error"]} for e in errores],
        })


def _agrupar_resultados(resultados: list[dict]) -> list[dict]:
    """Agrupa resultados de cálculo por subconjunto para la respuesta AJAX."""
    grupos: dict[str, dict] = {}
    for r in resultados:
        key = r["subconjunto_nombre"] or "General"
        if key not in grupos:
            grupos[key] = {"nombre": key, "lineas": []}
        grupos[key]["lineas"].append(r)
    return list(grupos.values())


# ── 5. Guardar despiece ───────────────────────────────────────────────────────

class GuardarDespieceMaestroView(View):
    """
    POST: Recalcula y guarda el despiece en estado GUARDADO.

    Body JSON esperado:
      {
        "variables_entrada": {"total_powergrip": 2000, "desperdicio": 1.05}
      }

    Idempotente: guardar varias veces reemplaza las líneas anteriores.
    Respuesta: redirect a DespieceMaestroView.
    """

    def post(self, request, pk):
        dm = get_object_or_404(DespieceMaestro, pk=pk)

        try:
            body = json.loads(request.body)
            variables_entrada    = body.get("variables_entrada", {})
            seleccion_productos  = body.get("seleccion_productos", {})
        except (json.JSONDecodeError, TypeError):
            variables_entrada   = {}
            seleccion_productos = {}

        if not isinstance(variables_entrada, dict):
            variables_entrada = {}
        if not isinstance(seleccion_productos, dict):
            seleccion_productos = {}

        dm.variables_entrada = variables_entrada
        svc = DespieceMaestroService(dm)

        try:
            resultados = svc.calcular()
        except Exception as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)

        try:
            svc.guardar(resultados, variables_entrada, seleccion_productos)
        except Exception as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=500)

        return JsonResponse({
            "ok": True,
            "redirect_url": reverse("ingenieria:despiece_maestro", kwargs={"pk": dm.pk}),
            "estado": dm.estado,
            "total_lineas": len(resultados),
        })


# ── 6. Lista de despieces guardados ──────────────────────────────────────────

class DespiecesGuardadosView(ListView):
    """Lista todos los despieces (guardados y borradores)."""
    model = DespieceMaestro
    template_name = "ingenieria/despieces_guardados.html"
    context_object_name = "despieces"
    paginate_by = 30

    def get_queryset(self):
        qs = (
            DespieceMaestro.objects
            .select_related("subsistema__sistema")
            .prefetch_related("subconjuntos")
            .order_by("-created_at")
        )

        estado = self.request.GET.get("estado", "").strip()
        q      = self.request.GET.get("q", "").strip()

        if estado in (DespieceMaestro.BORRADOR, DespieceMaestro.GUARDADO):
            qs = qs.filter(estado=estado)
        if q:
            qs = qs.filter(nombre__icontains=q) | qs.filter(subsistema__nombre__icontains=q)
            qs = qs.distinct()

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["estado_filtro"] = self.request.GET.get("estado", "")
        ctx["q"] = self.request.GET.get("q", "")
        ctx["BORRADOR"] = DespieceMaestro.BORRADOR
        ctx["GUARDADO"] = DespieceMaestro.GUARDADO
        return ctx


# ── 7. Eliminar despiece ──────────────────────────────────────────────────────

class EliminarDespieceMaestroView(View):
    """POST: elimina un DespieceMaestro."""

    def post(self, request, pk):
        dm = get_object_or_404(DespieceMaestro, pk=pk)
        dm.delete()
        messages.success(request, "Despiece eliminado correctamente.")
        return redirect("ingenieria:despieces_guardados")


# ── 8. APU básico desde despiece guardado ────────────────────────────────────

class APUDespieceMaestroView(DetailView):
    """
    Vista de APU básico calculado a partir de un DespieceMaestro guardado.

    Valida que el despiece esté en estado GUARDADO antes de mostrar el APU.
    Usa ReglaAPUSubsistema para calcular el costo por tipo de APU.
    """
    model = DespieceMaestro
    template_name = "ingenieria/despiece_apu_basico.html"
    context_object_name = "despiece"

    def get(self, request, *args, **kwargs):
        dm = get_object_or_404(DespieceMaestro, pk=kwargs["pk"])
        if not dm.esta_guardado:
            messages.error(
                request,
                "El despiece debe estar guardado antes de generar el APU. "
                "Guarda el despiece primero."
            )
            return redirect("ingenieria:despiece_maestro", pk=dm.pk)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        dm = self.object

        # Cargar líneas agrupadas por subconjunto
        ctx["lineas_por_subconjunto"] = _agrupar_lineas(dm.lineas.all())

        # Cargar reglas APU del subsistema para mostrar fórmulas
        from apps.presupuestos.models import ReglaAPUSubsistema
        ctx["reglas_apu"] = list(
            ReglaAPUSubsistema.objects.filter(subsistema=dm.subsistema)
            .order_by("orden")
        )

        # Contexto del cálculo (para evaluar reglas APU si existen)
        svc = DespieceMaestroService(dm)
        ctx["variables_entrada"] = svc.get_variables_requeridas()

        return ctx


# ── 9. Búsqueda de productos (AJAX autocomplete) ──────────────────────────

class BuscarProductosView(View):
    """
    GET /calculador/productos/buscar/?q=<texto>&categoria=<nombre>

    Retorna hasta 20 productos activos que coincidan con el término de búsqueda.
    Incluye precio_actual, moneda, unidad y fecha_actualizacion_precio para
    poblar la tabla del workbench sin necesidad de recargar la página.
    """

    def get(self, request):
        from apps.catalogos.models import Producto

        q         = request.GET.get("q", "").strip()
        categoria = request.GET.get("categoria", "").strip()

        qs = Producto.objects.filter(activo=True).select_related("unidad", "categoria")

        if q:
            qs = qs.filter(nombre__icontains=q) | Producto.objects.filter(
                activo=True, codigo__icontains=q
            ).select_related("unidad", "categoria")
            qs = qs.distinct()

        if categoria:
            qs = qs.filter(categoria__nombre__icontains=categoria)

        qs = qs.order_by("nombre")[:20]

        productos = []
        for p in qs:
            productos.append({
                "id":                        p.pk,
                "codigo":                    p.codigo,
                "nombre":                    p.nombre,
                "unidad":                    p.unidad.abreviatura if p.unidad else "",
                "precio_unitario":           float(p.precio_actual),
                "moneda":                    p.moneda,
                "fecha_actualizacion_precio": (
                    p.fecha_actualizacion_precio.strftime("%Y-%m-%dT%H:%M:%S")
                    if p.fecha_actualizacion_precio else None
                ),
            })

        return JsonResponse({"ok": True, "productos": productos})
