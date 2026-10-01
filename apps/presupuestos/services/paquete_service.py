"""
apps/presupuestos/services/paquete_service.py — Paquetes APU maestros (Fase 3.A).

Capa delgada entre la interfaz del catálogo y los modelos de Fase 2. No define
reglas económicas propias: el valor diario sale de `ItemCatalogoAPU` (fuente
única `apps.presupuestos.economia`) y el aporte de `calcular_aporte`.

Responsabilidades:
  - parsear/validar la composición enviada por el constructor de paquetes;
  - guardar datos generales + componentes de forma atómica;
  - calcular la previsualización (valor diario × cantidad = aporte, total).
"""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.presupuestos.economia import ValorDiarioError, calcular_aporte, calcular_valor_diario
from apps.presupuestos.models import ItemCatalogoAPU, PaqueteAPU, PaqueteAPUItem

# Iconografía (Bootstrap Icons) por TipoAPU, compartida por catálogo y subsistema.
TIPO_APU_ICONO = {
    "MANO_DE_OBRA": "people",
    "HERRAMIENTAS_EQUIPOS": "tools",
    "TRANSPORTE": "truck",
    "ADMINISTRACION": "briefcase",
    "MATERIALES": "box-seam",
}

# Límites de PaqueteAPUItem.cantidad: DecimalField(max_digits=14, decimal_places=4).
_CANTIDAD_DECIMALES = 4
_CANTIDAD_ENTEROS = 10


def formato_cop(valor) -> str:
    """$1.234.567 (pesos enteros): el mismo filtro `currency` que usan las plantillas."""
    from apps.catalogos.templatetags.catalogo_tags import currency
    return "" if valor is None else currency(valor)


def parse_cantidad(valor) -> Decimal:
    """Cantidad decimal > 0 con hasta 4 decimales. Acepta coma o punto decimal."""
    texto = str(valor if valor is not None else "").strip().replace(",", ".")
    if not texto:
        raise ValidationError("Indica la cantidad.")
    try:
        cantidad = Decimal(texto)
    except InvalidOperation:
        raise ValidationError(f"«{valor}» no es una cantidad válida.")
    if not cantidad.is_finite() or cantidad <= 0:
        raise ValidationError("La cantidad debe ser mayor que cero.")
    signo, digitos, exponente = cantidad.normalize().as_tuple()
    if exponente < -_CANTIDAD_DECIMALES:
        raise ValidationError(f"La cantidad admite máximo {_CANTIDAD_DECIMALES} decimales.")
    if cantidad >= Decimal(10) ** _CANTIDAD_ENTEROS:
        raise ValidationError("La cantidad es demasiado grande.")
    return cantidad


def valor_diario_o_none(item):
    try:
        return calcular_valor_diario(item.valor_base, item.vida_util_dias)
    except ValorDiarioError:
        return None


def item_a_dict(item) -> dict:
    """Representación de un ítem para el selector de componentes."""
    vd = valor_diario_o_none(item)
    return {
        "id": item.pk,
        "codigo": item.codigo or "",
        "nombre": item.nombre,
        "categoria": item.categoria.nombre,
        "categoria_id": item.categoria_id,
        "tipo_apu": item.categoria.tipo_apu,
        "unidad": item.get_unidad_display(),
        "activo": item.activo,
        "calculable": vd is not None,
        "valor_diario": str(vd) if vd is not None else None,
        "valor_diario_fmt": formato_cop(vd) if vd is not None else None,
    }


def resumen_paquete(paquete) -> dict:
    """Datos de presentación de un paquete maestro (valor desde el modelo de Fase 2)."""
    comps = list(paquete.componentes())
    pendientes = [c for c in comps if not c.item_catalogo.es_calculable]
    valor = paquete.valor_paquete() if comps else None
    return {
        "obj": paquete,
        "componentes": comps,
        "n_componentes": len(comps),
        "n_pendientes": len(pendientes),
        "valor": valor,
        "valor_fmt": formato_cop(valor) if valor is not None else None,
        "icono": TIPO_APU_ICONO.get(paquete.tipo_apu, "stack"),
        "categoria_ids": sorted({c.item_catalogo.categoria_id for c in comps}),
    }


def parse_componentes(filas, tipo_apu, permitidos_inactivos=()) -> list:
    """
    Valida la composición enviada por el constructor.

    filas: iterable de dicts {"item": <id>, "cantidad": <str>}; el orden de la
    lista define `orden`. Solo admite ítems existentes del TipoAPU del paquete,
    sin duplicados. Los ítems inactivos solo se aceptan si ya eran componentes
    (`permitidos_inactivos`), para no perder composición histórica.

    Devuelve [(item, cantidad, orden)] o lanza ValidationError con la lista de
    mensajes.
    """
    errores, resultado, vistos = [], [], set()
    ids = []
    for fila in filas:
        try:
            ids.append(int(fila.get("item")))
        except (TypeError, ValueError):
            errores.append("Hay un componente sin ítem válido.")
    items = {
        i.pk: i for i in
        ItemCatalogoAPU.objects.select_related("categoria").filter(pk__in=ids)
    }
    for orden, fila in enumerate(filas):
        try:
            item_id = int(fila.get("item"))
        except (TypeError, ValueError):
            continue
        item = items.get(item_id)
        if item is None:
            errores.append(f"El ítem #{item_id} no existe en el catálogo.")
            continue
        if item_id in vistos:
            errores.append(f"«{item.nombre}» está repetido en el paquete.")
            continue
        vistos.add(item_id)
        if item.categoria.tipo_apu != tipo_apu:
            errores.append(
                f"«{item.nombre}» es de otro TipoAPU; el paquete solo admite ítems de su tipo."
            )
            continue
        if not item.activo and item_id not in permitidos_inactivos:
            errores.append(f"«{item.nombre}» está inactivo y no puede agregarse.")
            continue
        try:
            cantidad = parse_cantidad(fila.get("cantidad"))
        except ValidationError as exc:
            errores.append(f"«{item.nombre}»: {exc.messages[0]}")
            continue
        resultado.append((item, cantidad, orden))
    if errores:
        raise ValidationError(errores)
    return resultado


@transaction.atomic
def guardar_paquete(paquete: PaqueteAPU, componentes: list) -> PaqueteAPU:
    """
    Guarda datos generales y composición (upsert) en una sola transacción.

    Los componentes retirados se eliminan antes de guardar el paquete para que
    `PaqueteAPU.clean()` evalúe la composición final.
    """
    nuevos = {item.pk: (cantidad, orden) for item, cantidad, orden in componentes}
    if paquete.pk:
        paquete.items.exclude(item_catalogo_id__in=nuevos.keys()).delete()
    paquete.save()
    existentes = {c.item_catalogo_id: c for c in paquete.items.all()}
    for item, cantidad, orden in componentes:
        comp = existentes.get(item.pk)
        if comp is None:
            comp = PaqueteAPUItem(paquete=paquete, item_catalogo=item)
        comp.cantidad = cantidad
        comp.orden = orden
        comp.save()
    return paquete


def previsualizar(filas) -> dict:
    """
    Previsualización económica del constructor, calculada en backend:
    aporte = valor_diario × cantidad por fila y total = Σ aportes. Si algún ítem
    no es calculable el total es None (paquete no calculable). Una cantidad
    inválida anula el aporte de su fila y el total, con el error por fila.
    """
    ids = []
    for f in filas:
        try:
            ids.append(int(f.get("item")))
        except (TypeError, ValueError):
            pass
    items = {
        i.pk: i for i in
        ItemCatalogoAPU.objects.select_related("categoria").filter(pk__in=ids)
    }
    salida, total, completo, pendientes = [], Decimal("0"), True, 0
    for f in filas:
        try:
            item = items.get(int(f.get("item")))
        except (TypeError, ValueError):
            item = None
        fila = {"item": f.get("item"), "aporte": None, "aporte_fmt": None, "error": None}
        if item is None:
            fila["error"] = "Ítem inexistente."
            completo = False
            salida.append(fila)
            continue
        vd = valor_diario_o_none(item)
        try:
            cantidad = parse_cantidad(f.get("cantidad"))
        except ValidationError as exc:
            fila["error"] = exc.messages[0]
            cantidad = None
        if vd is None:
            pendientes += 1
        if vd is None or cantidad is None:
            completo = False
        else:
            aporte = calcular_aporte(vd, cantidad)
            fila["aporte"] = str(aporte)
            fila["aporte_fmt"] = formato_cop(aporte)
            total += aporte
        salida.append(fila)
    return {
        "filas": salida,
        "calculable": completo,
        "pendientes": pendientes,
        "total": str(total) if completo else None,
        "total_fmt": formato_cop(total) if completo else None,
    }
