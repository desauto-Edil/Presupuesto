"""
Tests para PresentacionProductoService y la bifurcación en DespieceService._ejecutar_desde_db.

Usa django.test.TestCase (transaccional) con creación mínima de objetos en BD.
"""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from apps.presupuestos.services.presentacion_service import PresentacionProductoService


# ── Helpers para crear objetos mínimos ───────────────────────────────────────

def _crear_sistema(**kwargs):
    from apps.ingenieria.models import Sistema
    from apps.common.choices import LineaNegocio, TipoSistema
    defaults = dict(
        codigo="SIS_TEST",
        nombre="Sistema Test",
        linea_negocio=LineaNegocio.CUBIERTAS,
        tipo_sistema=TipoSistema.CONSTRUCTIVO,
    )
    defaults.update(kwargs)
    return Sistema.objects.create(**defaults)


def _crear_subsistema(sistema, **kwargs):
    from apps.ingenieria.models import Subsistema
    defaults = dict(
        sistema=sistema,
        codigo="SUB_TEST",
        nombre="Subsistema Test",
    )
    defaults.update(kwargs)
    return Subsistema.objects.create(**defaults)


def _crear_categoria(**kwargs):
    from apps.catalogos.models import CategoriaProducto
    defaults = dict(nombre="Cat Test")
    defaults.update(kwargs)
    return CategoriaProducto.objects.create(**defaults)


def _crear_componente(subsistema, **kwargs):
    from apps.ingenieria.models import ComponenteSubsistema
    defaults = dict(
        subsistema=subsistema,
        codigo="comp_a",
        nombre="Componente A",
        formula_texto="area_m2 * 2",
        orden=1,
    )
    defaults.update(kwargs)
    return ComponenteSubsistema.objects.create(**defaults)


def _crear_proyecto(**kwargs):
    from apps.comercial.models import Proyecto, TipoProyecto
    tipo = TipoProyecto.objects.first() or TipoProyecto.objects.create(nombre="Tipo Test")
    defaults = dict(
        consecutivo="P-TEST",
        nombre="Proyecto Test",
        tipo_proyecto=tipo,
    )
    defaults.update(kwargs)
    return Proyecto.objects.create(**defaults)


def _crear_ps(proyecto, sistema, subsistema):
    from apps.presupuestos.models import ProyectoSistema
    return ProyectoSistema.objects.create(
        proyecto=proyecto,
        sistema=sistema,
        subsistema=subsistema,
        # area_m2 y perimetro_ml viven en parametros_entrada desde que se eliminaron
        # los campos del modelo Proyecto (migración comercial.0016).
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


def _crear_producto(categoria, cantidad_presentacion=None, **kwargs):
    from apps.catalogos.models import Producto, UnidadMedida
    unidad = UnidadMedida.objects.first() or UnidadMedida.objects.create(codigo="UN", nombre="Unidad")
    defaults = dict(
        nombre="Producto Test",
        categoria=categoria,
        unidad=unidad,
        activo=True,
        cantidad_presentacion=cantidad_presentacion,
    )
    defaults.update(kwargs)
    return Producto.objects.create(**defaults)


# ── Tests ─────────────────────────────────────────────────────────────────────

class RecalcularTrasAsignacionTest(TestCase):

    def setUp(self):
        self.sistema = _crear_sistema()
        self.subsistema = _crear_subsistema(self.sistema)
        self.categoria = _crear_categoria()
        self.proyecto = _crear_proyecto()
        self.ps = _crear_ps(self.proyecto, self.sistema, self.subsistema)

    def test_calcula_y_guarda_cuando_presentacion_valida(self):
        """recalcular_tras_asignacion calcula la cantidad y limpia pendiente_producto."""
        comp = _crear_componente(
            self.subsistema,
            formula_texto="area_m2 / pres",
            requiere_presentacion_producto=True,
            variable_presentacion_producto="pres",
            orden=1,
        )
        linea = _crear_linea(self.ps, comp, pendiente_producto=True)
        producto = _crear_producto(self.categoria, cantidad_presentacion=Decimal("5"))

        resultado = PresentacionProductoService.recalcular_tras_asignacion(linea, producto)

        linea.refresh_from_db()
        self.assertFalse(linea.pendiente_producto)
        # area_m2=100, pres=5 → 100/5 = 20
        self.assertEqual(linea.cantidad_calculada, Decimal("20.000000"))
        self.assertEqual(linea.presentacion_snapshot, Decimal("5"))
        self.assertEqual(len(resultado), 1)

    def test_lanza_error_si_presentacion_es_none(self):
        """recalcular_tras_asignacion lanza ValueError si cantidad_presentacion es None."""
        comp = _crear_componente(
            self.subsistema,
            formula_texto="area_m2 / pres",
            requiere_presentacion_producto=True,
            variable_presentacion_producto="pres",
        )
        linea = _crear_linea(self.ps, comp)
        producto = _crear_producto(self.categoria, cantidad_presentacion=None)

        with self.assertRaises(ValueError, msg="Debe fallar con presentacion=None"):
            PresentacionProductoService.recalcular_tras_asignacion(linea, producto)

    def test_lanza_error_si_presentacion_es_cero(self):
        """recalcular_tras_asignacion lanza ValueError si cantidad_presentacion es 0."""
        comp = _crear_componente(
            self.subsistema,
            formula_texto="area_m2 / pres",
            requiere_presentacion_producto=True,
            variable_presentacion_producto="pres",
        )
        linea = _crear_linea(self.ps, comp)
        producto = _crear_producto(self.categoria, cantidad_presentacion=Decimal("0"))

        with self.assertRaises(ValueError):
            PresentacionProductoService.recalcular_tras_asignacion(linea, producto)

    def test_lanza_error_si_componente_no_requiere_presentacion(self):
        """recalcular_tras_asignacion rechaza componentes sin la bandera activa."""
        comp = _crear_componente(
            self.subsistema,
            formula_texto="area_m2 * 2",
            requiere_presentacion_producto=False,
        )
        linea = _crear_linea(self.ps, comp)
        producto = _crear_producto(self.categoria, cantidad_presentacion=Decimal("5"))

        with self.assertRaises(ValueError):
            PresentacionProductoService.recalcular_tras_asignacion(linea, producto)

    def test_propaga_cascade_cuando_hay_variable_salida(self):
        """
        Si comp_a tiene variable_salida='val_a' y comp_b usa 'val_a' en su fórmula,
        al resolver comp_a también se resuelve comp_b.
        """
        comp_a = _crear_componente(
            self.subsistema,
            codigo="comp_a",
            formula_texto="area_m2 / pres",
            requiere_presentacion_producto=True,
            variable_presentacion_producto="pres",
            variable_salida="val_a",
            orden=1,
        )
        comp_b = _crear_componente(
            self.subsistema,
            codigo="comp_b",
            formula_texto="val_a * 3",
            requiere_presentacion_producto=False,
            variable_salida="",
            orden=2,
        )

        linea_a = _crear_linea(self.ps, comp_a, pendiente_producto=True)
        linea_b = _crear_linea(self.ps, comp_b, pendiente_producto=True, cantidad_calculada=None)

        producto = _crear_producto(self.categoria, cantidad_presentacion=Decimal("5"))

        resultado = PresentacionProductoService.recalcular_tras_asignacion(linea_a, producto)

        linea_a.refresh_from_db()
        linea_b.refresh_from_db()

        # comp_a: 100/5 = 20
        self.assertFalse(linea_a.pendiente_producto)
        self.assertEqual(linea_a.cantidad_calculada, Decimal("20.000000"))

        # comp_b: val_a * 3 = 20 * 3 = 60
        self.assertFalse(linea_b.pendiente_producto)
        self.assertEqual(linea_b.cantidad_calculada, Decimal("60.000000"))
        self.assertEqual(len(resultado), 2)


class LimpiarTrasEliminacionTest(TestCase):

    def setUp(self):
        self.sistema = _crear_sistema()
        self.subsistema = _crear_subsistema(self.sistema)
        self.categoria = _crear_categoria()
        self.proyecto = _crear_proyecto()
        self.ps = _crear_ps(self.proyecto, self.sistema, self.subsistema)

    def test_resetea_linea_a_pendiente(self):
        """limpiar_tras_eliminacion pone pendiente=True, cantidad=None, snapshot=None."""
        comp = _crear_componente(
            self.subsistema,
            formula_texto="area_m2 / pres",
            requiere_presentacion_producto=True,
            variable_presentacion_producto="pres",
        )
        producto = _crear_producto(self.categoria, cantidad_presentacion=Decimal("5"))
        linea = _crear_linea(
            self.ps, comp,
            pendiente_producto=False,
            cantidad_calculada=Decimal("20"),
            presentacion_snapshot=Decimal("5"),
            producto=producto,
        )

        PresentacionProductoService.limpiar_tras_eliminacion(linea)

        linea.refresh_from_db()
        self.assertTrue(linea.pendiente_producto)
        self.assertIsNone(linea.cantidad_calculada)
        self.assertIsNone(linea.presentacion_snapshot)

    def test_invalida_cascade_en_componentes_dependientes(self):
        """
        Al quitar el producto de comp_a (que tiene variable_salida='val_a'),
        comp_b (que usa 'val_a') también queda pendiente.
        """
        comp_a = _crear_componente(
            self.subsistema,
            codigo="comp_a",
            formula_texto="area_m2 / pres",
            requiere_presentacion_producto=True,
            variable_presentacion_producto="pres",
            variable_salida="val_a",
            orden=1,
        )
        comp_b = _crear_componente(
            self.subsistema,
            codigo="comp_b",
            formula_texto="val_a * 3",
            requiere_presentacion_producto=False,
            variable_salida="",
            orden=2,
        )

        producto = _crear_producto(self.categoria, cantidad_presentacion=Decimal("5"))
        linea_a = _crear_linea(
            self.ps, comp_a,
            pendiente_producto=False,
            cantidad_calculada=Decimal("20"),
            presentacion_snapshot=Decimal("5"),
            producto=producto,
        )
        linea_b = _crear_linea(
            self.ps, comp_b,
            pendiente_producto=False,
            cantidad_calculada=Decimal("60"),
        )

        PresentacionProductoService.limpiar_tras_eliminacion(linea_a)

        linea_a.refresh_from_db()
        linea_b.refresh_from_db()

        self.assertTrue(linea_a.pendiente_producto)
        self.assertTrue(linea_b.pendiente_producto)
        self.assertIsNone(linea_b.cantidad_calculada)


class DespieceServiceDeferidoTest(TestCase):
    """Tests de integración para _ejecutar_desde_db con componentes diferidos."""

    def setUp(self):
        from apps.presupuestos.services.despiece_service import DespieceService

        self.DespieceService = DespieceService
        self.sistema = _crear_sistema()
        self.subsistema = _crear_subsistema(self.sistema)
        self.categoria = _crear_categoria()
        self.proyecto = _crear_proyecto()
        self.ps = _crear_ps(self.proyecto, self.sistema, self.subsistema)

    def test_componente_diferido_queda_pendiente_sin_producto(self):
        """_ejecutar_desde_db marca pendiente_producto=True si el componente requiere presentación."""
        from apps.presupuestos.models import DespieceLinea

        _crear_componente(
            self.subsistema,
            codigo="comp_dif",
            formula_texto="area_m2 / pres",
            requiere_presentacion_producto=True,
            variable_presentacion_producto="pres",
            categoria=self.categoria,
            orden=1,
        )

        self.DespieceService(self.ps).ejecutar()

        linea = DespieceLinea.objects.get(proyecto_sistema=self.ps, componente_codigo="comp_dif")
        self.assertTrue(linea.pendiente_producto)
        self.assertIsNone(linea.cantidad_calculada)

    def test_cascade_block_marca_componente_dependiente_como_pendiente(self):
        """
        Si comp_a está diferido (variable_salida='val_a') y comp_b usa 'val_a',
        comp_b también queda pendiente_producto=True.
        """
        from apps.presupuestos.models import DespieceLinea

        _crear_componente(
            self.subsistema,
            codigo="comp_a",
            formula_texto="area_m2 / pres",
            requiere_presentacion_producto=True,
            variable_presentacion_producto="pres",
            variable_salida="val_a",
            categoria=self.categoria,
            orden=1,
        )
        _crear_componente(
            self.subsistema,
            codigo="comp_b",
            formula_texto="val_a * 3",
            requiere_presentacion_producto=False,
            categoria=self.categoria,
            orden=2,
        )

        self.DespieceService(self.ps).ejecutar()

        linea_a = DespieceLinea.objects.get(proyecto_sistema=self.ps, componente_codigo="comp_a")
        linea_b = DespieceLinea.objects.get(proyecto_sistema=self.ps, componente_codigo="comp_b")

        self.assertTrue(linea_a.pendiente_producto)
        self.assertIsNone(linea_a.cantidad_calculada)
        self.assertTrue(linea_b.pendiente_producto)
        self.assertIsNone(linea_b.cantidad_calculada)

    def test_componente_normal_no_afectado_por_diferido_sin_dependencia(self):
        """
        comp_a diferido no bloquea comp_c si comp_c no usa la variable_salida de comp_a.
        """
        from apps.presupuestos.models import DespieceLinea

        _crear_componente(
            self.subsistema,
            codigo="comp_a",
            formula_texto="area_m2 / pres",
            requiere_presentacion_producto=True,
            variable_presentacion_producto="pres",
            variable_salida="val_a",
            categoria=self.categoria,
            orden=1,
        )
        _crear_componente(
            self.subsistema,
            codigo="comp_c",
            formula_texto="area_m2 * 2",  # no usa val_a
            requiere_presentacion_producto=False,
            categoria=self.categoria,
            orden=2,
        )

        self.DespieceService(self.ps).ejecutar()

        linea_c = DespieceLinea.objects.get(proyecto_sistema=self.ps, componente_codigo="comp_c")
        self.assertFalse(linea_c.pendiente_producto)
        self.assertEqual(linea_c.cantidad_calculada, Decimal("200.000000"))  # 100*2

    def test_reejecutar_con_producto_asignado_resuelve_diferido(self):
        """
        Si se re-ejecuta el despiece y el componente diferido ya tiene producto,
        se calcula y pendiente_producto queda False.
        """
        from apps.presupuestos.models import DespieceLinea

        comp = _crear_componente(
            self.subsistema,
            codigo="comp_dif",
            formula_texto="area_m2 / pres",
            requiere_presentacion_producto=True,
            variable_presentacion_producto="pres",
            categoria=self.categoria,
            orden=1,
        )

        # Primera ejecución sin producto: queda pendiente
        self.DespieceService(self.ps).ejecutar()
        linea = DespieceLinea.objects.get(proyecto_sistema=self.ps, componente_codigo="comp_dif")
        self.assertTrue(linea.pendiente_producto)

        # Asignar producto
        producto = _crear_producto(self.categoria, cantidad_presentacion=Decimal("4"))
        linea.producto = producto
        linea.save(update_fields=["producto"])

        # Segunda ejecución con producto: debe resolver
        self.DespieceService(self.ps).ejecutar()
        linea.refresh_from_db()

        self.assertFalse(linea.pendiente_producto)
        self.assertEqual(linea.cantidad_calculada, Decimal("25.000000"))  # 100/4
