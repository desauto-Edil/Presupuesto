"""
apps/presupuestos/services/presentacion_comercial_service.py — Fase 3.D.

Presentación comercial de los ítems del presupuesto del proyecto.

LA ECONOMÍA DEL APU DEFINE EL DINERO. LA PRESENTACIÓN DEFINE CÓMO LO VE EL CLIENTE.

Este servicio NUNCA escribe en APUProyecto, APULinea, subsistema ni despiece, y
nunca recalcula el presupuesto: las filas económicas (`_build_filas`) y el AIU
(`_calcular_aiu`) de las vistas siguen siendo la única fuente del dinero.

  - `construir_items(filas)`  → helper común de las tres vistas (presupuesto,
    revisión y PDF cliente): lo que se muestra es lo mismo en las tres.
  - `guardar_presentacion()`  → valida TODO y luego persiste en una transacción.
  - `restablecer_presentacion()` → borra la cabecera (CASCADE a las líneas).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.presupuestos.models import (
    APUProyecto,
    LineaPresentacionPresupuesto,
    PresentacionItemPresupuesto,
)

# Estados visibles
ORIGINAL = "ORIGINAL"
PERSONALIZADO = "PERSONALIZADO"
DESGLOSADO = "DESGLOSADO"
REQUIERE_AJUSTE = "REQUIERE_AJUSTE"

ESTADO_LABEL = {
    ORIGINAL: "Original",
    PERSONALIZADO: "Personalizado",
    DESGLOSADO: "Desglosado",
    REQUIERE_AJUSTE: "Requiere ajuste",
}

NOMBRE_MAX = 200
DESCRIPCION_MAX = 2000
LINEAS_MIN = 2
LINEAS_MAX = 50
_DECIMALES = 4       # = APUProyecto.cantidad_base_apu (18,4)
_ENTEROS = 14

MODO_UNA = "una"
MODO_DESGLOSE = "desglose"


class PresentacionError(ValueError):
    """Error de validación. `errores` = lista de mensajes; `lineas` = {índice: mensaje}."""

    def __init__(self, mensaje, errores=None, lineas=None):
        super().__init__(mensaje)
        self.errores = errores or [mensaje]
        self.lineas = lineas or {}


class PresentacionBloqueada(PermissionError):
    """El presupuesto está en solo lectura por aprobación (regla apps.common.apu_lock)."""


# ─────────────────────────────────────────────────────────────────────────────
# Presupuesto: APU incluidos y bloqueo
# ─────────────────────────────────────────────────────────────────────────────

def apus_presupuesto(proyecto):
    """Misma selección que ProyectoPresupuestoView._get_apus_guardados."""
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


def presupuesto_bloqueado(proyecto, apus=None) -> bool:
    """
    True si el presupuesto está en solo lectura por aprobación. Reutiliza la
    regla única de apps.common.apu_lock: el proyecto (tiene_apu_aprobado) o
    cualquiera de sus APU del presupuesto (esta_aprobado).
    """
    from apps.common.apu_lock import objeto_bloqueado_por_apu

    if objeto_bloqueado_por_apu(proyecto):
        return True
    if apus is None:
        apus = apus_presupuesto(proyecto)
    return any(objeto_bloqueado_por_apu(a) for a in apus)


# ─────────────────────────────────────────────────────────────────────────────
# Lectura: helper común de las tres vistas
# ─────────────────────────────────────────────────────────────────────────────

def _dec(valor) -> Decimal:
    return Decimal(str(valor or 0))


def _item(fila, pres, numero) -> dict:
    """Presentación visible de UNA fila económica. No altera `fila`."""
    cantidad = _dec(fila["cantidad"])
    pu = _dec(fila["valor_unitario"])
    nombre_original = fila["nombre"]
    descripcion_original = fila["descripcion"]

    lineas_guardadas = list(pres.lineas.all()) if pres is not None else []
    distribuido = sum((ln.cantidad for ln in lineas_guardadas), Decimal("0"))

    if pres is None:
        estado = ORIGINAL
    elif not lineas_guardadas:
        estado = PERSONALIZADO
    elif distribuido == cantidad and len(lineas_guardadas) >= LINEAS_MIN:
        estado = DESGLOSADO
    else:
        estado = REQUIERE_AJUSTE

    usa_desglose = estado == DESGLOSADO
    sublineas = []
    if usa_desglose:
        for i, ln in enumerate(lineas_guardadas, start=1):
            sublineas.append({
                "numero": f"{numero}.{i}",
                "nombre": ln.nombre,
                "descripcion": ln.descripcion,
                "cantidad": ln.cantidad,
                # Importe DERIVADO para mostrar (cantidad × P.U. exacto). No se
                # guarda y no interviene en ningún total.
                "importe": ln.cantidad * pu,
            })

    return {
        "fila": fila,
        "apu": fila["apu"],
        "numero": numero,
        "estado": estado,
        "estado_label": ESTADO_LABEL[estado],
        "personalizado": pres is not None,
        # Texto visible (comercial si existe; si no, el original en vivo)
        "nombre": (pres.nombre_comercial if pres and pres.nombre_comercial else nombre_original),
        "descripcion": (
            pres.descripcion_comercial if pres and pres.descripcion_comercial else descripcion_original
        ),
        "nombre_original": nombre_original,
        "descripcion_original": descripcion_original,
        "nombre_comercial": pres.nombre_comercial if pres else "",
        "descripcion_comercial": pres.descripcion_comercial if pres else "",
        # Economía (siempre de la fila económica)
        "cantidad": cantidad,
        "unidad": fila["unidad"],
        "valor_unitario": fila["valor_unitario"],
        "valor_total": fila["valor_total"],
        # Desglose
        "usa_desglose": usa_desglose,
        "sublineas": sublineas,
        "lineas_guardadas": lineas_guardadas,
        "n_lineas": len(lineas_guardadas),
        "distribuido": distribuido,
        "pendiente": cantidad - distribuido,
    }


def construir_items(filas) -> list:
    """
    Ítems visibles del presupuesto a partir de las filas económicas.

    Un desglose solo se usa si es válido (Σ cantidades = cantidad económica
    actual y ≥2 líneas); si no, el ítem se muestra en una sola línea económica
    con su nombre/descripción comerciales y estado REQUIERE_AJUSTE.
    """
    apu_ids = [f["apu"].pk for f in filas]
    presentaciones = {
        p.apu_id: p
        for p in PresentacionItemPresupuesto.objects
        .filter(apu_id__in=apu_ids)
        .prefetch_related("lineas")
    }
    return [
        _item(fila, presentaciones.get(fila["apu"].pk), numero)
        for numero, fila in enumerate(filas, start=1)
    ]


def hay_desglose(items) -> bool:
    return any(it["usa_desglose"] for it in items)


def items_requieren_ajuste(items) -> list:
    return [it for it in items if it["estado"] == REQUIERE_AJUSTE]


def item_a_json(item) -> dict:
    """Datos del ítem para el modal "Personalizar presentación"."""
    return {
        "apu_id": item["apu"].pk,
        "nombre_original": item["nombre_original"],
        "descripcion_original": item["descripcion_original"],
        "nombre_comercial": item["nombre_comercial"],
        "descripcion_comercial": item["descripcion_comercial"],
        "cantidad": _texto_cantidad(item["cantidad"]),
        "unidad": item["unidad"],
        "estado": item["estado"],
        "personalizado": item["personalizado"],
        "lineas": [
            {
                "nombre": ln.nombre,
                "descripcion": ln.descripcion,
                "cantidad": _texto_cantidad(ln.cantidad),
            }
            for ln in item["lineas_guardadas"]
        ],
    }


def _texto_cantidad(valor) -> str:
    """Decimal sin ceros sobrantes ni notación científica (p. ej. '5412', '1912.125')."""
    d = _dec(valor)
    if d == d.to_integral_value():
        return str(d.quantize(Decimal("1")))
    return format(d.normalize(), "f")


# ─────────────────────────────────────────────────────────────────────────────
# Escritura
# ─────────────────────────────────────────────────────────────────────────────

def parse_cantidad(valor) -> Decimal:
    """Cantidad > 0 con máximo 4 decimales (Decimal 18,4). Acepta coma o punto."""
    texto = str(valor if valor is not None else "").strip().replace(" ", "")
    if not texto:
        raise PresentacionError("Indica la cantidad.")
    if "," in texto and "." in texto:
        raise PresentacionError(f"«{valor}» no es una cantidad válida (usa un solo separador decimal).")
    texto = texto.replace(",", ".")
    try:
        cantidad = Decimal(texto)
    except InvalidOperation:
        raise PresentacionError(f"«{valor}» no es una cantidad válida.")
    if not cantidad.is_finite() or cantidad <= 0:
        raise PresentacionError("La cantidad debe ser mayor que cero.")
    if cantidad.normalize().as_tuple().exponent < -_DECIMALES:
        raise PresentacionError(f"La cantidad admite máximo {_DECIMALES} decimales.")
    if cantidad >= Decimal(10) ** _ENTEROS:
        raise PresentacionError("La cantidad es demasiado grande.")
    return cantidad


def _texto(valor, maximo, etiqueta, obligatorio=False) -> str:
    texto = str(valor if valor is not None else "").strip()
    if obligatorio and not texto:
        raise PresentacionError(f"{etiqueta} es obligatorio.")
    if len(texto) > maximo:
        raise PresentacionError(f"{etiqueta} admite máximo {maximo} caracteres.")
    return texto


def validar_datos(datos, cantidad_economica) -> dict:
    """
    Valida la presentación completa SIN tocar la BD.

    `datos`: {"modo": "una"|"desglose", "nombre_comercial", "descripcion_comercial",
              "lineas": [{"nombre", "descripcion", "cantidad"}, ...]}
    Devuelve los datos normalizados o lanza PresentacionError con todos los errores.
    """
    errores = []
    errores_lineas = {}

    modo = datos.get("modo") or MODO_UNA
    if modo not in (MODO_UNA, MODO_DESGLOSE):
        raise PresentacionError("Modo de presentación inválido.")

    try:
        nombre = _texto(datos.get("nombre_comercial"), NOMBRE_MAX, "El nombre comercial")
    except PresentacionError as exc:
        errores.append(str(exc)); nombre = ""
    try:
        descripcion = _texto(datos.get("descripcion_comercial"), DESCRIPCION_MAX, "La descripción comercial")
    except PresentacionError as exc:
        errores.append(str(exc)); descripcion = ""

    lineas = []
    if modo == MODO_DESGLOSE:
        crudas = datos.get("lineas") or []
        if not isinstance(crudas, list):
            raise PresentacionError("Las líneas del desglose no tienen un formato válido.")
        if len(crudas) < LINEAS_MIN:
            errores.append(f"Un desglose necesita al menos {LINEAS_MIN} líneas.")
        if len(crudas) > LINEAS_MAX:
            errores.append(f"Un desglose admite máximo {LINEAS_MAX} líneas.")
        for i, cruda in enumerate(crudas):
            cruda = cruda if isinstance(cruda, dict) else {}
            try:
                lineas.append({
                    "nombre": _texto(cruda.get("nombre"), NOMBRE_MAX, "El nombre", obligatorio=True),
                    "descripcion": _texto(cruda.get("descripcion"), DESCRIPCION_MAX, "La descripción"),
                    "cantidad": parse_cantidad(cruda.get("cantidad")),
                })
            except PresentacionError as exc:
                errores_lineas[i] = str(exc)

        if not errores_lineas and len(lineas) >= LINEAS_MIN:
            distribuido = sum((ln["cantidad"] for ln in lineas), Decimal("0"))
            economica = _dec(cantidad_economica)
            if distribuido < economica:
                errores.append(
                    f"Falta distribuir {_texto_cantidad(economica - distribuido)}: la suma de las líneas "
                    f"({_texto_cantidad(distribuido)}) debe ser igual a la cantidad económica "
                    f"({_texto_cantidad(economica)})."
                )
            elif distribuido > economica:
                errores.append(
                    f"Exceso de {_texto_cantidad(distribuido - economica)}: la suma de las líneas "
                    f"({_texto_cantidad(distribuido)}) supera la cantidad económica "
                    f"({_texto_cantidad(economica)})."
                )

    if errores_lineas:
        errores.append("Revisa las líneas marcadas.")
    if errores:
        raise PresentacionError(errores[0], errores=errores, lineas=errores_lineas)

    return {"modo": modo, "nombre": nombre, "descripcion": descripcion, "lineas": lineas}


def _apu_del_presupuesto(proyecto, apu_id, bloquear=False):
    qs = apus_presupuesto(proyecto)
    if bloquear:
        qs = qs.select_for_update(of=("self",))
    apu = qs.filter(pk=apu_id).first()
    if apu is None:
        raise PresentacionError("El ítem no pertenece al presupuesto de este proyecto.")
    return apu


def guardar_presentacion(proyecto, apu_id, datos, usuario=None) -> PresentacionItemPresupuesto | None:
    """
    Guarda la presentación completa de un ítem en UNA transacción.

    Se valida todo antes de escribir; si algo falla no se guarda nada.
    - modo "una"      → conserva/crea la cabecera y elimina las líneas.
                        Si nombre y descripción quedan vacíos, equivale a la
                        presentación original: se elimina la cabecera.
    - modo "desglose" → reemplaza todas las líneas (orden = posición recibida).
    Nunca escribe en el APU.
    """
    with transaction.atomic():
        apu = _apu_del_presupuesto(proyecto, apu_id, bloquear=True)
        if presupuesto_bloqueado(proyecto):
            raise PresentacionBloqueada(
                "El presupuesto está aprobado: la presentación comercial es de solo lectura."
            )
        limpio = validar_datos(datos, apu.cantidad_base_apu)

        pres = PresentacionItemPresupuesto.objects.filter(apu=apu).first()

        if limpio["modo"] == MODO_UNA and not limpio["nombre"] and not limpio["descripcion"]:
            if pres is not None:
                pres.delete()
            return None

        if pres is None:
            pres = PresentacionItemPresupuesto(apu=apu)
        pres.nombre_comercial = limpio["nombre"]
        pres.descripcion_comercial = limpio["descripcion"]
        pres.actualizado_por = usuario
        pres.save()

        pres.lineas.all().delete()
        if limpio["modo"] == MODO_DESGLOSE:
            LineaPresentacionPresupuesto.objects.bulk_create([
                LineaPresentacionPresupuesto(
                    presentacion=pres,
                    nombre=ln["nombre"],
                    descripcion=ln["descripcion"],
                    cantidad=ln["cantidad"],
                    orden=i,
                )
                for i, ln in enumerate(limpio["lineas"], start=1)
            ])
        return pres


def restablecer_presentacion(proyecto, apu_id) -> bool:
    """Elimina la presentación comercial (CASCADE a sus líneas). No toca el APU."""
    with transaction.atomic():
        apu = _apu_del_presupuesto(proyecto, apu_id, bloquear=True)
        if presupuesto_bloqueado(proyecto):
            raise PresentacionBloqueada(
                "El presupuesto está aprobado: la presentación comercial es de solo lectura."
            )
        borrados, _ = PresentacionItemPresupuesto.objects.filter(apu=apu).delete()
        return borrados > 0
