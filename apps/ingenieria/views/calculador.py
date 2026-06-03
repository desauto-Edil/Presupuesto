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
    ConsolidacionDespieceMaestro,
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
        ctx["proyecto_pk"]       = self.request.GET.get("proyecto_pk", "").strip()
        return ctx


# ── 2. Seleccionar subsistema + subconjuntos ──────────────────────────────────

class CalculadorSeleccionarView(View):
    """
    GET:  Muestra los subsistemas del sistema y los subconjuntos de cada uno.
    POST: Crea un DespieceMaestro en estado BORRADOR y redirige al workbench.
    """
    template_name = "ingenieria/calculador_seleccionar.html"

    def _get_proyecto(self, request):
        """Retorna el Proyecto asociado si viene `proyecto_pk` en GET/POST, o None."""
        pk = (request.POST.get("proyecto_pk") or request.GET.get("proyecto_pk", "")).strip()
        if pk and pk.isdigit():
            try:
                from apps.comercial.models import Proyecto
                return Proyecto.objects.get(pk=int(pk))
            except Exception:
                pass
        return None

    def get(self, request, sistema_pk):
        from django.shortcuts import render
        sistema = get_object_or_404(Sistema, pk=sistema_pk, tipo_sistema=TipoSistema.CONSTRUCTIVO)
        subsistemas = (
            Subsistema.objects
            .filter(sistema=sistema, activo=True)
            .prefetch_related("subconjuntos_receta", "variables_db")
            .order_by("codigo")
        )
        proyecto = self._get_proyecto(request)
        return render(request, self.template_name, {
            "sistema":     sistema,
            "subsistemas": subsistemas,
            "proyecto":    proyecto,
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

        nombre   = request.POST.get("nombre", "").strip()
        proyecto = self._get_proyecto(request)

        # Auto-name when coming from a project and the user left the field empty
        if not nombre and proyecto:
            nombre = f"Despiece - {proyecto.consecutivo}"

        with transaction.atomic():
            dm = DespieceMaestro.objects.create(
                subsistema=subsistema,
                nombre=nombre,
                estado=DespieceMaestro.BORRADOR,
                variables_entrada={},
                proyecto=proyecto,
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
    template_name = "ingenieria/despiece_maestro.html"
    context_object_name = "despiece"

    def get_queryset(self):
        return (
            super().get_queryset()
            .select_related("subsistema__sistema", "proyecto")
            .prefetch_related("subconjuntos", "lineas__subconjunto")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        dm = self.object
        svc = DespieceMaestroService(dm)

        # Variables de entrada para el formulario
        # Si hay subconjuntos seleccionados, mostrar solo las variables que usan esos subconjuntos.
        todas_variables = svc.get_variables_requeridas()
        variables_filtradas = svc.get_variables_para_subconjuntos()
        vars_filtradas_nombres = {v["variable"] for v in variables_filtradas}
        variables_extra = [v for v in todas_variables if v["variable"] not in vars_filtradas_nombres]
        ctx["variables_requeridas"] = variables_filtradas
        ctx["variables_extra"]      = variables_extra
        ctx["variables_filtradas"]  = bool(variables_extra)

        # Mapa {variable_tecnica: label_visible} para mostrar etiqueta
        # legible en el modal de Detalle del cálculo. Incluye todas las
        # variables del subsistema (las filtradas y las extra).
        ctx["var_labels_json"] = json.dumps(
            {v["variable"]: v["label"] for v in todas_variables},
            ensure_ascii=False,
        )

        # Líneas agrupadas por subconjunto (si ya fue guardado)
        ctx["lineas_por_subconjunto"] = _agrupar_lineas(dm.lineas.all())

        # Subconjuntos seleccionados para mostrar cuáles se incluyen
        ctx["subconjuntos_seleccionados"] = list(
            dm.subconjuntos.order_by("orden", "id")
        )

        # Proyecto asociado (si existe) para mostrar vínculo de regreso
        ctx["proyecto"] = dm.proyecto

        # Notas técnicas del subsistema (consulta para el usuario final)
        ctx["notas_tecnicas"] = (dm.subsistema.notas_tecnicas or "").strip()

        # Controla visibilidad del botón APU:
        # solo despieces guardados Y asociados a un proyecto pueden generar APU.
        ctx["puede_generar_apu"] = dm.esta_guardado and dm.proyecto_id is not None

        # Si ya existe un APU para este despiece, exponer su pk para enlace directo.
        ctx["apu_pk"] = None
        if dm.proyecto_id and dm.subsistema_id:
            try:
                from apps.presupuestos.models import ProyectoSistema, APUProyecto
                ps = ProyectoSistema.objects.filter(
                    proyecto_id=dm.proyecto_id,
                    sistema=dm.subsistema.sistema,
                    subsistema=dm.subsistema,
                ).first()
                if ps:
                    apu = APUProyecto.objects.filter(proyecto_sistema=ps).first()
                    if apu:
                        ctx["apu_pk"] = apu.pk
            except Exception:
                pass

        # Serialización JSON de líneas guardadas para inicializar la tabla en JS
        import math as _math
        lineas_data = []
        for linea in dm.lineas.order_by("orden"):
            cant_calc = float(linea.cantidad_calculada)
            cant_red  = (
                linea.cantidad_redondeada
                if linea.cantidad_redondeada is not None
                else _math.ceil(cant_calc)
            )
            lineas_data.append({
                "pk":                    linea.pk,
                "subconjunto_nombre":    linea.subconjunto_nombre,
                "componente_codigo":     linea.componente_codigo,
                "componente_nombre":     linea.componente_nombre,
                "cantidad_calculada":    cant_calc,
                "cantidad_redondeada":   cant_red,
                "unidad":                linea.unidad,
                "categoria_nombre":      linea.categoria_nombre,
                "formula_texto":         linea.formula_texto,
                "valores_usados":        linea.valores_usados or {},
                "variable_salida":       linea.variable_salida,
                "variable_referencia_apu": linea.variable_referencia_apu,
                "unidad_apu":            linea.unidad_apu,
                "subconjunto_id":        linea.subconjunto_id,
                "producto_id":           linea.producto_id,
                "producto_codigo":       linea.producto_codigo,
                "producto_nombre":       linea.producto_nombre,
                "precio_unitario": (
                    float(linea.precio_unitario) if linea.precio_unitario is not None else None
                ),
                "moneda":      linea.moneda,
                "fecha_precio": (
                    linea.fecha_precio.strftime("%Y-%m-%d") if linea.fecha_precio else None
                ),
            })
        ctx["lineas_json"] = json.dumps(lineas_data, ensure_ascii=False)

        # Consolidaciones guardadas para inicializar el estado JS
        consolidaciones_data = []
        for c in dm.consolidaciones.order_by("orden"):
            consolidaciones_data.append({
                "id":                 c.pk,
                "label":              c.label,
                "lineas_ids":         c.lineas_ids,
                "cantidad_total":     float(c.cantidad_total),
                "cantidad_redondeada": c.cantidad_redondeada,
                "unidad":             c.unidad,
                "orden":              c.orden,
                "producto_id":        c.producto_id,
                "producto_codigo":    c.producto_codigo,
                "producto_nombre":    c.producto_nombre,
                "precio_unitario": (
                    float(c.precio_unitario) if c.precio_unitario is not None else None
                ),
                "moneda":      c.moneda,
                "fecha_precio": (
                    c.fecha_precio.strftime("%Y-%m-%d") if c.fecha_precio else None
                ),
            })
        ctx["consolidaciones_json"] = json.dumps(consolidaciones_data, ensure_ascii=False)

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
    """Agrupa resultados de cálculo por subconjunto_id para la respuesta AJAX.

    Usa subconjunto_id (no el nombre) para evitar colisiones entre subconjuntos
    distintos con el mismo nombre y garantizar orden estable.
    """
    grupos: dict = {}
    for r in resultados:
        key = r["subconjunto_id"]  # None para componentes sin subconjunto
        if key not in grupos:
            grupos[key] = {"nombre": r["subconjunto_nombre"] or "General", "lineas": []}
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
            consolidaciones_data = body.get("consolidaciones", [])
        except (json.JSONDecodeError, TypeError):
            variables_entrada    = {}
            seleccion_productos  = {}
            consolidaciones_data = []

        if not isinstance(variables_entrada, dict):
            variables_entrada = {}
        if not isinstance(seleccion_productos, dict):
            seleccion_productos = {}
        if not isinstance(consolidaciones_data, list):
            consolidaciones_data = []

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

        # ── Guardar consolidaciones ───────────────────────────────────────────
        if consolidaciones_data:
            lineas_guardadas = list(dm.lineas.order_by("orden"))
            dm.consolidaciones.all().delete()
            from decimal import Decimal as _D
            from django.utils.dateparse import parse_datetime

            nuevas_cons = []
            for idx_c, c in enumerate(consolidaciones_data):
                indices  = [i for i in (c.get("indices") or []) if isinstance(i, int)]
                lineas_pks = [
                    lineas_guardadas[i].pk
                    for i in indices
                    if 0 <= i < len(lineas_guardadas)
                ]
                prod_data   = c.get("_prod") or {}
                precio_u    = None
                precio_t    = None
                fecha_precio = None

                if prod_data.get("precio_unitario") is not None:
                    try:
                        precio_u = _D(str(prod_data["precio_unitario"]))
                        cantidad = _D(str(c.get("cantidad_total") or 0))
                        precio_t = (cantidad * precio_u).quantize(_D("0.01"))
                    except Exception:
                        pass

                if prod_data.get("fecha_precio"):
                    fecha_precio = parse_datetime(str(prod_data["fecha_precio"]))

                nuevas_cons.append(ConsolidacionDespieceMaestro(
                    despiece=dm,
                    label=str(c.get("label") or "Consolidado")[:200],
                    lineas_ids=lineas_pks,
                    cantidad_total=_D(str(c.get("cantidad_total") or 0)),
                    cantidad_redondeada=int(c.get("cantidad_redondeada") or 0),
                    unidad=str(c.get("unidad") or "")[:40],
                    orden=idx_c + 1,
                    producto_id=prod_data.get("producto_id") or None,
                    producto_codigo=str(prod_data.get("producto_codigo") or "")[:50],
                    producto_nombre=str(prod_data.get("producto_nombre") or "")[:300],
                    precio_unitario=precio_u,
                    precio_total=precio_t,
                    moneda=str(prod_data.get("moneda") or "")[:3],
                    fecha_precio=fecha_precio,
                ))

            ConsolidacionDespieceMaestro.objects.bulk_create(nuevas_cons)
        else:
            # Si no hay consolidaciones, limpiar las anteriores
            dm.consolidaciones.all().delete()

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
    template_name = "ingenieria/despiece_list.html"
    context_object_name = "despieces"
    paginate_by = 30

    def get_queryset(self):
        qs = (
            DespieceMaestro.objects
            .select_related("subsistema__sistema", "proyecto")
            .order_by("-created_at")
        )

        estado      = self.request.GET.get("estado", "").strip()
        q           = self.request.GET.get("q", "").strip()
        proyecto_pk = self.request.GET.get("proyecto_pk", "").strip()

        if estado in (DespieceMaestro.BORRADOR, DespieceMaestro.GUARDADO):
            qs = qs.filter(estado=estado)
        if q:
            qs = qs.filter(nombre__icontains=q) | qs.filter(subsistema__nombre__icontains=q)
            qs = qs.distinct()
        if proyecto_pk and proyecto_pk.isdigit():
            qs = qs.filter(proyecto_id=int(proyecto_pk))

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["estado_filtro"] = self.request.GET.get("estado", "")
        ctx["q"]             = self.request.GET.get("q", "")
        ctx["proyecto_pk"]   = self.request.GET.get("proyecto_pk", "")
        ctx["BORRADOR"]      = DespieceMaestro.BORRADOR
        ctx["GUARDADO"]      = DespieceMaestro.GUARDADO
        # Si viene proyecto_pk, cargar el proyecto para mostrarlo en la cabecera
        proyecto_pk = ctx["proyecto_pk"]
        if proyecto_pk and proyecto_pk.isdigit():
            try:
                from apps.comercial.models import Proyecto
                ctx["proyecto_filtro"] = Proyecto.objects.get(pk=int(proyecto_pk))
            except Exception:
                pass
        return ctx


# ── 7. Eliminar despiece ──────────────────────────────────────────────────────

class EliminarDespieceMaestroView(View):
    """POST: elimina un DespieceMaestro."""

    def post(self, request, pk):
        dm = get_object_or_404(DespieceMaestro, pk=pk)
        dm.delete()
        messages.success(request, "Despiece eliminado correctamente.")
        return redirect("ingenieria:despiece_list")


# ── 8. APU desde despiece guardado — redirige a presupuestos:apu_list ────────

class APUDespieceMaestroView(View):
    """
    Redirige al módulo APU de presupuestos validando que el despiece sea apto.

    Validaciones backend (tarea 11):
      - El despiece debe estar en estado GUARDADO.
      - El despiece debe tener un proyecto asociado (despieces rápidos no generan APU).
      - El despiece debe tener líneas calculadas.
    """

    def get(self, request, pk):
        dm = get_object_or_404(DespieceMaestro, pk=pk)

        if not dm.esta_guardado:
            messages.error(
                request,
                "El despiece debe estar guardado antes de generar el APU."
            )
            return redirect("ingenieria:despiece_maestro", pk=dm.pk)

        if not dm.proyecto_id:
            messages.error(
                request,
                "Solo los despieces asociados a un proyecto pueden generar APU. "
                "Este despiece fue creado desde el calculador rápido."
            )
            return redirect("ingenieria:despiece_maestro", pk=dm.pk)

        if not dm.lineas.exists():
            messages.error(
                request,
                "El despiece no tiene líneas calculadas. Calcula y guarda primero."
            )
            return redirect("ingenieria:despiece_maestro", pk=dm.pk)

        return redirect("presupuestos:apu_list")


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
                # precio_unitario = precio real por unidad (precio_actual / unidades_por_presentacion)
                "precio_unitario":           float(p.precio_unitario_real),
                "precio_presentacion":       float(p.precio_actual),
                "unidades_por_presentacion": p.unidades_por_presentacion or 1,
                "moneda":                    p.moneda,
                "fecha_actualizacion_precio": (
                    p.fecha_actualizacion_precio.strftime("%Y-%m-%dT%H:%M:%S")
                    if p.fecha_actualizacion_precio else None
                ),
            })

        return JsonResponse({"ok": True, "productos": productos})
