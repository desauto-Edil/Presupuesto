"""
Tests para apps/ingenieria/helpers/presentacion.py — obtener_valor_presentacion.

Verifica:
  - CANTIDAD usa producto.cantidad_presentacion
  - ANCHO usa producto.ancho_presentacion
  - LARGO usa producto.largo_presentacion
  - campo vacío o desconocido recae en CANTIDAD
  - valor None/cero produce mensaje de error específico por campo
"""
from __future__ import annotations

from decimal import Decimal
from unittest import TestCase

from apps.ingenieria.helpers.presentacion import obtener_valor_presentacion


class FakeComp:
    def __init__(self, campo="CANTIDAD"):
        self.campo_presentacion_producto = campo


class FakeProd:
    nombre = "Membrana XYZ"
    cantidad_presentacion = None
    ancho_presentacion = None
    largo_presentacion = None


class ObtenerValorPresentacionTest(TestCase):

    # ── CANTIDAD ────────────────────────────────────────────────────────────────

    def test_cantidad_valida(self):
        comp = FakeComp("CANTIDAD")
        prod = FakeProd()
        prod.cantidad_presentacion = Decimal("30.48")
        val, err = obtener_valor_presentacion(comp, prod)
        self.assertIsNone(err)
        self.assertAlmostEqual(val, 30.48)

    def test_cantidad_nula_produce_error_especifico(self):
        comp = FakeComp("CANTIDAD")
        prod = FakeProd()
        prod.cantidad_presentacion = None
        val, err = obtener_valor_presentacion(comp, prod)
        self.assertIsNone(val)
        self.assertIn("cantidad por presentación", err)
        self.assertIn("Membrana XYZ", err)

    def test_cantidad_cero_produce_error(self):
        comp = FakeComp("CANTIDAD")
        prod = FakeProd()
        prod.cantidad_presentacion = Decimal("0")
        val, err = obtener_valor_presentacion(comp, prod)
        self.assertIsNone(val)
        self.assertIsNotNone(err)

    # ── ANCHO ────────────────────────────────────────────────────────────────────

    def test_ancho_valido(self):
        comp = FakeComp("ANCHO")
        prod = FakeProd()
        prod.ancho_presentacion = Decimal("1.50")
        val, err = obtener_valor_presentacion(comp, prod)
        self.assertIsNone(err)
        self.assertAlmostEqual(val, 1.50)

    def test_ancho_nulo_produce_error_especifico(self):
        comp = FakeComp("ANCHO")
        prod = FakeProd()
        prod.ancho_presentacion = None
        val, err = obtener_valor_presentacion(comp, prod)
        self.assertIsNone(val)
        self.assertIn("ancho", err)
        self.assertIn("Membrana XYZ", err)

    def test_ancho_cero_produce_error(self):
        comp = FakeComp("ANCHO")
        prod = FakeProd()
        prod.ancho_presentacion = Decimal("0")
        val, err = obtener_valor_presentacion(comp, prod)
        self.assertIsNone(val)
        self.assertIsNotNone(err)

    # ── LARGO ────────────────────────────────────────────────────────────────────

    def test_largo_valido(self):
        comp = FakeComp("LARGO")
        prod = FakeProd()
        prod.largo_presentacion = Decimal("25.0")
        val, err = obtener_valor_presentacion(comp, prod)
        self.assertIsNone(err)
        self.assertAlmostEqual(val, 25.0)

    def test_largo_nulo_produce_error_especifico(self):
        comp = FakeComp("LARGO")
        prod = FakeProd()
        prod.largo_presentacion = None
        val, err = obtener_valor_presentacion(comp, prod)
        self.assertIsNone(val)
        self.assertIn("largo", err)
        self.assertIn("Membrana XYZ", err)

    def test_largo_cero_produce_error(self):
        comp = FakeComp("LARGO")
        prod = FakeProd()
        prod.largo_presentacion = Decimal("0")
        val, err = obtener_valor_presentacion(comp, prod)
        self.assertIsNone(val)
        self.assertIsNotNone(err)

    # ── Fallbacks ───────────────────────────────────────────────────────────────

    def test_campo_vacio_usa_cantidad(self):
        """Un campo vacío o None debe comportarse como CANTIDAD."""
        comp = FakeComp("")
        prod = FakeProd()
        prod.cantidad_presentacion = Decimal("10")
        val, err = obtener_valor_presentacion(comp, prod)
        self.assertIsNone(err)
        self.assertAlmostEqual(val, 10.0)

    def test_campo_desconocido_usa_cantidad(self):
        """Un campo no válido (ej: PESO) debe caer en CANTIDAD."""
        comp = FakeComp("PESO")
        prod = FakeProd()
        prod.cantidad_presentacion = Decimal("7.5")
        val, err = obtener_valor_presentacion(comp, prod)
        self.assertIsNone(err)
        self.assertAlmostEqual(val, 7.5)

    def test_campo_none_usa_cantidad(self):
        """campo_presentacion_producto=None debe caer en CANTIDAD."""
        comp = FakeComp(None)
        prod = FakeProd()
        prod.cantidad_presentacion = Decimal("3")
        val, err = obtener_valor_presentacion(comp, prod)
        self.assertIsNone(err)
        self.assertAlmostEqual(val, 3.0)

    # ── Mensajes de error no se mezclan ─────────────────────────────────────────

    def test_error_ancho_no_menciona_cantidad(self):
        """El error de ANCHO no debe decir 'cantidad por presentación'."""
        comp = FakeComp("ANCHO")
        prod = FakeProd()
        prod.ancho_presentacion = None
        _, err = obtener_valor_presentacion(comp, prod)
        self.assertNotIn("cantidad por presentación", err)

    def test_error_largo_no_menciona_ancho(self):
        """El error de LARGO no debe decir 'ancho'."""
        comp = FakeComp("LARGO")
        prod = FakeProd()
        prod.largo_presentacion = None
        _, err = obtener_valor_presentacion(comp, prod)
        self.assertNotIn("ancho", err)
