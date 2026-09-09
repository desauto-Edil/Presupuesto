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
    APU, APUProyecto, APULinea, APUPoliza,
    CategoriaItemAPU, CuadrillaPreset, CuadrillaPresetItem, ItemCatalogoAPU,
)
from apps.comercial.models import Proyecto
from apps.comercial.views import registrar_log, _usuario_sistema
from apps.common.auth import (
    get_usuario_actual,
    es_admin,
    puede_aprobar_apu,
    puede_enviar_a_revision,
    puede_gestionar_unidad,
)
from apps.common.apu_lock import (
    objeto_bloqueado_por_apu,
    redirect_si_bloqueado,
    lineas_pendientes_producto,
    MENSAJE_BLOQUEO,
)
from apps.ingenieria.models import Sistema, Subsistema
from apps.common.choices import TipoAPU
from apps.presupuestos.forms import (
    ProyectoSistemaForm, DespieceLineaAjusteForm,
    ConfiguracionAPUForm, APUProyectoForm,
    CategoriaItemAPUForm, ItemCatalogoAPUForm,
    CuadrillaPresetForm, CuadrillaPresetItemFormSet,
)
from apps.comercial.forms import SolicitudForm
from apps.common.mixins import (
    UnidadFilterMixin, WithCreateFormMixin,
    AdminRequiredMixin, AdminGerenteRequiredMixin,
    GestionPresupuestosMixin, DescargaPDFMixin,
    APUSistemaAccesoMixin,
)

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _apu_unidad(apu) -> str:
    """Devuelve la unidad de negocio del APU (del cliente del proyecto, o '' si no tiene)."""
    try:
        proyecto = apu.get_proyecto()
        if proyecto:
            cliente = getattr(proyecto, "cliente", None)
            if cliente:
                return getattr(cliente, "unidad_negocio", "") or ""
    except Exception:
        pass
    return ""


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
        return reverse("presupuestos:despiece_proyecto", args=[self.object.proyecto_id])


# ── Despiece — Módulo lista ───────────────────────────────────────────────────

class DespieceListView(UnidadFilterMixin, WithCreateFormMixin, ListView):
    """Módulo Despiece — lista proyectos con despieces. Visible para todas las unidades."""
    model = Proyecto
    template_name = "presupuestos/despiece_list.html"
    context_object_name = "proyectos"
    form_class = SolicitudForm
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


class NuevoDespieceView(GestionPresupuestosMixin, View):
    """POST — redirige al nuevo calculador de sistemas."""

    def post(self, request):
        return redirect("ingenieria:calculador_sistemas")


class DespieceXLSXDownloadView(View):
    """GET /presupuestos/despiece/<pk>/xlsx/ — descarga xlsx de DespieceLineas del proyecto."""

    def get(self, request, pk):
        proyecto = get_object_or_404(Proyecto, pk=pk)

        unidad = request.session.get("unidad_negocio", "") or ""
        if unidad and proyecto.creado_por and proyecto.creado_por.unidad_negocio != unidad:
            messages.error(request, "No tiene acceso a este proyecto.")
            return redirect("presupuestos:despiece_list")

        from apps.presupuestos.xlsx_exports import build_despiece_xlsx
        buf = build_despiece_xlsx(proyecto)

        filename = f"despiece_{proyecto.consecutivo}.xlsx"
        response = HttpResponse(
            buf.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        registrar_log(
            request,
            accion="DESCARGAR_DESPIECE_XLSX",
            descripcion=f"Excel despiece — {proyecto.consecutivo}",
            modelo_afectado="Proyecto",
            objeto_id=proyecto.pk,
        )
        return response


class DespieceMaestroXLSXDownloadView(View):
    """GET /presupuestos/despiece-maestro/<pk>/xlsx/ — xlsx de un DespieceMaestro (ingeniería)."""

    _log = logging.getLogger("apps.presupuestos.views")

    def get(self, request, pk):
        from apps.ingenieria.models.despiece_maestro import DespieceMaestro
        despiece = get_object_or_404(
            DespieceMaestro.objects.select_related(
                "subsistema", "subsistema__sistema", "proyecto", "proyecto__cliente"
            ),
            pk=pk,
        )

        try:
            from apps.presupuestos.xlsx_exports import build_despiece_maestro_xlsx
            buf = build_despiece_maestro_xlsx(despiece)
        except Exception:
            self._log.exception(
                "Error generando xlsx para DespieceMaestro #%s (subsistema=%s)",
                pk,
                getattr(getattr(despiece, "subsistema", None), "codigo", "?"),
            )
            raise

        safe_name = (despiece.nombre or f"despiece_{pk}").replace("/", "-").replace("\\", "-")
        filename = f"despiece_{safe_name[:60]}.xlsx"
        response = HttpResponse(
            buf.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        registrar_log(
            request,
            accion="DESCARGAR_DESPIECE_MAESTRO_XLSX",
            descripcion=f"Excel DespieceMaestro #{pk} — {despiece.nombre or despiece.subsistema.codigo}",
            modelo_afectado="DespieceMaestro",
            objeto_id=pk,
        )
        return response


class APUXLSXDownloadView(View):
    """GET /presupuestos/apu/<pk>/xlsx/ — descarga xlsx con hojas Despiece + APU(s)."""

    def get(self, request, pk):
        apu = get_object_or_404(APUProyecto, pk=pk)

        # Si el APU tiene APUs consolidados, los cargamos para generar una pestaña por cada uno.
        apus_adicionales = None
        if apu.apus_presupuesto_ids:
            apus_adicionales = list(
                APUProyecto.objects.filter(
                    pk__in=apu.apus_presupuesto_ids,
                    archivado=False,
                ).select_related("proyecto_sistema__proyecto", "proyecto_sistema__sistema")
            )

        from apps.presupuestos.xlsx_exports import build_apu_xlsx
        buf = build_apu_xlsx(apu, apus_adicionales=apus_adicionales)

        safe_name = (apu.nombre or f"APU_{pk}").replace("/", "-").replace("\\", "-")
        filename = f"apu_{safe_name[:60]}.xlsx"
        response = HttpResponse(
            buf.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        try:
            proyecto_id = apu.proyecto_sistema.proyecto_id if apu.proyecto_sistema_id else None
            registrar_log(
                request,
                accion="DESCARGAR_APU_XLSX",
                descripcion=f"Excel APU — {apu.nombre}",
                modelo_afectado="APUProyecto",
                objeto_id=apu.pk,
            )
        except Exception:
            pass

        return response


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
        return reverse("presupuestos:despiece_proyecto", args=[self.object.proyecto_id])


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
        return (
            APUProyecto.objects
            .select_related(
                "proyecto_sistema__proyecto__cliente",
                "proyecto_sistema__sistema",
                "proyecto_sistema__subsistema",
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


def _build_info_card_data(apu) -> dict:
    """Datos consolidados para las tarjetas informativas por sección del APU."""
    from apps.common.choices import TipoAPU
    from apps.presupuestos.models import SubsistemaItemAPU

    pp_nombre = None
    pp_cantidad = None
    pp_unidad = None
    modo_rendimiento = None
    ps = apu.proyecto_sistema
    if ps:
        params = ps.parametros_entrada or {}
        modo_rendimiento = params.get("modo_rendimiento")
        pp_cantidad = params.get("cantidad_base")
        pp_unidad = params.get("unidad_base")
        pp_id = params.get("producto_principal_id")
        if pp_id:
            try:
                from apps.catalogos.models import Producto
                p = Producto.objects.only("nombre").get(pk=int(pp_id))
                pp_nombre = p.nombre
            except Exception:
                pp_nombre = None

    items_por_tipo: dict = {}
    if ps and ps.subsistema_id:
        for row in (
            SubsistemaItemAPU.objects
            .filter(subsistema_id=ps.subsistema_id, activo=True, item_catalogo__activo=True)
            .values("tipo")
            .annotate(n=Count("id"))
        ):
            items_por_tipo[row["tipo"]] = row["n"]

    proyecto = getattr(ps, "proyecto", None) if ps else None
    num_personas = getattr(proyecto, "num_personas", None) if proyecto else None
    dias_duracion = apu.dias_duracion or (getattr(proyecto, "dias_duracion", None) if proyecto else None)

    return {
        TipoAPU.MATERIALES: {
            "producto_principal": pp_nombre,
            "cantidad_base": pp_cantidad,
            "unidad_base": pp_unidad,
            "modo_rendimiento": modo_rendimiento,
            "formula": "rendimiento = cantidad del material / cantidad base del producto principal",
            "mensaje": (
                "Los materiales vienen del despiece seleccionado. "
                "El rendimiento se calcula dividiendo la cantidad de cada material "
                "entre la cantidad total del producto principal."
            ),
        },
        TipoAPU.HERRAMIENTAS_EQUIPOS: {
            "num_personas": num_personas,
            "dias_duracion": dias_duracion,
            "items_configurados": items_por_tipo.get(TipoAPU.HERRAMIENTAS_EQUIPOS, 0),
            "base_calculo": "Suma de costo por día de los ítems × días configurados",
            "mensaje": "Herramientas se calcula a partir de los ítems APU predeterminados del subsistema.",
        },
        TipoAPU.TRANSPORTE: {
            "num_personas": num_personas,
            "dias_duracion": dias_duracion,
            "items_configurados": items_por_tipo.get(TipoAPU.TRANSPORTE, 0),
            "base_calculo": "Costo total de los ítems APU configurados",
            "mensaje": "Transporte se calcula según los ítems APU predeterminados del subsistema.",
        },
        TipoAPU.MANO_DE_OBRA: {
            "num_personas": num_personas,
            "dias_duracion": dias_duracion,
            "items_configurados": items_por_tipo.get(TipoAPU.MANO_DE_OBRA, 0),
            "base_calculo": "Personas × días × rendimiento configurado",
            "mensaje": "La mano de obra se calcula con base en las personas requeridas y días de duración.",
        },
        TipoAPU.ADMINISTRACION: {
            "num_personas": num_personas,
            "dias_duracion": dias_duracion,
            "items_configurados": items_por_tipo.get(TipoAPU.ADMINISTRACION, 0),
            "base_calculo": "Suma de los ítems administrativos configurados",
            "mensaje": "Administración agrupa costos indirectos configurados para el subsistema.",
        },
    }


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

    info_cards = _build_info_card_data(apu)

    # Cargar todas las líneas del APU de una sola vez
    all_lineas = list(
        apu.lineas.select_related(
            "item_catalogo__categoria", "despiece_linea__producto", "despiece_maestro",
        ).order_by("descripcion")
    )

    # Anotar líneas MATERIALES con componente_nombre, producto_nombre, cantidad_total
    materiales = [l for l in all_lineas if l.tipo == TipoAPU.MATERIALES]
    if materiales:
        _comp_nombre_por_codigo: dict = {}
        try:
            ps = apu.proyecto_sistema
            if ps and ps.subsistema_id:
                from apps.ingenieria.models import ComponenteSubsistema
                for c in ComponenteSubsistema.objects.filter(
                    subsistema_id=ps.subsistema_id
                ).only("codigo", "nombre"):
                    _comp_nombre_por_codigo[c.codigo] = c.nombre
        except Exception:
            _comp_nombre_por_codigo = {}

        # Cache label de consolidaciones: (despiece_maestro_id, producto_id) → label
        # Permite mostrar "Tornillos combinados" en vez de "CONS_123" en la columna Componente.
        _cons_label_cache: dict = {}
        try:
            dm_ids_cons = {
                l.despiece_maestro_id
                for l in materiales
                if l.despiece_maestro_id
                and l.despiece_linea
                and (l.despiece_linea.componente_codigo or "").startswith("CONS_")
            }
            if dm_ids_cons:
                from apps.ingenieria.models import ConsolidacionDespieceMaestro
                for c in ConsolidacionDespieceMaestro.objects.filter(
                    despiece_id__in=dm_ids_cons
                ).only("despiece_id", "producto_id", "label"):
                    if c.despiece_id is not None and c.producto_id is not None:
                        _cons_label_cache[(c.despiece_id, c.producto_id)] = c.label
        except Exception:
            _cons_label_cache = {}

        for l in materiales:
            dl = l.despiece_linea
            codigo = (dl.componente_codigo if dl else "") or ""
            if codigo.startswith("CONS_"):
                # Línea consolidada: mostrar el label de la consolidación, no el código interno
                try:
                    prod_id = int(codigo[5:])
                    dm_pk = l.despiece_maestro_id
                    label = _cons_label_cache.get((dm_pk, prod_id))
                    l.componente_nombre = label or l.descripcion or "—"
                except (ValueError, TypeError):
                    l.componente_nombre = l.descripcion or "—"
            else:
                l.componente_nombre = _comp_nombre_por_codigo.get(codigo) or codigo or "—"
            if dl and dl.producto_id and dl.producto:
                l.producto_nombre = dl.producto.nombre
            else:
                l.producto_nombre = l.descripcion or "—"
            l.cantidad_total = dl.cantidad_final if dl else None

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

        cat_data = {
            **info,
            "grupos": grupos,
            "subtotal_costo": subtotal_costo,
            "subtotal_valor": subtotal_valor,
            "count": len(lineas_tipo),
            "info_card": info_cards.get(tipo, {}),
        }
        if tipo == TipoAPU.ADMINISTRACION:
            cat_data["lineas_admin_detalle"] = lineas_tipo

        categorias.append(cat_data)

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
        # APULinea no tiene campo 'cantidad' — el valor se integra en rendimiento.
        # Los modales muestran siempre 1 como punto de partida editable.
        ctx["lineas_item_ids"] = set(
            self.object.lineas
            .exclude(item_catalogo=None)
            .values_list("item_catalogo_id", flat=True)
        )
        ctx["lineas_cantidades"] = {}  # vacío; el default en template es 1
        # Precio efectivo con el que se generó cada línea detalle. Permite que
        # el modal "Configurar…" reabra con el precio que el usuario editó en
        # lugar de volver al valor del catálogo. Si el usuario no lo tocó,
        # coincide con la derivación del catálogo y no se nota diferencia.
        ctx["lineas_precios"] = {
            item_id: precio
            for item_id, precio in self.object.lineas
            .exclude(item_catalogo=None)
            .values_list("item_catalogo_id", "precio_referencia")
        }
        # Panel modalidades AIU (Fase 11.3) — necesario para que el panel
        # muestre valores en lugar de guiones en apu_detail.html.
        try:
            ctx["modalidades_aiu"] = self.object.calcular_modalidades_aiu()
            # Valores enteros para JS: los Decimal con locale es-CO se renderizan
            # con coma decimal (ej: "454454552,1990") → SyntaxError en <script>.
            # Pasamos int para evitar el problema de localización completamente.
            ctx["js_base_m1"] = int(ctx["modalidades_aiu"]["modalidad1"]["gran_total"] or 0)
            ctx["js_base_m2"] = int(ctx["modalidades_aiu"]["modalidad2"]["gran_total"] or 0)
        except Exception:
            ctx["modalidades_aiu"] = None
            ctx["js_base_m1"] = 0
            ctx["js_base_m2"] = 0

        # Autorizadores disponibles para el modal "Calcular Presupuesto"
        from apps.configuracion.models import ConfiguracionSistema
        from apps.common.choices import RolSistema
        ctx["autorizadores"] = ConfiguracionSistema.objects.filter(
            activo=True,
            rol__in=[RolSistema.ADMINISTRADOR, RolSistema.GERENTE, RolSistema.PRESUPUESTOS],
        ).order_by("nombre_completo")

        # Otros APUs del mismo proyecto (para combinar en presupuesto final)
        apus_mismo_proyecto = []
        if self.object.proyecto_sistema_id:
            try:
                proyecto = self.object.proyecto_sistema.proyecto
                apus_mismo_proyecto = list(
                    APUProyecto.objects
                    .filter(proyecto_sistema__proyecto=proyecto)
                    .exclude(pk=self.object.pk)
                    .exclude(archivado=True)
                    .values("pk", "nombre", "total_valor_venta", "subtotal_materiales")
                    .order_by("pk")
                )
            except Exception:
                apus_mismo_proyecto = []
        ctx["apus_mismo_proyecto"] = apus_mismo_proyecto

        # Opciones de base para el modal de pólizas
        ctx["poliza_base_choices"] = APUPoliza.BASE_CHOICES

        # ── Revisión y permisos (Issue 2 + 4) ─────────────────────────────────
        from apps.common.auth import puede_aprobar_apu as _puede_aprobar, get_usuario_actual as _get_usuario
        _usuario_actual = _get_usuario(self.request)
        ctx["ya_en_revision"] = bool(self.object.fecha_envio_revision)
        ctx["puede_aprobar"] = _puede_aprobar(self.request, self.object)
        # Es el "emisor": puede ver estado pero no aprobar (no es el revisor asignado)
        _proyecto = self.object.get_proyecto()
        _creado_por_id = getattr(_proyecto, "creado_por_id", None) if _proyecto else None
        ctx["es_emisor_revision"] = bool(
            _usuario_actual is not None
            and _creado_por_id is not None
            and _usuario_actual.pk == _creado_por_id
            and not ctx["puede_aprobar"]
        )

        # ── Cotización vigente (Fase 12) ───────────────────────────────────────
        try:
            from apps.presupuestos.services import CotizacionSnapshotService
            from apps.presupuestos.models.cotizacion import CotizacionAPU
            ctx["cotizacion_vigente"] = CotizacionSnapshotService.obtener_snapshot_vigente(self.object)
            # Histórico de versiones anteriores (estado=REEMPLAZADA)
            ctx["cotizaciones_historico"] = list(
                CotizacionAPU.objects
                .filter(apu=self.object, estado=CotizacionAPU.Estado.REEMPLAZADA)
                .order_by("-version")
            )
        except Exception:
            ctx["cotizacion_vigente"] = None
            ctx["cotizaciones_historico"] = []

        # ── Modo revisión (solo lectura cuando viene desde vista de revisor) ──────
        ctx["modo_revision"] = bool(self.request.GET.get("revisor"))

        # ── Admin modal: días, SIA items (Issue 5) ────────────────────────────
        ctx["apu_dias_duracion"] = self.object.dias_duracion or 0
        # Ítems configurados en SubsistemaItemAPU para el subsistema de este APU
        sia_item_ids: set = set()
        sia_admin: dict = {}
        if self.object.proyecto_sistema_id and self.object.proyecto_sistema.subsistema_id:
            try:
                from apps.ingenieria.models import SubsistemaItemAPU
                sia_qs = SubsistemaItemAPU.objects.filter(
                    subsistema=self.object.proyecto_sistema.subsistema,
                    activo=True,
                ).select_related("item_catalogo")
                for sia in sia_qs:
                    sia_item_ids.add(sia.item_catalogo_id)
                    if sia.item_catalogo.categoria.tipo_apu == "ADMINISTRACION":
                        sia_admin[str(sia.item_catalogo_id)] = {
                            "porcentaje": 100,  # default; se sobreescribe desde APULineas
                        }
            except Exception:
                pass

        # Sobreescribir con porcentajes ya guardados en APULineas del APU.
        # Las líneas de detalle de admin almacenan rendimiento = porcentaje (fracción).
        from apps.common.choices import TipoAPU as _TipoAPU
        for linea in self.object.lineas.filter(
            tipo=_TipoAPU.ADMINISTRACION,
        ).exclude(item_catalogo=None):
            sia_admin[str(linea.item_catalogo_id)] = {
                "porcentaje": round(float(linea.rendimiento) * 100, 2),
            }

        import json as _json
        ctx["sia_item_ids"] = sia_item_ids
        ctx["sia_admin_json"] = _json.dumps(sia_admin)

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


class APUGuardarView(GestionPresupuestosMixin, View):
    """
    POST /presupuestos/apu/<pk>/guardar/

    Guarda nombre, descripción del APU y además calcula y persiste la cantidad
    de referencia (cantidad_base_apu / unidad_base_apu) desde los parámetros del
    ProyectoSistema. Esto permite que la vista de presupuesto por proyecto pueda
    mostrar: valor_unitario (total_valor_venta) × cantidad_base_apu = valor_total.
    """
    def post(self, request, pk):
        from decimal import Decimal as _D
        apu = get_object_or_404(APUProyecto, pk=pk)
        nombre = request.POST.get("nombre", "").strip()
        descripcion = request.POST.get("descripcion", "").strip()
        campos = ["updated_at"]
        if nombre:
            apu.nombre = nombre
            campos.append("nombre")
        apu.descripcion = descripcion
        campos.append("descripcion")

        # Calcular cantidad_base_apu desde los parámetros del ProyectoSistema.
        # Esto consolida el «valor unitario del APU» con la cantidad total del proyecto.
        _cantidad_base = None
        _unidad_base = ""
        if apu.proyecto_sistema_id:
            try:
                params = apu.proyecto_sistema.parametros_entrada or {}
                _cb_raw = params.get("cantidad_base")
                _ub_raw = params.get("unidad_base", "")
                if _cb_raw not in (None, "", "0"):
                    _cantidad_base = _D(str(_cb_raw))
                    _unidad_base = str(_ub_raw or "")
            except Exception:
                pass
            if _cantidad_base is None:
                # Fallback: usar APUService._get_total_unidades()
                try:
                    from apps.presupuestos.services.apu_service import APUService
                    svc = APUService.for_apu(apu)
                    _total = svc._get_total_unidades()
                    if _total and _total > 1:
                        _cantidad_base = _D(str(_total))
                except Exception:
                    pass

        if _cantidad_base is not None:
            apu.cantidad_base_apu = _cantidad_base
            apu.unidad_base_apu = _unidad_base
            campos += ["cantidad_base_apu", "unidad_base_apu"]

        apu.save(update_fields=campos)
        msg_base = f" (base: {_cantidad_base} {_unidad_base})" if _cantidad_base else ""
        messages.success(request, f"APU «{apu.nombre}» guardado correctamente{msg_base}.")

        # Si el proyecto tiene ≥1 APU guardado, redirigir al presupuesto del proyecto.
        proyecto = apu.get_proyecto()
        if proyecto:
            n_apus_guardados = APUProyecto.objects.filter(
                proyecto_sistema__proyecto=proyecto,
                cantidad_base_apu__isnull=False,
                archivado=False,
            ).count()
            if n_apus_guardados >= 1:
                return redirect(
                    reverse("presupuestos:proyecto_presupuesto", args=[proyecto.pk])
                )
        return redirect(reverse("presupuestos:apu_detail", args=[pk]))


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
            return redirect(reverse("presupuestos:despiece_proyecto", args=[ps.proyecto_id]))


# PowerGripWizardView y CalcularPowerGripView eliminados (2026-04).
# El despiece ahora se maneja directamente en DespieceProyectoView (despiece_maestro.html)
# con soporte completo de sistemas/subsistemas definidos en DB.

# Stub de compatibilidad para imports históricos que puedan existir
class PowerGripWizardView(View):
    """Redirige al despiece general del proyecto."""
    def get(self, request, pk):
        return redirect(reverse("presupuestos:despiece_proyecto", args=[pk]))


class CalcularPowerGripView(View):
    """Redirige al despiece general del proyecto."""
    def post(self, request, pk):
        return redirect(reverse("presupuestos:despiece_proyecto", args=[pk]))


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
                items_data = _parse_items_catalogo(request)

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

            items_data = _parse_items_catalogo(request)

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
    Marca el APU (y su proyecto) como enviado a revisión/aprobación.
    Cambia proyecto.estado → APU_GENERADO si el modelo lo soporta.
    """
    def post(self, request, pk):
        apu = get_object_or_404(APUProyecto, pk=pk)
        try:
            # Actualizar el estado del proyecto si tiene proyecto_sistema
            if apu.proyecto_sistema:
                proyecto = apu.proyecto_sistema.proyecto
                # Intentar avanzar estado (si el campo existe y el valor es válido)
                from apps.common.choices import EstadoProyecto
                if hasattr(EstadoProyecto, "APU_GENERADO"):
                    proyecto.estado = EstadoProyecto.APU_GENERADO
                    proyecto.save(update_fields=["estado"])
                    messages.success(
                        request,
                        f"APU «{apu.nombre}» enviado a revisión. "
                        f"Proyecto {proyecto.consecutivo} marcado como APU_GENERADO."
                    )
                else:
                    messages.success(request, f"APU «{apu.nombre}» marcado para revisión.")
            else:
                messages.success(request, f"APU «{apu.nombre}» marcado para revisión.")
        except Exception as exc:
            messages.error(request, f"Error al enviar a revisión: {exc}")
            logger.exception("[APUEnviarRevisionView] Error APU %s", pk)

        return redirect(reverse("presupuestos:apu_detail", args=[pk]))


class APUSeleccionarDespiecesView(GestionPresupuestosMixin, View):
    """
    Fase 11.4 — Vista intermedia de selección manual de despieces.

    GET: lista los DespieceMaestro candidatos del proyecto (origen marcado
         y bloqueado, los demás opcionales). Si solo hay un candidato
         válido, genera el APU directo sin paso intermedio.

    POST: recibe la selección, valida con DespieceSelectionStrategy y
          ejecuta APUGenerationFacade.generar_desde_seleccion.
    """

    def get(self, request, pk):
        from apps.ingenieria.models import DespieceMaestro
        from apps.presupuestos.services.despiece_selection import (
            DespieceSelectionStrategy,
        )
        dm = get_object_or_404(DespieceMaestro, pk=pk)

        if not dm.esta_guardado:
            messages.error(request, "El despiece debe estar guardado antes de generar el APU.")
            return redirect("ingenieria:despiece_maestro", pk=dm.pk)
        if not dm.proyecto_id:
            messages.error(request, "Solo los despieces asociados a un proyecto pueden generar APU.")
            return redirect("ingenieria:despiece_maestro", pk=dm.pk)

        candidatos = DespieceSelectionStrategy.listar_candidatos(dm)
        secundarios = [c for c in candidatos if not c.es_origen]

        if not secundarios:
            return self._generar(request, dm, [dm.pk])

        return render(
            request,
            "presupuestos/apu_seleccionar_despieces.html",
            {
                "despiece_origen": dm,
                "proyecto": dm.proyecto,
                "candidatos": candidatos,
                "secundarios": secundarios,
            },
        )

    def post(self, request, pk):
        from apps.ingenieria.models import DespieceMaestro
        dm = get_object_or_404(DespieceMaestro, pk=pk)

        if not dm.esta_guardado or not dm.proyecto_id:
            messages.error(request, "El despiece origen no es válido para generar APU.")
            return redirect("ingenieria:despiece_maestro", pk=dm.pk)

        accion = request.POST.get("accion", "").strip()
        if accion == "solo_origen":
            ids_seleccionados = [dm.pk]
        else:
            ids_seleccionados = request.POST.getlist("despieces")
            try:
                ids_seleccionados = [int(x) for x in ids_seleccionados if str(x).isdigit()]
            except (TypeError, ValueError):
                ids_seleccionados = []
            if dm.pk not in ids_seleccionados:
                ids_seleccionados.append(dm.pk)

        return self._generar(request, dm, ids_seleccionados)

    def _generar(self, request, dm, ids_seleccionados):
        from apps.presupuestos.services.apu_facade import APUFacade
        try:
            apu, resumen, errores = APUFacade.generar_desde_seleccion(
                despiece_origen=dm,
                dm_ids_seleccionados=ids_seleccionados,
            )
        except Exception as exc:
            messages.error(request, f"Error al generar APU: {exc}")
            return redirect("ingenieria:despiece_maestro", pk=dm.pk)

        if errores:
            for err in errores:
                messages.error(request, err)
            return redirect("ingenieria:despiece_maestro", pk=dm.pk)

        if resumen.get("apu_existia"):
            messages.success(
                request,
                f"APU actualizado correctamente con {resumen['despieces_incluidos']} despiece(s).",
            )
        else:
            messages.success(
                request,
                f"APU generado correctamente con {resumen['despieces_incluidos']} despiece(s).",
            )

        registrar_log(
            request,
            accion="GENERAR_APU",
            descripcion=(
                f"APU {'actualizado' if resumen.get('apu_existia') else 'generado'} desde "
                f"despiece maestro #{dm.pk} con {resumen['despieces_incluidos']} despieces "
                f"seleccionados — {dm.proyecto.consecutivo}"
            ),
            modelo_afectado="Proyecto",
            objeto_id=dm.proyecto_id,
        )
        return redirect(reverse("presupuestos:apu_detail", args=[apu.pk]))


class APUGenerarDesdeDespiece(GestionPresupuestosMixin, View):
    """
    Compatibilidad Fase 11.3 → 11.4. El botón antiguo POSTea aquí; ahora
    redirigimos siempre a la vista de selección manual, que internamente
    maneja el caso degenerado de "un solo despiece" sin paso intermedio.
    """
    def post(self, request, pk):
        return redirect("presupuestos:apu_seleccionar_despieces", pk=pk)

    def get(self, request, pk):
        return redirect("presupuestos:apu_seleccionar_despieces", pk=pk)


class _APUGenerarDesdeDespiece_LEGACY(View):
    """LEGADO (Fase 11.3 e inferior). Conservado como referencia; no enrutado."""
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


# ── Fase 6E: armar APU con producto principal ────────────────────────────────


class APUArmarDesdeDespieceView(GestionPresupuestosMixin, View):
    """
    POST: arma el APU desde DespieceMaestro con un producto principal seleccionado.

    Diferencia con APUGenerarDesdeDespiece:
      - Recibe `producto_principal_id` (FK a catalogos.Producto).
      - Revalida con validar_despiece_listo_para_apu en backend (no confía en el modal).
      - Verifica que el producto principal está en las líneas finales.
      - Recalcula cantidad_base como sumatoria de líneas finales con ese producto.
      - Persiste en `ProyectoSistema.parametros_entrada`:
            producto_principal_id, cantidad_base, unidad_base,
            modo_rendimiento="PRODUCTO_PRINCIPAL"
        Sin tocar modelos ni crear migraciones.
      - Luego ejecuta la misma sincronización consolidado→DespieceLinea y
        llama APUService.generar(ps). La fórmula nueva de rendimiento se
        adopta en Fase 6F leyendo `parametros_entrada`.
    """

    def post(self, request, pk):
        from apps.ingenieria.models import DespieceMaestro
        from apps.ingenieria.services.lineas_finales_apu import (
            validar_despiece_listo_para_apu,
            productos_principal_opciones,
            calcular_base_apu_backend,
        )
        from django.db import transaction as db_transaction
        from decimal import Decimal

        dm = get_object_or_404(DespieceMaestro, pk=pk)

        blk = redirect_si_bloqueado(
            request, getattr(dm, "proyecto", None),
            reverse("ingenieria:despiece_maestro", args=[dm.pk]),
        )
        if blk:
            return blk

        # ── 1. Revalidación backend obligatoria ──────────────────────────────
        validacion = validar_despiece_listo_para_apu(dm)
        if not validacion["ok"]:
            for err in validacion["errores"]:
                messages.error(request, err)
            return redirect("ingenieria:despiece_maestro", pk=dm.pk)

        # ── 2. Determinar modo de rendimiento y validar entrada ──────────────
        modo_rendimiento = request.POST.get("modo_rendimiento")
        parametros_rendimiento = {}
        log_msg_part = ""

        if modo_rendimiento == "BASE_APU":
            # Modo Base APU: no requiere producto principal. La base se recalcula en backend.
            base_apu_data = calcular_base_apu_backend(dm)
            if not base_apu_data["valida"]:
                messages.error(request, "No se pudo calcular una Base APU válida. Revise las variables de entrada.")
                return redirect("ingenieria:despiece_maestro", pk=dm.pk)

            cantidad_base = base_apu_data["total"]
            unidad_base = base_apu_data["unidad"]
            parametros_rendimiento = {
                "producto_principal_id": None,
                "cantidad_base": str(cantidad_base),
                "unidad_base": unidad_base,
                "modo_rendimiento": "BASE_APU",
            }
            log_msg_part = f"con Base APU (cant_base={cantidad_base} {unidad_base})"

        else:  # Fallback a PRODUCTO_PRINCIPAL
            try:
                producto_principal_id = int(request.POST.get("producto_principal_id", "") or 0)
            except (TypeError, ValueError):
                producto_principal_id = 0
            if not producto_principal_id:
                messages.error(request, "Debe seleccionar un producto principal para armar el APU.")
                return redirect("ingenieria:despiece_maestro", pk=dm.pk)

            opciones = productos_principal_opciones(validacion["lineas_finales"])
            elegido = next(
                (o for o in opciones if o["producto_id"] == producto_principal_id),
                None,
            )
            if elegido is None:
                messages.error(request, "El producto principal debe pertenecer a las líneas finales del despiece.")
                return redirect("ingenieria:despiece_maestro", pk=dm.pk)

            cantidad_base = elegido["cantidad_base"]
            unidad_base = elegido["unidad"] or ""

            if not cantidad_base or Decimal(str(cantidad_base)) <= Decimal("0"):
                messages.error(request, "La cantidad base del producto principal debe ser mayor que cero.")
                return redirect("ingenieria:despiece_maestro", pk=dm.pk)

            parametros_rendimiento = {
                "producto_principal_id": producto_principal_id,
                "cantidad_base": str(cantidad_base),
                "unidad_base": unidad_base,
                "modo_rendimiento": "PRODUCTO_PRINCIPAL",
            }
            log_msg_part = (
                f"con producto principal #{producto_principal_id} "
                f"(cant_base={cantidad_base} {unidad_base})"
            )

        # ── 5. Sincronización + generación (mismo flujo que APUGenerar…) ─────
        try:
            with db_transaction.atomic():
                ps, _ = ProyectoSistema.objects.get_or_create(
                    proyecto=dm.proyecto,
                    sistema=dm.subsistema.sistema,
                    subsistema=dm.subsistema,
                )
                # Variables_entrada del despiece → parametros_entrada del PS
                if dm.variables_entrada:
                    ps.parametros_entrada = {
                        **(ps.parametros_entrada or {}),
                        **dm.variables_entrada,
                    }

                ps.parametros_entrada = {
                    **(ps.parametros_entrada or {}),
                    **parametros_rendimiento,
                }
                ps.save(update_fields=["parametros_entrada"])

                # 7. Sincronización del PS desde el despiece actual ───────────
                # Fix 6E-B (regla del usuario):
                #   El APU debe generarse ÚNICAMENTE con las líneas finales
                #   mostradas en el modal "Armar mi APU". Eso es exactamente
                #   obtener_lineas_finales_para_apu(dm) del despiece que
                #   disparó el POST. No se consolidan otros despieces del
                #   mismo subsistema, no se reutilizan DespieceLinea
                #   antiguas — el conjunto del PS se reconstruye 1:1 con lo
                #   que el usuario vio en el modal.
                #
                #   Consecuencias:
                #   - Si había DespieceLinea antiguas en el PS que ya no
                #     corresponden al despiece actual → se eliminan.
                #   - Si en el subsistema hay varios DM guardados con
                #     materiales distintos, cada armado de APU reemplaza
                #     completamente al anterior (el último botón gana).
                lineas_finales = validacion["lineas_finales"]

                # Pre-cargar componente_codigo de líneas "normales" en 1 query
                # (lo necesitamos como clave estable de DespieceLinea).
                normal_ids = [f["id"] for f in lineas_finales if f["tipo"] == "normal"]
                codigos_por_pk: dict = {}
                if normal_ids:
                    from apps.ingenieria.models import DespieceMaestroLinea
                    codigos_por_pk = dict(
                        DespieceMaestroLinea.objects.filter(pk__in=normal_ids)
                        .values_list("pk", "componente_codigo")
                    )

                consolidado: dict = {}
                for f in lineas_finales:
                    # Defensa: si pasara una línea sin producto (no debería tras
                    # la validación), se omite. NO crashea el armado.
                    if not f.get("producto_id"):
                        continue

                    # Clave estable en DespieceLinea:
                    #   - Consolidadas: CONS_{producto_id} (igual que el legacy
                    #     para mantener compatibilidad de datos históricos).
                    #   - Normales: componente_codigo del DML.
                    if f["tipo"] == "consolidada":
                        clave = f"CONS_{f['producto_id']}"
                    else:
                        clave = codigos_por_pk.get(f["id"]) or f"LIN_{f['id']}"

                    # Precio: snapshot de la línea final si existe; si no, el
                    # precio activo del producto.
                    precio_snapshot = f.get("precio_unitario")
                    if precio_snapshot in (None, ""):
                        prod_obj = f.get("producto")
                        precio_snapshot = (
                            getattr(prod_obj, "precio_unitario_real", None)
                            if prod_obj is not None else None
                        )

                    # Si el mismo producto principal aparece en varias líneas
                    # (mismo componente_codigo no debería repetirse en un mismo
                    # DM, pero por defensa sumamos cantidades).
                    if clave in consolidado:
                        consolidado[clave]["cantidad"] += Decimal(str(f["cantidad_total"] or 0))
                    else:
                        consolidado[clave] = {
                            "cantidad": Decimal(str(f["cantidad_total"] or 0)),
                            "precio_snapshot": precio_snapshot,
                            "producto": f.get("producto"),
                        }

                # Upsert de las líneas finales como DespieceLinea del PS.
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

                # Eliminar DespieceLinea OBSOLETAS del PS (cualquiera que no
                # esté en el set de líneas finales del modal actual). Esto
                # cubre la regla "no debe usar líneas antiguas".
                DespieceLinea.objects.filter(
                    proyecto_sistema=ps
                ).exclude(componente_codigo__in=consolidado.keys()).delete()

                apu_existia = APUProyecto.objects.filter(proyecto_sistema=ps).exists()

                from apps.presupuestos.services.apu_service import APUService
                apu = APUService.generar(ps)

                # ── Fase 11.4 · Trazabilidad explícita despiece → APU ───────
                # El botón "Armar mi APU" usa un único DespieceMaestro origen.
                # Sin este registro, el APU se marca como "legacy sin selección"
                # aunque haya sido creado por el flujo moderno. Replica el
                # patrón de APUMultiDespieceBuilder._sincronizar_inclusiones.
                from apps.common.choices import TipoAPU as _TipoAPU
                from apps.presupuestos.models import APUDespieceIncluido
                sistema_nombre = dm.subsistema.sistema.nombre if dm.subsistema_id else ""
                subsistema_nombre = dm.subsistema.nombre if dm.subsistema_id else ""
                APUDespieceIncluido.objects.update_or_create(
                    apu=apu,
                    despiece_maestro=dm,
                    defaults={
                        "sistema_nombre_snapshot": sistema_nombre,
                        "subsistema_nombre_snapshot": subsistema_nombre,
                        "orden": 0,
                        "activo": True,
                    },
                )
                # Anotar despiece_maestro + snapshots en las líneas MATERIALES
                # recién creadas para agrupar correctamente en apu_detail/PDFs.
                apu.lineas.filter(
                    tipo=_TipoAPU.MATERIALES,
                    despiece_maestro__isnull=True,
                ).update(
                    despiece_maestro=dm,
                    sistema_nombre_snapshot=sistema_nombre,
                    subsistema_nombre_snapshot=subsistema_nombre,
                )

        except Exception as exc:
            messages.error(request, f"Error al armar APU: {exc}")
            return redirect("ingenieria:despiece_maestro", pk=dm.pk)

        verbo = "actualizado" if apu_existia else "armado"
        messages.success(
            request,
            f"APU {verbo} correctamente. Base de rendimiento: {cantidad_base} {unidad_base}.",
        )

        registrar_log(
            request,
            accion="ARMAR_APU",
            descripcion=(
                f"APU {verbo} {log_msg_part} "
                f"desde despiece maestro #{dm.pk} — "
                f"{ps.proyecto.consecutivo} / {ps.sistema.nombre}"
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

def _filtrar_items_por_sia(apu, tipo_apu, items_data):
    """Fase 6L-H — Filtra items_data dejando solo los que están asociados al
    subsistema (SubsistemaItemAPU) bajo el tipo_apu indicado.

    Defensa de servidor para evitar que entren al APU ítems no configurados
    en el subsistema, incluso si el cliente manipula el POST. Si el
    subsistema no tiene ítems configurados para el tipo, devuelve lista
    vacía y la vista de origen muestra mensaje al usuario.
    """
    from apps.presupuestos.models import SubsistemaItemAPU

    ps = apu.proyecto_sistema
    if not ps or not ps.subsistema_id:
        return [], 0
    permitidos = set(
        SubsistemaItemAPU.objects
        .filter(subsistema_id=ps.subsistema_id, tipo=tipo_apu, activo=True,
                item_catalogo__activo=True)
        .values_list("item_catalogo_id", flat=True)
    )
    if not permitidos:
        return [], 0
    filtrados = [d for d in items_data if int(d.get("item_id", 0)) in permitidos]
    descartados = len(items_data) - len(filtrados)
    return filtrados, descartados


def _parse_items_catalogo(request):
    """
    Lee las filas de los modales "Configurar…" del APU.

    Campos por fila:
        item_id[]      — PK del ItemCatalogoAPU (obligatorio)
        cantidad_<pk>  — entero >= 1 (default 1)
        precio_<pk>    — precio unitario editado por el usuario (opcional)

    Se admite además el formato posicional legacy `cantidad[]` / `precio[]`,
    que sigue usando el modal de administración (su JS serializa a mano y solo
    emite filas marcadas, por lo que ahí las listas sí quedan alineadas).

    Por qué la clave por PK: los `item_id[]` son checkboxes y el navegador NO
    envía los desmarcados, mientras que los `<input>` de cantidad y precio se
    envían siempre. Con listas paralelas, desmarcar una fila intermedia
    desplazaba las cantidades de todas las siguientes y se guardaban valores
    del ítem equivocado. Indexar por PK elimina el problema de raíz.

    `precio_override` es un override por APU: vacío o no numérico → None y el
    servicio deriva el precio del catálogo. Un precio de 0 SÍ es un override
    válido (permite anular el costo de un ítem sin quitarlo); solo se
    descartan los negativos.
    """
    item_ids   = request.POST.getlist("item_id[]")
    cantidades = request.POST.getlist("cantidad[]")
    precios    = request.POST.getlist("precio[]")

    def _valor(nombre_keyed, lista, idx):
        """Clave por PK si existe; si no, posición en la lista legacy."""
        crudo = request.POST.get(nombre_keyed)
        if crudo is not None:
            return crudo
        return lista[idx] if idx < len(lista) else ""

    items_data = []
    for idx, iid in enumerate(item_ids):
        if not iid:
            continue
        try:
            item_id = int(iid)
        except (TypeError, ValueError):
            continue

        try:
            cantidad = max(int(_valor(f"cantidad_{iid}", cantidades, idx) or 1), 1)
        except (TypeError, ValueError):
            cantidad = 1

        precio_override = None
        raw = (_valor(f"precio_{iid}", precios, idx) or "").strip().replace(",", ".")
        if raw:
            try:
                valor = float(raw)
                if valor >= 0:
                    precio_override = valor
            except (TypeError, ValueError):
                precio_override = None

        items_data.append({
            "item_id": item_id,
            "cantidad": cantidad,
            "precio_override": precio_override,
        })
    return items_data


class APUManoObraView(GestionPresupuestosMixin, View):
    """
    POST /presupuestos/apu/<pk>/mano-obra/

    Registra mano de obra desde catálogo.
    Acepta:
      - preset_id: carga todos los ítems del preset seleccionado
      - item_id[] + cantidad[] + precio[]: selección manual ítem a ítem,
        con precio unitario editable por APU (ver _parse_items_catalogo).
    Borra líneas MANO_DE_OBRA previas antes de guardar (reemplaza).
    """
    def post(self, request, pk):
        apu = get_object_or_404(APUProyecto, pk=pk)
        blk = redirect_si_bloqueado(request, apu, reverse("presupuestos:apu_detail", args=[apu.pk]))
        if blk:
            return blk
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
                items_data = _parse_items_catalogo(request)

            if not items_data:
                messages.warning(request, "Seleccione al menos un ítem de mano de obra.")
                return redirect(reverse("presupuestos:apu_detail", args=[apu.pk]))

            # Fase 6L-13: el modal "Configurar mano de obra" es ahora la
            # biblioteca completa del catálogo. Se permite cualquier
            # ItemCatalogoAPU activo de tipo MANO_DE_OBRA — la restricción a
            # SubsistemaItemAPU se eliminó porque los predeterminados solo
            # actúan como marcado visual en el modal, no como tope.
            apu.lineas.filter(tipo="MANO_DE_OBRA").delete()
            svc = APUService.for_apu(apu)
            svc.generar_mano_obra_desde_catalogo(items_data)
            svc.finalizar()
            messages.success(request, f"Mano de obra registrada: {len(items_data)} cargo(s).")
        except Exception as exc:
            messages.error(request, f"Error al registrar mano de obra: {exc}")
            logger.exception("[APUManoObraView] Error APU %s", pk)

        return redirect(reverse("presupuestos:apu_detail", args=[apu.pk]))


class APUHerramientasView(GestionPresupuestosMixin, View):
    """
    POST /presupuestos/apu/<pk>/herramientas/

    Registra herramientas/equipos desde catálogo.
    Acepta item_id[] + cantidad[].
    Borra líneas HERRAMIENTAS_EQUIPOS previas antes de guardar (reemplaza).
    """
    def post(self, request, pk):
        apu = get_object_or_404(APUProyecto, pk=pk)
        blk = redirect_si_bloqueado(request, apu, reverse("presupuestos:apu_detail", args=[apu.pk]))
        if blk:
            return blk
        try:
            from apps.presupuestos.services.apu_service import APUService

            items_data = _parse_items_catalogo(request)

            if not items_data:
                messages.warning(request, "No se seleccionaron herramientas del catálogo.")
                return redirect(reverse("presupuestos:apu_detail", args=[apu.pk]))

            # Fase 6L-13: biblioteca completa — sin filtro por subsistema.
            apu.lineas.filter(tipo="HERRAMIENTAS_EQUIPOS").delete()
            svc = APUService.for_apu(apu)
            svc.generar_herramientas_desde_catalogo(items_data)
            svc.finalizar()
            messages.success(request, f"{len(items_data)} herramienta(s) registrada(s).")
        except Exception as exc:
            messages.error(request, f"Error al registrar herramientas: {exc}")
            logger.exception("[APUHerramientasView] Error APU %s", pk)

        return redirect(reverse("presupuestos:apu_detail", args=[apu.pk]))


class APUTransporteView(GestionPresupuestosMixin, View):
    """
    POST /presupuestos/apu/<pk>/transporte/

    Registra ítems de transporte del APU (retiro, envío, flete, etc.).
    El form envía múltiples filas: descripcion[] y precio_total[].
    Borra las líneas TRANSPORTE previas antes de crear las nuevas (reemplaza).
    """
    def post(self, request, pk):
        apu = get_object_or_404(APUProyecto, pk=pk)
        blk = redirect_si_bloqueado(request, apu, reverse("presupuestos:apu_detail", args=[apu.pk]))
        if blk:
            return blk
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


class APULineaUpdateView(GestionPresupuestosMixin, View):
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
        apu_pk = linea.apu_id

        blk = redirect_si_bloqueado(request, linea, reverse("presupuestos:apu_detail", args=[apu_pk]))
        if blk:
            return blk

        try:
            if linea.tipo == TipoAPU.ADMINISTRACION:
                porcentaje_str = request.POST.get("rendimiento", "").strip()
                precio_str = request.POST.get("precio_referencia", "").strip()

                linea.rendimiento = Decimal(str(porcentaje_str)) if porcentaje_str else linea.rendimiento
                linea.precio_referencia = Decimal(str(precio_str)) if precio_str else linea.precio_referencia

                valor_total = (linea.precio_referencia * linea.admin_cantidad * linea.admin_numero_meses * linea.rendimiento)
                linea.costo_total = valor_total
                linea.valor_total = valor_total
                linea.costo_unitario = valor_total
                linea.valor_unitario = valor_total
                linea.save(update_fields=["rendimiento", "precio_referencia", "costo_total", "valor_total", "costo_unitario", "valor_unitario", "updated_at"])
            else:
                rend_str = request.POST.get("rendimiento", "").strip()
                precio_str = request.POST.get("precio_referencia", "").strip()
                if rend_str:
                    linea.rendimiento = Decimal(str(float(rend_str)))
                if precio_str:
                    linea.precio_referencia = Decimal(str(float(precio_str)))
                linea.save(update_fields=["rendimiento", "precio_referencia", "updated_at"])
                linea.calcular() # El método calcular() ya hace el save final

            linea.apu.recalcular()
            messages.success(request, f"Línea «{linea.descripcion}» actualizada.")
        except Exception as exc:
            messages.error(request, f"Error al actualizar línea: {exc}")
            logger.exception("[APULineaUpdateView] Error línea %s", pk)

        return redirect(reverse("presupuestos:apu_detail", args=[apu_pk]))


class APUArchivarView(AdminGerenteRequiredMixin, View):
    """
    POST /presupuestos/apu/<pk>/archivar/

    Marca el APU como archivado. No borra líneas ni relaciones consolidadas.
    Funciona tanto para APUs individuales (incluyendo los que son origen de un
    consolidado) como para APUs consolidados (no toca los APUs origen).
    """

    def post(self, request, pk, *args, **kwargs):
        from django.utils import timezone
        apu = get_object_or_404(APUProyecto, pk=pk)
        if apu.archivado:
            messages.info(request, f"El APU «{apu.nombre}» ya estaba archivado.")
            return redirect("presupuestos:apu_detail", pk=pk)
        motivo = (request.POST.get("motivo") or "").strip()
        apu.archivado = True
        apu.fecha_archivado = timezone.now()
        apu.motivo_archivado = motivo
        usuario = _usuario_sistema(request)
        if usuario is not None:
            apu.archivado_por = usuario
        apu.save(update_fields=[
            "archivado", "fecha_archivado", "motivo_archivado",
            "archivado_por", "updated_at",
        ])
        messages.success(request, f"APU «{apu.nombre}» archivado. Trazabilidad preservada.")
        return redirect("presupuestos:apu_detail", pk=pk)


class APUProyectoEliminarView(View):
    """
    POST /presupuestos/apu/<pk>/eliminar/

    Eliminación física de un APU. Solo disponible para el rol
    ADMINISTRADOR global; el resto debe usar `apu_archivar` para
    conservar trazabilidad.

    Delega en `eliminar_apu_admin` (servicio explícito) que borra en orden:
    APUs consolidados dependientes, cotizaciones/snapshots, relaciones
    `APUConsolidadoOrigen`, `APUDespieceIncluido` y, finalmente, el APU.
    """

    def post(self, request, pk, *args, **kwargs):
        from apps.common.auth import es_admin, get_usuario_actual
        apu = get_object_or_404(APUProyecto, pk=pk)
        if not es_admin(request):
            messages.error(
                request,
                "Solo el administrador global puede eliminar físicamente un APU. "
                "Para conservar trazabilidad, archive el APU.",
            )
            return redirect("presupuestos:apu_detail", pk=pk)
        nombre = apu.nombre
        proyecto_pk = None
        try:
            proyecto_pk = apu.proyecto_sistema.proyecto_id
        except Exception:
            try:
                proyecto_pk = apu.proyecto_id
            except Exception:
                proyecto_pk = None
        try:
            from apps.presupuestos.services.admin_eliminacion import (
                eliminar_apu_admin,
            )
            eliminar_apu_admin(apu, usuario=get_usuario_actual(request))
        except Exception as exc:
            logger.exception("[APUProyectoEliminarView] Error en APU pk=%s", pk)
            messages.error(request, f"No se pudo eliminar el APU «{nombre}»: {exc}")
            return redirect("presupuestos:apu_detail", pk=pk)
        messages.success(request, f"APU «{nombre}» eliminado definitivamente.")
        if proyecto_pk:
            return redirect("comercial:proyecto_detail", pk=proyecto_pk)
        return redirect("presupuestos:apu_list")


class APULineaDeleteView(GestionPresupuestosMixin, View):
    """
    POST /presupuestos/apu/linea/<pk>/eliminar/

    Elimina una APULinea individual de tipo no-MATERIALES.
    El signal post_delete dispara apu.recalcular() automáticamente.
    """
    def post(self, request, pk):
        from apps.presupuestos.models import APULinea
        linea = get_object_or_404(APULinea, pk=pk)
        blk = redirect_si_bloqueado(request, linea, reverse("presupuestos:apu_detail", args=[linea.apu_id]))
        if blk:
            return blk
        if linea.tipo == "MATERIALES":
            messages.error(request, "Las líneas de materiales se regeneran desde el despiece.")
            return redirect(reverse("presupuestos:apu_detail", args=[linea.apu_id]))
        apu_pk = linea.apu_id
        desc = linea.descripcion
        linea.delete()
        messages.success(request, f"Línea «{desc}» eliminada.")
        return redirect(reverse("presupuestos:apu_detail", args=[apu_pk]))


class APUAdminView(GestionPresupuestosMixin, View):
    """
    POST /presupuestos/apu/<pk>/administrativo/

    Recibe los ítems seleccionados del modal "Configurar administración":
      item_id[]    — PK del ItemCatalogoAPU
      cantidad[]   — cantidad para cada ítem
      precio[]     — precio unitario editado por el usuario (opcional)
      porcentaje[] — porcentaje en % (e.g. 100 → 1.0, 50 → 0.5)

    Llama a generar_administracion_desde_catalogo() con la fórmula:
      valor_total = valor_dia * dias_duracion * cantidad * porcentaje
    Reemplaza todas las líneas ADMINISTRACION previas.
    """
    def post(self, request, pk):
        apu = get_object_or_404(APUProyecto, pk=pk)
        blk = redirect_si_bloqueado(request, apu, reverse("presupuestos:apu_detail", args=[apu.pk]))
        if blk:
            return blk
        try:
            from apps.presupuestos.services.apu_service import APUService

            # item_id / cantidad / precio comparten el parser de los demás
            # modales; administración añade su propio porcentaje por fila.
            items_data = _parse_items_catalogo(request)
            porcentajes = request.POST.getlist("porcentaje[]")

            for idx, fila in enumerate(items_data):
                try:
                    pct_pct = float(porcentajes[idx]) if idx < len(porcentajes) else 100.0
                except (ValueError, TypeError):
                    pct_pct = 100.0
                fila["porcentaje"] = max(pct_pct / 100.0, 0.0)

            if not items_data:
                messages.warning(request, "No se seleccionaron ítems de administración válidos.")
                return redirect(reverse("presupuestos:apu_detail", args=[apu.pk]))

            svc = APUService.for_apu(apu)
            svc.generar_administracion_desde_catalogo(items_data)
            svc.finalizar()
            messages.success(request, f"{len(items_data)} ítem(s) de administración registrados.")
        except Exception as exc:
            messages.error(request, f"Error al registrar administrativo: {exc}")
            logger.exception("[APUAdminView] Error APU %s", pk)

        return redirect(reverse("presupuestos:apu_detail", args=[apu.pk]))


# ══════════════════════════════════════════════════════════════════════════════
# PÓLIZAS APU
# ══════════════════════════════════════════════════════════════════════════════

class APUPolizasView(GestionPresupuestosMixin, View):
    """
    POST /presupuestos/apu/<pk>/polizas/

    Recibe la tabla de pólizas en formato de filas indexadas (row-indexed):
      nombre_0, porcentaje_0, base_calculo_0, activa_0
      nombre_1, porcentaje_1, base_calculo_1, activa_1
      ...
      polizas_count — número total de filas enviadas

    Reemplaza completamente el conjunto de pólizas del APU:
      - Elimina las pólizas existentes
      - Crea las nuevas con los valores enviados
      - Llama apu.recalcular() para actualizar subtotal_polizas
    """

    def post(self, request, pk):
        from django.db import transaction
        apu = get_object_or_404(APUProyecto, pk=pk)
        blk = redirect_si_bloqueado(request, apu, reverse("presupuestos:apu_detail", args=[apu.pk]))
        if blk:
            return blk

        try:
            count_str = request.POST.get("polizas_count", "0")
            count = max(int(count_str or 0), 0)

            polizas_data = []
            bases_validas = {c[0] for c in APUPoliza.BASE_CHOICES}
            for i in range(count):
                nombre     = request.POST.get(f"nombre_{i}", "").strip()
                pct_str    = request.POST.get(f"porcentaje_{i}", "0").strip()
                # Issue 6: múltiples bases por póliza (checkboxes: bases_calculo_i[])
                bases_raw  = request.POST.getlist(f"bases_calculo_{i}[]")
                if not bases_raw:
                    # Compatibilidad: intentar base única legada
                    base_single = request.POST.get(f"base_calculo_{i}", "total_directo").strip()
                    bases_raw = [base_single] if base_single else ["total_directo"]
                activa_raw = request.POST.get(f"activa_{i}", "")

                if not nombre:
                    continue  # Fila vacía — omitir

                try:
                    porcentaje = Decimal(pct_str or "0")
                except Exception:
                    porcentaje = Decimal("0")
                if porcentaje < 0:
                    porcentaje = Decimal("0")

                # Filtrar solo bases válidas
                bases_list = [b for b in bases_raw if b in bases_validas]
                if not bases_list:
                    bases_list = ["total_directo"]
                # Base legada (primera seleccionada, para compatibilidad)
                base_legacy = bases_list[0]

                # El checkbox activa_N solo aparece en POST cuando está tildado.
                activa = bool(activa_raw)

                polizas_data.append(dict(
                    nombre=nombre,
                    porcentaje=porcentaje,
                    base_calculo=base_legacy,
                    bases_calculo=bases_list,
                    activa=activa,
                    orden=i,
                ))

            with transaction.atomic():
                apu.polizas.all().delete()
                nuevas = [APUPoliza(apu=apu, **d) for d in polizas_data]
                APUPoliza.objects.bulk_create(nuevas)
                # recalcular() llama _recalcular_polizas() internamente
                apu.recalcular()

            messages.success(
                request,
                f"{len(polizas_data)} póliza(s) guardadas. "
                f"Subtotal: ${apu.subtotal_polizas:,.2f}",
            )

        except Exception as exc:
            messages.error(request, f"Error al guardar pólizas: {exc}")
            logger.exception("[APUPolizasView] Error APU %s", pk)

        return redirect(reverse("presupuestos:apu_detail", args=[apu.pk]))


# ══════════════════════════════════════════════════════════════════════════════
# CATÁLOGO APU — Vista principal + CRUD
# ══════════════════════════════════════════════════════════════════════════════

class CatalogoAPUView(APUSistemaAccesoMixin, ListView):
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

class CategoriaItemAPUCreateView(APUSistemaAccesoMixin, CreateView):
    model = CategoriaItemAPU
    form_class = CategoriaItemAPUForm
    template_name = "presupuestos/catalogo_apu_categoria_form.html"
    success_url = reverse_lazy("presupuestos:catalogo_apu")


class CategoriaItemAPUUpdateView(APUSistemaAccesoMixin, UpdateView):
    model = CategoriaItemAPU
    form_class = CategoriaItemAPUForm
    template_name = "presupuestos/catalogo_apu_categoria_form.html"
    success_url = reverse_lazy("presupuestos:catalogo_apu")


class CategoriaItemAPUDeleteView(APUSistemaAccesoMixin, DeleteView):
    model = CategoriaItemAPU
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("presupuestos:catalogo_apu")


# ── ItemCatalogoAPU CRUD ──────────────────────────────────────────────────────

class ItemCatalogoAPUCreateView(APUSistemaAccesoMixin, CreateView):
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


class ItemCatalogoAPUUpdateView(APUSistemaAccesoMixin, UpdateView):
    model = ItemCatalogoAPU
    form_class = ItemCatalogoAPUForm
    template_name = "presupuestos/catalogo_apu_item_form.html"
    success_url = reverse_lazy("presupuestos:catalogo_apu")


class ItemCatalogoAPUDeleteView(APUSistemaAccesoMixin, DeleteView):
    model = ItemCatalogoAPU
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("presupuestos:catalogo_apu")


# ── CuadrillaPreset CRUD ──────────────────────────────────────────────────────

class CuadrillaPresetCreateView(AdminRequiredMixin, CreateView):
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


class CuadrillaPresetUpdateView(AdminRequiredMixin, UpdateView):
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


class CuadrillaPresetDeleteView(AdminRequiredMixin, DeleteView):
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


class APUPDFInternoView(DescargaPDFMixin, View):
    """
    GET /presupuestos/apu/<pk>/pdf-interno/

    Documento técnico interno: puede mostrar costos internos, rendimientos y
    detalles que no verá el cliente. Se genera con WeasyPrint en memoria y se
    entrega como attachment. No se persiste archivo en disco.
    """
    def get(self, request, pk):
        from weasyprint import HTML  # import perezoso: errores de sistema afloran al usar el botón

        apu = get_object_or_404(APUProyecto, pk=pk)
        lineas = apu.lineas.order_by("tipo", "descripcion").select_related(
            "despiece_linea__producto", "item_catalogo",
        )
        resumen = apu.get_resumen_cotizacion()
        # Fase 11.5.2 — proyecto contenedor (sirve tanto a individual como a
        # consolidado, donde proyecto_sistema puede ser None).
        proyecto = apu.get_proyecto()
        ctx = {
            "apu": apu,
            "lineas": lineas,
            "resumen": resumen,
            "proyecto": proyecto,
            "fecha_generacion": date.today().strftime("%d/%m/%Y"),
            "request": request,
        }
        if apu.es_consolidado:
            ctx.update(_build_apu_consolidado_context(apu))
        html_str = render_to_string("presupuestos/pdf/apu_pdf_interno.html", ctx)
        pdf_bytes = HTML(string=html_str, base_url=request.build_absolute_uri("/")).write_pdf()
        consecutivo = getattr(apu, "consecutivo", None) or apu.pk
        filename = f"APU_Interno_{consecutivo}.pdf"
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class APUPDFClienteView(DescargaPDFMixin, View):
    """
    GET /presupuestos/apu/<pk>/pdf-cliente/

    Cotización comercial para enviar al cliente. Usa get_resumen_cotizacion()
    como única fuente de verdad para totales (garantía Red Shield, AIU aprobado,
    IVA sobre Utilidad, total final). No muestra costos internos, rendimientos
    ni fórmulas. Se genera con WeasyPrint en memoria y se entrega como
    attachment. No se persiste archivo en disco.
    """
    def get(self, request, pk):
        from decimal import Decimal
        from weasyprint import HTML  # import perezoso

        apu = get_object_or_404(APUProyecto, pk=pk)
        resumen = apu.get_resumen_cotizacion()
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
                        if key == "area_m2":
                            unidad_principal = "m²"
                    except Exception:
                        pass
                    break
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

        # ── Construir ítem comercial único para cotización cliente ───────────
        # Un solo ítem representa el alcance completo del sistema.
        # El valor unitario deriva de resumen.subtotal_con_aiu / cantidad.
        # No se expone el desglose interno de costos por categoría.
        qty = qty_principal if qty_principal > 0 else Decimal("1")
        subtotal_comercial = Decimal(str(resumen.get("subtotal_con_aiu", 0) or 0))
        valor_unitario_c = (subtotal_comercial / qty).quantize(Decimal("0.01")) if subtotal_comercial else Decimal("0")
        items_cliente = [{
            "item": "1,0",
            "descripcion": desc_sistema,
            "unidad": unidad_principal,
            "cantidad": qty,
            "valor_unitario": valor_unitario_c,
            "subtotal": subtotal_comercial,
        }]

        # Fase 11.5.2 — proyecto contenedor para cabecera comercial
        # (en consolidado ps puede ser None pero apu.proyecto sí existe).
        proyecto = apu.get_proyecto()
        ctx = {
            "apu": apu,
            "ps": ps,
            "proyecto": proyecto,
            "resumen": resumen,
            "items_cliente": items_cliente,
            "fecha_generacion": date.today().strftime("%d/%m/%Y"),
            "request": request,
        }
        if apu.es_consolidado:
            ctx.update(_build_apu_consolidado_context(apu))
        html_str = render_to_string("presupuestos/pdf/apu_pdf_cliente.html", ctx)
        pdf_bytes = HTML(string=html_str, base_url=request.build_absolute_uri("/")).write_pdf()
        consecutivo = getattr(apu, "consecutivo", None) or apu.pk
        filename = f"Cotizacion_Cliente_{consecutivo}.pdf"
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


# ═══════════════════════════════════════════════════════════════════════════════
# Fase 12 — PDFs desde snapshot inmutable (CotizacionAPU)
# ═══════════════════════════════════════════════════════════════════════════════

class CotizacionPDFInternoView(DescargaPDFMixin, View):
    """
    GET /presupuestos/cotizacion/<pk>/pdf-interno/

    Genera PDF Interno desde un snapshot APROBADO. NO toca datos vivos.
    Se entrega como attachment, sin persistir archivo en disco.
    """
    def get(self, request, pk):
        from weasyprint import HTML
        from apps.presupuestos.models import CotizacionAPU
        from apps.presupuestos.services import CotizacionSnapshotService

        snapshot = get_object_or_404(CotizacionAPU, pk=pk)
        ctx = CotizacionSnapshotService.construir_contexto_pdf(snapshot)
        apu = snapshot.apu  # solo para que la plantilla pueda referenciar nombre/tipo
        ctx.update({
            "apu": apu,
            "lineas": apu.lineas.order_by("tipo", "descripcion").select_related(
                "despiece_linea__producto", "item_catalogo",
            ),
            "proyecto": snapshot.proyecto,
            "fecha_generacion": date.today().strftime("%d/%m/%Y"),
            "request": request,
        })
        if apu.es_consolidado:
            ctx.update(_build_apu_consolidado_context(apu))
        html_str = render_to_string("presupuestos/pdf/apu_pdf_interno.html", ctx)
        pdf_bytes = HTML(string=html_str, base_url=request.build_absolute_uri("/")).write_pdf()
        filename = f"APU_Interno_Aprobado_{snapshot.consecutivo_cotizacion}.pdf"
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class CotizacionPDFClienteView(DescargaPDFMixin, View):
    """
    GET /presupuestos/cotizacion/<pk>/pdf-cliente/

    Genera PDF Cliente desde un snapshot APROBADO. NO toca datos vivos.
    Reutiliza la plantilla del PDF Cliente vivo pasando el contexto rehidratado.
    """
    def get(self, request, pk):
        from decimal import Decimal as _Dec
        from weasyprint import HTML
        from apps.presupuestos.models import CotizacionAPU
        from apps.presupuestos.services import CotizacionSnapshotService

        snapshot = get_object_or_404(CotizacionAPU, pk=pk)
        ctx = CotizacionSnapshotService.construir_contexto_pdf(snapshot)
        apu = snapshot.apu
        ps = apu.proyecto_sistema
        lineas_qs = list(apu.lineas.order_by("tipo", "descripcion").select_related(
            "despiece_linea__producto__unidad", "item_catalogo",
        ))

        # Reconstruir secciones comerciales con los subtotales del snapshot.
        moneda_principal = snapshot.moneda_snapshot or "COP"
        unidad_principal = "und"
        qty_principal = _Dec("1")
        desc_sistema = apu.nombre or "Sistema"

        if ps:
            params = ps.parametros_entrada or {}
            for key in ("total_powergrip", "cantidad", "area_m2"):
                if key in params:
                    try:
                        qty_principal = _Dec(str(params[key]))
                        if key == "area_m2":
                            unidad_principal = "m²"
                    except Exception:
                        pass
                    break
            for linea in lineas_qs:
                if linea.tipo == "MATERIALES" and linea.despiece_linea and linea.despiece_linea.producto:
                    prod = linea.despiece_linea.producto
                    if prod.unidad:
                        unidad_principal = str(prod.unidad)
                    break
            desc_sistema = (
                f"{ps.sistema.nombre}"
                + (f" / {ps.subsistema.nombre}" if ps.subsistema else "")
            )

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
            valor_subtotal = sum(_Dec(str(l.valor_total or 0)) for l in lineas_tipo)
            if valor_subtotal <= 0:
                continue
            qty = qty_principal if qty_principal > 0 else _Dec("1")
            valor_unitario = (valor_subtotal / qty).quantize(_Dec("0.1"))
            iva_factor = (snapshot.iva_pct or _Dec("0")) / _Dec("100")
            iva_monto = (valor_subtotal * iva_factor).quantize(_Dec("0.1")) if snapshot.aplica_iva else _Dec("0")
            secciones.append({
                "tipo": tipo_key,
                "label": tipo_label,
                "descripcion": f"{tipo_label} — {desc_sistema}",
                "unidad": unidad_principal,
                "cantidad": qty,
                "valor_unitario": valor_unitario,
                "subtotal": valor_subtotal,
                "iva_monto": iva_monto,
                "total_con_iva": valor_subtotal + iva_monto,
                "moneda": moneda_sec,
                "aplica_iva": snapshot.aplica_iva,
                "iva_pct": snapshot.iva_pct,
            })

        productos_con_ficha = []
        vistos = set()
        for linea in lineas_qs:
            if linea.despiece_linea and linea.despiece_linea.producto:
                prod = linea.despiece_linea.producto
                if prod.pk not in vistos and prod.ficha_tecnica:
                    productos_con_ficha.append(prod)
                    vistos.add(prod.pk)

        ctx.update({
            "apu": apu,
            "ps": ps,
            "proyecto": snapshot.proyecto,
            "secciones": secciones,
            "productos_con_ficha": productos_con_ficha,
            "fecha_generacion": date.today().strftime("%d/%m/%Y"),
            "request": request,
        })
        if apu.es_consolidado:
            ctx.update(_build_apu_consolidado_context(apu))
        html_str = render_to_string("presupuestos/pdf/apu_pdf_cliente.html", ctx)
        pdf_bytes = HTML(string=html_str, base_url=request.build_absolute_uri("/")).write_pdf()
        filename = f"Cotizacion_Cliente_Aprobada_{snapshot.consecutivo_cotizacion}.pdf"
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class APUEnviarRevisionView(GestionPresupuestosMixin, View):
    """
    POST /presupuestos/apu/<pk>/enviar-revision/
    Asigna revisor, marca el APU como enviado a revisión y avanza el estado del proyecto.
    """
    def post(self, request, pk):
        from django.utils import timezone as tz
        from apps.configuracion.models import ConfiguracionSistema
        apu = get_object_or_404(APUProyecto, pk=pk)

        # Fase 12.2 — Gate de permisos
        if not puede_enviar_a_revision(request, apu):
            registrar_log(
                request, accion="APROBACION_DENEGADA",
                descripcion=f"Intento no autorizado de enviar APU {apu.pk} a revisión.",
                modelo_afectado="APUProyecto", objeto_id=apu.pk,
            )
            messages.error(
                request,
                "No tiene permiso para enviar este APU a revisión.",
            )
            return redirect(reverse("presupuestos:apu_detail", args=[pk]))

        # Fase 12.3 — Bloqueo: no reenviar a revisión un APU ya aprobado.
        ya_aprobado = bool(
            (apu.modalidad_aiu_seleccionada or "").strip()
            or apu.fecha_aprobacion
            or apu.aprobado_por_id
        )
        if ya_aprobado:
            registrar_log(
                request, accion="APROBACION_DENEGADA",
                descripcion=f"Intento de reenviar a revisión APU {apu.pk} ya aprobado.",
                modelo_afectado="APUProyecto", objeto_id=apu.pk,
            )
            messages.error(
                request,
                "Este APU ya fue aprobado y no puede reenviarse a revisión. "
                "Si requiere cambios, primero debe resetear la modalidad según el flujo autorizado.",
            )
            return redirect(reverse("presupuestos:apu_detail", args=[pk]))

        pendientes = lineas_pendientes_producto(apu.proyecto_sistema)
        if pendientes:
            codigos = ", ".join(l.componente_codigo for l in pendientes)
            messages.error(
                request,
                f"No se puede remitir a revisión: los siguientes componentes requieren que se "
                f"asigne un producto antes de calcular su cantidad: {codigos}.",
            )
            return redirect(reverse("presupuestos:apu_detail", args=[pk]))

        try:
            revisor_pk = request.POST.get("revisor_id", "").strip()
            revisor = None
            if revisor_pk:
                revisor = ConfiguracionSistema.objects.filter(pk=revisor_pk).first()

            # Segregación de funciones: no tiene sentido enviarse el APU a uno
            # mismo, porque luego no podría autorizarlo. Se rechaza aquí con un
            # mensaje claro en lugar de dejar el APU en un callejón sin salida.
            _remitente = get_usuario_actual(request)
            if revisor and _remitente and revisor.pk == _remitente.pk:
                messages.error(
                    request,
                    "No puede asignarse a usted mismo como autorizador: quien "
                    "envía el presupuesto no puede autorizarlo. Seleccione a "
                    "otra persona como autorizador.",
                )
                return redirect(reverse("presupuestos:apu_detail", args=[pk]))

            # Guardar descripción si viene del modal "Calcular Presupuesto"
            descripcion_modal = request.POST.get("descripcion_modal", "").strip()
            if descripcion_modal:
                apu.descripcion = descripcion_modal

            update_fields = ["fecha_envio_revision", "enviado_por", "updated_at"]
            apu.fecha_envio_revision = tz.now()
            # Queda registrado quién envía: es la base de la regla
            # "quien envía no autoriza" (ver apps/common/auth.py).
            apu.enviado_por = get_usuario_actual(request)
            if revisor:
                apu.revisor = revisor
                update_fields.append("revisor")
            if descripcion_modal:
                update_fields.append("descripcion")

            # Guardar APUs incluidos en el presupuesto final
            apus_incluidos_raw = request.POST.getlist("apus_incluidos")
            apus_incluidos_ids = []
            for v in apus_incluidos_raw:
                try:
                    apus_incluidos_ids.append(int(v))
                except (ValueError, TypeError):
                    pass
            apu.apus_presupuesto_ids = apus_incluidos_ids
            update_fields.append("apus_presupuesto_ids")

            # Un solo save con todos los campos acumulados
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

            apus_txt = ""
            if apus_incluidos_ids:
                apus_txt = f" APUs incluidos en presupuesto: {', '.join(str(x) for x in apus_incluidos_ids)}."

            revisor_txt = f" Autorizador: {revisor}." if revisor else ""
            registrar_log(
                request, accion="ENVIAR_REVISION",
                descripcion=(
                    f"APU {apu.pk} ({apu.nombre}) enviado a cálculo de presupuesto."
                    f"{revisor_txt}{apus_txt}"
                ),
                modelo_afectado="APUProyecto", objeto_id=apu.pk,
            )
            messages.success(
                request,
                f"APU «{apu.nombre}» enviado a revisión.{revisor_txt}",
            )
        except Exception as exc:
            messages.error(request, f"Error al enviar a revisión: {exc}")
            logger.exception("[APUEnviarRevisionView] Error APU %s", pk)

        return redirect(reverse("presupuestos:apu_detail", args=[pk]))


class APURevisarView(GestionPresupuestosMixin, View):
    """
    GET /presupuestos/apu/<pk>/revisar/
    Redirige a la nueva vista de revisión por proyecto (ProyectoRevisarView).
    Se conserva el URL para compatibilidad con links existentes.
    """

    def get(self, request, pk):
        apu = get_object_or_404(APUProyecto, pk=pk)
        proyecto = apu.get_proyecto()
        if proyecto:
            return redirect(reverse("presupuestos:proyecto_revisar", args=[proyecto.pk]))
        return redirect(reverse("presupuestos:apu_detail", args=[pk]))

    def post(self, request, pk):
        return self.get(request, pk)

    # ── Código legado preservado por si se necesita rollback ──────────────────
    def _render_legado(self, request, pk, preview: bool = False):
        from decimal import Decimal, InvalidOperation
        from apps.configuracion.models import ConfiguracionSistema
        apu = get_object_or_404(APUProyecto, pk=pk)
        # Fase 12.3 ext — Gate por unidad: ADMINISTRADOR siempre, resto sólo su unidad.
        # Bypass: el creador del proyecto del APU siempre puede revisar.
        _usuario = get_usuario_actual(request)
        _proyecto = apu.get_proyecto()
        _creado_por_id = getattr(_proyecto, "creado_por_id", None)
        _es_creador = (
            _usuario is not None
            and _creado_por_id is not None
            and _usuario.pk == _creado_por_id
        )
        # El revisor asignado siempre puede acceder aunque no sea creador ni su unidad.
        _es_revisor_asignado = puede_aprobar_apu(request, apu)
        if not _es_creador and not _es_revisor_asignado and not puede_gestionar_unidad(request, _apu_unidad(apu)):
            messages.error(request, "No tiene permiso para acceder a información de otra unidad.")
            return redirect("comercial:dashboard")
        if not apu.fecha_envio_revision:
            messages.warning(request, "Este APU aún no ha sido enviado a revisión.")
            return redirect(reverse("presupuestos:apu_detail", args=[pk]))

        # Issue 2 — Determinar si el usuario puede ver el detalle de revisión.
        # Solo el revisor asignado y el administrador ven el formulario de aprobación.
        # El creador (emisor) y otros usuarios ven solo el resumen de estado.
        _puede_ver_detalle = puede_aprobar_apu(request, apu)

        efectivos = apu.get_aiu_pct_efectivos()
        pct_form = {
            "admin": efectivos["admin"],
            "imprevistos": efectivos["imprevistos"],
            "utilidad": efectivos["utilidad"],
        }
        pct_override = None
        if preview:
            try:
                def _p(name, fallback):
                    raw = request.POST.get(name, "")
                    if str(raw).strip() == "":
                        return Decimal(str(fallback))
                    return Decimal(str(raw).replace(",", "."))
                pct_form["admin"] = _p("aiu_final_admin_pct", efectivos["admin"])
                pct_form["imprevistos"] = _p("aiu_final_imprevistos_pct", efectivos["imprevistos"])
                pct_form["utilidad"] = _p("aiu_final_utilidad_pct", efectivos["utilidad"])
                if any(v < 0 for v in pct_form.values()):
                    raise ValueError("Los porcentajes no pueden ser negativos.")
                pct_override = pct_form
            except (InvalidOperation, ValueError) as exc:
                messages.error(request, f"Porcentajes inválidos: {exc}")

        # Fase 12.2 — Contexto de permisos
        usuario_actual = get_usuario_actual(request)
        puede_aprobar = puede_aprobar_apu(request, apu)
        es_aprobador_asignado = (
            usuario_actual is not None
            and apu.revisor_id is not None
            and apu.revisor_id == usuario_actual.pk
        )
        es_administrador = es_admin(request)

        modalidades_aiu_actual = apu.calcular_modalidades_aiu(pct_override=pct_override)

        # Fase 13 — Otros APUs incluidos en el presupuesto consolidado
        apus_incluidos_lista = []
        total_m1_combinado = None
        total_m2_combinado = None
        if apu.apus_presupuesto_ids:
            apus_incluidos_qs = APUProyecto.objects.filter(
                pk__in=apu.apus_presupuesto_ids
            ).only("pk", "nombre", "total_valor_venta", "modalidad_aiu_seleccionada",
                   "subtotal_materiales")
            for otro_apu in apus_incluidos_qs:
                try:
                    otro_m = otro_apu.calcular_modalidades_aiu()
                    apus_incluidos_lista.append({
                        "apu": otro_apu,
                        "modalidades": otro_m,
                    })
                except Exception:
                    apus_incluidos_lista.append({
                        "apu": otro_apu,
                        "modalidades": None,
                    })

        # ── Cálculo consolidado: sumar subtotales de TODOS los APUs incluidos ──────
        # Si hay APUs incluidos, calcular UNA sola modalidad unificada en lugar
        # de mostrar cuadros separados. Los porcentajes I y U son los del APU principal.
        modalidades_consolidadas = None
        if apus_incluidos_lista:
            from decimal import Decimal as _D
            from collections import OrderedDict as _OD
            try:
                # Subtotales del APU principal
                _ms = modalidades_aiu_actual["subtotales"]
                c_mat    = _D(str(_ms.get("materiales", 0) or 0))
                c_herr   = _D(str(_ms.get("herramientas", 0) or 0))
                c_transp = _D(str(_ms.get("transporte", 0) or 0))
                c_mo     = _D(str(_ms.get("mano_de_obra", 0) or 0))
                c_admin  = _D(str(_ms.get("administracion", 0) or 0))
                c_pol    = _D(str(_ms.get("polizas", 0) or 0))

                # Sumar subtotales de cada APU incluido
                for entry in apus_incluidos_lista:
                    em = entry.get("modalidades")
                    if not em:
                        continue
                    ems = em.get("subtotales", {})
                    c_mat    += _D(str(ems.get("materiales", 0) or 0))
                    c_herr   += _D(str(ems.get("herramientas", 0) or 0))
                    c_transp += _D(str(ems.get("transporte", 0) or 0))
                    c_mo     += _D(str(ems.get("mano_de_obra", 0) or 0))
                    c_admin  += _D(str(ems.get("administracion", 0) or 0))
                    c_pol    += _D(str(ems.get("polizas", 0) or 0))

                # Porcentajes I y U del APU principal (pueden ser overrideados por el revisor)
                _pct_I = _D(str(pct_form.get("imprevistos", efectivos["imprevistos"])))
                _pct_U = _D(str(pct_form.get("utilidad", efectivos["utilidad"])))
                _Q = _D("0.01")

                c_admin_total = c_admin + c_pol

                # Modalidad 1: base = mat + herr + transp + mo
                _base_m1 = c_mat + c_herr + c_transp + c_mo
                _pct_admin_m1 = (c_admin_total / _base_m1 * 100).quantize(_Q) if _base_m1 else _D("0")
                _I_m1  = (_base_m1 * _pct_I / 100).quantize(_Q)
                _U_m1  = (_base_m1 * _pct_U / 100).quantize(_Q)
                _sub1  = _base_m1 + c_admin_total + _I_m1 + _U_m1
                _iva1  = (_sub1 * _D(str(apu.iva_pct or 0)) / 100).quantize(_Q) if apu.aplica_iva else _D("0")
                _tot1  = _sub1 + _iva1

                # Modalidad 2: base = herr + transp + mo (mat a precio venta)
                _base_m2 = c_herr + c_transp + c_mo
                _pct_admin_m2 = (c_admin_total / _base_m2 * 100).quantize(_Q) if _base_m2 else _D("0")
                _I_m2  = (_base_m2 * _pct_I / 100).quantize(_Q)
                _U_m2  = (_base_m2 * _pct_U / 100).quantize(_Q)
                _sub2  = c_mat + _base_m2 + c_admin_total + _I_m2 + _U_m2
                _iva2  = (_sub2 * _D(str(apu.iva_pct or 0)) / 100).quantize(_Q) if apu.aplica_iva else _D("0")
                _tot2  = _sub2 + _iva2

                _subs_comb = _OD([
                    ("materiales",    c_mat),
                    ("herramientas",  c_herr),
                    ("mano_de_obra",  c_mo),
                    ("mano_obra",     c_mo),
                    ("transporte",    c_transp),
                    ("administracion", c_admin),
                    ("polizas",       c_pol),
                    ("total",         c_mat + c_herr + c_transp + c_mo + c_admin_total),
                ])
                modalidades_consolidadas = {
                    "porcentajes": {
                        "admin": _pct_admin_m1,
                        "imprevistos": _pct_I,
                        "utilidad": _pct_U,
                        "es_final": efectivos["es_final"],
                    },
                    "subtotales": _subs_comb,
                    "modalidad1": {
                        "label": "AIU sobre todos los costos directos",
                        "base": _base_m1,
                        "admin": c_admin,
                        "polizas": c_pol,
                        "admin_total": c_admin_total,
                        "admin_pct": _pct_admin_m1,
                        "imprevistos": _I_m1,
                        "utilidad": _U_m1,
                        "subtotal_con_aiu": _sub1,
                        "iva_valor": _iva1,
                        "total_con_iva": _tot1,
                        "gran_total": _tot1,
                        "valor_total_mat": c_mat,
                    },
                    "modalidad2": {
                        "label": "AIU sobre costos directos sin materiales",
                        "base": _base_m2,
                        "admin": c_admin,
                        "polizas": c_pol,
                        "admin_total": c_admin_total,
                        "admin_pct": _pct_admin_m2,
                        "imprevistos": _I_m2,
                        "utilidad": _U_m2,
                        "subtotal_con_aiu": _sub2,
                        "iva_valor": _iva2,
                        "total_con_iva": _tot2,
                        "gran_total": _tot2,
                        "valor_total_mat": c_mat,
                    },
                    "n_apus": 1 + len(apus_incluidos_lista),
                }
            except Exception:
                pass

        ctx = {
            "apu": apu,
            "modalidades_aiu": modalidades_aiu_actual,
            "modalidades_consolidadas": modalidades_consolidadas,
            "pct_form": pct_form,
            "pct_efectivos": efectivos,
            "es_preview": preview and pct_override is not None,
            "revisores": ConfiguracionSistema.objects.filter(activo=True).order_by("nombre_completo"),
            "ya_aprobado": bool(apu.modalidad_aiu_seleccionada),
            "puede_aprobar": puede_aprobar,
            "es_aprobador_asignado": es_aprobador_asignado,
            "es_administrador": es_administrador,
            "usuario_actual": usuario_actual,
            # Issue 2 — Solo_vista: el emisor/otros ven estado sin formulario de aprobación
            "solo_vista": not _puede_ver_detalle,
            "es_emisor": _es_creador and not _puede_ver_detalle,
            # Fase 13 — presupuesto consolidado
            "apus_incluidos_lista": apus_incluidos_lista,
        }
        return render(request, self.template_name, ctx)


class APUAprobarModalidadView(GestionPresupuestosMixin, View):
    """
    POST /presupuestos/apu/<pk>/aprobar-modalidad/
    Guarda la modalidad AIU seleccionada por el revisor, junto con los
    porcentajes finales A/I/U (Fase 10A), y avanza el estado del proyecto a COTIZADO.
    """
    def post(self, request, pk):
        from django.utils import timezone as tz
        from decimal import Decimal, InvalidOperation
        from apps.common.choices import EstadoProyecto, EstadoSolicitud
        apu = get_object_or_404(APUProyecto, pk=pk)

        # Fase 12.2 — Gate de permisos
        if not puede_aprobar_apu(request, apu):
            registrar_log(
                request, accion="APROBACION_DENEGADA",
                descripcion=f"Intento no autorizado de aprobar APU {apu.pk}.",
                modelo_afectado="APUProyecto", objeto_id=apu.pk,
            )
            messages.error(
                request,
                "No tiene permiso para aprobar este APU. Solo el aprobador "
                "asignado puede realizar esta acción.",
            )
            return redirect(reverse("presupuestos:apu_detail", args=[pk]))

        pendientes = lineas_pendientes_producto(apu.proyecto_sistema)
        if pendientes:
            codigos = ", ".join(l.componente_codigo for l in pendientes)
            messages.error(
                request,
                f"No se puede aprobar el APU: los siguientes componentes requieren que se "
                f"asigne un producto antes de calcular su cantidad: {codigos}.",
            )
            return redirect(reverse("presupuestos:apu_detail", args=[pk]))

        try:
            modalidad = request.POST.get("modalidad_aiu", "").strip()
            if modalidad not in ("1", "2"):
                messages.error(request, "Modalidad AIU inválida. Solo se admiten Modalidad 1 o Modalidad 2 en esta fase.")
                return redirect(reverse("presupuestos:apu_revisar", args=[pk]))

            # Validar porcentajes A/I/U finales (opcionales — si vienen se persisten).
            def _parse_pct(raw, label):
                if raw is None or str(raw).strip() == "":
                    return None
                try:
                    val = Decimal(str(raw).replace(",", "."))
                except (InvalidOperation, ValueError):
                    raise ValueError(f"Porcentaje de {label} no es numérico.")
                if val < 0:
                    raise ValueError(f"Porcentaje de {label} no puede ser negativo.")
                return val

            # Fase AIU — el % Admin enviado por el form se IGNORA (ahora es
            # readonly/derivado). Se persiste el % derivado calculado a partir
            # de subtotal_administracion / base_directa_sin_admin para que el
            # snapshot histórico refleje el valor real al momento de aprobar.
            pct_imprev = _parse_pct(request.POST.get("aiu_final_imprevistos_pct"), "Imprevistos")
            pct_util = _parse_pct(request.POST.get("aiu_final_utilidad_pct"), "Utilidad")

            modalidades_calc = apu.calcular_modalidades_aiu(pct_override={
                "imprevistos": pct_imprev or Decimal("0"),
                "utilidad":    pct_util  or Decimal("0"),
            })
            modalidad_key = "modalidad1" if modalidad == "1" else "modalidad2"
            pct_admin = modalidades_calc[modalidad_key]["admin_pct"]

            # Fase 12.2 — aprobado_por = usuario en sesión, ignorar campos del form.
            aprobador = get_usuario_actual(request)

            apu.modalidad_aiu_seleccionada = modalidad
            apu.fecha_aprobacion = tz.now()
            update_fields = ["modalidad_aiu_seleccionada", "fecha_aprobacion", "updated_at"]
            if pct_admin is not None:
                apu.aiu_final_admin_pct = pct_admin
                update_fields.append("aiu_final_admin_pct")
            if pct_imprev is not None:
                apu.aiu_final_imprevistos_pct = pct_imprev
                update_fields.append("aiu_final_imprevistos_pct")
            if pct_util is not None:
                apu.aiu_final_utilidad_pct = pct_util
                update_fields.append("aiu_final_utilidad_pct")
            if aprobador is not None:
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

            # Fase 12 — Snapshot inmutable de cotización aprobada.
            # Se crea DESPUÉS de los estados para reflejar el momento final
            # de la aprobación. Versiona automáticamente y marca las anteriores
            # como REEMPLAZADA. NUNCA borra histórico.
            from apps.presupuestos.services import CotizacionSnapshotService
            snapshot = CotizacionSnapshotService.crear_snapshot(apu)

            registrar_log(
                request, accion="APROBAR_MODALIDAD",
                descripcion=(
                    f"APU {apu.pk} ({apu.nombre}) aprobado: modalidad {modalidad}, "
                    f"cotización v{snapshot.version}."
                ),
                modelo_afectado="APUProyecto", objeto_id=apu.pk,
            )
            messages.success(
                request,
                f"Modalidad AIU {modalidad} aprobada para el APU «{apu.nombre}». "
                f"Cotización aprobada v{snapshot.version} generada.",
            )
        except ValueError as exc:
            messages.error(request, str(exc))
        except Exception as exc:
            messages.error(request, f"Error al aprobar modalidad: {exc}")
            logger.exception("[APUAprobarModalidadView] Error APU %s", pk)

        return redirect(reverse("presupuestos:apu_revisar", args=[pk]))


class APUResetModalidadView(AdminGerenteRequiredMixin, View):
    """
    POST /presupuestos/apu/<pk>/reset-modalidad/
    Limpia la aprobación de modalidad (Fase 10A-8) conservando los porcentajes
    A/I/U finales para que el revisor pueda re-aprobar otra modalidad sin perder
    el ajuste ya hecho.
    """
    def post(self, request, pk):
        from apps.common.choices import EstadoProyecto, EstadoSolicitud
        apu = get_object_or_404(APUProyecto, pk=pk)

        # Fase 12.2 — Gate de permisos (mismo que aprobar)
        if not puede_aprobar_apu(request, apu):
            registrar_log(
                request, accion="APROBACION_DENEGADA",
                descripcion=f"Intento no autorizado de reset modalidad APU {apu.pk}.",
                modelo_afectado="APUProyecto", objeto_id=apu.pk,
            )
            messages.error(
                request,
                "No tiene permiso para resetear la modalidad de este APU.",
            )
            return redirect(reverse("presupuestos:apu_detail", args=[pk]))

        try:
            apu.modalidad_aiu_seleccionada = None
            apu.aprobado_por = None
            apu.fecha_aprobacion = None
            apu.save(update_fields=[
                "modalidad_aiu_seleccionada", "aprobado_por", "fecha_aprobacion", "updated_at",
            ])
            registrar_log(
                request, accion="RESET_MODALIDAD",
                descripcion=f"APU {apu.pk} ({apu.nombre}): modalidad reseteada.",
                modelo_afectado="APUProyecto", objeto_id=apu.pk,
            )

            # Revertir estados de Proyecto y Solicitud — si el APU ya no tiene
            # modalidad aprobada, el flujo comercial vuelve a revisión.
            if apu.proyecto_sistema:
                proyecto = apu.proyecto_sistema.proyecto
                proyecto.estado = EstadoProyecto.APU_GENERADO
                proyecto.save(update_fields=["estado"])
                if proyecto.solicitud_id:
                    proyecto.solicitud.estado = EstadoSolicitud.EN_REVISION
                    proyecto.solicitud.save(update_fields=["estado"])

            messages.success(
                request,
                "La modalidad AIU fue reiniciada. El proyecto y la solicitud vuelven a revisión. "
                "Los porcentajes A/I/U finales se conservan.",
            )
        except Exception as exc:
            messages.error(request, f"Error al resetear modalidad: {exc}")
            logger.exception("[APUResetModalidadView] Error APU %s", pk)
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
            "area_m2": (ps.parametros_entrada or {}).get("area_m2"),
            "tiene_resultados": bool(lineas),
            "sin_capas_definidas": not capas,
        }
        return render(request, self.template_name, ctx)


class EjecutarCalculoConsumoView(GestionPresupuestosMixin, View):
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


class AsignarProductoConsumoAPIView(GestionPresupuestosMixin, View):
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




class APUCotizacionFinalView(GestionPresupuestosMixin, View):
    """
    Fase 11 — Cotización final en pantalla a partir del APU.

    GET /presupuestos/apu/<pk>/cotizacion/

    - Si existe snapshot aprobado (CotizacionAPU con estado=APROBADA): muestra
      los valores congelados del snapshot para que coincidan con el PDF oficial
      ya entregado al cliente.
    - Si no existe snapshot (APU sin aprobación o aprobado sin snapshot):
      calcula en vivo con get_resumen_cotizacion().
    - En ambos casos el template es el mismo; "resumen" conserva la misma forma.
    """
    template_name = "presupuestos/apu_cotizacion_final.html"

    def get(self, request, pk):
        from apps.presupuestos.services import CotizacionSnapshotService

        apu = get_object_or_404(APUProyecto, pk=pk)
        snapshot = CotizacionSnapshotService.obtener_snapshot_vigente(apu)

        if snapshot is not None:
            ctx_snap = CotizacionSnapshotService.construir_contexto_pdf(snapshot)
            resumen = ctx_snap["resumen"]
        else:
            resumen = apu.get_resumen_cotizacion()

        return render(request, self.template_name, {
            "apu": apu,
            "resumen": resumen,
            "snapshot": snapshot,
        })


# ─────────────────────────────────────────────────────────────────────────────
# Fase 11.5 — Consolidación opcional de APUs
# ─────────────────────────────────────────────────────────────────────────────

class APUConsolidarSeleccionarView(GestionPresupuestosMixin, View):
    """
    GET — Pinta la página de selección de APUs del proyecto.
    POST → preview.
    La consolidación es opcional. El usuario decide si la usa.
    """
    template_name = "presupuestos/apu_consolidar_seleccionar.html"

    def get(self, request, pk):
        proyecto = get_object_or_404(Proyecto, pk=pk)
        apus = self._apus_del_proyecto(proyecto)
        return render(request, self.template_name, {
            "proyecto": proyecto,
            "apus_individuales": [a for a in apus if not a.es_consolidado],
            "apus_consolidados": [a for a in apus if a.es_consolidado],
        })

    @staticmethod
    def _apus_del_proyecto(proyecto):
        # APUs individuales del proyecto via ProyectoSistema
        del_proyecto = APUProyecto.objects.filter(
            proyecto_sistema__proyecto=proyecto
        )
        # APUs consolidados via FK directa
        consolidados = APUProyecto.objects.filter(proyecto=proyecto)
        ids = list(del_proyecto.values_list("pk", flat=True)) + \
              list(consolidados.values_list("pk", flat=True))
        return (
            APUProyecto.objects
            .filter(pk__in=ids)
            .select_related("proyecto_sistema__subsistema__sistema")
            .order_by("tipo_apu", "pk")
        )


class APUConsolidarPreviewView(GestionPresupuestosMixin, View):
    """
    POST — recibe ids de APUs y muestra el resumen previo. No persiste.
    Botón "Confirmar" envía a APUConsolidarConfirmarView.
    """
    template_name = "presupuestos/apu_consolidar_preview.html"

    def post(self, request, pk):
        from apps.presupuestos.services.apu_consolidacion_facade import (
            APUConsolidacionFacade,
        )
        proyecto = get_object_or_404(Proyecto, pk=pk)
        ids = request.POST.getlist("apus")
        validacion, resumen = APUConsolidacionFacade.preview(proyecto, ids)

        if not validacion.ok:
            for err in validacion.errores:
                messages.error(request, err)
            return redirect("presupuestos:apu_consolidar_seleccionar", pk=proyecto.pk)

        return render(request, self.template_name, {
            "proyecto": proyecto,
            "apus_origen": validacion.apus,
            "resumen": resumen,
            "ids_csv": ",".join(str(a.pk) for a in validacion.apus),
        })


class APUConsolidarConfirmarView(GestionPresupuestosMixin, View):
    """
    POST — confirma y persiste el APU consolidado. Redirige a apu_detail.
    """
    def post(self, request, pk):
        from apps.presupuestos.services.apu_consolidacion_facade import (
            APUConsolidacionFacade,
        )
        proyecto = get_object_or_404(Proyecto, pk=pk)
        ids_csv = request.POST.get("ids_csv", "")
        ids = [int(x) for x in ids_csv.split(",") if x.strip().isdigit()]
        nombre = (request.POST.get("nombre") or "").strip()

        validacion, apu_consolidado = APUConsolidacionFacade.consolidar(
            proyecto=proyecto, apu_ids=ids, nombre=nombre,
        )
        if not validacion.ok or apu_consolidado is None:
            for err in validacion.errores:
                messages.error(request, err)
            return redirect("presupuestos:apu_consolidar_seleccionar", pk=proyecto.pk)

        messages.success(
            request,
            f"APU consolidado #{apu_consolidado.pk} creado a partir de "
            f"{len(validacion.apus)} APUs individuales.",
        )
        registrar_log(
            request,
            accion="CONSOLIDAR_APU",
            descripcion=(
                f"APU consolidado #{apu_consolidado.pk} creado a partir de "
                f"APUs {[a.pk for a in validacion.apus]} "
                f"en proyecto {proyecto.consecutivo}"
            ),
            modelo_afectado="Proyecto",
            objeto_id=proyecto.pk,
        )
        return redirect("presupuestos:apu_detail", pk=apu_consolidado.pk)


# ══════════════════════════════════════════════════════════════════════════════
# PRESUPUESTO PROYECTO — Vista consolidada de todos los APUs guardados
# ══════════════════════════════════════════════════════════════════════════════

class ProyectoPresupuestoView(GestionPresupuestosMixin, View):
    """
    GET  /presupuestos/proyecto/<pk>/presupuesto/
    POST /presupuestos/proyecto/<pk>/presupuesto/  — Guardar configuración AIU + confirmar

    Muestra la tabla consolidada de todos los APUs "guardados" (con cantidad_base_apu)
    del proyecto. Permite:
      1. Editar descripción de cada APU (col. Descripción en la tabla del PDF).
      2. Definir porcentajes de Imprevistos (I%) y Utilidad (U%).
      3. Seleccionar si aplica IVA final y su %.
      4. Elegir a quién se envía para revisión/aprobación.
      5. Confirmar el presupuesto → marca APU principal como "en revisión".

    Fórmula AIU:
        base_total      = Σ (apu.total_valor_venta × apu.cantidad_base_apu)
        admin_total     = Σ (apu.subtotal_administracion × apu.cantidad_base_apu)
        imprevistos     = base_total × I% / 100
        utilidad        = base_total × U% / 100
        subtotal_aiu    = base_total + admin_total + imprevistos + utilidad
        iva_valor       = subtotal_aiu × IVA% / 100  (si aplica)
        total_final     = subtotal_aiu + iva_valor
    """

    template_name = "presupuestos/presupuesto_proyecto.html"

    def _get_apus_guardados(self, proyecto):
        """APUs del proyecto con cantidad_base_apu definida, ordenados por pk."""
        return (
            APUProyecto.objects
            .filter(
                proyecto_sistema__proyecto=proyecto,
                cantidad_base_apu__isnull=False,
                archivado=False,
            )
            .select_related(
                "proyecto_sistema__subsistema__sistema",
                "proyecto_sistema__proyecto",
            )
            .order_by("pk")
        )

    def _build_filas(self, apus_qs):
        """Construye la lista de filas para la tabla del presupuesto.

        Modalidad 1 (default): P.U. = mat + MO + herr + transp
        Modalidad 2:           P.U. = MO + herr + transp
                               (materiales se muestran aparte en el resumen AIU)
        En ambas modalidades la administración queda fuera del P.U.
        """
        from decimal import Decimal as _D
        filas = []
        for apu in apus_qs:
            cant = _D(str(apu.cantidad_base_apu or 0))
            total_venta   = _D(str(apu.total_valor_venta or 0))
            admin_costo   = _D(str(apu.subtotal_administracion or 0))
            mat_valor_u   = _D(str(apu.valor_materiales or 0))  # ya es valor_total (con margen+iva)
            fv            = _D("1") + _D(str(apu.factor_venta_pct or 0)) / _D("100")
            admin_valor_u = admin_costo * fv          # admin expresado en valor venta
            # P.U. base: sin admin
            vu_m1 = total_venta - admin_valor_u       # Modalidad 1: mat+MO+herr+transp
            vu_m2 = vu_m1 - mat_valor_u               # Modalidad 2: MO+herr+transp
            modalidad = apu.modalidad_aiu_seleccionada or "1"
            vu = vu_m2 if modalidad == "2" else vu_m1
            vt = cant * vu
            ps = apu.proyecto_sistema
            nombre_subsistema = ""
            if ps and ps.subsistema_id:
                nombre_subsistema = ps.subsistema.nombre
            elif ps and ps.sistema_id:
                nombre_subsistema = ps.sistema.nombre
            if not nombre_subsistema:
                nombre_subsistema = apu.nombre

            filas.append({
                "apu": apu,
                "nombre": nombre_subsistema,
                "descripcion": apu.descripcion or "",
                "cantidad": cant,
                "unidad": apu.unidad_base_apu or "",
                "valor_unitario": vu,
                "valor_total": vt,
                "admin_unitario": admin_valor_u,
                "admin_total": cant * admin_valor_u,
                "mat_unitario": mat_valor_u,
                "mat_total": cant * mat_valor_u,
                "modalidad": modalidad,
            })
        return filas

    def _calcular_aiu(self, filas, pct_imprevistos, pct_utilidad, aplica_iva, iva_pct):
        """Calcula el AIU consolidado a partir de las filas del presupuesto.

        Modalidad 1: base = mat+MO+herr+transp; mat incluida en valor_total de cada fila.
        Modalidad 2: base = MO+herr+transp; materiales se suman por separado (mat_total).
        Filas de distinta modalidad se mezclan correctamente porque cada fila
        ya trae su P.U. ajustado según su propia modalidad.
        """
        from decimal import Decimal as _D, ROUND_HALF_UP

        base_total  = sum(f["valor_total"] for f in filas) if filas else _D("0")
        admin_total = sum(f["admin_total"] for f in filas) if filas else _D("0")
        # Materiales separados: solo de filas con Modalidad 2
        mat_total   = sum(f["mat_total"] for f in filas if f.get("modalidad") == "2") if filas else _D("0")
        tiene_m2    = any(f.get("modalidad") == "2" for f in filas)

        _Q = _D("0.01")
        pct_i = _D(str(pct_imprevistos))
        pct_u = _D(str(pct_utilidad))

        # I y U se aplican sobre la base de costos directos (sin mat en M2)
        imprevistos = (base_total * pct_i / 100).quantize(_Q, rounding=ROUND_HALF_UP)
        utilidad    = (base_total * pct_u / 100).quantize(_Q, rounding=ROUND_HALF_UP)
        # En M2 los materiales se suman al subtotal, no son base de I/U
        subtotal_aiu = mat_total + base_total + admin_total + imprevistos + utilidad

        iva_valor = _D("0")
        if aplica_iva:
            iva_valor = (subtotal_aiu * _D(str(iva_pct)) / 100).quantize(_Q, rounding=ROUND_HALF_UP)

        total_final = subtotal_aiu + iva_valor

        pct_admin_derivado = (
            (admin_total / base_total * 100).quantize(_Q)
            if base_total else _D("0")
        )

        return {
            "base_total": base_total,
            "mat_total": mat_total,
            "tiene_m2": tiene_m2,
            "admin_total": admin_total,
            "pct_admin_derivado": pct_admin_derivado,
            "pct_imprevistos": pct_i,
            "pct_utilidad": pct_u,
            "imprevistos": imprevistos,
            "utilidad": utilidad,
            "subtotal_aiu": subtotal_aiu,
            "aplica_iva": aplica_iva,
            "iva_pct": _D(str(iva_pct)),
            "iva_valor": iva_valor,
            "total_final": total_final,
        }

    def get(self, request, pk):
        from apps.configuracion.models import ConfiguracionSistema
        from apps.common.choices import RolSistema

        proyecto = get_object_or_404(Proyecto, pk=pk)
        apus = self._get_apus_guardados(proyecto)
        filas = self._build_filas(apus)

        # Porcentajes: prioridad query-string (redirect POST) > APU guardado > defecto
        def _qp(name, default):
            raw = request.GET.get(name, "")
            try:
                return max(float(raw.replace(",", ".")), 0)
            except (ValueError, TypeError):
                return default

        pct_i = 3
        pct_u = 5
        aplica_iva = True
        iva_pct = 19
        if apus:
            primer = apus.first()
            pct_i   = float(primer.aiu_proyecto_imprevistos_pct or 3)
            pct_u   = float(primer.aiu_proyecto_utilidad_pct or 5)
            aplica_iva = primer.aplica_iva
            iva_pct = float(primer.iva_pct or 19)

        # Query-string override (después del POST de preview)
        pct_i = _qp("pct_i", pct_i)
        pct_u = _qp("pct_u", pct_u)
        _aplica_iva_qs = request.GET.get("aplica_iva")
        if _aplica_iva_qs is not None:
            aplica_iva = _aplica_iva_qs == "1"
        iva_pct = _qp("iva_pct", iva_pct)

        aiu = self._calcular_aiu(filas, pct_i, pct_u, aplica_iva, iva_pct)

        autorizadores = ConfiguracionSistema.objects.filter(
            activo=True,
            rol__in=[RolSistema.ADMINISTRADOR, RolSistema.GERENTE, RolSistema.PRESUPUESTOS],
        ).order_by("nombre_completo")

        return render(request, self.template_name, {
            "proyecto": proyecto,
            "filas": filas,
            "aiu": aiu,
            "pct_imprevistos": pct_i,
            "pct_utilidad": pct_u,
            "aplica_iva": aplica_iva,
            "iva_pct": iva_pct,
            "autorizadores": autorizadores,
            "n_apus": len(filas),
        })

    def post(self, request, pk):
        """
        Guarda las descripciones de los APUs y redirige de vuelta (preview).
        Si se confirma, guarda el APU principal como "enviado a revisión".
        """
        from decimal import Decimal as _D, InvalidOperation
        from apps.configuracion.models import ConfiguracionSistema
        from apps.common.choices import RolSistema
        from django.utils import timezone

        proyecto = get_object_or_404(Proyecto, pk=pk)
        apus = self._get_apus_guardados(proyecto)

        # 1. Guardar descripciones por APU
        for apu in apus:
            desc_key = f"descripcion_{apu.pk}"
            nueva_desc = request.POST.get(desc_key, "").strip()
            if nueva_desc != apu.descripcion:
                apu.descripcion = nueva_desc
                apu.save(update_fields=["descripcion", "updated_at"])

        # 2. Leer porcentajes AIU
        def _pct(name, default):
            raw = request.POST.get(name, "").strip()
            try:
                return max(float(raw.replace(",", ".")), 0)
            except (ValueError, TypeError):
                return default

        pct_i = _pct("pct_imprevistos", 3)
        pct_u = _pct("pct_utilidad", 5)
        aplica_iva = request.POST.get("aplica_iva") == "1"
        iva_pct = _pct("iva_pct", 19)

        # 3. Acción: "solo preview" vs "confirmar"
        accion = request.POST.get("accion", "preview")

        if accion == "confirmar":
            from apps.common.choices import EstadoProyecto
            # Persistir porcentajes en todos los APUs del proyecto
            revisor_id_str = request.POST.get("revisor_id", "")
            revisor_obj = None
            if revisor_id_str.isdigit():
                try:
                    revisor_obj = ConfiguracionSistema.objects.get(pk=int(revisor_id_str))
                except ConfiguracionSistema.DoesNotExist:
                    pass

            # Segregación de funciones: quien envía no autoriza, así que
            # asignarse a sí mismo dejaría el presupuesto sin quien lo apruebe.
            _remitente = get_usuario_actual(request)
            if revisor_obj and _remitente and revisor_obj.pk == _remitente.pk:
                messages.error(
                    request,
                    "No puede asignarse a usted mismo como autorizador: quien "
                    "envía el presupuesto no puede autorizarlo. Seleccione a "
                    "otra persona como autorizador.",
                )
                return redirect(reverse("presupuestos:proyecto_presupuesto", args=[pk]))

            n_confirmados = 0
            for apu in apus:
                apu.aiu_proyecto_imprevistos_pct = _D(str(pct_i))
                apu.aiu_proyecto_utilidad_pct    = _D(str(pct_u))
                apu.aplica_iva = aplica_iva
                apu.iva_pct    = _D(str(iva_pct))
                if revisor_obj:
                    apu.revisor = revisor_obj
                if not apu.fecha_envio_revision:
                    apu.fecha_envio_revision = timezone.now()
                # Se registra el remitente en cada envío para la regla
                # "quien envía no autoriza" (ver apps/common/auth.py).
                apu.enviado_por = _remitente
                apu.save(update_fields=[
                    "aiu_proyecto_imprevistos_pct", "aiu_proyecto_utilidad_pct",
                    "aplica_iva", "iva_pct", "revisor", "fecha_envio_revision",
                    "enviado_por", "updated_at",
                ])
                n_confirmados += 1

            # Avanzar estado del proyecto a "APU enviado a revisión"
            proyecto.estado = EstadoProyecto.APU_GENERADO
            proyecto.save(update_fields=["estado", "updated_at"])

            messages.success(
                request,
                f"Presupuesto de {n_confirmados} APU(s) confirmado y enviado a revisión."
            )
        else:
            messages.success(request, "Porcentajes actualizados. Revisa el resumen abajo.")

        # Redirigir de vuelta a la vista con los nuevos valores
        from urllib.parse import urlencode
        params = urlencode({
            "pct_i": pct_i,
            "pct_u": pct_u,
            "aplica_iva": "1" if aplica_iva else "0",
            "iva_pct": iva_pct,
        })
        # Redirigir a revisión si el proyecto ya fue enviado a revisión
        if accion == "confirmar":
            return redirect(reverse("presupuestos:proyecto_revisar", args=[pk]))

        return redirect(
            reverse("presupuestos:proyecto_presupuesto", args=[pk]) + f"?{params}"
        )


class ProyectoRevisarView(GestionPresupuestosMixin, View):
    """
    GET  /presupuestos/proyectos/<pk>/revisar/
    POST /presupuestos/proyectos/<pk>/revisar/  — Aprobar / Devolver / Modificar

    Vista del aprobador: muestra la tabla consolidada de APUs del proyecto (igual
    que ProyectoPresupuestoView pero en modo solo-lectura) con una columna adicional
    "Acciones" que enlaza al APU y al despiece de cada ítem.

    Botones:
      aprobar  → Proyecto.estado = APROBADO + modalidad_aiu_seleccionada = "M1" en cada APU
      devolver → Proyecto.estado = APU + limpia fecha_envio_revision + guarda motivo
      modificar → redirige a ProyectoPresupuestoView (edición)
    """

    template_name = "presupuestos/proyecto_revisar.html"

    # Reutiliza los helpers de ProyectoPresupuestoView ─────────────────────────

    def _get_apus_guardados(self, proyecto):
        return (
            APUProyecto.objects
            .filter(
                proyecto_sistema__proyecto=proyecto,
                cantidad_base_apu__isnull=False,
                archivado=False,
            )
            .select_related(
                "proyecto_sistema__subsistema__sistema",
                "proyecto_sistema__proyecto",
            )
            .order_by("pk")
        )

    def _build_filas(self, apus_qs):
        """
        Modalidad 1 (default): P.U. = mat + MO + herr + transp
        Modalidad 2:           P.U. = MO + herr + transp
                               (materiales se muestran aparte en el resumen AIU)
        En ambas modalidades la administración queda fuera del P.U.
        """
        from decimal import Decimal as _D
        filas = []
        for apu in apus_qs:
            cant = _D(str(apu.cantidad_base_apu or 0))
            total_venta   = _D(str(apu.total_valor_venta or 0))
            admin_costo   = _D(str(apu.subtotal_administracion or 0))
            mat_valor_u   = _D(str(apu.valor_materiales or 0))  # ya es valor_total (con margen+iva)
            fv            = _D("1") + _D(str(apu.factor_venta_pct or 0)) / _D("100")
            admin_valor_u = admin_costo * fv          # admin expresado en valor venta
            vu_m1 = total_venta - admin_valor_u       # Modalidad 1: mat+MO+herr+transp
            vu_m2 = vu_m1 - mat_valor_u               # Modalidad 2: MO+herr+transp
            modalidad = apu.modalidad_aiu_seleccionada or "1"
            vu = vu_m2 if modalidad == "2" else vu_m1
            vt = cant * vu
            ps = apu.proyecto_sistema
            nombre_subsistema = ""
            if ps and ps.subsistema_id:
                nombre_subsistema = ps.subsistema.nombre
            elif ps and ps.sistema_id:
                nombre_subsistema = ps.sistema.nombre
            if not nombre_subsistema:
                nombre_subsistema = apu.nombre

            # Obtener PK del despiece vinculado (si existe)
            despiece_pk = None
            try:
                if ps and ps.despiece_linea and ps.despiece_linea.despiece:
                    despiece_pk = ps.despiece_linea.despiece.pk
                elif ps:
                    from apps.presupuestos.models import DespieceLinea as _DL
                    dl = _DL.objects.filter(proyecto_sistema=ps).first()
                    if dl and dl.despiece_id:
                        despiece_pk = dl.despiece_id
            except Exception:
                despiece_pk = None

            filas.append({
                "apu": apu,
                "nombre": nombre_subsistema,
                "descripcion": apu.descripcion or "",
                "cantidad": cant,
                "unidad": apu.unidad_base_apu or "",
                "valor_unitario": vu,
                "valor_total": vt,
                "admin_unitario": admin_valor_u,
                "admin_total": cant * admin_valor_u,
                "mat_unitario": mat_valor_u,
                "mat_total": cant * mat_valor_u,
                "modalidad": modalidad,
                "despiece_pk": despiece_pk,
            })
        return filas

    def _calcular_aiu(self, filas, pct_imprevistos, pct_utilidad, aplica_iva, iva_pct):
        """Modalidad 1: base = mat+MO+herr+transp. Modalidad 2: base = MO+herr+transp; mat aparte."""
        from decimal import Decimal as _D, ROUND_HALF_UP
        base_total  = sum(f["valor_total"] for f in filas) if filas else _D("0")
        admin_total = sum(f["admin_total"] for f in filas) if filas else _D("0")
        mat_total   = sum(f["mat_total"] for f in filas if f.get("modalidad") == "2") if filas else _D("0")
        tiene_m2    = any(f.get("modalidad") == "2" for f in filas)
        _Q = _D("0.01")
        pct_i = _D(str(pct_imprevistos))
        pct_u = _D(str(pct_utilidad))
        imprevistos = (base_total * pct_i / 100).quantize(_Q, rounding=ROUND_HALF_UP)
        utilidad    = (base_total * pct_u / 100).quantize(_Q, rounding=ROUND_HALF_UP)
        subtotal_aiu = mat_total + base_total + admin_total + imprevistos + utilidad
        iva_valor = _D("0")
        if aplica_iva:
            iva_valor = (subtotal_aiu * _D(str(iva_pct)) / 100).quantize(_Q, rounding=ROUND_HALF_UP)
        total_final = subtotal_aiu + iva_valor
        pct_admin_derivado = (
            (admin_total / base_total * 100).quantize(_Q) if base_total else _D("0")
        )
        return {
            "base_total": base_total,
            "mat_total": mat_total,
            "tiene_m2": tiene_m2,
            "admin_total": admin_total,
            "pct_admin_derivado": pct_admin_derivado,
            "pct_imprevistos": pct_i,
            "pct_utilidad": pct_u,
            "imprevistos": imprevistos,
            "utilidad": utilidad,
            "subtotal_aiu": subtotal_aiu,
            "aplica_iva": aplica_iva,
            "iva_pct": _D(str(iva_pct)),
            "iva_valor": iva_valor,
            "total_final": total_final,
        }

    # ── GET ───────────────────────────────────────────────────────────────────

    def get(self, request, pk):
        from apps.common.choices import EstadoProyecto
        proyecto = get_object_or_404(Proyecto, pk=pk)
        apus = self._get_apus_guardados(proyecto)
        filas = self._build_filas(apus)

        # Porcentajes desde los APUs guardados (solo lectura)
        pct_i, pct_u, aplica_iva, iva_pct = 3, 5, True, 19
        if apus.exists():
            primer = apus.first()
            pct_i     = float(primer.aiu_proyecto_imprevistos_pct or 3)
            pct_u     = float(primer.aiu_proyecto_utilidad_pct or 5)
            aplica_iva = primer.aplica_iva
            iva_pct   = float(primer.iva_pct or 19)

        aiu = self._calcular_aiu(filas, pct_i, pct_u, aplica_iva, iva_pct)
        aprobado = (proyecto.estado == EstadoProyecto.APROBADO)

        # Segregación de funciones: la plantilla oculta los botones cuando el
        # usuario no puede autorizar y explica el motivo. El POST vuelve a
        # validar — esto es solo la capa visual.
        from apps.common.auth import (
            puede_aprobar_proyecto, motivo_no_puede_aprobar_proyecto,
            puede_reasignar_revisor,
        )
        from apps.configuracion.models import ConfiguracionSistema
        primer_apu = apus.first()

        return render(request, self.template_name, {
            "proyecto": proyecto,
            "filas": filas,
            "aiu": aiu,
            "pct_imprevistos": pct_i,
            "pct_utilidad": pct_u,
            "aplica_iva": aplica_iva,
            "iva_pct": iva_pct,
            "n_apus": len(filas),
            "aprobado": aprobado,
            "motivo_devolucion": proyecto.motivo_devolucion or "",
            "puede_aprobar": puede_aprobar_proyecto(request, proyecto),
            "motivo_no_aprobar": motivo_no_puede_aprobar_proyecto(request, proyecto),
            "puede_reasignar": bool(primer_apu) and puede_reasignar_revisor(request, primer_apu),
            "apu_revisor": primer_apu.revisor if primer_apu and primer_apu.revisor_id else None,
            "apu_enviado_por": primer_apu.enviado_por if primer_apu and primer_apu.enviado_por_id else None,
            "autorizadores": ConfiguracionSistema.objects.filter(activo=True).order_by("nombre_completo"),
        })

    # ── POST ──────────────────────────────────────────────────────────────────

    def post(self, request, pk):
        from apps.common.choices import EstadoProyecto
        from django.utils import timezone

        from apps.common.auth import (
            puede_aprobar_proyecto, motivo_no_puede_aprobar_proyecto,
        )

        proyecto = get_object_or_404(Proyecto, pk=pk)
        apus = self._get_apus_guardados(proyecto)
        accion = request.POST.get("accion", "")

        # Gate de autorización: aprobar y devolver son actos del autorizador.
        # "modificar" no lo es (solo navega al editor) y queda fuera.
        if accion in ("aprobar", "devolver") and not puede_aprobar_proyecto(request, proyecto):
            motivo = motivo_no_puede_aprobar_proyecto(request, proyecto)
            registrar_log(
                request, accion="APROBACION_DENEGADA",
                descripcion=(
                    f"Intento no autorizado de {accion} el presupuesto del "
                    f"proyecto {proyecto.pk}. Motivo: {motivo}"
                ),
                modelo_afectado="Proyecto", objeto_id=proyecto.pk,
            )
            messages.error(request, motivo or "No tiene permiso para autorizar este presupuesto.")
            return redirect(reverse("presupuestos:proyecto_revisar", args=[pk]))

        if accion == "aprobar":
            aprobador = get_usuario_actual(request)
            for apu in apus:
                campos = ["updated_at"]
                # Si el APU ya tiene modalidad seleccionada, respetarla; si no, usar "1" por defecto
                if not apu.modalidad_aiu_seleccionada:
                    apu.modalidad_aiu_seleccionada = "1"
                    campos.append("modalidad_aiu_seleccionada")
                # Trazabilidad de quién autorizó y cuándo.
                apu.aprobado_por = aprobador
                apu.fecha_aprobacion = timezone.now()
                campos += ["aprobado_por", "fecha_aprobacion"]
                apu.save(update_fields=campos)
            proyecto.estado = EstadoProyecto.APROBADO
            proyecto.motivo_devolucion = ""
            proyecto.save(update_fields=["estado", "motivo_devolucion", "updated_at"])
            registrar_log(
                request, accion="APROBAR_PRESUPUESTO",
                descripcion=(
                    f"Presupuesto del proyecto {proyecto.pk} aprobado "
                    f"({apus.count()} APU(s))."
                ),
                modelo_afectado="Proyecto", objeto_id=proyecto.pk,
            )
            messages.success(request, "Presupuesto aprobado. Ya puede descargar PDF y Excel.")

        elif accion == "devolver":
            motivo = request.POST.get("motivo_devolucion", "").strip()
            for apu in apus:
                apu.fecha_envio_revision = None
                apu.modalidad_aiu_seleccionada = None
                apu.save(update_fields=["fecha_envio_revision", "modalidad_aiu_seleccionada", "updated_at"])
            proyecto.estado = EstadoProyecto.APU
            proyecto.motivo_devolucion = motivo
            proyecto.save(update_fields=["estado", "motivo_devolucion", "updated_at"])
            messages.warning(
                request,
                "Presupuesto devuelto para ajustes." + (f" Motivo: {motivo}" if motivo else "")
            )
            return redirect(reverse("presupuestos:proyecto_presupuesto", args=[pk]))

        elif accion == "modificar":
            return redirect(reverse("presupuestos:proyecto_presupuesto", args=[pk]))

        return redirect(reverse("presupuestos:proyecto_revisar", args=[pk]))


class ProyectoReasignarRevisorView(GestionPresupuestosMixin, View):
    """
    POST /presupuestos/proyectos/<pk>/reasignar-autorizador/

    Cambia el autorizador de todos los APUs del proyecto que están en revisión.

    Es la salida prevista cuando quien envió el presupuesto resulta ser también
    el autorizador asignado, o cuando el autorizador no está disponible.
    Reasignar NO aprueba nada: solo cambia a quién le corresponde autorizar,
    por eso lo puede hacer también quien envió (ver `puede_reasignar_revisor`).

    Campos del POST:
        revisor_id — PK del ConfiguracionSistema que autorizará
    """
    http_method_names = ["post"]

    def post(self, request, pk):
        from django.utils import timezone
        from apps.configuracion.models import ConfiguracionSistema
        from apps.common.auth import puede_reasignar_revisor

        proyecto = get_object_or_404(Proyecto, pk=pk)
        apus = list(
            APUProyecto.objects.filter(
                proyecto_sistema__proyecto=proyecto,
                archivado=False,
                cantidad_base_apu__isnull=False,
            )
        )
        destino = reverse("presupuestos:proyecto_revisar", args=[pk])

        if not apus:
            messages.error(request, "El proyecto no tiene presupuestos para reasignar.")
            return redirect(destino)

        # Basta con poder reasignar el primero: todos comparten el flujo del
        # proyecto y se reasignan en bloque.
        if not puede_reasignar_revisor(request, apus[0]):
            registrar_log(
                request, accion="APROBACION_DENEGADA",
                descripcion=(
                    f"Intento no autorizado de reasignar el autorizador del "
                    f"proyecto {proyecto.pk}."
                ),
                modelo_afectado="Proyecto", objeto_id=proyecto.pk,
            )
            messages.error(
                request,
                "No tiene permiso para reasignar el autorizador de este presupuesto.",
            )
            return redirect(destino)

        nuevo = ConfiguracionSistema.objects.filter(
            pk=(request.POST.get("revisor_id") or "").strip(), activo=True,
        ).first()
        if nuevo is None:
            messages.error(request, "Debe seleccionar un autorizador válido.")
            return redirect(destino)

        # El nuevo autorizador no puede ser quien envió: reasignar no debe
        # servir para saltarse la segregación de funciones.
        conflictivos = [a for a in apus if a.enviado_por_id and a.enviado_por_id == nuevo.pk]
        if conflictivos:
            messages.error(
                request,
                f"«{nuevo.nombre_completo or nuevo.email}» remitió este presupuesto a "
                "revisión, así que no puede ser su autorizador. Seleccione a otra persona.",
            )
            return redirect(destino)

        actor = get_usuario_actual(request)
        ahora = timezone.now()
        anterior = apus[0].revisor
        for apu in apus:
            apu.revisor = nuevo
            apu.reasignado_por = actor
            apu.fecha_reasignacion = ahora
            apu.save(update_fields=[
                "revisor", "reasignado_por", "fecha_reasignacion", "updated_at",
            ])

        registrar_log(
            request, accion="REASIGNAR_AUTORIZADOR",
            descripcion=(
                f"Autorizador del proyecto {proyecto.pk} reasignado de "
                f"«{anterior or '— sin asignar —'}» a «{nuevo}» "
                f"en {len(apus)} APU(s)."
            ),
            modelo_afectado="Proyecto", objeto_id=proyecto.pk,
        )
        messages.success(
            request,
            f"Autorizador reasignado a «{nuevo.nombre_completo or nuevo.email}». "
            f"Se actualizaron {len(apus)} presupuesto(s).",
        )
        return redirect(destino)


# ═══════════════════════════════════════════════════════════════════════════════
# PDF de proyecto aprobado — cotización cliente consolidada
# ═══════════════════════════════════════════════════════════════════════════════

class ProyectoPDFClienteView(DescargaPDFMixin, View):
    """
    GET /presupuestos/proyectos/<pk>/pdf-cliente/

    Genera un PDF vertical (A4 portrait) con la tabla consolidada del proyecto:
    todos los APUs con cantidad, P.U. y P.Total, más el resumen AIU al final.
    Solo disponible cuando el proyecto está APROBADO.
    """

    def get(self, request, pk):
        from weasyprint import HTML
        from apps.common.choices import EstadoProyecto
        from decimal import Decimal

        proyecto = get_object_or_404(Proyecto, pk=pk)

        # Reutiliza los mismos helpers de ProyectoRevisarView
        revisar_view = ProyectoRevisarView()
        apus = revisar_view._get_apus_guardados(proyecto)
        filas = revisar_view._build_filas(apus)

        pct_i, pct_u, aplica_iva, iva_pct = 3, 5, True, 19
        if apus.exists():
            primer = apus.first()
            pct_i      = float(primer.aiu_proyecto_imprevistos_pct or 3)
            pct_u      = float(primer.aiu_proyecto_utilidad_pct or 5)
            aplica_iva = primer.aplica_iva
            iva_pct    = float(primer.iva_pct or 19)

        aiu = revisar_view._calcular_aiu(filas, pct_i, pct_u, aplica_iva, iva_pct)
        aprobado = (proyecto.estado == EstadoProyecto.APROBADO)

        ctx = {
            "proyecto": proyecto,
            "filas": filas,
            "aiu": aiu,
            "aprobado": aprobado,
            "fecha_generacion": date.today().strftime("%d/%m/%Y"),
        }

        html_str = render_to_string("presupuestos/pdf/proyecto_pdf_cliente.html", ctx)
        pdf_bytes = HTML(string=html_str, base_url=request.build_absolute_uri("/")).write_pdf()
        consecutivo = getattr(proyecto, "consecutivo", None) or proyecto.pk
        filename = f"Cotizacion_Proyecto_{consecutivo}.pdf"
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
