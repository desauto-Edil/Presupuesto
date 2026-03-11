"""
management/commands/seed_full.py

Carga completa de datos de prueba y datos maestros para el sistema Imperandina.
Incluye: unidades, categorías, sistemas, subsistemas, productos, proveedores,
         precios, clientes, contactos, solicitudes, proyectos demo.

Uso:
    python manage.py seed_full
    python manage.py seed_full --reset   # borra y recrea todo
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal


# ---------------------------------------------------------------------------
# Datos maestros base (unidades, categorías, productos)
# ---------------------------------------------------------------------------

UNIDADES = [
    {"codigo": "UND",  "nombre": "Unidad",          "abreviatura": "und"},
    {"codigo": "GAL",  "nombre": "Galón",            "abreviatura": "gal"},
    {"codigo": "KG",   "nombre": "Kilogramo",        "abreviatura": "kg"},
    {"codigo": "CAR",  "nombre": "Cartucho",         "abreviatura": "crt"},
    {"codigo": "M2",   "nombre": "Metro cuadrado",   "abreviatura": "m²"},
    {"codigo": "ML",   "nombre": "Metro lineal",     "abreviatura": "ml"},
    {"codigo": "GLB",  "nombre": "Global",           "abreviatura": "glb"},
    {"codigo": "VJE",  "nombre": "Viaje",            "abreviatura": "vje"},
    {"codigo": "DIA",  "nombre": "Día",              "abreviatura": "día"},
    {"codigo": "MES",  "nombre": "Mes",              "abreviatura": "mes"},
]

CATEGORIAS = [
    {"codigo": "FIJACION",   "nombre": "Fijaciones",               "descripcion": "Tornillería y sujetadores"},
    {"codigo": "QUIMICO",    "nombre": "Químicos",                 "descripcion": "Limpiadores, selladores, adhesivos"},
    {"codigo": "ACCESORIO",  "nombre": "Accesorios sistema",       "descripcion": "Accesorios del sistema de cubierta"},
    {"codigo": "PROTECCION", "nombre": "Protección",               "descripcion": "EPP y elementos de protección"},
    {"codigo": "MANO_OBRA",  "nombre": "Mano de obra",             "descripcion": "Servicios de instalación"},
    {"codigo": "LAMINA",     "nombre": "Láminas y paneles",        "descripcion": "Cubiertas metálicas y membranas"},
    {"codigo": "ESTRUCTURA", "nombre": "Estructura metálica",      "descripcion": "Perfiles, correas y soportes"},
    {"codigo": "HERRAMIENTA","nombre": "Herramientas y equipos",   "descripcion": "Equipos de instalación"},
    {"codigo": "TRANSPORTE", "nombre": "Transporte y logística",   "descripcion": "Fletes y movilización de personal"},
]

PRODUCTOS = [
    # PowerGrip sistemas
    {"codigo": "PG-U7",         "nombre": "PowerGrip Universal 7",          "categoria": "ACCESORIO",  "unidad": "UND", "origen": "IMPORTADO", "linea": "PowerGrip"},
    {"codigo": "PG-PLUS",       "nombre": "PowerGrip Plus TPO",             "categoria": "ACCESORIO",  "unidad": "UND", "origen": "IMPORTADO", "linea": "PowerGrip"},
    # Fijaciones HDF
    {"codigo": "FIJ-HDF-114C",  "nombre": "Fijación HDF 1-1/4 Chino",      "categoria": "FIJACION",   "unidad": "UND", "origen": "IMPORTADO", "linea": "HDF"},
    {"codigo": "FIJ-HDF-114E",  "nombre": "Fijación HDF 1-1/4 Elevate",    "categoria": "FIJACION",   "unidad": "UND", "origen": "IMPORTADO", "linea": "HDF"},
    {"codigo": "FIJ-HDF-2C",    "nombre": "Fijación HDF 2 Chino",          "categoria": "FIJACION",   "unidad": "UND", "origen": "IMPORTADO", "linea": "HDF"},
    {"codigo": "FIJ-HDF-2E",    "nombre": "Fijación HDF 2 Elevate",        "categoria": "FIJACION",   "unidad": "UND", "origen": "IMPORTADO", "linea": "HDF"},
    {"codigo": "FIJ-HDF-3C",    "nombre": "Fijación HDF 3 Chino",          "categoria": "FIJACION",   "unidad": "UND", "origen": "IMPORTADO", "linea": "HDF"},
    {"codigo": "FIJ-HDF-3E",    "nombre": "Fijación HDF 3 Elevate",        "categoria": "FIJACION",   "unidad": "UND", "origen": "IMPORTADO", "linea": "HDF"},
    {"codigo": "FIJ-HDF-4C",    "nombre": "Fijación HDF 4 Chino",          "categoria": "FIJACION",   "unidad": "UND", "origen": "IMPORTADO", "linea": "HDF"},
    {"codigo": "FIJ-HDF-4E",    "nombre": "Fijación HDF 4 Elevate",        "categoria": "FIJACION",   "unidad": "UND", "origen": "IMPORTADO", "linea": "HDF"},
    {"codigo": "FIJ-HDF-5C",    "nombre": "Fijación HDF 5 Chino",          "categoria": "FIJACION",   "unidad": "UND", "origen": "IMPORTADO", "linea": "HDF"},
    {"codigo": "FIJ-HDF-5E",    "nombre": "Fijación HDF 5 Elevate",        "categoria": "FIJACION",   "unidad": "UND", "origen": "IMPORTADO", "linea": "HDF"},
    {"codigo": "FIJ-CDF-C",     "nombre": "Concrete Drive Fastener Chino", "categoria": "FIJACION",   "unidad": "UND", "origen": "IMPORTADO", "linea": "HDF"},
    {"codigo": "FIJ-CDF-E",     "nombre": "Concrete Drive Fastener Elevate","categoria":"FIJACION",   "unidad": "UND", "origen": "IMPORTADO", "linea": "HDF"},
    # Químicos
    {"codigo": "LMP-SPLICE",    "nombre": "Limpiador Splice Wash",          "categoria": "QUIMICO",    "unidad": "GAL", "origen": "IMPORTADO", "linea": "Químicos"},
    {"codigo": "LMP-VARSOL",    "nombre": "Limpiador Varsol Industrial",    "categoria": "QUIMICO",    "unidad": "GAL", "origen": "NACIONAL",  "linea": "Químicos"},
    {"codigo": "ESTOPA",        "nombre": "Estopa industrial",              "categoria": "QUIMICO",    "unidad": "KG",  "origen": "NACIONAL",  "linea": "Químicos"},
    {"codigo": "SELL-CUT",      "nombre": "Sellador Cut Edge Sealant",      "categoria": "QUIMICO",    "unidad": "CAR", "origen": "IMPORTADO", "linea": "Químicos"},
    {"codigo": "SELL-WB",       "nombre": "Sellador WaterBlock",           "categoria": "QUIMICO",    "unidad": "CAR", "origen": "IMPORTADO", "linea": "Químicos"},
    # Láminas y membranas
    {"codigo": "MEM-TPO-045",   "nombre": "Membrana TPO 45 mil",           "categoria": "LAMINA",     "unidad": "M2",  "origen": "IMPORTADO", "linea": "Membranas"},
    {"codigo": "MEM-TPO-060",   "nombre": "Membrana TPO 60 mil",           "categoria": "LAMINA",     "unidad": "M2",  "origen": "IMPORTADO", "linea": "Membranas"},
    {"codigo": "LAM-ALUZINC",   "nombre": "Lámina Aluzinc Ondulada",       "categoria": "LAMINA",     "unidad": "M2",  "origen": "NACIONAL",  "linea": "Cubiertas Metálicas"},
    {"codigo": "LAM-TEJA-IMP",  "nombre": "Teja Imperial Asbesto Cero",    "categoria": "LAMINA",     "unidad": "M2",  "origen": "NACIONAL",  "linea": "Cubiertas Metálicas"},
    # EPP y protección
    {"codigo": "EPP-ARNES",     "nombre": "Arnés de seguridad certificado","categoria": "PROTECCION", "unidad": "UND", "origen": "NACIONAL",  "linea": "EPP"},
    {"codigo": "EPP-ESCOTIN",   "nombre": "Escotin de seguridad",          "categoria": "PROTECCION", "unidad": "UND", "origen": "NACIONAL",  "linea": "EPP"},
    {"codigo": "EPP-CASCO",     "nombre": "Casco de seguridad dieléctrico","categoria": "PROTECCION", "unidad": "UND", "origen": "NACIONAL",  "linea": "EPP"},
    # Estructura
    {"codigo": "CORREA-Z200",   "nombre": "Correa Z 200×50×15mm",          "categoria": "ESTRUCTURA", "unidad": "ML",  "origen": "NACIONAL",  "linea": "Estructura"},
    {"codigo": "CORREA-C150",   "nombre": "Correa C 150×50×15mm",          "categoria": "ESTRUCTURA", "unidad": "ML",  "origen": "NACIONAL",  "linea": "Estructura"},
]

# ---------------------------------------------------------------------------
# Sistemas y subsistemas
# ---------------------------------------------------------------------------

SISTEMAS = [
    {
        "codigo": "POWERGRIP",
        "nombre": "PowerGrip",
        "linea_negocio": "CUBIERTAS",
        "descripcion": "Sistema de fijación mecánica para cubiertas TPO/PVC",
    },
    {
        "codigo": "CUBIERTA-MET",
        "nombre": "Cubiertas Metálicas",
        "linea_negocio": "CUBIERTAS",
        "descripcion": "Cubiertas en lámina de acero galvanizado y aluzinc",
    },
    {
        "codigo": "FACHADA-IND",
        "nombre": "Fachadas Industriales",
        "linea_negocio": "FACHADAS",
        "descripcion": "Sistema de revestimiento exterior para naves industriales",
    },
]

SUBSISTEMAS = {
    "POWERGRIP": [
        {"codigo": "PG-U7",   "nombre": "Universal 7",  "descripcion": "Variante Universal 7 — 8 fijaciones base"},
        {"codigo": "PG-PLUS", "nombre": "Plus TPO",     "descripcion": "Variante Plus TPO — 9 fijaciones base"},
    ],
    "CUBIERTA-MET": [
        {"codigo": "CM-ALUZINC",  "nombre": "Aluzinc Ondulada", "descripcion": "Cubierta en lámina aluzinc ondulada"},
        {"codigo": "CM-TEJA",     "nombre": "Teja Imperial",    "descripcion": "Cubierta en teja asbesto cero"},
    ],
    "FACHADA-IND": [
        {"codigo": "FA-PANEL",  "nombre": "Panel Composite",  "descripcion": "Fachada en panel composite aluminio"},
        {"codigo": "FA-LAMINA", "nombre": "Lámina Expuesta",   "descripcion": "Fachada en lámina metálica expuesta"},
    ],
}

# ---------------------------------------------------------------------------
# Proveedores
# ---------------------------------------------------------------------------

PROVEEDORES = [
    {
        "nit": "800123456-1",
        "nombre": "Elevate Roofing Products Colombia",
        "ciudad": "Bogotá",
        "direccion": "Cra 30 # 25-90, Zona Industrial",
        "telefono": "601-2345678",
        "email": "ventas@elevate-co.com",
    },
    {
        "nit": "900234567-2",
        "nombre": "Suministros Industriales del Norte SAS",
        "ciudad": "Medellín",
        "direccion": "Calle 50 # 50-55, Guayabal",
        "telefono": "604-3456789",
        "email": "compras@suminorte.com",
    },
    {
        "nit": "901345678-3",
        "nombre": "Ferretería Técnica Andina Ltda",
        "ciudad": "Cali",
        "direccion": "Av. 3N # 24-50, Centro",
        "telefono": "602-4567890",
        "email": "pedidos@ferretecnica.co",
    },
    {
        "nit": "800456789-4",
        "nombre": "Importadora PowerGrip SAS",
        "ciudad": "Bogotá",
        "direccion": "Zona Franca Bogotá Bod. 12",
        "telefono": "601-5678901",
        "email": "powergrip@importadora.com",
    },
    {
        "nit": "900567890-5",
        "nombre": "Metales y Perfiles del Pacífico SAS",
        "ciudad": "Buenaventura",
        "direccion": "Parque Industrial Zona Franca",
        "telefono": "602-6789012",
        "email": "ventas@metalpack.co",
    },
]

# ---------------------------------------------------------------------------
# Precios proveedor (productos_proveedor)
# ---------------------------------------------------------------------------

PRECIOS = [
    # Proveedor: Importadora PowerGrip
    {"producto": "PG-U7",        "proveedor": "800456789-4", "precio": Decimal("28500.00"),  "moneda": "COP"},
    {"producto": "PG-PLUS",      "proveedor": "800456789-4", "precio": Decimal("32000.00"),  "moneda": "COP"},
    {"producto": "FIJ-HDF-114C", "proveedor": "800456789-4", "precio": Decimal("850.00"),    "moneda": "COP"},
    {"producto": "FIJ-HDF-114E", "proveedor": "800456789-4", "precio": Decimal("1250.00"),   "moneda": "COP"},
    {"producto": "FIJ-HDF-2C",   "proveedor": "800456789-4", "precio": Decimal("920.00"),    "moneda": "COP"},
    {"producto": "FIJ-HDF-2E",   "proveedor": "800456789-4", "precio": Decimal("1380.00"),   "moneda": "COP"},
    {"producto": "FIJ-HDF-3C",   "proveedor": "800456789-4", "precio": Decimal("1050.00"),   "moneda": "COP"},
    {"producto": "FIJ-HDF-3E",   "proveedor": "800456789-4", "precio": Decimal("1550.00"),   "moneda": "COP"},
    {"producto": "FIJ-HDF-4C",   "proveedor": "800456789-4", "precio": Decimal("1180.00"),   "moneda": "COP"},
    {"producto": "FIJ-HDF-4E",   "proveedor": "800456789-4", "precio": Decimal("1720.00"),   "moneda": "COP"},
    {"producto": "FIJ-HDF-5C",   "proveedor": "800456789-4", "precio": Decimal("1320.00"),   "moneda": "COP"},
    {"producto": "FIJ-HDF-5E",   "proveedor": "800456789-4", "precio": Decimal("1900.00"),   "moneda": "COP"},
    {"producto": "FIJ-CDF-C",    "proveedor": "800456789-4", "precio": Decimal("1600.00"),   "moneda": "COP"},
    {"producto": "FIJ-CDF-E",    "proveedor": "800456789-4", "precio": Decimal("2100.00"),   "moneda": "COP"},
    # Químicos — Elevate
    {"producto": "LMP-SPLICE",   "proveedor": "800123456-1", "precio": Decimal("185000.00"), "moneda": "COP"},
    {"producto": "SELL-CUT",     "proveedor": "800123456-1", "precio": Decimal("48500.00"),  "moneda": "COP"},
    {"producto": "SELL-WB",      "proveedor": "800123456-1", "precio": Decimal("52000.00"),  "moneda": "COP"},
    # Químicos — Suministros Norte
    {"producto": "LMP-VARSOL",   "proveedor": "900234567-2", "precio": Decimal("32000.00"),  "moneda": "COP"},
    {"producto": "ESTOPA",       "proveedor": "900234567-2", "precio": Decimal("8500.00"),   "moneda": "COP"},
    # Láminas — Metales y Perfiles
    {"producto": "MEM-TPO-045",  "proveedor": "800123456-1", "precio": Decimal("68000.00"),  "moneda": "COP"},
    {"producto": "MEM-TPO-060",  "proveedor": "800123456-1", "precio": Decimal("89000.00"),  "moneda": "COP"},
    {"producto": "LAM-ALUZINC",  "proveedor": "900567890-5", "precio": Decimal("42000.00"),  "moneda": "COP"},
    {"producto": "LAM-TEJA-IMP", "proveedor": "900567890-5", "precio": Decimal("38500.00"),  "moneda": "COP"},
    # Estructura — Ferretería Técnica
    {"producto": "CORREA-Z200",  "proveedor": "901345678-3", "precio": Decimal("28000.00"),  "moneda": "COP"},
    {"producto": "CORREA-C150",  "proveedor": "901345678-3", "precio": Decimal("22500.00"),  "moneda": "COP"},
    # EPP
    {"producto": "EPP-ARNES",    "proveedor": "900234567-2", "precio": Decimal("185000.00"), "moneda": "COP"},
    {"producto": "EPP-ESCOTIN",  "proveedor": "900234567-2", "precio": Decimal("95000.00"),  "moneda": "COP"},
    {"producto": "EPP-CASCO",    "proveedor": "900234567-2", "precio": Decimal("65000.00"),  "moneda": "COP"},
]

# ---------------------------------------------------------------------------
# Tipos de proyecto
# ---------------------------------------------------------------------------

TIPOS_PROYECTO = [
    {"codigo": "BODEGA",    "nombre": "Bodega"},
    {"codigo": "PTAR",      "nombre": "Planta de Tratamiento"},
    {"codigo": "INDUSTRIA", "nombre": "Industrial"},
    {"codigo": "COMERCIO",  "nombre": "Comercial"},
    {"codigo": "CUBIERTA",  "nombre": "Cubierta general"},
    {"codigo": "OFICINAS",  "nombre": "Oficinas y administración"},
    {"codigo": "FACHADA",   "nombre": "Fachada"},
]

# ---------------------------------------------------------------------------
# Clientes y contactos demo
# ---------------------------------------------------------------------------

CLIENTES = [
    {
        "nit": "830012345-1",
        "razon_social": "Alimentos del Campo SAS",
        "ciudad": "Bogotá",
        "direccion": "Calle 13 # 68-50, Zona Industrial Puente Aranda",
        "telefono_principal": "601-4001234",
        "email_principal": "gerencia@alimentosdecampo.com",
        "contactos": [
            {"nombre": "Rodrigo Acevedo Mejía", "cargo": "Gerente de Planta",     "email": "r.acevedo@alimentosdecampo.com", "telefono": "310-1234567", "es_principal": True},
            {"nombre": "Sandra Ruiz Cárdenas",   "cargo": "Coordinadora Técnica",  "email": "s.ruiz@alimentosdecampo.com",   "telefono": "311-2345678", "es_principal": False},
        ],
    },
    {
        "nit": "900098765-2",
        "razon_social": "Logística Integral de Colombia SA",
        "ciudad": "Medellín",
        "direccion": "Carrera 50 # 12-85, Itagüí",
        "telefono_principal": "604-3456789",
        "email_principal": "compras@logisticaintegral.co",
        "contactos": [
            {"nombre": "Fernando Osorio Londoño", "cargo": "Director de Proyectos", "email": "f.osorio@logisticaintegral.co", "telefono": "312-3456789", "es_principal": True},
        ],
    },
    {
        "nit": "890765432-3",
        "razon_social": "Textiles y Confecciones del Valle SA",
        "ciudad": "Cali",
        "direccion": "Av. Simón Bolívar # 30-100, Arroyohondo",
        "telefono_principal": "602-5678901",
        "email_principal": "infraestructura@textilsvalle.com",
        "contactos": [
            {"nombre": "Claudia Montoya García",  "cargo": "Jefe de Mantenimiento", "email": "c.montoya@textilsvalle.com",   "telefono": "315-4567890", "es_principal": True},
            {"nombre": "Hernando Perea Salcedo",  "cargo": "Asesor Técnico",        "email": "h.perea@textilsvalle.com",     "telefono": "316-5678901", "es_principal": False},
        ],
    },
    {
        "nit": "800543210-4",
        "razon_social": "Inversiones Inmobiliarias Progreso SAS",
        "ciudad": "Barranquilla",
        "direccion": "Carrera 46 # 74-150, Ciudad Industrial",
        "telefono_principal": "605-6789012",
        "email_principal": "proyectos@invprogreso.com",
        "contactos": [
            {"nombre": "Jorge Barros Molinares", "cargo": "Gerente Técnico",  "email": "j.barros@invprogreso.com", "telefono": "317-6789012", "es_principal": True},
        ],
    },
]

# ---------------------------------------------------------------------------
# Configuración APU
# ---------------------------------------------------------------------------

CONFIG_APU = {
    "nombre": "Configuración global",
    "porcentaje_ganancia": 20,
    "aiu_contratista": 30,
    "desperdicio": 3,
    "margen_ganancia_contratista": 30,
}

# ---------------------------------------------------------------------------
# Solicitudes y proyectos demo
# ---------------------------------------------------------------------------

SOLICITUDES_DEMO = [
    {
        "cliente_nit": "830012345-1",
        "nombre": "Ampliación cubierta bodega norte",
        "descripcion": "Reemplazo de cubierta en bodega norte 2.000 m². Sistema TPO PowerGrip Universal 7.",
        "estado": "EN_GESTION",
    },
    {
        "cliente_nit": "900098765-2",
        "nombre": "Cubierta centro de distribución Itagüí",
        "descripcion": "Cubierta nueva para bodega 3.500 m². Sistema PowerGrip Plus TPO.",
        "estado": "APROBADA",
    },
    {
        "cliente_nit": "890765432-3",
        "nombre": "Mantenimiento y reparación cubierta planta principal",
        "descripcion": "Reparación de filtraciones en 800 m² de cubierta metálica.",
        "estado": "BORRADOR",
    },
]


class Command(BaseCommand):
    help = "Carga datos completos de prueba (maestros + clientes + solicitudes + proyectos demo)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Borra y recrea todos los datos")

    @transaction.atomic
    def handle(self, *args, **options):
        from core.models import (
            UnidadMedida, CategoriaProducto, Producto,
            Sistema, Subsistema, Proveedor, ProductoProveedor,
            Cliente, ContactoCliente, Solicitud, TipoProyecto,
            ConfiguracionAPU,
        )

        if options["reset"]:
            self.stdout.write(self.style.WARNING("Reseteando datos..."))
            Solicitud.objects.all().delete()
            ContactoCliente.objects.all().delete()
            Cliente.objects.all().delete()
            ProductoProveedor.objects.all().delete()
            Proveedor.objects.all().delete()
            Producto.objects.all().delete()
            Subsistema.objects.all().delete()
            Sistema.objects.all().delete()
            CategoriaProducto.objects.all().delete()
            UnidadMedida.objects.all().delete()
            TipoProyecto.objects.all().delete()
            ConfiguracionAPU.objects.all().delete()
            self.stdout.write(self.style.WARNING("  Reset completo."))

        # ── 1. Unidades de medida ─────────────────────────────────────────
        self.stdout.write("→ Cargando unidades de medida...")
        for u in UNIDADES:
            obj, created = UnidadMedida.objects.get_or_create(
                codigo=u["codigo"],
                defaults={"nombre": u["nombre"], "abreviatura": u["abreviatura"]},
            )
            if created:
                self.stdout.write(f"  + {obj.codigo}")

        # ── 2. Categorías ─────────────────────────────────────────────────
        self.stdout.write("→ Cargando categorías de producto...")
        for c in CATEGORIAS:
            obj, created = CategoriaProducto.objects.get_or_create(
                codigo=c["codigo"],
                defaults={"nombre": c["nombre"], "descripcion": c.get("descripcion", "")},
            )
            if created:
                self.stdout.write(f"  + {obj.codigo}")

        # ── 3. Productos ──────────────────────────────────────────────────
        self.stdout.write("→ Cargando productos...")
        for p in PRODUCTOS:
            cat = CategoriaProducto.objects.get(codigo=p["categoria"])
            uni = UnidadMedida.objects.get(codigo=p["unidad"])
            obj, created = Producto.objects.get_or_create(
                codigo=p["codigo"],
                defaults={
                    "nombre":  p["nombre"],
                    "categoria": cat,
                    "unidad":  uni,
                    "origen":  p.get("origen", "NACIONAL"),
                    "linea":   p.get("linea", ""),
                },
            )
            if created:
                self.stdout.write(f"  + {obj.codigo}")

        # ── 4. Sistemas y subsistemas ─────────────────────────────────────
        self.stdout.write("→ Cargando sistemas...")
        for s in SISTEMAS:
            sistema, created = Sistema.objects.get_or_create(
                codigo=s["codigo"],
                defaults=s,
            )
            if created:
                self.stdout.write(f"  + Sistema: {sistema.nombre}")

            for sub_data in SUBSISTEMAS.get(s["codigo"], []):
                sub, s_created = Subsistema.objects.get_or_create(
                    codigo=sub_data["codigo"],
                    defaults={**sub_data, "sistema": sistema},
                )
                if s_created:
                    self.stdout.write(f"    + Subsistema: {sub.nombre}")

        # ── 5. Proveedores ────────────────────────────────────────────────
        self.stdout.write("→ Cargando proveedores...")
        for pv in PROVEEDORES:
            obj, created = Proveedor.objects.get_or_create(
                nit=pv["nit"],
                defaults=pv,
            )
            if created:
                self.stdout.write(f"  + {obj.nombre}")

        # ── 6. Precios proveedor ──────────────────────────────────────────
        self.stdout.write("→ Cargando precios proveedor...")
        for pr in PRECIOS:
            try:
                producto  = Producto.objects.get(codigo=pr["producto"])
                proveedor = Proveedor.objects.get(nit=pr["proveedor"])
                obj, created = ProductoProveedor.objects.get_or_create(
                    producto=producto,
                    proveedor=proveedor,
                    defaults={"precio_unitario": pr["precio"], "moneda": pr["moneda"]},
                )
                if not created:
                    obj.precio_unitario = pr["precio"]
                    obj.save(update_fields=["precio_unitario"])
            except (Producto.DoesNotExist, Proveedor.DoesNotExist) as e:
                self.stdout.write(self.style.WARNING(f"  ! Precio omitido: {e}"))

        # ── 7. Tipos de proyecto ──────────────────────────────────────────
        self.stdout.write("→ Cargando tipos de proyecto...")
        for tp in TIPOS_PROYECTO:
            TipoProyecto.objects.get_or_create(
                codigo=tp["codigo"],
                defaults=tp,
            )

        # ── 8. Configuración APU ──────────────────────────────────────────
        self.stdout.write("→ Configuración APU...")
        ConfiguracionAPU.objects.get_or_create(
            nombre=CONFIG_APU["nombre"],
            defaults={
                "porcentaje_ganancia":         CONFIG_APU["porcentaje_ganancia"],
                "aiu_contratista":             CONFIG_APU["aiu_contratista"],
                "desperdicio":                 CONFIG_APU["desperdicio"],
                "margen_ganancia_contratista": CONFIG_APU["margen_ganancia_contratista"],
            },
        )

        # ── 9. Clientes y contactos demo ─────────────────────────────────
        self.stdout.write("→ Cargando clientes demo...")
        for cl in CLIENTES:
            contactos_data = cl.pop("contactos", [])
            cliente, created = Cliente.objects.get_or_create(
                nit=cl["nit"],
                defaults=cl,
            )
            if created:
                self.stdout.write(f"  + Cliente: {cliente.razon_social}")

            for co in contactos_data:
                ContactoCliente.objects.get_or_create(
                    cliente=cliente,
                    email=co["email"],
                    defaults=co,
                )
            cl["contactos"] = contactos_data  # Restaurar por si se reutiliza

        # ── 10. Solicitudes demo ──────────────────────────────────────────
        self.stdout.write("→ Cargando solicitudes demo...")
        for sol_data in SOLICITUDES_DEMO:
            try:
                cliente = Cliente.objects.get(nit=sol_data["cliente_nit"])
                contacto = cliente.contactos.filter(es_principal=True).first()
                # Solo crear si no existe una con el mismo nombre para el mismo cliente
                sol, created = Solicitud.objects.get_or_create(
                    cliente=cliente,
                    nombre=sol_data["nombre"],
                    defaults={
                        "consecutivo":  Solicitud.siguiente_consecutivo(),
                        "descripcion":  sol_data["descripcion"],
                        "estado":       sol_data["estado"],
                        "contacto":     contacto,
                    },
                )
                if created:
                    self.stdout.write(f"  + Solicitud: {sol.consecutivo} — {sol.nombre[:50]}")
            except Cliente.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"  ! Cliente no encontrado: {sol_data['cliente_nit']}"))

        self.stdout.write(self.style.SUCCESS(
            "\n✅  Seed completo cargado correctamente.\n"
            "   Recuerda ejecutar también: python manage.py seed_powergrip\n"
            "   para cargar las reglas de cálculo PowerGrip.\n"
        ))
