"""apps/presupuestos/views — Vistas del módulo de presupuestos."""

import json
import logging

from django.db.models import Prefetch
from django.urls import reverse_lazy, reverse
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.views import View
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.http import JsonResponse

from apps.presupuestos.models import ProyectoSistema, DespieceLinea, ConfiguracionAPU, APUProyecto, APULinea
from apps.comercial.models import Proyecto
from apps.ingenieria.models import Sistema, Subsistema
from apps.presupuestos.forms import ProyectoSistemaForm, DespieceLineaAjusteForm, ConfiguracionAPUForm, APUProyectoForm

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
    template_name = "presupuestos/confirm_delete.html"
    success_url = reverse_lazy("presupuestos:proyectosistema_list")


# ── Despiece — Vista principal ─────────────────────────────────────────────────

class DespieceProyectoView(DetailView):
    """Workbench principal del despiece de un proyecto."""
    model = Proyecto
    template_name = "presupuestos/despiece_maestro.html"
    context_object_name = "proyecto"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["sistemas"] = self.object.proyecto_sistemas.select_related(
            "sistema", "subsistema"
        ).prefetch_related(
            "despiece_lineas__producto",
            "despiece_lineas__categoria_producto",
            "despiece_lineas__regla",
        ).order_by("sistema__nombre")
        ctx["all_sistemas"]    = Sistema.objects.filter(activo=True).order_by("nombre")
        ctx["all_subsistemas"] = (
            Subsistema.objects.select_related("sistema")
            .filter(activo=True)
            .order_by("sistema__nombre", "nombre")
        )
        return ctx


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
            sistema_id    = body.get("sistema_id")
            subsistema_id = body.get("subsistema_id") or None
            parametros    = body.get("parametros", {})
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
            return redirect(reverse("presupuestos:despiece_proyecto", args=[pk]))

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

            from apps.presupuestos.services.despiece_service import DespieceService

            lineas = DespieceService(ps).ejecutar()
            messages.success(request, f"Despiece calculado: {len(lineas)} líneas generadas.")
        except Exception as exc:
            messages.error(request, f"Error al calcular despiece: {exc}")

        return redirect(reverse("presupuestos:despiece_proyecto", args=[pk]))


# ── Despiece — POST clásico: re-ejecutar cálculo de un PS existente ───────────

class DespieceEjecutarView(View):
    """Ejecuta el cálculo del despiece para un ProyectoSistema existente."""
    def post(self, request, pk):
        ps = get_object_or_404(ProyectoSistema, pk=pk)
        try:
            from apps.presupuestos.services.despiece_service import DespieceService

            lineas = DespieceService(ps).ejecutar()
            messages.success(request, f"Despiece ejecutado: {len(lineas)} líneas calculadas.")
        except Exception as exc:
            messages.error(request, f"Error al ejecutar despiece: {exc}")
        return redirect(reverse("presupuestos:despiece_proyecto", args=[ps.proyecto_id]))


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
            body   = json.loads(request.body)
            valor  = body.get("cantidad_ajustada")
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
                "linea_pk":          linea.pk,
                "cantidad_calculada": str(linea.cantidad_calculada),
                "cantidad_ajustada":  str(linea.cantidad_ajustada),
                "cantidad_final":     str(linea.cantidad_final),
                "motivo_ajuste":      linea.motivo_ajuste or "",
            })
        except Exception as exc:
            return JsonResponse({"error": str(exc)}, status=500)


class DespieceLineaAjusteView(UpdateView):
    """Ajuste manual de cantidad en una línea de despiece (formulario clásico)."""
    model = DespieceLinea
    form_class = DespieceLineaAjusteForm
    template_name = "presupuestos/despiece_ajuste_form.html"

    def get_success_url(self):
        return reverse("presupuestos:despiece_proyecto", args=[self.object.proyecto_id])


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

class APUProyectoDetailView(DetailView):
    model = APUProyecto
    template_name = "presupuestos/apu_detail.html"
    context_object_name = "apu"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["lineas"] = self.object.lineas.order_by("tipo", "descripcion")
        return ctx


class APUProyectoUpdateView(UpdateView):
    model = APUProyecto
    form_class = APUProyectoForm
    template_name = "presupuestos/apu_form.html"

    def get_success_url(self):
        return reverse("presupuestos:apu_detail", args=[self.object.pk])


class APUGenerarView(View):
    """Genera el APU para un ProyectoSistema dado."""
    def post(self, request, pk):
        ps = get_object_or_404(ProyectoSistema, pk=pk)
        try:
            from apps.presupuestos.services.apu_service import APUService
            apu = APUService.generar(ps)
            messages.success(request, "APU generado correctamente.")
            return redirect(reverse("presupuestos:apu_detail", args=[apu.pk]))
        except Exception as exc:
            messages.error(request, f"Error al generar APU: {exc}")
            return redirect(reverse("presupuestos:despiece_proyecto", args=[ps.proyecto_id]))


# ══════════════════════════════════════════════════════════════════════════════
# WIZARD POWERGRIP — Flujo guiado completo
# ══════════════════════════════════════════════════════════════════════════════

class PowerGripWizardView(View):
    """
    Vista principal del wizard PowerGrip.

    GET  /presupuestos/powergrip/<proyecto_pk>/
    Muestra en una sola pantalla:
      1. Selección de subsistema
      2. Variables de entrada + selección de productos por categoría
      3. Resultado del despiece (si ya fue calculado)
      4. APU por secciones (Materiales / Mano de Obra / Herramientas / Admin / Consolidado)
    """
    template_name = "presupuestos/powergrip_wizard.html"

    def get(self, request, pk):
        proyecto = get_object_or_404(Proyecto, pk=pk)

        try:
            sistema_pg = Sistema.objects.get(codigo="POWERGRIP")
        except Sistema.DoesNotExist:
            messages.error(request, "Sistema POWERGRIP no encontrado. Créelo en Ingeniería → Sistemas.")
            return redirect(reverse("comercial:proyecto_list"))

        subsistemas = Subsistema.objects.filter(sistema=sistema_pg, activo=True).order_by("nombre")

        # ProyectoSistemas PowerGrip existentes para este proyecto
        ps_list = (
            ProyectoSistema.objects
            .filter(proyecto=proyecto, sistema=sistema_pg)
            .prefetch_related(
                Prefetch("despiece_lineas", queryset=DespieceLinea.objects.select_related(
                    "producto", "producto__unidad", "categoria_producto"
                ).order_by("id")),
            )
            .select_related("subsistema")
        )

        # Productos disponibles por categoría (para los selects del wizard)
        from apps.catalogos.models import CategoriaProducto, Producto
        CATEGORIAS_PG = ["PowerGrip", "Fijaciones", "Accesorios", "Estopa", "Sellador"]
        productos_por_categoria = {}
        for slug in CATEGORIAS_PG:
            prods = list(
                Producto.objects.filter(
                    categoria__nombre__iexact=slug, activo=True
                ).values("pk", "nombre", "codigo")
            )
            productos_por_categoria[slug] = prods

        # Variables de cada subsistema (para el JS dinámico)
        from apps.ingenieria.system_defs.registry import get_subsistema_def
        subsistemas_def = {}
        for sub in subsistemas:
            sub_def = get_subsistema_def(sistema_pg.codigo, sub.codigo)
            if sub_def:
                VARS_PROYECTO = {"area_m2", "perimetro_ml"}
                subsistemas_def[sub.pk] = {
                    "variables": [
                        {
                            "variable":    v.variable,
                            "label":       v.label,
                            "unidad":      v.unidad,
                            "default":     v.default,
                            "opciones":    v.opciones,
                            "descripcion": v.descripcion,
                        }
                        for v in sub_def.variables
                        if v.variable not in VARS_PROYECTO
                    ],
                    "categorias": [c.categoria_slug for c in sub_def.componentes],
                }

        ctx = {
            "proyecto":                proyecto,
            "sistema_pg":              sistema_pg,
            "subsistemas":             subsistemas,
            "ps_list":                 ps_list,
            "productos_por_categoria": json.dumps(productos_por_categoria),
            "subsistemas_def":         json.dumps(subsistemas_def),
        }
        return render(request, self.template_name, ctx)


class CalcularPowerGripView(View):
    """
    POST /presupuestos/powergrip/calcular/<proyecto_pk>/

    Payload (form POST):
      subsistema_id
      parametros[total_powergrip]
      parametros[tornilleria_u7]   (o tornilleria_plus)
      parametros[desperdicio]
      productos[PowerGrip]         → producto_pk
      productos[Fijaciones]        → producto_pk
      productos[Accesorios]        → producto_pk
      productos[Estopa]            → producto_pk
      productos[Sellador]          → producto_pk

    Valida que todos los productos estén seleccionados ANTES de calcular.
    Llama a ProyectoService.calcular_powergrip() que orquesta todo.
    """
    def post(self, request, pk):
        proyecto = get_object_or_404(Proyecto, pk=pk)
        post = request.POST

        subsistema_id = post.get("subsistema_id")
        if not subsistema_id:
            messages.error(request, "Debe seleccionar un subsistema.")
            return redirect(reverse("presupuestos:powergrip_wizard", args=[pk]))

        # Parsear parametros[variable] → float
        parametros = {}
        for key, val in post.items():
            if key.startswith("parametros[") and key.endswith("]") and val not in ("", None):
                var_name = key[len("parametros["):-1]
                try:
                    parametros[var_name] = float(val)
                except (ValueError, TypeError):
                    parametros[var_name] = val

        # Parsear productos[categoria] → int(pk)
        productos_map = {}
        for key, val in post.items():
            if key.startswith("productos[") and key.endswith("]") and val:
                cat_slug = key[len("productos["):-1]
                try:
                    productos_map[cat_slug] = int(val)
                except (ValueError, TypeError):
                    pass

        # Validación temprana: todos los productos deben estar seleccionados
        CATEGORIAS_PG = ["PowerGrip", "Fijaciones", "Accesorios", "Estopa", "Sellador"]
        faltantes = [c for c in CATEGORIAS_PG if c not in productos_map]
        if faltantes:
            messages.error(
                request,
                f"Seleccione un producto para cada categoría antes de calcular. "
                f"Faltan: {', '.join(faltantes)}."
            )
            return redirect(reverse("presupuestos:powergrip_wizard", args=[pk]))

        try:
            from apps.presupuestos.services.proyecto_service import ProyectoService
            ps = ProyectoService.calcular_powergrip(
                proyecto_id=proyecto.pk,
                subsistema_id=int(subsistema_id),
                parametros=parametros,
                productos_map=productos_map,
            )
            messages.success(request, f"Despiece PowerGrip calculado: {ps.despiece_lineas.count()} líneas.")
        except Exception as exc:
            messages.error(request, f"Error al calcular: {exc}")

        return redirect(reverse("presupuestos:powergrip_wizard", args=[pk]))


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
    Usado por el wizard cuando el usuario cambia el subsistema (JS fetch).
    """
    def get(self, request, pk):
        sub = get_object_or_404(Subsistema, pk=pk)
        from apps.ingenieria.system_defs.registry import get_subsistema_def
        sub_def = get_subsistema_def(sub.sistema.codigo, sub.codigo)
        if not sub_def:
            return JsonResponse({"error": "Sin definición backend para este subsistema."}, status=404)

        VARS_PROYECTO = {"area_m2", "perimetro_ml"}
        return JsonResponse({
            "subsistema_pk":  sub.pk,
            "subsistema_cod": sub.codigo,
            "variables": [
                {
                    "variable":    v.variable,
                    "label":       v.label,
                    "unidad":      v.unidad,
                    "default":     v.default,
                    "opciones":    v.opciones,
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

    Registra las líneas de mano de obra del APU.
    El usuario ingresa los costos diarios de cada concepto (APE).
    La cuadrilla tiene 7 personas (predeterminado del modelo APUProyecto).

    IMPORTANTE: La cuadrilla NO se relaciona con el despiece — es un APE independiente.
    """
    def post(self, request, pk):
        apu = get_object_or_404(APUProyecto, pk=pk)
        try:
            cuadrilla_personas = int(request.POST.get("cuadrilla_personas", 7) or 7)
            hya_dia        = float(request.POST.get("hya_dia", 0) or 0)
            cuadrilla_dia  = float(request.POST.get("cuadrilla_dia", 0) or 0)
            dotacion_dia   = float(request.POST.get("dotacion_dia", 0) or 0)
            proteccion_dia = float(request.POST.get("proteccion_dia", 0) or 0)

            # Actualizar cuadrilla_personas en el APU si cambió
            if apu.cuadrilla_personas != cuadrilla_personas:
                apu.cuadrilla_personas = cuadrilla_personas
                apu.save(update_fields=["cuadrilla_personas", "updated_at"])

            from apps.presupuestos.services.apu_service import APUService
            svc = APUService(apu.proyecto_sistema)
            svc.apu = apu  # Reusar APU existente sin recrear
            svc.generar_mano_obra(
                hya_dia=hya_dia,
                cuadrilla_dia=cuadrilla_dia,
                dotacion_dia=dotacion_dia,
                proteccion_dia=proteccion_dia,
            )
            svc.finalizar()
            messages.success(request, "Mano de obra registrada y APU actualizado.")
        except Exception as exc:
            messages.error(request, f"Error al registrar mano de obra: {exc}")
            logger.exception("[APUManoObraView] Error APU %s", pk)

        return redirect(reverse("presupuestos:apu_detail", args=[apu.pk]))


class APUHerramientasView(View):
    """
    POST /presupuestos/apu/<pk>/herramientas/

    Registra ítems de herramientas/equipos al APU.
    El form puede enviar múltiples filas: descripcion[] y precio_total[].
    """
    def post(self, request, pk):
        apu = get_object_or_404(APUProyecto, pk=pk)
        try:
            descripciones  = request.POST.getlist("descripcion[]")
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
                messages.warning(request, "No se ingresaron ítems de herramientas válidos.")
                return redirect(reverse("presupuestos:apu_detail", args=[apu.pk]))

            from apps.presupuestos.services.apu_service import APUService
            svc = APUService(apu.proyecto_sistema)
            svc.apu = apu
            svc.generar_herramientas(items)
            svc.finalizar()
            messages.success(request, f"{len(items)} ítem(s) de herramientas registrados.")
        except Exception as exc:
            messages.error(request, f"Error al registrar herramientas: {exc}")
            logger.exception("[APUHerramientasView] Error APU %s", pk)

        return redirect(reverse("presupuestos:apu_detail", args=[apu.pk]))


class APUAdminView(View):
    """
    POST /presupuestos/apu/<pk>/administrativo/

    Registra el costo administrativo del APU como porcentaje sobre la base
    (materiales + mano de obra + herramientas) o como valor directo.
    """
    def post(self, request, pk):
        apu = get_object_or_404(APUProyecto, pk=pk)
        try:
            modo = request.POST.get("modo", "porcentaje")  # "porcentaje" | "valor"
            valor_str = request.POST.get("valor", "0") or "0"
            valor = float(valor_str)

            if modo == "porcentaje":
                base = float(
                    apu.subtotal_materiales
                    + apu.subtotal_mano_obra
                    + apu.subtotal_herramientas
                )
                costo_admin = base * (valor / 100)
            else:
                costo_admin = valor

            from apps.presupuestos.services.apu_service import APUService
            svc = APUService(apu.proyecto_sistema)
            svc.apu = apu
            svc.generar_administracion(costo_admin)
            svc.finalizar()
            messages.success(request, f"Administrativo registrado: ${costo_admin:,.2f}.")
        except Exception as exc:
            messages.error(request, f"Error al registrar administrativo: {exc}")
            logger.exception("[APUAdminView] Error APU %s", pk)

        return redirect(reverse("presupuestos:apu_detail", args=[apu.pk]))
