"""
management/commands/seed_powergrip.py

Carga la base de datos con los datos maestros del sistema PowerGrip
(sistemas, subsistemas, productos, reglas de cálculo y dependencias técnicas)
según la MATRIZ CORE.

Uso:
    python manage.py seed_powergrip
    python manage.py seed_powergrip --reset   # borra y recrea
"""

from django.core.management.base import BaseCommand
from django.db import transaction


UNIDADES = [
    {"codigo": "UND",  "nombre": "Unidad",   "abreviatura": "und"},
    {"codigo": "GAL",  "nombre": "Galón",    "abreviatura": "gal"},
    {"codigo": "KG",   "nombre": "Kilogramo","abreviatura": "kg"},
    {"codigo": "CAR",  "nombre": "Cartucho", "abreviatura": "crt"},
    {"codigo": "M2",   "nombre": "Metro cuadrado","abreviatura": "m²"},
    {"codigo": "ML",   "nombre": "Metro lineal",  "abreviatura": "ml"},
]

CATEGORIAS = [
    {"codigo": "FIJACION",  "nombre": "Fijaciones"},
    {"codigo": "QUIMICO",   "nombre": "Químicos"},
    {"codigo": "ACCESORIO", "nombre": "Accesorios"},
    {"codigo": "PROTECCION","nombre": "Protección"},
    {"codigo": "MANO_OBRA", "nombre": "Mano de obra"},
]

PRODUCTOS = [
    # PowerGrip principal
    {"codigo": "PG-U7",         "nombre": "PowerGrip Universal 7",        "categoria": "ACCESORIO", "unidad": "UND"},
    {"codigo": "PG-PLUS",       "nombre": "PowerGrip Plus TPO",           "categoria": "ACCESORIO", "unidad": "UND"},
    # Fijaciones Universal 7
    {"codigo": "FIJ-HDF-114C",  "nombre": "Fijación HDF 1-1/4 Chino",    "categoria": "FIJACION",  "unidad": "UND"},
    {"codigo": "FIJ-HDF-114E",  "nombre": "Fijación HDF 1-1/4 Elevate",  "categoria": "FIJACION",  "unidad": "UND"},
    {"codigo": "FIJ-HDF-2C",    "nombre": "Fijación HDF 2 Chino",        "categoria": "FIJACION",  "unidad": "UND"},
    {"codigo": "FIJ-HDF-2E",    "nombre": "Fijación HDF 2 Elevate",      "categoria": "FIJACION",  "unidad": "UND"},
    {"codigo": "FIJ-HDF-3C",    "nombre": "Fijación HDF 3 Chino",        "categoria": "FIJACION",  "unidad": "UND"},
    {"codigo": "FIJ-HDF-3E",    "nombre": "Fijación HDF 3 Elevate",      "categoria": "FIJACION",  "unidad": "UND"},
    {"codigo": "FIJ-HDF-4C",    "nombre": "Fijación HDF 4 Chino",        "categoria": "FIJACION",  "unidad": "UND"},
    {"codigo": "FIJ-HDF-4E",    "nombre": "Fijación HDF 4 Elevate",      "categoria": "FIJACION",  "unidad": "UND"},
    {"codigo": "FIJ-HDF-5C",    "nombre": "Fijación HDF 5 Chino",        "categoria": "FIJACION",  "unidad": "UND"},
    {"codigo": "FIJ-HDF-5E",    "nombre": "Fijación HDF 5 Elevate",      "categoria": "FIJACION",  "unidad": "UND"},
    {"codigo": "FIJ-CDF-C",     "nombre": "Concrete Drive Fastener Chino","categoria":"FIJACION",  "unidad": "UND"},
    {"codigo": "FIJ-CDF-E",     "nombre": "Concrete Drive Fastener Elevate","categoria":"FIJACION","unidad": "UND"},
    # Químicos
    {"codigo": "LMP-SPLICE",    "nombre": "Limpiador Splice Wash",        "categoria": "QUIMICO",   "unidad": "GAL"},
    {"codigo": "LMP-VARSOL",    "nombre": "Limpiador Varsol Industrial",   "categoria": "QUIMICO",   "unidad": "GAL"},
    {"codigo": "ESTOPA",        "nombre": "Estopa industrial",            "categoria": "QUIMICO",   "unidad": "KG"},
    {"codigo": "SELL-CUT",      "nombre": "Sellador Cut Edge Sealant",    "categoria": "QUIMICO",   "unidad": "CAR"},
    {"codigo": "SELL-WB",       "nombre": "Sellador WaterBlock",         "categoria": "QUIMICO",   "unidad": "CAR"},
]

SISTEMA = {
    "codigo": "POWERGRIP",
    "nombre": "PowerGrip",
    "linea_negocio": "CUBIERTAS",
    "descripcion": "Sistema de fijación mecánica para cubiertas TPO/PVC",
}

SUBSISTEMAS = [
    {"codigo": "PG-U7",   "nombre": "Universal 7",  "descripcion": "Variante Universal 7 con 8 fijaciones base"},
    {"codigo": "PG-PLUS", "nombre": "Plus TPO",     "descripcion": "Variante Plus TPO con 9 fijaciones base"},
]

# Reglas de cálculo indexadas por subsistema
REGLAS = {
    "PG-U7": [
        {
            "codigo": "U7-R01", "nombre": "Fijaciones Universal 7",
            "producto": "FIJ-HDF-114C",
            "variable_entrada": "Total_PowerGrip",
            "coeficiente": 8, "divisor": 1, "factor_desperdicio": 1.01,
            "formula_texto": "(8 × Total_PowerGrip) × 101%",
            "formula_python": "(8 * Total_PowerGrip) * 1.01",
            "tipo_regla": "FIJA", "orden_ejecucion": 1,
        },
        {
            "codigo": "U7-R02", "nombre": "Limpiador Universal 7",
            "producto": "LMP-SPLICE",
            "variable_entrada": "Total_PowerGrip",
            "coeficiente": 0.04, "divisor": 50, "factor_desperdicio": 1.01,
            "formula_texto": "((Total_PowerGrip × 0.04) / 50) × 101%",
            "formula_python": "((Total_PowerGrip * 0.04) / 50) * 1.01",
            "tipo_regla": "FIJA", "orden_ejecucion": 2,
        },
        {
            "codigo": "U7-R03", "nombre": "Estopa Universal 7",
            "producto": "ESTOPA",
            "variable_entrada": "LMP_SPLICE",
            "coeficiente": 1, "divisor": 2, "factor_desperdicio": 1.0,
            "formula_texto": "Limpiador / 2",
            "formula_python": "((Total_PowerGrip * 0.04) / 50) * 1.01 / 2",
            "tipo_regla": "DERIVADA", "orden_ejecucion": 3,
        },
        {
            "codigo": "U7-R04", "nombre": "Sellador Universal 7",
            "producto": "SELL-WB",
            "variable_entrada": "Total_PowerGrip",
            "coeficiente": 0.56, "divisor": 12, "factor_desperdicio": 1.01,
            "formula_texto": "((Total_PowerGrip × 0.56) / 12) × 101%",
            "formula_python": "((Total_PowerGrip * 0.56) / 12) * 1.01",
            "tipo_regla": "FIJA", "orden_ejecucion": 4,
        },
    ],
    "PG-PLUS": [
        {
            "codigo": "PLUS-R01", "nombre": "Fijaciones Plus TPO",
            "producto": "FIJ-HDF-114C",
            "variable_entrada": "Total_PowerGrip",
            "coeficiente": 9, "divisor": 1, "factor_desperdicio": 1.01,
            "formula_texto": "(9 × Total_PowerGrip) × 101%",
            "formula_python": "(9 * Total_PowerGrip) * 1.01",
            "tipo_regla": "FIJA", "orden_ejecucion": 1,
        },
        {
            "codigo": "PLUS-R02", "nombre": "Limpiador Plus TPO",
            "producto": "LMP-SPLICE",
            "variable_entrada": "Total_PowerGrip",
            "coeficiente": 0.09, "divisor": 50, "factor_desperdicio": 1.01,
            "formula_texto": "((Total_PowerGrip × 0.09) / 50) × 101%",
            "formula_python": "((Total_PowerGrip * 0.09) / 50) * 1.01",
            "tipo_regla": "FIJA", "orden_ejecucion": 2,
        },
        {
            "codigo": "PLUS-R03", "nombre": "Estopa Plus TPO",
            "producto": "ESTOPA",
            "variable_entrada": "LMP_SPLICE",
            "coeficiente": 1, "divisor": 2, "factor_desperdicio": 1.0,
            "formula_texto": "Limpiador / 2",
            "formula_python": "((Total_PowerGrip * 0.09) / 50) * 1.01 / 2",
            "tipo_regla": "DERIVADA", "orden_ejecucion": 3,
        },
        {
            "codigo": "PLUS-R04", "nombre": "Sellador Plus TPO",
            "producto": "SELL-CUT",
            "variable_entrada": "Total_PowerGrip",
            "coeficiente": 1.16, "divisor": 36.1, "factor_desperdicio": 1.01,
            "formula_texto": "((Total_PowerGrip × 1.16) / 36.1) × 101%",
            "formula_python": "((Total_PowerGrip * 1.16) / 36.1) * 1.01",
            "tipo_regla": "FIJA", "orden_ejecucion": 4,
        },
    ],
}

# Dependencias obligatorias por subsistema (se inyectan automáticamente)
DEPENDENCIAS = {
    "PG-U7": [
        {"producto_origen": None, "producto_dependiente": "LMP-SPLICE",  "orden": 1},
        {"producto_origen": None, "producto_dependiente": "ESTOPA",      "orden": 2},
        {"producto_origen": None, "producto_dependiente": "SELL-WB",     "orden": 3},
    ],
    "PG-PLUS": [
        {"producto_origen": None, "producto_dependiente": "LMP-SPLICE",  "orden": 1},
        {"producto_origen": None, "producto_dependiente": "ESTOPA",      "orden": 2},
        {"producto_origen": None, "producto_dependiente": "SELL-CUT",    "orden": 3},
    ],
}

# Configuración APU predeterminada
CONFIG_APU = {
    "porcentaje_ganancia":        20,
    "aiu_contratista":            30,
    "desperdicio":                3,
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
    help = "Carga datos maestros del sistema PowerGrip en la base de datos."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Elimina y recrea los datos")

    @transaction.atomic
    def handle(self, *args, **options):
        from core.models import (
            UnidadMedida, CategoriaProducto, Producto,
            Sistema, Subsistema, ReglaCalculo, DependenciaTecnica,
            ConfiguracionAPU, TipoProyecto,
        )

        if options["reset"]:
            self.stdout.write("⚠️  Reseteando datos maestros...")
            ReglaCalculo.objects.all().delete()
            DependenciaTecnica.objects.all().delete()
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
            CategoriaProducto.objects.get_or_create(codigo=c["codigo"], defaults={"nombre": c["nombre"]})

        # 3. Productos
        self.stdout.write("→ Productos")
        for p in PRODUCTOS:
            cat = CategoriaProducto.objects.get(codigo=p["categoria"])
            uni = UnidadMedida.objects.get(codigo=p["unidad"])
            Producto.objects.get_or_create(
                codigo=p["codigo"],
                defaults={"nombre": p["nombre"], "categoria": cat, "unidad": uni}
            )

        # 4. Sistema
        self.stdout.write("→ Sistema PowerGrip")
        sistema, _ = Sistema.objects.get_or_create(
            codigo=SISTEMA["codigo"],
            defaults=SISTEMA
        )

        # 5. Subsistemas + Reglas + Dependencias
        for sub_data in SUBSISTEMAS:
            self.stdout.write(f"  → Subsistema {sub_data['nombre']}")
            sub, _ = Subsistema.objects.get_or_create(
                codigo=sub_data["codigo"],
                defaults={**sub_data, "sistema": sistema}
            )

            # Reglas de cálculo
            for r in REGLAS.get(sub_data["codigo"], []):
                producto = Producto.objects.get(codigo=r.pop("producto"))
                ReglaCalculo.objects.get_or_create(
                    subsistema=sub,
                    codigo=r["codigo"],
                    version=1,
                    defaults={**r, "producto": producto, "subsistema": sub}
                )

            # Dependencias técnicas
            for d in DEPENDENCIAS.get(sub_data["codigo"], []):
                prod_dep = Producto.objects.get(codigo=d["producto_dependiente"])
                DependenciaTecnica.objects.get_or_create(
                    subsistema=sub,
                    producto_dependiente=prod_dep,
                    defaults={
                        "producto_origen": None,
                        "obligatoria": True,
                        "orden": d["orden"],
                        "tipo_regla": "FIJA",
                    }
                )

        # 6. Configuración APU
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
