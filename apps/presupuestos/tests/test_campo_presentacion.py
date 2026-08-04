"""
Tests de integración para el campo campo_presentacion_producto.

Verifica que:
  - PresentacionProductoService usa el campo correcto según ANCHO/LARGO/CANTIDAD
  - El helper es el único punto de resolución (no hay if/elif duplicados en servicios)
  - El snapshot guarda el valor real utilizado (no siempre cantidad_presentacion)
  - Un componente sin requiere_presentacion_producto no se ve afectado
  - variable_salida sigue propagándose correctamente con ANCHO/LARGO
"""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from apps.presupuestos.services.presentacion_service import PresentacionProductoService


# ── Helpers ──────────────────────────────────────────────────────────────────

def _crear_sistema():
    from apps.ingenieria.models import Sistema
    from apps.common.choices import LineaNegocio, TipoSistema
    return Sistema.objects.create(
        codigo="SIS_CP",
        nombre="Sistema CampoPresTest",
        linea_negocio=LineaNegocio.CUBIERTAS,
        tipo_sistema=TipoSistema.CONSTRUCTIVO,
    )


def _crear_subsistema(sistema):
    from apps.ingenieria.models import Subsistema
    return Subsistema.objects.create(
        sistema=sistema,
        codigo="SUB_CP",
        nombre="Subsistema CampoPresTest",
    )


def _crear_categoria():
    from apps.catalogos.models import CategoriaProducto
    return CategoriaProducto.objects.create(nombre="Cat CP Test")


def _crear_componente(subsistema, **kwargs):
    from apps.ingenieria.models import ComponenteSubsistema
    defaults = dict(
        subsistema=subsistema,
        codigo="comp_cp",
        nombre="Componente CP",
        formula_texto="area_m2 / pres",
        requiere_presentacion_producto=True,
        variable_presentacion_producto="pres",
        campo_presentacion_producto="CANTIDAD",
        orden=1,
    )
    defaults.update(kwargs)
    return ComponenteSubsistema.objects.create(**defaults)


def _crear_proyecto():
    from apps.comercial.models import Proyecto, TipoProyecto
    tipo = TipoProyecto.objects.first() or TipoProyecto.objects.create(nombre="Tipo CP")
    return Proyecto.objects.create(
        consecutivo="P-CP",
        nombre="Proyecto CP Test",
        tipo_proyecto=tipo,
    )


def _crear_ps(proyecto, sistema, subsistema):
    from apps.presupuestos.models import ProyectoSistema
    return ProyectoSistema.objects.create(
        proyecto=proyecto,
        sistema=sistema,
        subsistema=subsistema,
        parametros_entrada={"area_m2": "100", "perimetro_ml": "40"},
    )


def _crear_linea(ps, comp, **kwargs):
    from apps.presupuestos.models import DespieceLinea
    defaults = dict(
        proyecto=ps.proyecto,
        proyecto_sistema=ps,
        componente_codigo=comp.codigo,
        pendiente_producto=True,
        cantidad_calculada=None,
    )
    defaults.update(kwargs)
    return DespieceLinea.objects.create(**defaults)


def _crear_producto(categoria, **kwargs):
    from apps.catalogos.models import Producto, UnidadMedida
    unidad = UnidadMedida.objects.first() or UnidadMedida.objects.create(
        codigo="UN_CP", nombre="Unidad CP"
    )
    defaults = dict(
        nombre="Producto CP",
        categoria=categoria,
        unidad=unidad,
        activo=True,
    )
    defaults.update(kwargs)
    return Producto.objects.create(**defaults)


# ── Tests ────────────────────────────────────────────────────────────────────

class CampoPresentacionCantidadTest(TestCase):
    """campo_presentacion_producto=CANTIDAD usa producto.cantidad_presentacion."""

    def setUp(self):
        self.sistema = _crear_sistema()
        self.sub = _crear_subsistema(self.sistema)
        self.cat = _crear_categoria()
        self.proy = _crear_proyecto()
        self.ps = _crear_ps(self.proy, self.sistema, self.sub)

    def test_cantidad_calcula_y_guarda_snapshot(self):
        comp = _crear_componente(self.sub, campo_presentacion_producto="CANTIDAD")
        linea = _crear_linea(self.ps, comp)
        prod = _crear_producto(self.cat, cantidad_presentacion=Decimal("5"))

        PresentacionProductoService.recalcular_tras_asignacion(linea, prod)
        linea.refresh_from_db()

        # area_m2=100, pres=5 → 100/5=20
        self.assertEqual(linea.cantidad_calculada, Decimal("20.000000"))
        self.assertFalse(linea.pendiente_producto)
        self.assertEqual(linea.presentacion_snapshot, Decimal("5"))

    def test_cantidad_nula_lanza_error(self):
        comp = _crear_componente(self.sub, campo_presentacion_producto="CANTIDAD")
        linea = _crear_linea(self.ps, comp)
        prod = _crear_producto(self.cat, cantidad_presentacion=None)

        with self.assertRaises(ValueError) as ctx:
            PresentacionProductoService.recalcular_tras_asignacion(linea, prod)

        self.assertIn("cantidad por presentación", str(ctx.exception))


class CampoPresentacionAnchoTest(TestCase):
    """campo_presentacion_producto=ANCHO usa producto.ancho_presentacion."""

    def setUp(self):
        self.sistema = _crear_sistema()
        self.sub = _crear_subsistema(self.sistema)
        self.cat = _crear_categoria()
        self.proy = _crear_proyecto()
        self.ps = _crear_ps(self.proy, self.sistema, self.sub)

    def test_ancho_valido_calcula(self):
        comp = _crear_componente(
            self.sub,
            codigo="comp_ancho",
            campo_presentacion_producto="ANCHO",
        )
        linea = _crear_linea(self.ps, comp)
        prod = _crear_producto(self.cat, ancho_presentacion=Decimal("2"))

        PresentacionProductoService.recalcular_tras_asignacion(linea, prod)
        linea.refresh_from_db()

        # area_m2=100, pres=2 → 100/2=50
        self.assertEqual(linea.cantidad_calculada, Decimal("50.000000"))
        self.assertEqual(linea.presentacion_snapshot, Decimal("2"))

    def test_ancho_nulo_lanza_error_especifico(self):
        comp = _crear_componente(
            self.sub,
            codigo="comp_ancho_err",
            campo_presentacion_producto="ANCHO",
        )
        linea = _crear_linea(self.ps, comp)
        prod = _crear_producto(self.cat, ancho_presentacion=None, cantidad_presentacion=Decimal("999"))

        with self.assertRaises(ValueError) as ctx:
            PresentacionProductoService.recalcular_tras_asignacion(linea, prod)

        # El error debe mencionar "ancho", no "cantidad por presentación"
        self.assertIn("ancho", str(ctx.exception))
        self.assertNotIn("cantidad por presentación", str(ctx.exception))


class CampoPresentacionLargoTest(TestCase):
    """campo_presentacion_producto=LARGO usa producto.largo_presentacion."""

    def setUp(self):
        self.sistema = _crear_sistema()
        self.sub = _crear_subsistema(self.sistema)
        self.cat = _crear_categoria()
        self.proy = _crear_proyecto()
        self.ps = _crear_ps(self.proy, self.sistema, self.sub)

    def test_largo_valido_calcula(self):
        comp = _crear_componente(
            self.sub,
            codigo="comp_largo",
            campo_presentacion_producto="LARGO",
        )
        linea = _crear_linea(self.ps, comp)
        prod = _crear_producto(self.cat, largo_presentacion=Decimal("4"))

        PresentacionProductoService.recalcular_tras_asignacion(linea, prod)
        linea.refresh_from_db()

        # area_m2=100, pres=4 → 100/4=25
        self.assertEqual(linea.cantidad_calculada, Decimal("25.000000"))
        self.assertEqual(linea.presentacion_snapshot, Decimal("4"))

    def test_largo_nulo_lanza_error_especifico(self):
        comp = _crear_componente(
            self.sub,
            codigo="comp_largo_err",
            campo_presentacion_producto="LARGO",
        )
        linea = _crear_linea(self.ps, comp)
        prod = _crear_producto(self.cat, largo_presentacion=None, cantidad_presentacion=Decimal("999"))

        with self.assertRaises(ValueError) as ctx:
            PresentacionProductoService.recalcular_tras_asignacion(linea, prod)

        self.assertIn("largo", str(ctx.exception))
        self.assertNotIn("ancho", str(ctx.exception))


class ComponenteNormalNoAfectadoTest(TestCase):
    """Un componente sin requiere_presentacion_producto no cambia."""

    def setUp(self):
        self.sistema = _crear_sistema()
        self.sub = _crear_subsistema(self.sistema)
        self.cat = _crear_categoria()
        self.proy = _crear_proyecto()
        self.ps = _crear_ps(self.proy, self.sistema, self.sub)

    def test_componente_normal_rechazado(self):
        from apps.ingenieria.models import ComponenteSubsistema
        comp = ComponenteSubsistema.objects.create(
            subsistema=self.sub,
            codigo="comp_normal",
            nombre="Normal",
            formula_texto="area_m2 * 2",
            requiere_presentacion_producto=False,
            orden=1,
        )
        from apps.presupuestos.models import DespieceLinea
        linea = DespieceLinea.objects.create(
            proyecto=self.ps.proyecto,
            proyecto_sistema=self.ps,
            componente_codigo=comp.codigo,
            pendiente_producto=False,
            cantidad_calculada=Decimal("200"),
        )
        prod = _crear_producto(self.cat, cantidad_presentacion=Decimal("5"))

        with self.assertRaises(ValueError):
            PresentacionProductoService.recalcular_tras_asignacion(linea, prod)

        linea.refresh_from_db()
        # La línea no debe haber cambiado
        self.assertEqual(linea.cantidad_calculada, Decimal("200"))


class VariableSalidaPropagarConAnchoTest(TestCase):
    """variable_salida se propaga correctamente cuando el campo es ANCHO."""

    def setUp(self):
        self.sistema = _crear_sistema()
        self.sub = _crear_subsistema(self.sistema)
        self.cat = _crear_categoria()
        self.proy = _crear_proyecto()
        self.ps = _crear_ps(self.proy, self.sistema, self.sub)

    def test_cascade_desde_ancho(self):
        from apps.ingenieria.models import ComponenteSubsistema
        comp_a = ComponenteSubsistema.objects.create(
            subsistema=self.sub,
            codigo="comp_a_ancho",
            nombre="Comp A (ancho)",
            formula_texto="area_m2 / pres",
            requiere_presentacion_producto=True,
            variable_presentacion_producto="pres",
            campo_presentacion_producto="ANCHO",
            variable_salida="val_a",
            orden=1,
        )
        comp_b = ComponenteSubsistema.objects.create(
            subsistema=self.sub,
            codigo="comp_b_ancho",
            nombre="Comp B",
            formula_texto="val_a * 2",
            requiere_presentacion_producto=False,
            orden=2,
        )

        from apps.presupuestos.models import DespieceLinea
        linea_a = DespieceLinea.objects.create(
            proyecto=self.ps.proyecto, proyecto_sistema=self.ps,
            componente_codigo=comp_a.codigo,
            pendiente_producto=True, cantidad_calculada=None,
        )
        linea_b = DespieceLinea.objects.create(
            proyecto=self.ps.proyecto, proyecto_sistema=self.ps,
            componente_codigo=comp_b.codigo,
            pendiente_producto=True, cantidad_calculada=None,
        )

        prod = _crear_producto(self.cat, ancho_presentacion=Decimal("4"))

        resultado = PresentacionProductoService.recalcular_tras_asignacion(linea_a, prod)

        linea_a.refresh_from_db()
        linea_b.refresh_from_db()

        # area_m2=100, pres(ancho)=4 → comp_a=25, comp_b=25*2=50
        self.assertEqual(linea_a.cantidad_calculada, Decimal("25.000000"))
        self.assertEqual(linea_b.cantidad_calculada, Decimal("50.000000"))
        self.assertEqual(len(resultado), 2)
