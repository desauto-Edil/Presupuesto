"""apps/catalogos/templatetags/catalogo_tags.py

Template tags and filters for the catalogos module.

Usage:
    {% load catalogo_tags %}
    {{ producto.precio_actual|currency:producto.moneda }}
    {{ precio|currency:"USD" }}
    {{ moneda_code|currency_symbol }}
"""

from django import template
from django.utils.formats import number_format

register = template.Library()


# ── Símbolos por moneda ───────────────────────────────────────────────────────

_SYMBOLS = {
    "COP": "$",
    "USD": "USD ",
    "EUR": "€",
}

_LOCALE_FORMAT = {
    "COP": True,   # usa separador de miles
    "USD": True,
    "EUR": True,
}


@register.filter(name="currency_symbol")
def currency_symbol(moneda_code: str) -> str:
    """Returns the display symbol for a currency code.

    {{ 'USD'|currency_symbol }}  →  'USD '
    {{ 'COP'|currency_symbol }}  →  '$'
    """
    return _SYMBOLS.get(str(moneda_code).upper(), "$")


@register.filter(name="currency")
def currency(value, moneda_code="COP"):
    """Format a number as currency with the correct symbol and decimal places.

    {{ linea.precio_snapshot|currency:linea.producto.moneda }}
    {{ apu.total_valor_venta|currency:"COP" }}

    COP → $1.234.567
    USD → USD 1,234.56
    EUR → €1.234,56
    """
    if value is None or value == "":
        return "—"

    moneda = str(moneda_code).upper() if moneda_code else "COP"
    symbol = _SYMBOLS.get(moneda, "$")

    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)

    if moneda == "COP":
        # No decimals for COP (whole pesos)
        formatted = f"{num:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{symbol}{formatted}"
    else:
        # 2 decimal places for foreign currencies
        formatted = f"{num:,.2f}"
        return f"{symbol}{formatted}"


@register.filter(name="sum_attr")
def sum_attr(objects, attr):
    """Suma el atributo 'attr' de cada objeto en la lista.

    {{ cat_group.list|sum_attr:"costo_por_dia"|floatformat:2 }}
    """
    try:
        return sum(float(getattr(obj, attr, 0) or 0) for obj in objects)
    except (TypeError, ValueError):
        return 0


@register.filter(name="multiply")
def multiply(value, arg):
    """Multiplica value por arg. Útil para calcular totales en plantillas."""
    try:
        return float(value) * float(arg)
    except (TypeError, ValueError):
        return ""


@register.filter(name="get_item")
def get_item(dictionary, key):
    """Accede a un dict con clave variable en templates.

    {{ lineas_cantidades|get_item:item.pk }}
    Prueba la clave tal cual, luego como int y luego como str.
    """
    if not isinstance(dictionary, dict):
        return None
    val = dictionary.get(key)
    if val is not None:
        return val
    # Intentar conversión int → por si la clave viene como str
    try:
        val = dictionary.get(int(key))
        if val is not None:
            return val
    except (TypeError, ValueError):
        pass
    return dictionary.get(str(key))


@register.filter(name="currency_nodec")
def currency_nodec(value, moneda_code="COP"):
    """Same as currency but always 0 decimal places (for totals)."""
    if value is None or value == "":
        return "—"
    moneda = str(moneda_code).upper() if moneda_code else "COP"
    symbol = _SYMBOLS.get(moneda, "$")
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)

    if moneda == "COP":
        formatted = f"{num:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
    else:
        formatted = f"{num:,.0f}"
    return f"{symbol}{formatted}"
