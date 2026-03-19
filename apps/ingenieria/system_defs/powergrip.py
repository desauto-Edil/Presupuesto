"""
apps/ingenieria/system_defs/powergrip.py — Definición backend del sistema PowerGrip.

Fuente: Excel "PT-13145 PowerGrip para cubierta TPO CEDI ARA. (Cota y Gachancipá).xlsx"
Hoja:   "Despiece PowerGrip" — Convertida a definición Python con fórmulas verificadas.

═══════════════════════════════════════════════════════════════════════════
  SUBSISTEMA: Universal 7
═══════════════════════════════════════════════════════════════════════════
  Variables de entrada:
    - total_powergrip   : Unidades de PowerGrip a instalar (ej: 2883)
    - tornilleria_u7    : Tornillos por PowerGrip Universal 7 (default: 8)
    - desperdicio        : Factor de desperdicio (default: 1.01)

  Componentes (en orden de ejecución):
    1. PowerGrip Universal 7   → cantidad = total_powergrip
    2. Fijaciones              → (total_powergrip × tornilleria_u7) × desperdicio
       Excel: 2883 × 8 × 1.01 = 23.294,64
    3. Limpiador (Splice Wash) → ((total_powergrip × 0.04) / 50) × desperdicio
       Excel: (2883 × 0.04 / 50) × 1.01 = 2,33 galon
       → Produce variable "limpiador" en contexto para paso 4
    4. Estopa                  → limpiador / 2
       Excel: 2,33 / 2 = 1,16 kg
    5. Sellador Water Block    → ((total_powergrip × 0.56) / 12) × desperdicio
       Excel: (2883 × 0.56 / 12) × 1.01 = 135,89 cartuchos

═══════════════════════════════════════════════════════════════════════════
  SUBSISTEMA: PowerGrip Plus TPO
═══════════════════════════════════════════════════════════════════════════
  Variables de entrada:
    - total_powergrip   : Unidades de PowerGrip a instalar (ej: 2883)
    - tornilleria_plus  : Tornillos por PowerGrip Plus (default: 9)
    - desperdicio        : Factor de desperdicio (default: 1.01)

  Componentes (en orden de ejecución):
    1. PowerGrip Plus          → cantidad = total_powergrip
    2. Fijaciones              → (total_powergrip × tornilleria_plus) × desperdicio
       Excel: 2883 × 9 × 1.01 = 26.206,47
    3. Limpiador (Splice Wash) → ((total_powergrip × 0.09) / 20) × desperdicio
       Excel: (2883 × 0.09 / 20) × 1.01 = 13,10 galon
       → Produce variable "limpiador" en contexto para paso 4
    4. Estopa                  → limpiador / 2
       Excel: 13,10 / 2 = 6,55 kg
    5. Sellador TPO            → ((total_powergrip × 1.16) / 36.1) × desperdicio
       Excel: (2883 × 1.16 / 36.1) × 1.01 = 93,57 litros
"""

from apps.ingenieria.system_defs.base import (
    SistemaDef, SubsistemaDef, ComponenteDef, VariableRequerida,
)


# ── Variables comunes a ambos subsistemas ─────────────────────────────────────

_VAR_TOTAL_PG = VariableRequerida(
    variable="total_powergrip",
    label="Total de PowerGrips a instalar",
    unidad="und",
    default=0.0,
    descripcion="Unidades de PowerGrip calculadas desde el plano o conteo de área.",
)
_VAR_DESPERDICIO = VariableRequerida(
    variable="desperdicio",
    label="Factor de desperdicio",
    unidad="",
    default=1.01,
    descripcion="Factor multiplicador de desperdicio. Default: 1.01 (1%).",
)


# ── Subsistema: Universal 7 ───────────────────────────────────────────────────

_UNIVERSAL_7 = SubsistemaDef(
    codigo="PG_UNIVERSAL_7",
    nombre="PowerGrip Universal 7",
    variables=[
        _VAR_TOTAL_PG,
        VariableRequerida(
            variable="tornilleria_u7",
            label="Tornillos por unidad (Universal 7)",
            unidad="und",
            default=8.0,
            descripcion="Cantidad de tornillos Heavy Duty 3\" por cada PowerGrip Universal 7.",
        ),
        _VAR_DESPERDICIO,
    ],
    componentes=[
        ComponenteDef(
            codigo="pg_universal_7",
            nombre="PowerGrip Universal 7",
            categoria_slug="PowerGrip",
            formula=lambda ctx: ctx["total_powergrip"],
            unidad="und",
            orden=1,
            pendiente_seleccion=True,
            descripcion="Fijador principal del sistema. El usuario elige el producto de la categoría PowerGrip.",
        ),
        ComponenteDef(
            codigo="fijaciones_u7",
            nombre='Fijaciones Heavy Duty Fastener 3"',
            categoria_slug="Fijaciones",
            formula=lambda ctx: (ctx["total_powergrip"] * ctx["tornilleria_u7"]) * ctx["desperdicio"],
            unidad="und",
            orden=2,
            pendiente_seleccion=True,
            descripcion="Tornillos de fijación al sustrato. Fórmula: (PowerGrips × tornillos/ud) × desperdicio.",
        ),
        ComponenteDef(
            codigo="limpiador_u7",
            nombre="Accesorios: Splice Wash SW-100",
            categoria_slug="Accesorios",
            formula=lambda ctx: ((ctx["total_powergrip"] * (0.2 * 0.2)) / 50) * ctx["desperdicio"],
            unidad="galon",
            orden=3,
            variable_salida="limpiador",
            pendiente_seleccion=True,
            descripcion=(
                "Limpiador Splice Wash. "
                "Fórmula: ((PowerGrips × 0.04) / 50) × desperdicio. "
                "El resultado queda disponible como 'limpiador' para calcular Estopa."
            ),
        ),
        ComponenteDef(
            codigo="estopa_u7",
            nombre="Estopa",
            categoria_slug="Estopa",
            formula=lambda ctx: ctx["limpiador"] / 2,
            unidad="kg",
            orden=4,
            pendiente_seleccion=True,
            descripcion="Estopa para limpieza. Fórmula: Limpiador / 2.",
        ),
        ComponenteDef(
            codigo="sellador_u7",
            nombre="Sellador Water Block",
            categoria_slug="Sellador",
            formula=lambda ctx: ((ctx["total_powergrip"] * 0.56) / 12) * ctx["desperdicio"],
            unidad="cartucho",
            orden=5,
            pendiente_seleccion=True,
            descripcion="Sellador de bordes Water Block. Fórmula: ((PowerGrips × 0.56) / 12) × desperdicio.",
        ),
    ],
)


# ── Subsistema: PowerGrip Plus TPO ───────────────────────────────────────────

_PLUS_TPO = SubsistemaDef(
    codigo="PG_PLUS_TPO",
    nombre="PowerGrip Plus TPO",
    variables=[
        _VAR_TOTAL_PG,
        VariableRequerida(
            variable="tornilleria_plus",
            label="Tornillos por unidad (Plus TPO)",
            unidad="und",
            default=9.0,
            descripcion="Cantidad de tornillos Heavy Duty 3\" por cada PowerGrip Plus.",
        ),
        _VAR_DESPERDICIO,
    ],
    componentes=[
        ComponenteDef(
            codigo="pg_plus",
            nombre="PowerGrip Plus",
            categoria_slug="PowerGrip",
            formula=lambda ctx: ctx["total_powergrip"],
            unidad="und",
            orden=1,
            pendiente_seleccion=True,
            descripcion="Fijador principal del sistema TPO. El usuario elige el producto de la categoría PowerGrip.",
        ),
        ComponenteDef(
            codigo="fijaciones_plus",
            nombre='Fijaciones Heavy Duty Fastener 3"',
            categoria_slug="Fijaciones",
            formula=lambda ctx: (ctx["total_powergrip"] * ctx["tornilleria_plus"]) * ctx["desperdicio"],
            unidad="und",
            orden=2,
            pendiente_seleccion=True,
            descripcion="Tornillos de fijación. Fórmula: (PowerGrips × tornillos/ud) × desperdicio.",
        ),
        ComponenteDef(
            codigo="limpiador_plus",
            nombre="Accesorios: Splice Wash SW-100",
            categoria_slug="Accesorios",
            formula=lambda ctx: ((ctx["total_powergrip"] * (0.3 * 0.3)) / 20) * ctx["desperdicio"],
            unidad="galon",
            orden=3,
            variable_salida="limpiador",
            pendiente_seleccion=True,
            descripcion=(
                "Limpiador Splice Wash para TPO. "
                "Fórmula: ((PowerGrips × 0.09) / 20) × desperdicio. "
                "El resultado queda disponible como 'limpiador' para calcular Estopa."
            ),
        ),
        ComponenteDef(
            codigo="estopa_plus",
            nombre="Estopa",
            categoria_slug="Estopa",
            formula=lambda ctx: ctx["limpiador"] / 2,
            unidad="kg",
            orden=4,
            pendiente_seleccion=True,
            descripcion="Estopa para limpieza. Fórmula: Limpiador / 2.",
        ),
        ComponenteDef(
            codigo="sellador_tpo",
            nombre="Sellador TPO Clear Cut Edge Sealant",
            categoria_slug="Sellador",
            formula=lambda ctx: ((ctx["total_powergrip"] * 1.16) / 36.1) * ctx["desperdicio"],
            unidad="litro",
            orden=5,
            pendiente_seleccion=True,
            descripcion="Sellador TPO para bordes. Fórmula: ((PowerGrips × 1.16) / 36.1) × desperdicio.",
        ),
    ],
)


# ── Definición del sistema completo ──────────────────────────────────────────

POWERGRIP = SistemaDef(
    codigo="POWERGRIP",
    nombre="PowerGrip",
    subsistemas=[_UNIVERSAL_7, _PLUS_TPO],
)
