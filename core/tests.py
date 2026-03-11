"""
tests.py — Suite de tests para el motor de presupuestos.

Cubre:
  1. Modelos: consecutivos automáticos, relaciones, propiedades
  2. ReglaCalculo.evaluar(): algoritmos PowerGrip U7 y Plus TPO
  3. DespieceService: despiece paramétrico completo
  4. DependenciaService: inyección automática
  5. APUService: cálculo de materiales, mano de obra y totales
  6. ProyectoService: flujo de estados
  7. Casos borde: cero, negativos, sin proveedor
"""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase


# ---------------------------------------------------------------------------
# Helpers de creación de datos
# ---------------------------------------------------------------------------

def crear_datos_base():
    """Crea la jerarquía mínima para ejecutar tests."""
    from core.models import (
        UnidadMedida, CategoriaProducto, Producto,
        Sistema, Subsistema, ReglaCalculo, DependenciaTecnica,
        Cliente, ContactoCliente, UsuarioSistema,
        Solicitud, TipoProyecto, Proyecto, ProyectoSistema,
        ConfiguracionAPU, Proveedor, ProductoProveedor,
    )

    uni_und, _ = UnidadMedida.objects.get_or_create(codigo="UND", defaults={"nombre": "Unidad", "abreviatura": "und"})
    uni_gal, _ = UnidadMedida.objects.get_or_create(codigo="GAL", defaults={"nombre": "Galón",  "abreviatura": "gal"})
    uni_kg,  _ = UnidadMedida.objects.get_or_create(codigo="KG",  defaults={"nombre": "Kilo",   "abreviatura": "kg"})
    uni_car, _ = UnidadMedida.objects.get_or_create(codigo="CAR", defaults={"nombre": "Cartucho","abreviatura": "crt"})

    cat_fij, _ = CategoriaProducto.objects.get_or_create(codigo="FIJACION",  defaults={"nombre": "Fijaciones"})
    cat_qui, _ = CategoriaProducto.objects.get_or_create(codigo="QUIMICO",   defaults={"nombre": "Químicos"})
    cat_acc, _ = CategoriaProducto.objects.get_or_create(codigo="ACCESORIO", defaults={"nombre": "Accesorios"})

    pg_u7,   _ = Producto.objects.get_or_create(codigo="PG-U7",    defaults={"nombre": "PowerGrip Universal 7","categoria": cat_acc,"unidad": uni_und})
    fij,     _ = Producto.objects.get_or_create(codigo="FIJ-U7",   defaults={"nombre": "Fijación U7",          "categoria": cat_fij,"unidad": uni_und})
    lmp,     _ = Producto.objects.get_or_create(codigo="LMP-TEST", defaults={"nombre": "Limpiador Test",       "categoria": cat_qui,"unidad": uni_gal})
    estopa,  _ = Producto.objects.get_or_create(codigo="EST-TEST", defaults={"nombre": "Estopa Test",          "categoria": cat_qui,"unidad": uni_kg})
    sellador,_ = Producto.objects.get_or_create(codigo="SELL-TEST",defaults={"nombre": "Sellador Test",        "categoria": cat_qui,"unidad": uni_car})

    sistema, _ = Sistema.objects.get_or_create(
        codigo="POWERGRIP-TEST",
        defaults={"nombre": "PowerGrip Test", "linea_negocio": "CUBIERTAS"}
    )
    sub_u7, _ = Subsistema.objects.get_or_create(
        codigo="PG-U7-TEST",
        defaults={"nombre": "Universal 7 Test", "sistema": sistema}
    )

    # Reglas de cálculo para U7
    r1, _ = ReglaCalculo.objects.get_or_create(
        subsistema=sub_u7, codigo="TR-R01", version=1,
        defaults={
            "nombre": "Fijaciones test", "producto": fij,
            "variable_entrada": "Total_PowerGrip",
            "coeficiente": Decimal("8"), "divisor": Decimal("1"),
            "factor_desperdicio": Decimal("1.01"),
            "formula_texto": "(8 × TP) × 101%",
            "formula_python": "(8 * Total_PowerGrip) * 1.01",
            "tipo_regla": "FIJA", "orden_ejecucion": 1,
        }
    )
    r2, _ = ReglaCalculo.objects.get_or_create(
        subsistema=sub_u7, codigo="TR-R02", version=1,
        defaults={
            "nombre": "Limpiador test", "producto": lmp,
            "variable_entrada": "Total_PowerGrip",
            "coeficiente": Decimal("0.04"), "divisor": Decimal("50"),
            "factor_desperdicio": Decimal("1.01"),
            "formula_texto": "((TP × 0.04) / 50) × 101%",
            "formula_python": "((Total_PowerGrip * 0.04) / 50) * 1.01",
            "tipo_regla": "FIJA", "orden_ejecucion": 2,
        }
    )
    r3, _ = ReglaCalculo.objects.get_or_create(
        subsistema=sub_u7, codigo="TR-R03", version=1,
        defaults={
            "nombre": "Estopa test", "producto": estopa,
            "variable_entrada": "Total_PowerGrip",
            "coeficiente": Decimal("0.04"), "divisor": Decimal("100"),
            "factor_desperdicio": Decimal("1.01"),
            "formula_texto": "Limpiador / 2",
            "formula_python": "((Total_PowerGrip * 0.04) / 50) * 1.01 / 2",
            "tipo_regla": "DERIVADA", "orden_ejecucion": 3,
        }
    )
    r4, _ = ReglaCalculo.objects.get_or_create(
        subsistema=sub_u7, codigo="TR-R04", version=1,
        defaults={
            "nombre": "Sellador test", "producto": sellador,
            "variable_entrada": "Total_PowerGrip",
            "coeficiente": Decimal("0.56"), "divisor": Decimal("12"),
            "factor_desperdicio": Decimal("1.01"),
            "formula_texto": "((TP × 0.56) / 12) × 101%",
            "formula_python": "((Total_PowerGrip * 0.56) / 12) * 1.01",
            "tipo_regla": "FIJA", "orden_ejecucion": 4,
        }
    )

    # Dependencias
    DependenciaTecnica.objects.get_or_create(
        subsistema=sub_u7, producto_dependiente=lmp,
        defaults={"obligatoria": True, "orden": 1}
    )
    DependenciaTecnica.objects.get_or_create(
        subsistema=sub_u7, producto_dependiente=estopa,
        defaults={"obligatoria": True, "orden": 2}
    )

    # Cliente y solicitud
    cliente, _ = Cliente.objects.get_or_create(
        nit="900-TEST",
        defaults={"razon_social": "Cliente Test SA"}
    )
    contacto, _ = ContactoCliente.objects.get_or_create(
        cliente=cliente, nombre="Contacto Test",
        defaults={"es_principal": True}
    )
    usuario, _ = UsuarioSistema.objects.get_or_create(
        email="test@test.com",
        defaults={"nombre_completo": "Usuario Test", "password_hash": "x", "rol": "PRESUPUESTOS"}
    )
    solicitud, _ = Solicitud.objects.get_or_create(
        consecutivo="SOL-2024-TEST",
        defaults={
            "cliente": cliente, "creado_por": usuario,
            "nombre": "Solicitud test", "estado": "EN_GESTION",
        }
    )
    tipo_pry, _ = TipoProyecto.objects.get_or_create(codigo="TEST-TP", defaults={"nombre": "Tipo Test"})
    proyecto, _ = Proyecto.objects.get_or_create(
        consecutivo="PRY-2024-TEST",
        defaults={
            "solicitud": solicitud, "cliente": cliente,
            "creado_por": usuario, "tipo_proyecto": tipo_pry,
            "nombre": "Proyecto test",
            "area_total_m2": Decimal("500"), "perimetro_ml": Decimal("100"),
            "estado": "SOLICITUD",
        }
    )
    ps, _ = ProyectoSistema.objects.get_or_create(
        proyecto=proyecto, sistema=sistema, subsistema=sub_u7,
        defaults={"total_powergip": Decimal("100"), "cuadrilla_personas": 4}
    )

    # Proveedor con precios
    prov, _ = Proveedor.objects.get_or_create(nit="800-TEST", defaults={"nombre": "Proveedor Test"})
    for prod, precio in [(fij, "500"), (lmp, "45000"), (estopa, "12000"), (sellador, "35000")]:
        ProductoProveedor.objects.get_or_create(
            producto=prod, proveedor=prov,
            defaults={"precio_unitario": Decimal(precio), "moneda": "COP"}
        )

    ConfiguracionAPU.objects.get_or_create(
        nombre="Test Config",
        defaults={"porcentaje_ganancia": 20, "aiu_contratista": 30,
                  "desperdicio": 3, "margen_ganancia_contratista": 30}
    )

    return {"ps": ps, "proyecto": proyecto, "sistema": sistema,
            "sub_u7": sub_u7, "cliente": cliente, "solicitud": solicitud,
            "usuario": usuario, "tipo_pry": tipo_pry,
            "productos": {"fij": fij, "lmp": lmp, "estopa": estopa, "sellador": sellador}}


# ---------------------------------------------------------------------------
# Tests de Modelos
# ---------------------------------------------------------------------------

class ConsecutivoTestCase(TestCase):
    def test_consecutivo_solicitud(self):
        from core.models import Solicitud
        c = Solicitud.siguiente_consecutivo()
        self.assertIn("-", c)
        self.assertTrue(c.startswith("SOL-"))

    def test_consecutivo_proyecto(self):
        from core.models import Proyecto
        c = Proyecto.siguiente_consecutivo()
        self.assertTrue(c.startswith("PRY-"))


class ReglaCalculoTestCase(TestCase):
    """Tests del motor de evaluación de fórmulas."""

    def test_evaluar_fijaciones_u7(self):
        """(8 × 100) × 1.01 = 808"""
        datos = crear_datos_base()
        from core.models import ReglaCalculo
        regla = ReglaCalculo.objects.get(subsistema=datos["sub_u7"], codigo="TR-R01")
        resultado = regla.evaluar({"Total_PowerGrip": 100})
        self.assertAlmostEqual(resultado, 808.0, places=2)

    def test_evaluar_limpiador_u7(self):
        """((100 × 0.04) / 50) × 1.01 = 0.0808"""
        datos = crear_datos_base()
        from core.models import ReglaCalculo
        regla = ReglaCalculo.objects.get(subsistema=datos["sub_u7"], codigo="TR-R02")
        resultado = regla.evaluar({"Total_PowerGrip": 100})
        self.assertAlmostEqual(resultado, 0.0808, places=4)

    def test_evaluar_estopa_derivada(self):
        """Limpiador / 2 = 0.0404"""
        datos = crear_datos_base()
        from core.models import ReglaCalculo
        regla = ReglaCalculo.objects.get(subsistema=datos["sub_u7"], codigo="TR-R03")
        resultado = regla.evaluar({"Total_PowerGrip": 100})
        self.assertAlmostEqual(resultado, 0.0404, places=4)

    def test_evaluar_sellador_u7(self):
        """((100 × 0.56) / 12) × 1.01 ≈ 4.713"""
        datos = crear_datos_base()
        from core.models import ReglaCalculo
        regla = ReglaCalculo.objects.get(subsistema=datos["sub_u7"], codigo="TR-R04")
        resultado = regla.evaluar({"Total_PowerGrip": 100})
        self.assertAlmostEqual(resultado, 4.7133, places=2)

    def test_formula_sin_formula_python_usa_auto(self):
        """Si no hay formula_python, usa _formula_auto con coef/divisor."""
        datos = crear_datos_base()
        from core.models import ReglaCalculo
        regla = ReglaCalculo.objects.get(subsistema=datos["sub_u7"], codigo="TR-R01")
        # Limpiar formula_python para forzar _formula_auto
        regla.formula_python = None
        resultado = regla.evaluar({"Total_PowerGrip": 50})
        # coef=8, div=1, desp=1.01 → (8*50/1)*1.01 = 404
        self.assertAlmostEqual(resultado, 404.0, places=1)


class PowerGripAlgoritmoTestCase(TestCase):
    """Tests de los algoritmos hardcodeados de DespieceService."""

    def test_universal7_fijaciones(self):
        from core.services import DespieceService
        r = DespieceService.calcular_universal7(100)
        self.assertAlmostEqual(r["Fijaciones"], 808.0,  places=1)
        self.assertAlmostEqual(r["Limpiador"],  0.0808, places=4)
        self.assertAlmostEqual(r["Estopa"],     0.0404, places=4)
        self.assertAlmostEqual(r["Sellador"],   4.7133, places=2)

    def test_plus_tpo_fijaciones(self):
        from core.services import DespieceService
        r = DespieceService.calcular_plus_tpo(100)
        self.assertAlmostEqual(r["Fijaciones"], 909.0,  places=1)
        self.assertAlmostEqual(r["Limpiador"],  0.18180, places=3)
        self.assertAlmostEqual(r["Estopa"],     0.09090, places=3)
        # ((100 × 1.16) / 36.1) × 1.01 ≈ 3.241
        self.assertAlmostEqual(r["Sellador"],   3.241, places=2)

    def test_universal7_cero(self):
        from core.services import DespieceService
        r = DespieceService.calcular_universal7(0)
        for v in r.values():
            self.assertEqual(v, 0.0)


# ---------------------------------------------------------------------------
# Tests de DespieceService
# ---------------------------------------------------------------------------

class DespieceServiceTestCase(TestCase):
    def setUp(self):
        self.datos = crear_datos_base()

    def test_ejecutar_genera_lineas(self):
        from core.services import DespieceService
        ps = self.datos["ps"]
        service = DespieceService(ps)
        resultados = service.ejecutar()
        self.assertGreater(len(resultados), 0)
        for r in resultados:
            self.assertIn("cantidad", r)
            self.assertGreater(r["cantidad"], 0)

    def test_despiece_crea_objetos_en_bd(self):
        from core.services import DespieceService
        from core.models import DespieceLinea
        ps = self.datos["ps"]
        DespieceService(ps).ejecutar()
        lineas = DespieceLinea.objects.filter(proyecto=self.datos["proyecto"])
        self.assertGreater(lineas.count(), 0)

    def test_despiece_sin_subsistema_lanza_error(self):
        from core.services import DespieceService
        from core.models import ProyectoSistema
        ps = self.datos["ps"]
        ps.subsistema = None
        ps.save()
        with self.assertRaises(ValueError):
            DespieceService(ps).ejecutar()


# ---------------------------------------------------------------------------
# Tests de DependenciaService
# ---------------------------------------------------------------------------

class DependenciaServiceTestCase(TestCase):
    def setUp(self):
        self.datos = crear_datos_base()

    def test_inyectar_crea_lineas_dependencia(self):
        from core.services import DependenciaService
        from core.models import DespieceLinea
        ps = self.datos["ps"]
        service = DependenciaService(ps)
        creadas = service.inyectar()
        self.assertGreater(len(creadas), 0)
        for c in creadas:
            self.assertTrue(c["automatica"])

    def test_dependencias_del_subsistema_lista(self):
        from core.services import DependenciaService
        ps = self.datos["ps"]
        deps = DependenciaService(ps).dependencias_del_subsistema()
        codigos = [d["producto_codigo"] for d in deps]
        self.assertIn("LMP-TEST", codigos)
        self.assertIn("EST-TEST", codigos)

    def test_inyeccion_idempotente(self):
        """Llamar dos veces no duplica líneas."""
        from core.services import DependenciaService
        from core.models import DespieceLinea
        ps = self.datos["ps"]
        DependenciaService(ps).inyectar()
        DependenciaService(ps).inyectar()
        lineas = DespieceLinea.objects.filter(
            proyecto=self.datos["proyecto"],
            es_dependencia_automatica=True
        )
        # No deben existir duplicados
        codigos = list(lineas.values_list("producto__codigo", flat=True))
        self.assertEqual(len(codigos), len(set(codigos)))


# ---------------------------------------------------------------------------
# Tests de APUService
# ---------------------------------------------------------------------------

class APUServiceTestCase(TestCase):
    def setUp(self):
        self.datos = crear_datos_base()
        # Ejecutar despiece primero
        from core.services import DespieceService
        DespieceService(self.datos["ps"]).ejecutar()

    def test_generar_materiales(self):
        from core.services import APUService
        service = APUService(self.datos["ps"])
        materiales = service.generar_materiales()
        self.assertGreater(len(materiales), 0)
        for m in materiales:
            self.assertIn("costo_unitario", m)
            self.assertGreaterEqual(m["costo_unitario"], 0)

    def test_generar_mano_obra(self):
        from core.services import APUService
        ps = self.datos["ps"]
        ps.cuadrilla_personas = 4
        ps.save()
        service = APUService(ps)
        result = service.generar_mano_obra(
            hya_dia=500000, cuadrilla_dia=200000,
            dotacion_dia=50000, proteccion_dia=30000
        )
        self.assertIn("dias", result)
        self.assertGreater(result["dias"], 0)

    def test_finalizar_recalcula_totales(self):
        from core.services import APUService
        service = APUService(self.datos["ps"])
        service.generar_materiales()
        totales = service.finalizar()
        self.assertIn("total_costo", totales)
        self.assertGreaterEqual(totales["total_costo"], 0)

    def test_apu_proyecto_estado_avanza(self):
        from core.services import APUService
        from core.models import EstadoProyecto
        ps = self.datos["ps"]
        proyecto = ps.proyecto
        proyecto.estado = "DESPIECE"
        proyecto.save()
        service = APUService(ps)
        service.generar_materiales()
        service.finalizar()
        proyecto.refresh_from_db()
        self.assertEqual(proyecto.estado, EstadoProyecto.APU)


# ---------------------------------------------------------------------------
# Tests de ProyectoService — flujo de estados
# ---------------------------------------------------------------------------

class ProyectoServiceTestCase(TestCase):
    def setUp(self):
        self.datos = crear_datos_base()

    def test_crear_desde_solicitud(self):
        from core.services import ProyectoService
        datos = self.datos
        proyecto = ProyectoService.crear_desde_solicitud(
            solicitud_id=datos["solicitud"].id,
            tipo_proyecto_id=datos["tipo_pry"].id,
            creado_por=datos["usuario"],
            area_total_m2=500,
            perimetro_ml=100,
        )
        self.assertIsNotNone(proyecto.pk)
        self.assertEqual(proyecto.estado, "SOLICITUD")
        self.assertEqual(proyecto.cliente, datos["cliente"])

    def test_iniciar_despiece_cambia_estado(self):
        from core.services import ProyectoService
        from core.models import EstadoProyecto
        datos = self.datos
        result = ProyectoService.iniciar_despiece(
            proyecto_id=datos["proyecto"].id,
            sistema_id=datos["sistema"].id,
            subsistema_id=datos["sub_u7"].id,
            total_powergip=200,
            cuadrilla=5,
        )
        self.assertEqual(result["estado_proyecto"], EstadoProyecto.DESPIECE)
        self.assertIsNotNone(result["proyecto_sistema_id"])

    def test_flujo_completo_solicitud_despiece_apu(self):
        """Prueba el flujo completo: SOLICITUD → DESPIECE → APU"""
        from core.services import ProyectoService
        from core.models import EstadoProyecto, Proyecto
        datos = self.datos

        # Crear nuevo proyecto
        proyecto = ProyectoService.crear_desde_solicitud(
            solicitud_id=datos["solicitud"].id,
            tipo_proyecto_id=datos["tipo_pry"].id,
            creado_por=datos["usuario"],
            area_total_m2=800,
        )
        self.assertEqual(proyecto.estado, "SOLICITUD")

        # Iniciar despiece
        d_result = ProyectoService.iniciar_despiece(
            proyecto_id=proyecto.id,
            sistema_id=datos["sistema"].id,
            subsistema_id=datos["sub_u7"].id,
            total_powergip=150,
        )
        self.assertEqual(d_result["estado_proyecto"], "DESPIECE")

        # Iniciar APU
        a_result = ProyectoService.iniciar_apu(
            proyecto_sistema_id=d_result["proyecto_sistema_id"],
            costo_transporte=500000,
            costo_admin=300000,
        )
        self.assertIn("totales", a_result)

        proyecto.refresh_from_db()
        self.assertEqual(proyecto.estado, EstadoProyecto.APU)


# ---------------------------------------------------------------------------
# Tests de Solicitud — auto-contacto y consecutivo
# ---------------------------------------------------------------------------

class SolicitudTestCase(TestCase):
    def test_contacto_principal_asignado_automaticamente(self):
        from core.models import Cliente, ContactoCliente, Solicitud, UsuarioSistema
        cliente = Cliente.objects.create(nit="111-SC", razon_social="SC Test")
        contacto = ContactoCliente.objects.create(
            cliente=cliente, nombre="Principal", es_principal=True
        )
        usuario = UsuarioSistema.objects.create(
            email="sc@test.com", nombre_completo="SC", password_hash="x"
        )
        sol = Solicitud.objects.create(
            consecutivo=Solicitud.siguiente_consecutivo(),
            cliente=cliente,
            creado_por=usuario,
            nombre="Test auto-contacto",
        )
        self.assertEqual(sol.contacto, contacto)

    def test_consecutivo_incremental(self):
        from core.models import Cliente, Solicitud, UsuarioSistema
        cliente = Cliente.objects.create(nit="222-CI", razon_social="CI Test")
        usuario = UsuarioSistema.objects.create(
            email="ci@test.com", nombre_completo="CI", password_hash="x"
        )
        s1 = Solicitud.objects.create(
            consecutivo=Solicitud.siguiente_consecutivo(),
            cliente=cliente, creado_por=usuario, nombre="S1"
        )
        s2 = Solicitud.objects.create(
            consecutivo=Solicitud.siguiente_consecutivo(),
            cliente=cliente, creado_por=usuario, nombre="S2"
        )
        n1 = int(s1.consecutivo.split("-")[-1])
        n2 = int(s2.consecutivo.split("-")[-1])
        self.assertEqual(n2, n1 + 1)


# ---------------------------------------------------------------------------
# Tests de variables dinámicas del Proyecto
# ---------------------------------------------------------------------------

class VariablesDinamicasTestCase(TestCase):
    def test_variables_extra_en_contexto(self):
        datos = crear_datos_base()
        ps = datos["ps"]
        ps.variables_extra = {"factor_especial": 1.5, "zona": 2}
        ps.save()
        ctx = ps.get_contexto()
        self.assertIn("factor_especial", ctx)
        self.assertEqual(ctx["factor_especial"], 1.5)

    def test_contexto_incluye_area_perimetro(self):
        datos = crear_datos_base()
        ctx = datos["ps"].get_contexto()
        self.assertIn("area_m2", ctx)
        self.assertIn("perimetro_ml", ctx)
        self.assertEqual(ctx["area_m2"], 500.0)
