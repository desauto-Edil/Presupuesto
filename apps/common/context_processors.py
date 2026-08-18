"""
apps/common/context_processors.py
===================================

Context processors globales inyectados en todos los templates.

IMPORTANTE: Ninguno de estos processors puede provocar un error que rompa
la navegación. Ante cualquier fallo, devuelven valores nulos seguros.
"""


def trm_global(request):
    """
    Inyecta la TRM vigente en todos los templates.

    Variables disponibles:
        trm_global  — Decimal o None si no hay TRM disponible
        trm_fecha   — datetime.date de la TRM vigente, o None

    Si la TRM no está disponible (nunca se ha ejecutado `actualizar_trm`),
    se inyectan None y el template muestra "TRM: No disponible".
    Este error NO interrumpe la navegación.
    """
    try:
        from apps.common.trm_service import obtener_trm_registro, TRMNoDisponibleError
        registro = obtener_trm_registro()
        return {
            "trm_global": registro.valor,
            "trm_fecha":  registro.fecha,
        }
    except Exception:
        return {
            "trm_global": None,
            "trm_fecha":  None,
        }
