"""
management command: cargar_datos_powergrip

Carga todos los datos necesarios para probar el flujo completo PowerGrip:
  - Unidades de medida
  - Categorías de productos (PowerGrip, Fijaciones, Accesorios, Estopa, Sellador)
  - Proveedor demo
  - Productos (2 por categoría con precios)
  - Sistema POWERGRIP + subsistemas PG_UNIVERSAL_7 y PG_PLUS_TPO
  - TipoProyecto
  - Cliente demo
  - 2 Proyectos de prueba (uno por subsistema)

Uso:
    python manage.py cargar_datos_powergrip
    python manage.py cargar_datos_powergrip --reset  # elimina y recrea todo
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal


class Command(BaseCommand):
    help = "Carga datos de prueba para el flujo PowerGrip (ambos subsistemas)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Elimina proyectos y despieces de prueba antes de cargar.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        from apps.catalogos.models import (
            UnidadMedida, CategoriaProducto, Producto, Proveedor, ProductoProveedor,
        )
        from apps.ingenieria.models import Sistema, Subsistema
        from apps.comercial.models import Cliente, TipoProyecto, Proyecto

        if options["reset"]:
            self.stdout.write("⚠  Eliminando proyectos de prueba existentes...")
            Proyecto.objects.filter(nombre__startswith="[TEST]").delete()
            self.stdout.write(self.style.WARNING("  Proyectos de prueba eliminados."))

        # ── 1. Unidades de medida ─────────────────────────────────────────────
        self.stdout.write("\n[1/7] Unidades de medida...")
        unidades = {
            "UND": ("und", "Unidad"),
            "GAL": ("gal", "Galón"),
            "KG":  ("kg",  "Kilogramo"),
            "CAR": ("car", "Cartucho"),
            "LT":  ("lt",  "Litro"),
            "M2":  ("m2",  "Metro cuadrado"),
        }
        umd = {}
        for cod, (abrev, nombre) in unidades.items():
            obj, created = UnidadMedida.objects.get_or_create(
                codigo=cod,
                defaults={"nombre": nombre, "abreviatura": abrev},
            )
            umd[cod] = obj
            self.stdout.write(f"  {'✓ Creada' if created else '· Existe'}: {cod}")

        # ── 2. Categorías de producto ─────────────────────────────────────────
        self.stdout.write("\n[2/7] Categorías de producto...")
        categorias_def = [
            ("CAT-PG",   "PowerGrip",  "Fijadores PowerGrip (base del sistema)"),
            ("CAT-FIJ",  "Fijaciones", "Tornillería y fijaciones Heavy Duty"),
            ("CAT-ACC",  "Accesorios", "Limpiadores y accesorios de instalación"),
            ("CAT-EST",  "Estopa",     "Estopa para limpieza de superficies"),
            ("CAT-SEL",  "Sellador",   "Selladores de bordes y uniones"),
        ]
        cats = {}
        for cod, nombre, desc in categorias_def:
            obj, created = CategoriaProducto.objects.get_or_create(
                nombre=nombre,
                defaults={"codigo": cod, "descripcion": desc, "activa": True},
            )
            cats[nombre] = obj
            self.stdout.write(f"  {'✓ Creada' if created else '· Existe'}: {nombre}")

        # ── 3. Proveedor demo ─────────────────────────────────────────────────
        self.stdout.write("\n[3/7] Proveedor...")
        proveedor, created = Proveedor.objects.get_or_create(
            nit="900123456-1",
            defaults={
                "nombre":    "Firestone Building Products Colombia",
                "ciudad":    "Bogotá",
                "direccion": "Cra 50 # 20-30",
                "telefono":  "6017654321",
                "email":     "ventas@firestone.co",
                "activo":    True,
            },
        )
        self.stdout.write(f"  {'✓ Creado' if created else '· Existe'}: {proveedor.nombre}")

        # ── 4. Productos (2 por categoría) ────────────────────────────────────
        self.stdout.write("\n[4/7] Productos...")

        productos_def = [
            # (categoria, codigo, nombre, unidad_cod, precio)
            # PowerGrip
            ("PowerGrip", "PG-U7-001", "PowerGrip Universal 7 — 2\"",        "UND", Decimal("8500")),
            ("PowerGrip", "PG-U7-002", "PowerGrip Universal 7 — 2.5\"",      "UND", Decimal("9200")),
            ("PowerGrip", "PG-TPO-001","PowerGrip Plus TPO — 2\"",            "UND", Decimal("9800")),
            ("PowerGrip", "PG-TPO-002","PowerGrip Plus TPO — 2.5\" reforzado","UND", Decimal("10500")),
            # Fijaciones
            ("Fijaciones","FIJ-HD3-001","Fijación Heavy Duty Fastener 3\" estándar","UND", Decimal("420")),
            ("Fijaciones","FIJ-HD3-002","Fijación Heavy Duty Fastener 3\" acero inox","UND", Decimal("680")),
            # Accesorios (Limpiador)
            ("Accesorios","ACC-SW-001", "Splice Wash SW-100 — 5 gal",         "GAL", Decimal("185000")),
            ("Accesorios","ACC-SW-002", "Splice Wash SW-200 — 5 gal reforzado","GAL", Decimal("215000")),
            # Estopa
            ("Estopa",    "EST-001",    "Estopa blanca industrial",            "KG",  Decimal("4800")),
            ("Estopa",    "EST-002",    "Estopa amarilla absorbente",          "KG",  Decimal("5200")),
            # Sellador
            ("Sellador",  "SEL-WB-001", "Sellador Water Block 10 oz",         "CAR", Decimal("28000")),
            ("Sellador",  "SEL-WB-002", "Sellador Water Block Pro 10 oz",     "CAR", Decimal("34000")),
            ("Sellador",  "SEL-TPO-001","Sellador TPO Clear Cut Edge 1 lt",   "LT",  Decimal("52000")),
            ("Sellador",  "SEL-TPO-002","Sellador TPO Premium Edge 1 lt",     "LT",  Decimal("61000")),
        ]

        productos = {}
        for cat_nombre, codigo, nombre, unidad_cod, precio in productos_def:
            prod, created = Producto.objects.get_or_create(
                codigo=codigo,
                defaults={
                    "nombre":    nombre,
                    "categoria": cats[cat_nombre],
                    "unidad":    umd[unidad_cod],
                    "activo":    True,
                },
            )
            productos[codigo] = prod

            # Precio con proveedor
            pp, pp_created = ProductoProveedor.objects.get_or_create(
                producto=prod,
                proveedor=proveedor,
                defaults={"precio_unitario": precio, "moneda": "COP", "activo": True},
            )
            if not pp_created and pp.precio_unitario != precio:
                pp.precio_unitario = precio
                pp.save(update_fields=["precio_unitario"])

            self.stdout.write(
                f"  {'✓' if created else '·'} {codigo} — ${precio:,.0f} COP"
            )

        # ── 5. Sistema + Subsistemas ──────────────────────────────────────────
        self.stdout.write("\n[5/7] Sistema POWERGRIP y subsistemas...")
        sistema, created = Sistema.objects.get_or_create(
            codigo="POWERGRIP",
            defaults={
                "nombre":        "PowerGrip",
                "linea_negocio": "CUBIERTAS",
                "descripcion":   "Sistema de fijación mecánica PowerGrip para cubiertas TPO/EPDM.",
                "activo":        True,
            },
        )
        self.stdout.write(f"  {'✓ Creado' if created else '· Existe'}: {sistema.nombre}")

        subsistemas_def = [
            ("PG_UNIVERSAL_7", "PowerGrip Universal 7",
             "Subsistema de fijación Universal 7. 8 fijaciones por unidad estándar."),
            ("PG_PLUS_TPO",    "PowerGrip Plus TPO",
             "Subsistema de fijación Plus TPO. 9 fijaciones por unidad."),
        ]
        for cod, nombre, desc in subsistemas_def:
            sub, created = Subsistema.objects.get_or_create(
                sistema=sistema,
                codigo=cod,
                defaults={"nombre": nombre, "descripcion": desc, "activo": True},
            )
            self.stdout.write(f"  {'✓ Creado' if created else '· Existe'}: {sub.nombre}")

        # ── 6. TipoProyecto + Cliente demo ────────────────────────────────────
        self.stdout.write("\n[6/7] TipoProyecto y Cliente...")
        tipo_pry, _ = TipoProyecto.objects.get_or_create(
            nombre="Cubierta TPO",
            defaults={"codigo": "TPO"},
        )

        cliente, created = Cliente.objects.get_or_create(
            nit="800456789-2",
            defaults={
                "razon_social":      "Distribuidora ARA Colombia S.A.S.",
                "ciudad":            "Bogotá",
                "direccion":         "Calle 100 # 19-61",
                "telefono_principal":"6017891234",
                "email_principal":   "proyectos@ara.com.co",
                "activo":            True,
            },
        )
        self.stdout.write(f"  {'✓' if created else '·'} Cliente: {cliente.razon_social}")

        # ── 7. Proyectos de prueba ────────────────────────────────────────────
        self.stdout.write("\n[7/7] Proyectos de prueba...")

        def crear_proyecto(nombre, area, consecutivo_hint):
            consec = Proyecto.siguiente_consecutivo()
            pry, created = Proyecto.objects.get_or_create(
                nombre=nombre,
                defaults={
                    "consecutivo":       consec,
                    "cliente":           cliente,
                    "tipo_proyecto":     tipo_pry,
                    "area_total_m2":     Decimal(str(area)),
                    "perimetro_ml":      Decimal("0"),
                    "trm":               Decimal("4200"),
                    "margen_comercial_pct": Decimal("20"),
                    "iva_pct":           Decimal("19"),
                    "aiu_pct":           Decimal("0"),
                    "moneda":            "COP",
                    "aplica_exencion_iva": False,
                    "estado":            "SOLICITUD",
                },
            )
            return pry, created

        pry_u7, c1 = crear_proyecto("[TEST] CEDI ARA — Cota (Universal 7)", 2883, "COTA-001")
        self.stdout.write(
            f"  {'✓ Creado' if c1 else '· Existe'}: {pry_u7.consecutivo} — {pry_u7.nombre}"
        )

        pry_tpo, c2 = crear_proyecto("[TEST] CEDI ARA — Gachancipá (Plus TPO)", 1950, "GACH-001")
        self.stdout.write(
            f"  {'✓ Creado' if c2 else '· Existe'}: {pry_tpo.consecutivo} — {pry_tpo.nombre}"
        )

        # ── Resumen ───────────────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS("\n✅ Datos PowerGrip cargados correctamente.\n"))
        self.stdout.write("URLs para probar el wizard:")
        self.stdout.write(self.style.HTTP_INFO(
            f"  Universal 7 → http://localhost:8080/presupuestos/powergrip/{pry_u7.pk}/"
        ))
        self.stdout.write(self.style.HTTP_INFO(
            f"  Plus TPO    → http://localhost:8080/presupuestos/powergrip/{pry_tpo.pk}/"
        ))
        self.stdout.write("\nProductos disponibles por categoría:")
        from apps.catalogos.models import CategoriaProducto
        for slug in ["PowerGrip", "Fijaciones", "Accesorios", "Estopa", "Sellador"]:
            count = Producto.objects.filter(categoria__nombre=slug, activo=True).count()
            self.stdout.write(f"  {slug}: {count} producto(s)")
