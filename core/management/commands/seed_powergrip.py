"""
management/commands/seed_powergrip.py

Carga la base de datos con los datos maestros del sistema PowerGrip
(sistemas, subsistemas, productos, reglas de cálculo).

Cambios FALKE 9 respecto a la versión anterior:
  - Las reglas usan categoria_producto en lugar de producto concreto;
    la variante específica se elige una sola vez por proyecto.
  - variable_salida permite derivación semántica real entre reglas:
    R02 (Limpiador) exporta "Limpiador" al contexto → R03 (Estopa)
    evalúa "Limpiador / 2" sin duplicar la fórmula.
  - R00 (tipo EDITABLE_USUARIO) registra el conector base en el despiece.
  - Se eliminan las DEPENDENCIAS redundantes; todo queda en REGLAS.
  - update_or_create en productos y reglas → seed idempotente.

Uso:
    python manage.py seed_powergrip
    python manage.py seed_powergrip --reset   # borra y recrea desde cero
"""

from django.core.management.base import BaseCommand
from django.db import transaction


UNIDADES = [
    {"codigo": "UND", "nombre": "Unidad",          "abreviatura": "und"},
    {"codigo": "GAL", "nombre": "Galón",            "abreviatura": "gal"},
    {"codigo": "KG",  "nombre": "Kilogramo",        "abreviatura": "kg"},
    {"codigo": "CAR", "nombre": "Cartucho",         "abreviatura": "crt"},
    {"codigo": "M2",  "nombre": "Metro cuadrado",   "abreviatura": "m²"},
    {"codigo": "ML",  "nombre": "Metro lineal",     "abreviatura": "ml"},
]

# Categorías granulares para PowerGrip.
# QUIMICO se mantiene por compatibilidad con registros previos.
CATEGORIAS = [
    {"codigo": "FIJACION",  "nombre": "Fijaciones"},
    {"codigo": "LIMPIADOR", "nombre": "Limpiadores"},
    {"codigo": "ESTOPA_KG", "nombre": "Estopa industrial"},
    {"codigo": "SELLADOR",  "nombre": "Selladores"},
    {"codigo": "ACCESORIO", "nombre": "Accesorios"},
    {"codigo": "PROTECCION","nombre": "Protección"},
    {"codigo": "MANO_OBRA", "nombre": "Mano de obra"},
    {"codigo": "QUIMICO",   "nombre": "Químicos (legado)"},  # legado
]

PRODUCTOS = [
    # ── Conectores PowerGrip ────────────────────────────────────────────────
    {"codigo": "PG-U7",        "nombre": "PowerGrip Universal 7",           "categoria": "ACCESORIO", "unidad": "UND"},
    {"codigo": "PG-PLUS",      "nombre": "PowerGrip Plus TPO",              "categoria": "ACCESORIO", "unidad": "UND"},
    # ── Fijaciones HDF (variante elegida por proyecto) ──────────────────────
    {"codigo": "FIJ-HDF-114C", "nombre": "Fijación HDF 1-1/4\" Chino",     "categoria": "FIJACION",  "unidad": "UND"},
    {"codigo": "FIJ-HDF-114E", "nombre": "Fijación HDF 1-1/4\" Elevate",   "categoria": "FIJACION",  "unidad": "UND"},
    {"codigo": "FIJ-HDF-2C",   "nombre": "Fijación HDF 2\" Chino",         "categoria": "FIJACION",  "unidad": "UND"},
    {"codigo": "FIJ-HDF-2E",   "nombre": "Fijación HDF 2\" Elevate",       "categoria": "FIJACION",  "unidad": "UND"},
    {"codigo": "FIJ-HDF-3C",   "nombre": "Fijación HDF 3\" Chino",         "categoria": "FIJACION",  "unidad": "UND"},
    {"codigo": "FIJ-HDF-3E",   "nombre": "Fijación HDF 3\" Elevate",       "categoria": "FIJACION",  "unidad": "UND"},
    {"codigo": "FIJ-HDF-4C",   "nombre": "Fijación HDF 4\" Chino",         "categoria": "FIJACION",  "unidad": "UND"},
    {"codigo": "FIJ-HDF-4E",   "nombre": "Fijación HDF 4\" Elevate",       "categoria": "FIJACION",  "unidad": "UND"},
    {"codigo": "FIJ-HDF-5C",   "nombre": "Fijación HDF 5\" Chino",         "categoria": "FIJACION",  "unidad": "UND"},
    {"codigo": "FIJ-HDF-5E",   "nombre": "Fijación HDF 5\" Elevate",       "categoria": "FIJACION",  "unidad": "UND"},
    {"codigo": "FIJ-CDF-C",    "nombre": "Concrete Drive Fastener Chino",  "categoria": "FIJACION",  "unidad": "UND"},
    {"codigo": "FIJ-CDF-E",    "nombre": "Concrete Drive Fastener Elevate","categoria": "FIJACION",  "unidad": "UND"},
    # ── Limpiadores (variante elegida por proyecto) ─────────────────────────
    {"codigo": "LMP-SPLICE",   "nombre": "Limpiador Splice Wash",           "categoria": "LIMPIADOR", "unidad": "GAL"},
    {"codigo": "LMP-VARSOL",   "nombre": "Limpiador Varsol Industrial",     "categoria": "LIMPIADOR", "unidad": "GAL"},
    # ── Estopa ──────────────────────────────────────────────────────────────
    {"codigo": "ESTOPA",       "nombre": "Estopa industrial",               "categoria": "ESTOPA_KG", "unidad": "KG"},
    # ── Selladores (variante elegida por proyecto) ──────────────────────────
    {"codigo": "SELL-CUT",     "nombre": "Sellador Cut Edge Sealant",       "categoria": "SELLADOR",  "unidad": "CAR"},
    {"codigo": "SELL-WB",      "nombre": "Sellador WaterBlock",             "categoria": "SELLADOR",  "unidad": "CAR"},
]

SISTEMA = {
    "codigo": "POWERGRIP",
    "nombre": "PowerGrip",
    "linea_negocio": "CUBIERTAS",
    "descripcion": "Sistema de fijación mecánica para cubiertas TPO/PVC",
}

SUBSISTEMAS = [
    {"codigo": "PG-U7",   "nombre": "Universal 7",
     "descripcion": "Variante Universal 7 — 8 fijaciones por conector"},
    {"codigo": "PG-PLUS", "nombre": "Plus TPO",
     "descripcion": "Variante Plus TPO — 9 fijaciones por conector"},
]

# ---------------------------------------------------------------------------
# RECETAS DE CÁLCULO  (FALKE 9)
#
# Cada entrada define:
#   categoria       → CategoriaProducto usada al crear el DespieceLinea
#   variable_salida → alias semántico que la regla aporta al contexto de
#                     evaluación; las reglas derivadas lo referencian por nombre
#   obligatoria     → si False el componente es opcional en el proyecto
#
# Orden de ejecución importa: R02 (Limpiador) debe ejecutarse antes de R03
# (Estopa) para que "Limpiador" esté disponible en el contexto.
# ---------------------------------------------------------------------------
REGLAS = {
    "PG-U7": [
        # ── R00: conector base (cantidad = Total_PowerGrip ingresado por proyecto)
        {
            "codigo": "U7-R00", "nombre": "Conector PowerGrip Universal 7",
            "categoria": "ACCESORIO",
            "variable_entrada": "Total_PowerGrip",
            "coeficiente": 1, "divisor": 1, "factor_desperdicio": 1.0,
            "formula_texto": "Total_PowerGrip",
            "formula_python": "Total_PowerGrip",
            "tipo_regla": "EDITABLE_USUARIO", "orden_ejecucion": 0,
            "variable_salida": "", "obligatoria": True,
        },
        # ── R01: fijaciones — 8 por conector + 1% desperdicio
        {
            "codigo": "U7-R01", "nombre": "Fijaciones Universal 7",
            "categoria": "FIJACION",
            "variable_entrada": "Total_PowerGrip",
            "coeficiente": 8, "divisor": 1, "factor_desperdicio": 1.01,
            "formula_texto": "(8 × Total_PowerGrip) × 101%",
            "formula_python": "(8 * Total_PowerGrip) * 1.01",
            "tipo_regla": "FIJA", "orden_ejecucion": 1,
            "variable_salida": "", "obligatoria": True,
        },
        # ── R02: limpiador — 0.04 gal por conector / 50 und por galón + 1%
        #    variable_salida="Limpiador" → R03 puede usar "Limpiador / 2" directamente
        {
            "codigo": "U7-R02", "nombre": "Limpiador Universal 7",
            "categoria": "LIMPIADOR",
            "variable_entrada": "Total_PowerGrip",
            "coeficiente": 0.04, "divisor": 50, "factor_desperdicio": 1.01,
            "formula_texto": "((Total_PowerGrip × 0.04) / 50) × 101%",
            "formula_python": "((Total_PowerGrip * 0.04) / 50) * 1.01",
            "tipo_regla": "FIJA", "orden_ejecucion": 2,
            "variable_salida": "Limpiador", "obligatoria": True,
        },
        # ── R03: estopa — derivada del limpiador ya calculado (0.5 kg por galón)
        #    NOTA: formula_python usa "Limpiador" del contexto, no una fórmula duplicada
        {
            "codigo": "U7-R03", "nombre": "Estopa Universal 7",
            "categoria": "ESTOPA_KG",
            "variable_entrada": "Limpiador",
            "coeficiente": 1, "divisor": 2, "factor_desperdicio": 1.0,
            "formula_texto": "Limpiador / 2",
            "formula_python": "Limpiador / 2",
            "tipo_regla": "DERIVADA", "orden_ejecucion": 3,
            "variable_salida": "", "obligatoria": True,
        },
        # ── R04: sellador — 0.56 m² / 12 und por cartucho + 1%
        {
            "codigo": "U7-R04", "nombre": "Sellador Universal 7",
            "categoria": "SELLADOR",
            "variable_entrada": "Total_PowerGrip",
            "coeficiente": 0.56, "divisor": 12, "factor_desperdicio": 1.01,
            "formula_texto": "((Total_PowerGrip × 0.56) / 12) × 101%",
            "formula_python": "((Total_PowerGrip * 0.56) / 12) * 1.01",
            "tipo_regla": "FIJA", "orden_ejecucion": 4,
            "variable_salida": "", "obligatoria": True,
        },
    ],
    "PG-PLUS": [
        # ── R00: conector base
        {
            "codigo": "PLUS-R00", "nombre": "Conector PowerGrip Plus TPO",
            "categoria": "ACCESORIO",
            "variable_entrada": "Total_PowerGrip",
            "coeficiente": 1, "divisor": 1, "factor_desperdicio": 1.0,
            "formula_texto": "Total_PowerGrip",
            "formula_python": "Total_PowerGrip",
            "tipo_regla": "EDITABLE_USUARIO", "orden_ejecucion": 0,
            "variable_salida": "", "obligatoria": True,
        },
        # ── R01: fijaciones — 9 por conector + 1%
        {
            "codigo": "PLUS-R01", "nombre": "Fijaciones Plus TPO",
            "categoria": "FIJACION",
            "variable_entrada": "Total_PowerGrip",
            "coeficiente": 9, "divisor": 1, "factor_desperdicio": 1.01,
            "formula_texto": "(9 × Total_PowerGrip) × 101%",
            "formula_python": "(9 * Total_PowerGrip) * 1.01",
            "tipo_regla": "FIJA", "orden_ejecucion": 1,
            "variable_salida": "", "obligatoria": True,
        },
        # ── R02: limpiador — 0.09 gal por conector / 50 und + 1%
        {
            "codigo": "PLUS-R02", "nombre": "Limpiador Plus TPO",
            "categoria": "LIMPIADOR",
            "variable_entrada": "Total_PowerGrip",
            "coeficiente": 0.09, "divisor": 50, "factor_desperdicio": 1.01,
            "formula_texto": "((Total_PowerGrip × 0.09) / 50) × 101%",
            "formula_python": "((Total_PowerGrip * 0.09) / 50) * 1.01",
            "tipo_regla": "FIJA", "orden_ejecucion": 2,
            "variable_salida": "Limpiador", "obligatoria": True,
        },
        # ── R03: estopa — la mitad del limpiador calculado
        {
            "codigo": "PLUS-R03", "nombre": "Estopa Plus TPO",
            "categoria": "ESTOPA_KG",
            "variable_entrada": "Limpiador",
            "coeficiente": 1, "divisor": 2, "factor_desperdicio": 1.0,
            "formula_texto": "Limpiador / 2",
            "formula_python": "Limpiador / 2",
            "tipo_regla": "DERIVADA", "orden_ejecucion": 3,
            "variable_salida": "", "obligatoria": True,
        },
        # ── R04: sellador de corte — 1.16 ml / 36.1 ml por cartucho + 1%
        {
            "codigo": "PLUS-R04", "nombre": "Sellador Plus TPO",
            "categoria": "SELLADOR",
            "variable_entrada": "Total_PowerGrip",
            "coeficiente": 1.16, "divisor": 36.1, "factor_desperdicio": 1.01,
            "formula_texto": "((Total_PowerGrip × 1.16) / 36.1) × 101%",
            "formula_python": "((Total_PowerGrip * 1.16) / 36.1) * 1.01",
            "tipo_regla": "FIJA", "orden_ejecucion": 4,
            "variable_salida": "", "obligatoria": True,
        },
    ],
}

# Configuración APU predeterminada
CONFIG_APU = {
    "porcentaje_ganancia":         20,
    "aiu_contratista":             30,
    "desperdicio":                 3,
    "margen_ganancia_contratista": 30,
}

# Tipos de proyecto
TIPOS_PROYECTO = [
    {"codigo": "BODEGA",    "nombre": "Bodega"},
    {"codigo": "PTAR",      "nombre": "PTAR"},
    {"codigo": "INDUSTRIA", "nombre": "Industrial"},
    {"codigo": "COMERCIO",  "nombre": "Comercial"},
    {"codigo": "CUBIERTA",  "nombre": "Cubierta"},
]


class Command(BaseCommand):
    help = "Carga datos maestros del sistema PowerGrip (FALKE 9 — category-based)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true",
            help="Elimina reglas, productos, subsistemas y sistema antes de recargar"
        )

    @transaction.atomic
    def handle(self, *args, **options):
        from core.models import (
            UnidadMedida, CategoriaProducto, Producto,
            Sistema, Subsistema, ReglaCalculo,
            ConfiguracionAPU, TipoProyecto,
        )

        if options["reset"]:
            self.stdout.write("⚠️  Reseteando datos maestros...")
            ReglaCalculo.objects.all().delete()
            Producto.objects.all().delete()
            Subsistema.objects.all().delete()
            Sistema.objects.all().delete()

        # 1. Unidades de medida
        self.stdout.write("→ Unidades de medida")
        for u in UNIDADES:
            UnidadMedida.objects.get_or_create(codigo=u["codigo"], defaults=u)

        # 2. Categorías de producto
        self.stdout.write("→ Categorías de producto")
        for c in CATEGORIAS:
            CategoriaProducto.objects.get_or_create(
                codigo=c["codigo"], defaults={"nombre": c["nombre"]}
            )

        # 3. Productos — update_or_create para que relanzar el seed
        #    actualice las categorías si cambiaron
        self.stdout.write("→ Productos")
        for p in PRODUCTOS:
            cat = CategoriaProducto.objects.get(codigo=p["categoria"])
            uni = UnidadMedida.objects.get(codigo=p["unidad"])
            Producto.objects.update_or_create(
                codigo=p["codigo"],
                defaults={"nombre": p["nombre"], "categoria": cat, "unidad": uni}
            )

        # 4. Sistema
        self.stdout.write("→ Sistema PowerGrip")
        sistema, _ = Sistema.objects.get_or_create(
            codigo=SISTEMA["codigo"],
            defaults=SISTEMA
        )

        # 5. Subsistemas + Reglas de cálculo
        for sub_data in SUBSISTEMAS:
            self.stdout.write(f"  → Subsistema {sub_data['nombre']}")
            sub, _ = Subsistema.objects.get_or_create(
                codigo=sub_data["codigo"],
                defaults={**sub_data, "sistema": sistema}
            )

            for regla_data in REGLAS.get(sub_data["codigo"], []):
                r = dict(regla_data)          # copia para no mutar la constante
                cat_codigo  = r.pop("categoria")
                var_salida  = r.pop("variable_salida", "")
                obligatoria = r.pop("obligatoria", True)
                categoria   = CategoriaProducto.objects.get(codigo=cat_codigo)

                obj, created = ReglaCalculo.objects.update_or_create(
                    subsistema=sub,
                    codigo=r["codigo"],
                    version=1,
                    defaults={
                        **r,
                        "categoria_producto": categoria,
                        "producto":           None,
                        "variable_salida":    var_salida,
                        "obligatoria":        obligatoria,
                        "subsistema":         sub,
                    }
                )
                action = "creada" if created else "actualizada"
                self.stdout.write(f"    [{action}] {obj.codigo} — {obj.nombre}")

        # 6. Configuración APU predeterminada
        self.stdout.write("→ Configuración APU predeterminada")
        ConfiguracionAPU.objects.get_or_create(
            nombre="Configuración global",
            defaults=CONFIG_APU
        )

        # 7. Tipos de proyecto
        self.stdout.write("→ Tipos de proyecto")
        for tp in TIPOS_PROYECTO:
            TipoProyecto.objects.get_or_create(codigo=tp["codigo"], defaults=tp)

        self.stdout.write(self.style.SUCCESS("✅  Datos maestros cargados correctamente."))
