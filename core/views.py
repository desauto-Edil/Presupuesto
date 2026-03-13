"""
core/views.py — Vistas Django para el sistema de presupuestos Imperandina.

Flujo de negocio implementado:
  ASESOR:
    ClienteListView / ClienteCreateView / ClienteEditView
    SolicitudListView / SolicitudCreateView / SolicitudDetailView
    EnviarCotizacionView
  PRESUPUESTOS:
    ProyectoCrearView
    ProyectoListView / ProyectoDetailView
    VariablesUpdateView  (despiece)
    ValidarPreciosView   (validar precios → enviar a Compras o avanzar)
    APUFormView          (diligenciar APU)
    EnviarRevisionAdminView (enviar APU al Administrador)
    APUDetailView
    AjusteLineaView
  COMPRAS:
    ComprasDashboardView
    ComprasActualizarPreciosView
    ComprasConfirmarView
  ADMINISTRADOR:
    AdminRevisionView (ingresar variables + aprobar/rechazar)

Endpoints JSON (API interna):
  - api_ejecutar_despiece : POST → ejecuta DespieceService, devuelve JSON
  - api_generar_apu       : POST → ejecuta APUService, devuelve JSON
  - api_resumen_proyecto  : GET  → resumen completo del proyecto en JSON
"""

import json
import logging

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from .forms import (
    AjusteLineaForm,
    APUCostosForm,
    IniciarDespieceForm,
    ProyectoSistemaVariablesForm,
    ClienteForm,
    ContactoClienteFormSet,
    SolicitudForm,
    ProyectoCrearForm,
    AdminRevisionForm,
    ProductoProveedorForm,
    ProveedorForm,
    ProductoForm,
    SistemaForm,
    SubsistemaFormSet,
    ComponenteSubsistemaFormSet,
    DependenciaSubsistemaFormSet,
    SeleccionarProductoForm,
)

from .models import (
    APUProyecto,
    DespieceLinea,
    EstadoProyecto,
    Proyecto,
    ProyectoSistema,
    Cliente,
    ContactoCliente,
    Solicitud,
    Producto,
    ProductoProveedor,
    Proveedor,
    Sistema,
    Subsistema,
    CategoriaProducto,
    ReglaCalculo,
    DependenciaTecnica,
)

from .services import APUService, DespieceService, ProyectoService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_ok(data: dict, status: int = 200) -> JsonResponse:
    return JsonResponse({"ok": True, **data}, status=status)


def _json_error(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"ok": False, "error": message}, status=status)


# ---------------------------------------------------------------------------
# Vista 1: Lista de proyectos
# ---------------------------------------------------------------------------

class ProyectoListView(View):
    """
    GET /proyectos/
    Lista todos los proyectos con filtros opcionales por estado y cliente.
    """

    def get(self, request):
        qs = Proyecto.objects.select_related("cliente", "tipo_proyecto").order_by("-id")

        estado  = request.GET.get("estado", "")
        cliente = request.GET.get("cliente", "")

        if estado:
            qs = qs.filter(estado=estado)
        if cliente:
            qs = qs.filter(cliente__razon_social__icontains=cliente)

        from .models import EstadoProyecto
        context = {
            "proyectos":     qs,
            "estados":       EstadoProyecto.choices,
            "filtro_estado": estado,
            "filtro_cliente": cliente,
            "total":         qs.count(),
        }
        return render(request, "core/proyecto_list.html", context)


# ---------------------------------------------------------------------------
# Vista 2: Detalle del proyecto
# ---------------------------------------------------------------------------

class ProyectoDetailView(View):
    """
    GET /proyectos/<pk>/
    Muestra el detalle del proyecto: sistemas asignados, despiece, APU.
    """

    def get(self, request, pk):
        proyecto = get_object_or_404(
            Proyecto.objects.select_related("cliente", "solicitud", "tipo_proyecto"),
            pk=pk,
        )
        sistemas = ProyectoSistema.objects.filter(proyecto=proyecto).select_related(
            "sistema", "subsistema"
        )
        lineas_despiece = DespieceLinea.objects.filter(proyecto=proyecto).select_related(
            "producto__unidad", "producto__categoria", "proyecto_sistema"
        )
        apu_proyectos = APUProyecto.objects.filter(
            proyecto_sistema__proyecto=proyecto
        ).select_related("proyecto_sistema")

        context = {
            "proyecto":       proyecto,
            "sistemas":       sistemas,
            "lineas_despiece": lineas_despiece,
            "apu_proyectos":  apu_proyectos,
            "total_materiales": sum(
                float(l.precio_snapshot or 0) * float(l.cantidad_final)
                for l in lineas_despiece
            ),
        }
        return render(request, "core/proyecto_detalle.html", context)


# ---------------------------------------------------------------------------
# Vista 3: Variables dinámicas (ProyectoSistema)
# ---------------------------------------------------------------------------

class VariablesUpdateView(View):
    """
    GET  /proyectos/<pk>/variables/   → Muestra formulario de variables
    POST /proyectos/<pk>/variables/   → Guarda variables y redirige a despiece
    """

    def get(self, request, pk):
        proyecto = get_object_or_404(Proyecto, pk=pk)
        ps = ProyectoSistema.objects.filter(proyecto=proyecto).first()
        form = ProyectoSistemaVariablesForm(instance=ps)
        init_form = IniciarDespieceForm()

        return render(request, "core/variables_form.html", {
            "proyecto":    proyecto,
            "ps":          ps,
            "form":        form,
            "init_form":   init_form,
        })

    def post(self, request, pk):
        proyecto = get_object_or_404(Proyecto, pk=pk)
        ps = ProyectoSistema.objects.filter(proyecto=proyecto).first()

        action = request.POST.get("action", "guardar")

        if action == "iniciar_despiece":
            # Nuevo despiece: selección de sistema + variables
            init_form = IniciarDespieceForm(request.POST)
            if init_form.is_valid():
                d = init_form.cleaned_data
                try:
                    result = ProyectoService.iniciar_despiece(
                        proyecto_id   = proyecto.pk,
                        sistema_id    = d["sistema"].pk,
                        subsistema_id = d["subsistema"].pk,
                        total_powergip= float(d["total_powergip"]),
                        cuadrilla     = d["cuadrilla_personas"],
                    )
                    messages.success(
                        request,
                        f"Despiece ejecutado: {len(result['lineas_despiece'])} líneas generadas."
                    )
                    logger.info(
                        "Despiece ejecutado para proyecto %s: %d líneas",
                        proyecto.consecutivo,
                        len(result["lineas_despiece"]),
                    )
                    return redirect("proyecto_detalle", pk=proyecto.pk)
                except Exception as e:
                    logger.error("Error en despiece proyecto %s: %s", proyecto.pk, e)
                    messages.error(request, f"Error al ejecutar despiece: {e}")
            form = ProyectoSistemaVariablesForm(instance=ps)
            return render(request, "core/variables_form.html", {
                "proyecto":  proyecto,
                "ps":        ps,
                "form":      form,
                "init_form": init_form,
            })

        else:
            # Actualizar variables del ProyectoSistema existente
            if ps is None:
                messages.error(request, "No hay sistema asignado a este proyecto.")
                return redirect("proyecto_variables", pk=proyecto.pk)

            form = ProyectoSistemaVariablesForm(request.POST, instance=ps)
            if form.is_valid():
                form.save()
                messages.success(request, "Variables actualizadas correctamente.")
                # Re-ejecutar despiece automáticamente
                try:
                    svc = DespieceService(ps)
                    resultado = svc.ejecutar()
                    messages.info(
                        request,
                        f"Despiece recalculado: {len(resultado)} líneas actualizadas."
                    )
                except Exception as e:
                    logger.warning("Re-ejecución de despiece falló: %s", e)
                    messages.warning(request, f"Variables guardadas, pero el despiece no pudo recalcularse: {e}")

                return redirect("proyecto_detalle", pk=proyecto.pk)

            return render(request, "core/variables_form.html", {
                "proyecto":  proyecto,
                "ps":        ps,
                "form":      form,
                "init_form": IniciarDespieceForm(),
            })


# ---------------------------------------------------------------------------
# Vista 4: Formulario APU
# ---------------------------------------------------------------------------

class APUFormView(View):
    """
    GET  /proyectos/<pk>/apu/   → Muestra formulario de costos APU
    POST /proyectos/<pk>/apu/   → Genera APU y redirige a detalle
    """

    def _get_ps(self, proyecto):
        """Retorna el ProyectoSistema del proyecto o None."""
        return ProyectoSistema.objects.filter(proyecto=proyecto).first()

    def get(self, request, pk):
        proyecto = get_object_or_404(Proyecto, pk=pk)
        ps = self._get_ps(proyecto)
        if not ps:
            messages.error(request, "Primero debe ejecutar el despiece del proyecto.")
            return redirect("proyecto_variables", pk=proyecto.pk)

        # Validar que el despiece haya sido validado antes de iniciar APU
        if proyecto.estado not in (
            EstadoProyecto.DESPIECE_VALIDADO,
            EstadoProyecto.APU,
            EstadoProyecto.APU_GENERADO,
        ):
            messages.error(
                request,
                "El despiece debe estar validado antes de iniciar el APU. "
                "Valide los precios primero."
            )
            return redirect("validar_precios", pk=proyecto.pk)

        apu = APUProyecto.objects.filter(proyecto_sistema=ps).first()
        form = APUCostosForm()

        return render(request, "core/apu_form.html", {
            "proyecto": proyecto,
            "ps":       ps,
            "apu":      apu,
            "form":     form,
            "motivo_devolucion": proyecto.motivo_devolucion,
        })

    def post(self, request, pk):
        proyecto = get_object_or_404(Proyecto, pk=pk)
        ps = self._get_ps(proyecto)
        if not ps:
            messages.error(request, "No hay sistema asignado.")
            return redirect("proyecto_variables", pk=proyecto.pk)

        form = APUCostosForm(request.POST)
        if form.is_valid():
            try:
                kwargs = form.to_service_kwargs()
                result = ProyectoService.iniciar_apu(
                    proyecto_sistema_id=ps.pk,
                    **kwargs,
                )
                totales = result["totales"]
                messages.success(
                    request,
                    f"APU generado correctamente. "
                    f"Total costo: ${totales['total_costo']:,.0f} | "
                    f"Valor venta: ${totales['total_valor_venta']:,.0f}"
                )
                logger.info(
                    "APU generado para proyecto %s: costo=%.2f venta=%.2f",
                    proyecto.consecutivo,
                    totales["total_costo"],
                    totales["total_valor_venta"],
                )
                return redirect("apu_detalle", pk=proyecto.pk)
            except Exception as e:
                logger.error("Error generando APU para proyecto %s: %s", proyecto.pk, e)
                messages.error(request, f"Error generando APU: {e}")

        apu = APUProyecto.objects.filter(proyecto_sistema=ps).first()
        return render(request, "core/apu_form.html", {
            "proyecto": proyecto,
            "ps":       ps,
            "apu":      apu,
            "form":     form,
        })


# ---------------------------------------------------------------------------
# Vista 5: Detalle del APU
# ---------------------------------------------------------------------------

class APUDetailView(View):
    """
    GET /proyectos/<pk>/apu/detalle/
    Muestra el APU completo con todas las líneas agrupadas por tipo.
    """

    def get(self, request, pk):
        from .models import APULinea, TipoAPU

        proyecto = get_object_or_404(Proyecto, pk=pk)
        ps = ProyectoSistema.objects.filter(proyecto=proyecto).first()
        if not ps:
            messages.error(request, "No hay sistema asignado a este proyecto.")
            return redirect("proyecto_detalle", pk=proyecto.pk)

        apu = get_object_or_404(APUProyecto, proyecto_sistema=ps)
        lineas = APULinea.objects.filter(apu=apu).order_by("tipo", "id")

        # Agrupar por tipo
        grupos = {}
        for tipo_code, tipo_label in TipoAPU.choices:
            grupos[tipo_code] = {
                "label":  tipo_label,
                "lineas": [l for l in lineas if l.tipo == tipo_code],
            }

        context = {
            "proyecto": proyecto,
            "ps":       ps,
            "apu":      apu,
            "grupos":   grupos,
            "tipos":    TipoAPU.choices,
        }
        return render(request, "core/apu_detalle.html", context)


# ---------------------------------------------------------------------------
# Vista 6: Ajuste manual de línea de despiece
# ---------------------------------------------------------------------------

class AjusteLineaView(View):
    """
    POST /proyectos/<pk>/despiece/<linea_pk>/ajustar/
    Ajusta manualmente la cantidad de una línea de despiece.
    """

    def post(self, request, pk, linea_pk):
        proyecto = get_object_or_404(Proyecto, pk=pk)
        linea = get_object_or_404(DespieceLinea, pk=linea_pk, proyecto=proyecto)

        form = AjusteLineaForm(request.POST, instance=linea)
        if form.is_valid():
            form.save()
            nombre_linea = linea.producto.codigo if linea.producto else str(linea.categoria_producto or "—")
            messages.success(
                request,
                f"Línea {nombre_linea} ajustada a {linea.cantidad_final}."
            )
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")

        return redirect("proyecto_detalle", pk=proyecto.pk)


# ===========================================================================
# ASESOR — Gestión de Clientes
# ===========================================================================

class ClienteListView(View):
    """GET /clientes/ — Lista de clientes."""

    def get(self, request):
        clientes = Cliente.objects.filter(activo=True).order_by("razon_social")
        q = request.GET.get("q", "")
        if q:
            clientes = clientes.filter(razon_social__icontains=q)
        return render(request, "core/cliente_list.html", {
            "clientes": clientes,
            "q": q,
        })


class ClienteCreateView(View):
    """
    GET/POST /clientes/nuevo/
    """

    def get(self, request):
        form_cliente = ClienteForm(prefix="cliente")
        formset      = ContactoClienteFormSet(prefix="contactos")
        return render(request, "core/cliente_form.html", {
            "form_cliente": form_cliente,
            "formset":      formset,
            "titulo":       "Nuevo cliente",
        })

    def post(self, request):
        from django.db import transaction
        form_cliente = ClienteForm(request.POST, prefix="cliente")
        formset      = ContactoClienteFormSet(request.POST, prefix="contactos")

        if form_cliente.is_valid() and formset.is_valid():
            with transaction.atomic():
                cliente = form_cliente.save()
                for form in formset:
                    if form.cleaned_data and not form.cleaned_data.get("DELETE"):
                        contacto = form.save(commit=False)
                        contacto.cliente = cliente
                        contacto.save()
            messages.success(request, f"Cliente '{cliente.razon_social}' creado.")
            return redirect("cliente_list")

        return render(request, "core/cliente_form.html", {
            "form_cliente": form_cliente,
            "formset":      formset,
            "titulo":       "Nuevo cliente",
        })


class ClienteEditView(View):
    """
    GET/POST /clientes/<pk>/editar/
    """

    def get(self, request, pk):
        cliente  = get_object_or_404(Cliente, pk=pk)
        form_cliente = ClienteForm(instance=cliente, prefix="cliente")
        formset      = ContactoClienteFormSet(instance=cliente, prefix="contactos")
        return render(request, "core/cliente_form.html", {
            "form_cliente": form_cliente,
            "formset":      formset,
            "titulo":       f"Editar: {cliente.razon_social}",
            "cliente":      cliente,
        })

    def post(self, request, pk):
        from django.db import transaction
        cliente      = get_object_or_404(Cliente, pk=pk)
        form_cliente = ClienteForm(request.POST, instance=cliente, prefix="cliente")
        formset      = ContactoClienteFormSet(request.POST, instance=cliente, prefix="contactos")

        if form_cliente.is_valid() and formset.is_valid():
            with transaction.atomic():
                form_cliente.save()
                formset.save()
            messages.success(request, "Cliente actualizado correctamente.")
            return redirect("cliente_list")

        return render(request, "core/cliente_form.html", {
            "form_cliente": form_cliente,
            "formset":      formset,
            "titulo":       f"Editar: {cliente.razon_social}",
            "cliente":      cliente,
        })


# ===========================================================================
# ASESOR — Gestión de Solicitudes
# ===========================================================================

class SolicitudListView(View):
    """GET /solicitudes/ — Lista de solicitudes."""

    def get(self, request):
        solicitudes = Solicitud.objects.select_related("cliente").order_by("-created_at")
        q = request.GET.get("q", "")
        if q:
            solicitudes = solicitudes.filter(nombre__icontains=q)
        return render(request, "core/solicitud_list.html", {
            "solicitudes": solicitudes,
            "q": q,
        })


class SolicitudCreateView(View):
    """GET/POST /solicitudes/nueva/ — Crear solicitud."""

    def get(self, request):
        form = SolicitudForm()
        return render(request, "core/solicitud_form.html", {
            "form": form,
            "titulo": "Nueva solicitud",
        })

    def post(self, request):
        form = SolicitudForm(request.POST)
        if form.is_valid():
            solicitud = form.save(commit=False)
            solicitud.consecutivo = Solicitud.siguiente_consecutivo()
            solicitud.save()
            messages.success(
                request,
                f"Solicitud {solicitud.consecutivo} creada. "
                "Presupuestos puede crear el proyecto cuando esté lista."
            )
            return redirect("solicitud_list")
        return render(request, "core/solicitud_form.html", {
            "form": form,
            "titulo": "Nueva solicitud",
        })


class SolicitudDetailView(View):
    """GET /solicitudes/<pk>/ — Detalle de solicitud + opción de crear proyecto."""

    def get(self, request, pk):
        solicitud = get_object_or_404(
            Solicitud.objects.select_related("cliente", "contacto"),
            pk=pk
        )
        proyectos = solicitud.proyectos.select_related("tipo_proyecto").all()
        return render(request, "core/solicitud_detalle.html", {
            "solicitud": solicitud,
            "proyectos": proyectos,
        })


# ===========================================================================
# PRESUPUESTOS — Crear proyecto desde solicitud
# ===========================================================================

class ProyectoCrearView(View):
    """
    GET/POST /solicitudes/<pk>/crear-proyecto/
    Presupuestos crea el proyecto vinculado a la solicitud con las variables financieras.
    """

    def get(self, request, pk):
        solicitud = get_object_or_404(Solicitud, pk=pk)
        form = ProyectoCrearForm(initial={
            "trm": 4200,
            "margen_comercial_pct": 20,
            "iva_pct": 19,
            "aiu_pct": 0,
        })
        return render(request, "core/proyecto_crear.html", {
            "solicitud": solicitud,
            "form": form,
        })

    def post(self, request, pk):
        solicitud = get_object_or_404(Solicitud, pk=pk)
        form = ProyectoCrearForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            try:
                proyecto = ProyectoService.crear_desde_solicitud(
                    solicitud_id          = solicitud.pk,
                    tipo_proyecto_id      = d["tipo_proyecto"].pk,
                    creado_por            = None,
                    area_total_m2         = d.get("area_total_m2"),
                    perimetro_ml          = d.get("perimetro_ml"),
                    trm                   = float(d["trm"]),
                    margen_comercial_pct  = float(d["margen_comercial_pct"]),
                    iva_pct               = float(d["iva_pct"]),
                    aiu_pct               = float(d["aiu_pct"]),
                    aplica_exencion_iva   = d.get("aplica_exencion_iva", False),
                    observaciones         = d.get("observaciones"),
                )
                messages.success(
                    request,
                    f"Proyecto {proyecto.consecutivo} creado. Proceda a seleccionar el sistema y crear el despiece."
                )
                return redirect("proyecto_detalle", pk=proyecto.pk)
            except Exception as e:
                logger.error("Error creando proyecto desde solicitud %s: %s", pk, e)
                messages.error(request, f"Error creando proyecto: {e}")

        return render(request, "core/proyecto_crear.html", {
            "solicitud": solicitud,
            "form": form,
        })


# ===========================================================================
# PRESUPUESTOS — Validar precios del despiece
# ===========================================================================

class ValidarPreciosView(View):
    """
    GET  /proyectos/<pk>/validar-precios/
    POST /proyectos/<pk>/validar-precios/

    Presupuestos revisa si todos los materiales tienen precio actualizado.
    Opciones:
      - 'enviar_compras': avanzar a EN_REVISION_COMPRAS
      - 'validar':        avanzar a DESPIECE_VALIDADO si todos tienen precio
    """

    def _get_context(self, proyecto):
        ps = ProyectoSistema.objects.filter(proyecto=proyecto).first()
        lineas = []
        if ps:
            lineas = list(DespieceLinea.objects.filter(
                proyecto_sistema=ps
            ).select_related("producto__unidad", "producto__categoria", "categoria_producto"))
        pendientes = [l for l in lineas if l.pendiente_seleccion]
        sin_precio = [l for l in lineas if not l.pendiente_seleccion and not l.precio_snapshot]
        return ps, lineas, pendientes, sin_precio

    def get(self, request, pk):
        proyecto = get_object_or_404(Proyecto, pk=pk)
        if proyecto.estado not in (EstadoProyecto.DESPIECE,
                                   EstadoProyecto.EN_REVISION_COMPRAS):
            messages.warning(request, "El proyecto no está en estado de validación de precios.")
            return redirect("proyecto_detalle", pk=pk)

        ps, lineas, pendientes, sin_precio = self._get_context(proyecto)
        return render(request, "core/validar_precios.html", {
            "proyecto":     proyecto,
            "ps":           ps,
            "lineas":       lineas,
            "pendientes":   pendientes,
            "sin_precio":   sin_precio,
            "puede_validar": len(sin_precio) == 0 and len(pendientes) == 0,
        })

    def post(self, request, pk):
        proyecto = get_object_or_404(Proyecto, pk=pk)
        accion = request.POST.get("accion")
        ps, lineas, pendientes, sin_precio = self._get_context(proyecto)

        if accion == "enviar_compras":
            proyecto.avanzar_a_revision_compras()
            messages.info(
                request,
                "Proyecto enviado a Compras para actualización de precios."
            )
            return redirect("proyecto_detalle", pk=pk)

        elif accion == "validar":
            if pendientes:
                messages.error(
                    request,
                    f"No se puede validar: {len(pendientes)} línea(s) con producto pendiente de selección."
                )
                return render(request, "core/validar_precios.html", {
                    "proyecto": proyecto, "ps": ps, "lineas": lineas,
                    "pendientes": pendientes, "sin_precio": sin_precio,
                    "puede_validar": False,
                })
            if sin_precio:
                messages.error(
                    request,
                    f"No se puede validar: {len(sin_precio)} material(es) sin precio. "
                    "Envíe a Compras para actualizarlos."
                )
                return render(request, "core/validar_precios.html", {
                    "proyecto": proyecto, "ps": ps, "lineas": lineas,
                    "pendientes": pendientes, "sin_precio": sin_precio,
                    "puede_validar": False,
                })
            proyecto.avanzar_a_despiece_validado()
            messages.success(
                request,
                "Precios validados. El proyecto avanza a Despiece Validado. "
                "Ya puede iniciar el APU."
            )
            return redirect("proyecto_detalle", pk=pk)

        messages.error(request, "Acción no reconocida.")
        return redirect("validar_precios", pk=pk)


# ===========================================================================
# PRESUPUESTOS — Enviar APU completo a revisión del Administrador
# ===========================================================================

class EnviarRevisionAdminView(View):
    """
    POST /proyectos/<pk>/enviar-revision/
    Presupuestos marca el APU como completo y lo envía al Administrador.
    El proyecto avanza de APU → APU_GENERADO.
    """

    def post(self, request, pk):
        proyecto = get_object_or_404(Proyecto, pk=pk)
        if proyecto.estado != EstadoProyecto.APU:
            messages.error(
                request,
                "Solo se puede enviar a revisión un proyecto en estado APU en proceso."
            )
            return redirect("proyecto_detalle", pk=pk)

        proyecto.avanzar_a_apu_generado()
        messages.success(
            request,
            "APU enviado al Administrador para revisión y aprobación del cálculo económico."
        )
        return redirect("proyecto_detalle", pk=pk)


# ===========================================================================
# COMPRAS — Dashboard y actualización de precios
# ===========================================================================

class ComprasDashboardView(View):
    """
    GET /compras/
    Lista los proyectos en estado EN_REVISION_COMPRAS que requieren
    actualización de precios.
    """

    def get(self, request):
        proyectos = Proyecto.objects.filter(
            estado=EstadoProyecto.EN_REVISION_COMPRAS
        ).select_related("cliente").order_by("-updated_at")

        return render(request, "core/compras_dashboard.html", {
            "proyectos": proyectos,
        })


class ComprasActualizarPreciosView(View):
    """
    GET/POST /compras/proyectos/<pk>/precios/
    Compras ve los materiales sin precio del proyecto y puede actualizarlos.
    """

    def _get_lineas_sin_precio(self, proyecto):
        ps = ProyectoSistema.objects.filter(proyecto=proyecto).first()
        if not ps:
            return ps, []
        lineas = DespieceLinea.objects.filter(
            proyecto_sistema=ps
        ).select_related("producto__unidad", "producto__proveedores_producto")
        return ps, lineas

    def get(self, request, pk):
        proyecto = get_object_or_404(Proyecto, pk=pk)
        ps, lineas = self._get_lineas_sin_precio(proyecto)
        proveedores = Proveedor.objects.filter(activo=True)
        return render(request, "core/compras_actualizar_precios.html", {
            "proyecto": proyecto,
            "ps": ps,
            "lineas": lineas,
            "proveedores": proveedores,
            "form": ProductoProveedorForm(),
        })

    def post(self, request, pk):
        proyecto = get_object_or_404(Proyecto, pk=pk)
        producto_id  = request.POST.get("producto_id")
        proveedor_id = request.POST.get("proveedor_id")
        precio       = request.POST.get("precio_unitario")
        moneda       = request.POST.get("moneda", "COP")

        if producto_id and proveedor_id and precio:
            try:
                producto  = Producto.objects.get(pk=producto_id)
                proveedor = Proveedor.objects.get(pk=proveedor_id)
                pp, creado = ProductoProveedor.objects.update_or_create(
                    producto=producto,
                    proveedor=proveedor,
                    defaults={
                        "precio_unitario": float(precio),
                        "moneda": moneda,
                        "activo": True,
                    }
                )
                # Actualizar snapshot en líneas del proyecto
                DespieceLinea.objects.filter(
                    proyecto_sistema__proyecto=proyecto,
                    producto=producto,
                ).update(precio_snapshot=float(precio))

                accion = "actualizado" if not creado else "creado"
                messages.success(
                    request,
                    f"Precio {accion} para '{producto.nombre}': "
                    f"${float(precio):,.2f} {moneda}"
                )
            except Exception as e:
                logger.error("Error actualizando precio en compras: %s", e)
                messages.error(request, f"Error actualizando precio: {e}")
        else:
            messages.error(request, "Complete todos los campos para actualizar el precio.")

        return redirect("compras_actualizar_precios", pk=pk)


class ComprasConfirmarView(View):
    """
    POST /compras/proyectos/<pk>/confirmar/
    Compras confirma que los precios están actualizados.
    El proyecto regresa a estado DESPIECE para que Presupuestos re-valide.
    """

    def post(self, request, pk):
        proyecto = get_object_or_404(Proyecto, pk=pk)
        if proyecto.estado != EstadoProyecto.EN_REVISION_COMPRAS:
            messages.error(request, "El proyecto no está en revisión de Compras.")
            return redirect("compras_dashboard")

        # Actualizar snapshots de precio para todas las líneas del proyecto
        ps = ProyectoSistema.objects.filter(proyecto=proyecto).first()
        if ps:
            lineas = DespieceLinea.objects.filter(proyecto_sistema=ps)
            for linea in lineas:
                linea.capturar_precio()

        proyecto.volver_de_compras()
        messages.success(
            request,
            f"Confirmación enviada para {proyecto.consecutivo}. "
            "El proyecto regresa a Presupuestos para validación final de precios."
        )
        return redirect("compras_dashboard")


# ===========================================================================
# ADMINISTRADOR — Revisión y aprobación del APU
# ===========================================================================

class AdminRevisionView(View):
    """
    GET/POST /admin-revision/proyectos/<pk>/
    El Administrador ingresa las variables económicas del proyecto y
    aprueba o rechaza el APU generado.
    """

    def _get_proyecto_y_apu(self, pk):
        proyecto = get_object_or_404(Proyecto, pk=pk)
        ps  = ProyectoSistema.objects.filter(proyecto=proyecto).first()
        apu = APUProyecto.objects.filter(proyecto_sistema=ps).first() if ps else None
        return proyecto, ps, apu

    def get(self, request, pk):
        proyecto, ps, apu = self._get_proyecto_y_apu(pk)
        if proyecto.estado != EstadoProyecto.APU_GENERADO:
            messages.warning(
                request,
                "Solo se puede revisar un proyecto en estado 'APU enviado a revisión'."
            )
            return redirect("admin_revision_list")

        form = AdminRevisionForm(initial={
            "trm": proyecto.trm,
            "margen_comercial_pct": proyecto.margen_comercial_pct,
            "iva_pct": proyecto.iva_pct,
            "aiu_pct": proyecto.aiu_pct,
        })
        return render(request, "core/admin_revision.html", {
            "proyecto": proyecto,
            "ps": ps,
            "apu": apu,
            "form": form,
        })

    def post(self, request, pk):
        proyecto, ps, apu = self._get_proyecto_y_apu(pk)
        form = AdminRevisionForm(request.POST)

        if form.is_valid():
            d = form.cleaned_data
            # Actualizar variables financieras del proyecto
            proyecto.trm                  = d["trm"]
            proyecto.margen_comercial_pct = d["margen_comercial_pct"]
            proyecto.iva_pct              = d["iva_pct"]
            proyecto.aiu_pct              = d["aiu_pct"]
            proyecto.save(update_fields=[
                "trm", "margen_comercial_pct", "iva_pct", "aiu_pct", "updated_at"
            ])

            if d["decision"] == "aprobar":
                proyecto.aprobar_cotizacion()
                messages.success(
                    request,
                    f"Proyecto {proyecto.consecutivo} aprobado. "
                    "La cotización está lista para ser remitida al cliente por el Asesor."
                )
            else:
                proyecto.rechazar_apu(motivo=d["motivo_devolucion"])
                messages.warning(
                    request,
                    f"Proyecto {proyecto.consecutivo} devuelto a Presupuestos para ajuste. "
                    f"Motivo: {d['motivo_devolucion']}"
                )

            return redirect("admin_revision_list")

        return render(request, "core/admin_revision.html", {
            "proyecto": proyecto,
            "ps": ps,
            "apu": apu,
            "form": form,
        })


class AdminRevisionListView(View):
    """GET /admin-revision/ — Lista de proyectos pendientes de aprobación."""

    def get(self, request):
        proyectos = Proyecto.objects.filter(
            estado=EstadoProyecto.APU_GENERADO
        ).select_related("cliente").order_by("-updated_at")
        return render(request, "core/admin_revision_list.html", {
            "proyectos": proyectos,
        })


# ===========================================================================
# ASESOR — Enviar cotización al cliente
# ===========================================================================

class EnviarCotizacionView(View):
    """
    GET/POST /proyectos/<pk>/enviar-cotizacion/
    El Asesor confirma que la cotización fue remitida al cliente.
    El proyecto avanza de COTIZADO → APROBADO.
    """

    def get(self, request, pk):
        proyecto = get_object_or_404(Proyecto, pk=pk)
        if proyecto.estado != EstadoProyecto.COTIZADO:
            messages.warning(
                request,
                "Solo se puede enviar la cotización de un proyecto en estado 'Cotizado'."
            )
            return redirect("proyecto_detalle", pk=pk)
        ps  = ProyectoSistema.objects.filter(proyecto=proyecto).first()
        apu = APUProyecto.objects.filter(proyecto_sistema=ps).first() if ps else None
        return render(request, "core/cotizacion_enviar.html", {
            "proyecto": proyecto,
            "apu": apu,
        })

    def post(self, request, pk):
        proyecto = get_object_or_404(Proyecto, pk=pk)
        if proyecto.estado != EstadoProyecto.COTIZADO:
            messages.error(request, "El proyecto no está listo para enviar cotización.")
            return redirect("proyecto_detalle", pk=pk)

        proyecto.avanzar_a_cotizado()
        messages.success(
            request,
            f"Cotización de {proyecto.consecutivo} registrada como enviada al cliente. "
            "El proyecto queda en estado Aprobado."
        )
        return redirect("proyecto_detalle", pk=pk)


# ===========================================================================
# API JSON — Endpoints para uso programático
# ===========================================================================

@method_decorator(csrf_exempt, name="dispatch")
class APIEjecutarDespiece(View):
    """
    POST /api/proyectos/<pk>/despiece/
    Body JSON:
    {
        "sistema_id": 1,
        "subsistema_id": 2,
        "total_powergip": 500,
        "cuadrilla": 4
    }
    """

    def post(self, request, pk):
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return _json_error("Body JSON inválido.")

        sistema_id    = body.get("sistema_id")
        subsistema_id = body.get("subsistema_id")
        total_powergip = body.get("total_powergip")
        cuadrilla     = body.get("cuadrilla", 1)

        if not all([sistema_id, subsistema_id, total_powergip]):
            return _json_error("Campos requeridos: sistema_id, subsistema_id, total_powergip.")

        try:
            total_powergip = float(total_powergip)
            if total_powergip <= 0:
                return _json_error("total_powergip debe ser positivo.")
        except (TypeError, ValueError):
            return _json_error("total_powergip debe ser un número.")

        try:
            result = ProyectoService.iniciar_despiece(
                proyecto_id   = pk,
                sistema_id    = sistema_id,
                subsistema_id = subsistema_id,
                total_powergip= total_powergip,
                cuadrilla     = int(cuadrilla),
            )
            logger.info(
                "API: Despiece ejecutado proyecto_id=%s, lineas=%d",
                pk, len(result["lineas_despiece"])
            )
            return _json_ok(result)
        except Exception as e:
            logger.error("API despiece error: %s", e)
            return _json_error(str(e))


@method_decorator(csrf_exempt, name="dispatch")
class APIGenerarAPU(View):
    """
    POST /api/proyectos/<pk>/apu/
    Body JSON:
    {
        "hya_dia": 50000,
        "cuadrilla_dia": 80000,
        "dotacion_dia": 15000,
        "proteccion_dia": 10000,
        "costo_transporte": 500000,
        "costo_admin": 200000,
        "herramientas_items": [
            {"descripcion": "Tornillo automático", "precio_total": 150000}
        ]
    }
    """

    def post(self, request, pk):
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return _json_error("Body JSON inválido.")

        proyecto = get_object_or_404(Proyecto, pk=pk)
        ps = ProyectoSistema.objects.filter(proyecto=proyecto).first()
        if not ps:
            return _json_error("El proyecto no tiene sistema asignado. Ejecute primero el despiece.", 404)

        try:
            result = ProyectoService.iniciar_apu(
                proyecto_sistema_id = ps.pk,
                hya_dia             = float(body.get("hya_dia", 0)),
                cuadrilla_dia       = float(body.get("cuadrilla_dia", 0)),
                dotacion_dia        = float(body.get("dotacion_dia", 0)),
                proteccion_dia      = float(body.get("proteccion_dia", 0)),
                costo_transporte    = float(body.get("costo_transporte", 0)),
                costo_admin         = float(body.get("costo_admin", 0)),
                herramientas_items  = body.get("herramientas_items", []),
            )
            logger.info(
                "API: APU generado proyecto_id=%s, total_costo=%.2f",
                pk, result["totales"]["total_costo"]
            )
            return _json_ok(result)
        except Exception as e:
            logger.error("API APU error: %s", e)
            return _json_error(str(e))


class APIResumenProyecto(View):
    """
    GET /api/proyectos/<pk>/resumen/
    Devuelve resumen completo del proyecto en JSON.
    """

    def get(self, request, pk):
        proyecto = get_object_or_404(
            Proyecto.objects.select_related("cliente", "tipo_proyecto"),
            pk=pk,
        )
        ps = ProyectoSistema.objects.filter(proyecto=proyecto).first()
        apu = APUProyecto.objects.filter(
            proyecto_sistema=ps
        ).first() if ps else None

        lineas_despiece = []
        if ps:
            for l in DespieceLinea.objects.filter(proyecto_sistema=ps).select_related(
                    "producto__unidad", "categoria_producto"):
                lineas_despiece.append({
                    "producto":   l.producto.codigo if l.producto else None,
                    "nombre":     l.producto.nombre if l.producto else f"[{l.categoria_producto}]",
                    "cantidad":   float(l.cantidad_final),
                    "unidad":     l.producto.unidad.abreviatura if l.producto else "—",
                    "precio":     float(l.precio_snapshot or 0),
                    "total":      float(l.cantidad_final) * float(l.precio_snapshot or 0),
                    "automatica": l.es_dependencia_automatica,
                    "pendiente":  l.pendiente_seleccion,
                })

        return _json_ok({
            "proyecto": {
                "id":           proyecto.pk,
                "consecutivo":  proyecto.consecutivo,
                "nombre":       proyecto.nombre,
                "cliente":      proyecto.cliente.razon_social,
                "tipo":         proyecto.tipo_proyecto.nombre if proyecto.tipo_proyecto else None,
                "estado":       proyecto.estado,
                "area_m2":      float(proyecto.area_total_m2 or 0),
                "trm":          float(proyecto.trm),
                "margen_pct":   float(proyecto.margen_comercial_pct),
                "iva_pct":      float(proyecto.iva_pct),
            },
            "sistema": {
                "id":             ps.pk if ps else None,
                "sistema":        ps.sistema.nombre if ps else None,
                "subsistema":     ps.subsistema.nombre if ps else None,
                "total_powergip": float(ps.total_powergip or 0) if ps else 0,
                "cuadrilla":      ps.cuadrilla_personas if ps else 0,
                "variables_extra": ps.variables_extra if ps else {},
            },
            "despiece": {
                "total_lineas":     len(lineas_despiece),
                "lineas":           lineas_despiece,
                "subtotal_material": sum(l["total"] for l in lineas_despiece),
            },
            "apu": {
                "total_costo":        float(apu.total_costo) if apu else 0,
                "total_valor_venta":  float(apu.total_valor_venta) if apu else 0,
                "subtotal_materiales":   float(apu.subtotal_materiales) if apu else 0,
                "subtotal_mano_obra":    float(apu.subtotal_mano_obra) if apu else 0,
                "subtotal_herramientas": float(apu.subtotal_herramientas) if apu else 0,
                "subtotal_transporte":   float(apu.subtotal_transporte) if apu else 0,
                "subtotal_admin":        float(apu.subtotal_administracion) if apu else 0,
                "dias_trabajo":          float(apu.dias_trabajo or 0) if apu else 0,
                "tiempo_meses":          float(apu.tiempo_estimado_meses or 0) if apu else 0,
            } if apu else None,
        })


# ===========================================================================
# CATÁLOGO — Proveedores
# ===========================================================================

class ProveedorListView(View):
    """GET /proveedores/"""

    def get(self, request):
        qs = Proveedor.objects.filter(activo=True).order_by("nombre")
        q  = request.GET.get("q", "")
        if q:
            qs = qs.filter(nombre__icontains=q) | qs.filter(nit__icontains=q)
        return render(request, "core/proveedor_list.html", {"proveedores": qs, "q": q})


class ProveedorCreateView(View):
    """GET/POST /proveedores/nuevo/"""

    def get(self, request):
        return render(request, "core/proveedor_form.html", {
            "form": ProveedorForm(), "titulo": "Nuevo proveedor",
        })

    def post(self, request):
        form = ProveedorForm(request.POST)
        if form.is_valid():
            proveedor = form.save()
            messages.success(request, f"Proveedor '{proveedor.nombre}' creado.")
            return redirect("proveedor_list")
        return render(request, "core/proveedor_form.html", {"form": form, "titulo": "Nuevo proveedor"})


class ProveedorEditView(View):
    """GET/POST /proveedores/<pk>/editar/"""

    def get(self, request, pk):
        proveedor = get_object_or_404(Proveedor, pk=pk)
        return render(request, "core/proveedor_form.html", {
            "form": ProveedorForm(instance=proveedor),
            "titulo": f"Editar: {proveedor.nombre}",
            "proveedor": proveedor,
        })

    def post(self, request, pk):
        proveedor = get_object_or_404(Proveedor, pk=pk)
        form = ProveedorForm(request.POST, instance=proveedor)
        if form.is_valid():
            form.save()
            messages.success(request, "Proveedor actualizado.")
            return redirect("proveedor_list")
        return render(request, "core/proveedor_form.html", {
            "form": form,
            "titulo": f"Editar: {proveedor.nombre}",
            "proveedor": proveedor,
        })


# ===========================================================================
# CATÁLOGO — Productos
# ===========================================================================

class ProductoListView(View):
    """GET /productos/"""

    def get(self, request):
        qs  = Producto.objects.select_related("categoria", "unidad").order_by("codigo")
        q   = request.GET.get("q", "")
        if q:
            qs = qs.filter(nombre__icontains=q) | qs.filter(codigo__icontains=q)
        return render(request, "core/producto_list.html", {"productos": qs, "q": q})


class ProductoCreateView(View):
    """GET/POST /productos/nuevo/"""

    def get(self, request):
        return render(request, "core/producto_form.html", {
            "form": ProductoForm(), "titulo": "Nuevo producto",
        })

    def post(self, request):
        from django.db import transaction
        form = ProductoForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                producto = form.save(commit=False)
                producto.codigo = Producto.generar_codigo(form.cleaned_data["categoria"])
                producto.save()
                proveedor = form.get_proveedor()
                if proveedor:
                    ProductoProveedor.objects.update_or_create(
                        producto=producto,
                        proveedor=proveedor,
                        defaults={
                            "precio_unitario": form.cleaned_data["precio_unitario"],
                            "moneda":          form.cleaned_data["moneda_proveedor"],
                            "activo":          True,
                        }
                    )
            messages.success(request, f"Producto '{producto.codigo} — {producto.nombre}' creado.")
            return redirect("producto_list")
        return render(request, "core/producto_form.html", {"form": form, "titulo": "Nuevo producto"})


class ProductoEditView(View):
    """GET/POST /productos/<pk>/editar/"""

    def get(self, request, pk):
        producto = get_object_or_404(Producto, pk=pk)
        return render(request, "core/producto_form.html", {
            "form":     ProductoForm(instance=producto),
            "titulo":   f"Editar: {producto.nombre}",
            "producto": producto,
        })

    def post(self, request, pk):
        from django.db import transaction
        producto = get_object_or_404(Producto, pk=pk)
        form     = ProductoForm(request.POST, instance=producto)
        if form.is_valid():
            with transaction.atomic():
                form.save()
                proveedor = form.get_proveedor()
                if proveedor:
                    ProductoProveedor.objects.update_or_create(
                        producto=producto,
                        proveedor=proveedor,
                        defaults={
                            "precio_unitario": form.cleaned_data["precio_unitario"],
                            "moneda":          form.cleaned_data["moneda_proveedor"],
                            "activo":          True,
                        }
                    )
            messages.success(request, "Producto actualizado.")
            return redirect("producto_list")
        return render(request, "core/producto_form.html", {
            "form": form, "titulo": f"Editar: {producto.nombre}", "producto": producto,
        })


# ===========================================================================
# CATÁLOGO — Sistemas (con subsistemas inline)
# ===========================================================================

class SistemaListView(View):
    """GET /sistemas/"""

    def get(self, request):
        qs = Sistema.objects.prefetch_related("subsistemas").order_by("codigo")
        q  = request.GET.get("q", "")
        if q:
            qs = qs.filter(nombre__icontains=q) | qs.filter(codigo__icontains=q)
        return render(request, "core/sistema_list.html", {"sistemas": qs, "q": q})


class SistemaCreateView(View):
    """GET/POST /sistemas/nuevo/"""

    def get(self, request):
        return render(request, "core/sistema_form.html", {
            "form":    SistemaForm(),
            "formset": SubsistemaFormSet(prefix="subsistemas"),
            "titulo":  "Nuevo sistema",
        })

    def post(self, request):
        from django.db import transaction
        form    = SistemaForm(request.POST)
        formset = SubsistemaFormSet(request.POST, prefix="subsistemas")
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                sistema = form.save()
                for sub_form in formset:
                    if sub_form.cleaned_data and not sub_form.cleaned_data.get("DELETE"):
                        sub = sub_form.save(commit=False)
                        sub.sistema = sistema
                        sub.save()
            messages.success(request, f"Sistema '{sistema.nombre}' creado.")
            return redirect("sistema_list")
        return render(request, "core/sistema_form.html", {
            "form": form, "formset": formset, "titulo": "Nuevo sistema",
        })


class SistemaEditView(View):
    """GET/POST /sistemas/<pk>/editar/"""

    def get(self, request, pk):
        sistema = get_object_or_404(Sistema, pk=pk)
        return render(request, "core/sistema_form.html", {
            "form":    SistemaForm(instance=sistema),
            "formset": SubsistemaFormSet(instance=sistema, prefix="subsistemas"),
            "titulo":  f"Editar: {sistema.nombre}",
            "sistema": sistema,
        })

    def post(self, request, pk):
        from django.db import transaction
        sistema = get_object_or_404(Sistema, pk=pk)
        form    = SistemaForm(request.POST, instance=sistema)
        formset = SubsistemaFormSet(request.POST, instance=sistema, prefix="subsistemas")
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                formset.save()
            messages.success(request, "Sistema actualizado.")
            return redirect("sistema_list")
        return render(request, "core/sistema_form.html", {
            "form": form, "formset": formset,
            "titulo": f"Editar: {sistema.nombre}", "sistema": sistema,
        })


# ===========================================================================
# FALKE 8 — Subsistema: editar componentes (reglas) y dependencias inline
# ===========================================================================

class SubsistemaEditView(View):
    """
    GET/POST /subsistemas/<pk>/editar/
    Edita un subsistema con sus reglas de cálculo (ComponenteSubsistemaFormSet)
    y sus dependencias técnicas (DependenciaSubsistemaFormSet) inline.
    """

    def _ctx(self, subsistema, comp_fs, dep_fs):
        return {
            "subsistema":  subsistema,
            "sistema":     subsistema.sistema,
            "comp_fs":     comp_fs,
            "dep_fs":      dep_fs,
            "titulo":      f"Componentes: {subsistema.nombre}",
        }

    def get(self, request, pk):
        subsistema = get_object_or_404(Subsistema.objects.select_related("sistema"), pk=pk)
        comp_fs = ComponenteSubsistemaFormSet(instance=subsistema, prefix="comp")
        dep_fs  = DependenciaSubsistemaFormSet(instance=subsistema, prefix="dep")
        return render(request, "core/subsistema_form.html",
                      self._ctx(subsistema, comp_fs, dep_fs))

    def post(self, request, pk):
        from django.db import transaction
        subsistema = get_object_or_404(Subsistema.objects.select_related("sistema"), pk=pk)
        comp_fs = ComponenteSubsistemaFormSet(request.POST, instance=subsistema, prefix="comp")
        dep_fs  = DependenciaSubsistemaFormSet(request.POST, instance=subsistema, prefix="dep")

        comp_ok = comp_fs.is_valid()
        dep_ok  = dep_fs.is_valid()

        if comp_ok and dep_ok:
            with transaction.atomic():
                comp_fs.save()
                dep_fs.save()
            messages.success(
                request,
                f"Componentes y dependencias de '{subsistema.nombre}' guardados."
            )
            return redirect("sistema_edit", pk=subsistema.sistema_id)

        return render(request, "core/subsistema_form.html",
                      self._ctx(subsistema, comp_fs, dep_fs))


# ===========================================================================
# FALKE 8 — Seleccionar producto concreto para una línea pendiente
# ===========================================================================

class SeleccionarProductoLineaView(View):
    """
    GET/POST /proyectos/<pk>/despiece/<lid>/seleccionar-producto/
    Presupuestos elige el producto concreto para una DespieceLinea pendiente.
    """

    def _get_linea(self, pk, lid):
        proyecto = get_object_or_404(Proyecto, pk=pk)
        linea    = get_object_or_404(DespieceLinea, pk=lid, proyecto=proyecto)
        return proyecto, linea

    def get(self, request, pk, lid):
        proyecto, linea = self._get_linea(pk, lid)
        if not linea.pendiente_seleccion:
            messages.info(request, "Esta línea ya tiene producto asignado.")
            return redirect("proyecto_detalle", pk=pk)
        form = SeleccionarProductoForm(categoria=linea.categoria_producto)
        return render(request, "core/seleccionar_producto_linea.html", {
            "proyecto": proyecto,
            "linea":    linea,
            "form":     form,
        })

    def post(self, request, pk, lid):
        proyecto, linea = self._get_linea(pk, lid)
        form = SeleccionarProductoForm(request.POST, categoria=linea.categoria_producto)
        if form.is_valid():
            producto = form.cleaned_data["producto"]
            linea.producto             = producto
            linea.categoria_producto   = None
            linea.save(update_fields=["producto", "categoria_producto", "updated_at"])
            linea.capturar_precio()
            messages.success(
                request,
                f"Producto '{producto.nombre}' asignado a la línea."
            )
            return redirect("proyecto_detalle", pk=pk)
        return render(request, "core/seleccionar_producto_linea.html", {
            "proyecto": proyecto,
            "linea":    linea,
            "form":     form,
        })


# ===========================================================================
# FALKE 8 — API: preview de componentes de un subsistema
# ===========================================================================

class APIPreviewSubsistema(View):
    """
    GET /api/subsistemas/<pk>/componentes/
    Devuelve las reglas de cálculo y dependencias del subsistema en JSON.
    Útil para mostrar un preview antes de seleccionarlo en un proyecto.
    """

    def get(self, request, pk):
        subsistema = get_object_or_404(
            Subsistema.objects.select_related("sistema"), pk=pk
        )
        reglas = ReglaCalculo.objects.filter(
            subsistema=subsistema, activa=True
        ).select_related("producto", "categoria_producto").order_by("orden_ejecucion")

        dependencias = DependenciaTecnica.objects.filter(
            subsistema=subsistema, obligatoria=True
        ).select_related("producto_dependiente", "categoria_producto")

        return JsonResponse({
            "subsistema": {
                "id":     subsistema.pk,
                "codigo": subsistema.codigo,
                "nombre": subsistema.nombre,
            },
            "reglas": [
                {
                    "codigo":            r.codigo,
                    "nombre":            r.nombre,
                    "producto":          r.producto.nombre if r.producto else None,
                    "categoria":         str(r.categoria_producto) if r.categoria_producto else None,
                    "formula":           r.formula_texto,
                    "variable_entrada":  r.variable_entrada,
                    "orden":             r.orden_ejecucion,
                }
                for r in reglas
            ],
            "dependencias": [
                {
                    "nombre":            d.nombre or (d.producto_dependiente.nombre if d.producto_dependiente else "—"),
                    "producto":          d.producto_dependiente.nombre if d.producto_dependiente else None,
                    "categoria":         str(d.categoria_producto) if d.categoria_producto else None,
                    "obligatoria":       d.obligatoria,
                    "tipo_regla":        d.tipo_regla,
                }
                for d in dependencias
            ],
        })
