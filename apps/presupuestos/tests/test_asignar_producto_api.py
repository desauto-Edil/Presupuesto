"""
Tests para AsignarProductoLineaAPIView (POST + DELETE).

Cubre:
  1. Asignación válida en componente diferido.
  2. Cambio entre productos con distinta presentación.
  3. Producto sin cantidad_presentacion → 422, rollback.
  4. Error de fórmula → 422, rollback completo (el producto no queda guardado).
  5. Asignación en componente normal: flujo preservado, no toca pendiente_producto.
  6. Retiro de producto (DELETE) en componente diferido.
  7. Invalidación de dependientes tras retiro.
  8. Bloqueo por APU aprobado → 403 en POST y DELETE.
  9. JSON correcto cuando cantidad_calculada es None (retiro de diferido).
"""
from __future__ import annotations

import json
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse


URL = "presupuestos:despiece_api_asignar_producto"


# ── Helpers mínimos ─────────────────────────────────────────────────────────

def _crear_sistema(**kw):
    from apps.ingenieria.models import Sistema
    from apps.common.choices import LineaNegocio, TipoSistema
    d = dict(codigo="S_API", nombre="S API", linea_negocio=LineaNegocio.CUBIERTAS,
             tipo_sistema=TipoSistema.CONSTRUCTIVO)
    d.update(kw)
    return Sistema.objects.create(**d)


def _crear_subsistema(sistema, **kw):
    from apps.ingenieria.models import Subsistema
    d = dict(sistema=sistema, codigo="SUB_API", nombre="Sub API")
    d.update(kw)
    return Subsistema.objects.create(**d)


def _crear_categoria(**kw):
    from apps.catalogos.models import CategoriaProducto
    d = dict(nombre="Cat API")
    d.update(kw)
    return CategoriaProducto.objects.create(**d)


def _crear_componente(subsistema, **kw):
    from apps.ingenieria.models import ComponenteSubsistema
    d = dict(subsistema=subsistema, codigo="comp_api", nombre="Comp API",
             formula_texto="area_m2 * 2", orden=1)
    d.update(kw)
    return ComponenteSubsistema.objects.create(**d)


def _crear_proyecto(**kw):
    from apps.comercial.models import Proyecto, TipoProyecto
    tipo = TipoProyecto.objects.first() or TipoProyecto.objects.create(nombre="Tipo API")
    d = dict(consecutivo="P-API", nombre="Proy API", tipo_proyecto=tipo)
    d.update(kw)
    return Proyecto.objects.create(**d)


def _crear_ps(proyecto, sistema, subsistema):
    from apps.presupuestos.models import ProyectoSistema
    return ProyectoSistema.objects.create(
        proyecto=proyecto,
        sistema=sistema,
        subsistema=subsistema,
        parametros_entrada={"area_m2": "100", "perimetro_ml": "40"},
    )


def _crear_linea(ps, comp, **kw):
    from apps.presupuestos.models import DespieceLinea
    d = dict(proyecto=ps.proyecto, proyecto_sistema=ps,
             componente_codigo=comp.codigo, pendiente_producto=True, cantidad_calculada=None)
    d.update(kw)
    return DespieceLinea.objects.create(**d)


_prod_seq = 0

def _crear_producto(categoria, cantidad_presentacion=None, **kw):
    global _prod_seq
    _prod_seq += 1
    from apps.catalogos.models import Producto, UnidadMedida
    unidad = UnidadMedida.objects.first() or UnidadMedida.objects.create(codigo="UN", nombre="Unidad")
    d = dict(nombre="Prod API", codigo=f"TEST-{_prod_seq}", categoria=categoria,
             unidad=unidad, activo=True, cantidad_presentacion=cantidad_presentacion)
    d.update(kw)
    return Producto.objects.create(**d)


def _set_session_rol(client: Client, rol: str = "PRESUPUESTOS"):
    """
    Inyecta rol y usuario_id en la sesión del cliente de test.
    AuthCustomMiddleware redirige a /configuracion/login/ si usuario_id no está presente.
    Como también inyectamos 'rol', el middleware no intenta rellenarlo desde BD.
    """
    session = client.session
    session["rol"] = rol
    session["usuario_id"] = 1  # cualquier entero; el bloque de relleno se omite al tener 'rol'
    session.save()


# ── Setup base reutilizable ──────────────────────────────────────────────────

class _Base(TestCase):
    def setUp(self):
        self.sistema = _crear_sistema()
        self.subsistema = _crear_subsistema(self.sistema)
        self.categoria = _crear_categoria()
        self.proyecto = _crear_proyecto()
        self.ps = _crear_ps(self.proyecto, self.sistema, self.subsistema)

        self.user = User.objects.create_user(username="u_api", password="x")
        self.client.login(username="u_api", password="x")
        _set_session_rol(self.client)

    def _post(self, linea_pk, body):
        url = reverse(URL, args=[linea_pk])
        return self.client.post(
            url, data=json.dumps(body), content_type="application/json"
        )

    def _delete(self, linea_pk):
        url = reverse(URL, args=[linea_pk])
        return self.client.delete(url, content_type="application/json")

    @staticmethod
    def _json(resp):
        if not resp.content:
            raise AssertionError(
                f"Respuesta vacía — status={resp.status_code} "
                f"location={resp.get('Location', '—')}"
            )
        return json.loads(resp.content)


# ── Test 1: Asignación válida en componente diferido ────────────────────────

class AsignacionDiferidoValidaTest(_Base):

    def test_calcula_y_responde_json_correcto(self):
        comp = _crear_componente(
            self.subsistema,
            codigo="comp_dif",
            formula_texto="area_m2 / pres",
            requiere_presentacion_producto=True,
            variable_presentacion_producto="pres",
            categoria=self.categoria,
        )
        linea = _crear_linea(self.ps, comp)
        producto = _crear_producto(self.categoria, cantidad_presentacion=Decimal("5"))

        resp = self._post(linea.pk, {"producto_id": producto.pk})
        data = self._json(resp)

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data["ok"])
        # area_m2=100, pres=5 → 100/5=20
        self.assertEqual(data["cantidad_calculada"], 20.0)
        self.assertFalse(data["pendiente_producto"])
        self.assertEqual(data["presentacion_snapshot"], 5.0)
        self.assertEqual(data["dependientes"], [])

        linea.refresh_from_db()
        self.assertEqual(linea.producto_id, producto.pk)
        self.assertFalse(linea.pendiente_producto)
        self.assertEqual(linea.cantidad_calculada, Decimal("20.000000"))


# ── Test 2: Cambio de producto con distinta presentación ────────────────────

class CambioProductoPresentacionTest(_Base):

    def test_cambia_calculo_con_nueva_presentacion(self):
        comp = _crear_componente(
            self.subsistema,
            codigo="comp_dif",
            formula_texto="area_m2 / pres",
            requiere_presentacion_producto=True,
            variable_presentacion_producto="pres",
            categoria=self.categoria,
        )
        prod_a = _crear_producto(self.categoria, cantidad_presentacion=Decimal("5"))
        prod_b = _crear_producto(self.categoria, cantidad_presentacion=Decimal("4"),
                                 nombre="Prod B")
        linea = _crear_linea(
            self.ps, comp,
            pendiente_producto=False,
            cantidad_calculada=Decimal("20"),
            presentacion_snapshot=Decimal("5"),
            producto=prod_a,
        )

        resp = self._post(linea.pk, {"producto_id": prod_b.pk})
        data = self._json(resp)

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data["ok"])
        # area_m2=100, pres=4 → 25
        self.assertEqual(data["cantidad_calculada"], 25.0)
        self.assertEqual(data["presentacion_snapshot"], 4.0)

        linea.refresh_from_db()
        self.assertEqual(linea.producto_id, prod_b.pk)
        self.assertEqual(linea.cantidad_calculada, Decimal("25.000000"))
        self.assertEqual(linea.presentacion_snapshot, Decimal("4"))


# ── Test 3: Producto sin cantidad_presentacion → 422, sin cambio ────────────

class SinCantidadPresentacionTest(_Base):

    def test_retorna_422_y_no_guarda_producto(self):
        comp = _crear_componente(
            self.subsistema,
            codigo="comp_dif",
            formula_texto="area_m2 / pres",
            requiere_presentacion_producto=True,
            variable_presentacion_producto="pres",
            categoria=self.categoria,
        )
        linea = _crear_linea(self.ps, comp)
        producto = _crear_producto(self.categoria, cantidad_presentacion=None)

        resp = self._post(linea.pk, {"producto_id": producto.pk})
        data = self._json(resp)

        self.assertEqual(resp.status_code, 422)
        self.assertIn("error", data)

        linea.refresh_from_db()
        self.assertIsNone(linea.producto_id, "El producto no debe quedar guardado tras el error")
        self.assertTrue(linea.pendiente_producto)
        self.assertIsNone(linea.cantidad_calculada)


# ── Test 4: Error de fórmula → 422, rollback completo ───────────────────────

class ErrorFormulaRollbackTest(_Base):

    def test_formula_invalida_no_guarda_producto(self):
        comp = _crear_componente(
            self.subsistema,
            codigo="comp_dif",
            # Fórmula que falla aunque pres sea válido (variable inexistente en contexto)
            formula_texto="variable_inexistente / pres",
            requiere_presentacion_producto=True,
            variable_presentacion_producto="pres",
            categoria=self.categoria,
        )
        linea = _crear_linea(self.ps, comp)
        producto = _crear_producto(self.categoria, cantidad_presentacion=Decimal("5"))

        resp = self._post(linea.pk, {"producto_id": producto.pk})
        data = self._json(resp)

        self.assertEqual(resp.status_code, 422)
        self.assertIn("error", data)

        linea.refresh_from_db()
        self.assertIsNone(linea.producto_id, "Rollback: producto no debe quedar asignado")
        self.assertIsNone(linea.cantidad_calculada)
        self.assertTrue(linea.pendiente_producto)


# ── Test 5: Componente normal — flujo preservado ─────────────────────────────

class ComponenteNormalTest(_Base):

    def test_asignacion_normal_no_toca_pendiente_producto(self):
        comp = _crear_componente(
            self.subsistema,
            codigo="comp_normal",
            formula_texto="area_m2 * 2",
            requiere_presentacion_producto=False,
            categoria=self.categoria,
        )
        linea = _crear_linea(
            self.ps, comp,
            pendiente_producto=False,
            cantidad_calculada=Decimal("200"),
        )
        producto = _crear_producto(self.categoria)

        resp = self._post(linea.pk, {"producto_id": producto.pk})
        data = self._json(resp)

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertFalse(data["pendiente_producto"])
        # cantidad_calculada no cambia (no es diferido)
        self.assertEqual(data["cantidad_calculada"], 200.0)
        self.assertIsNone(data["presentacion_snapshot"])
        self.assertEqual(data["dependientes"], [])

        linea.refresh_from_db()
        self.assertEqual(linea.producto_id, producto.pk)
        self.assertFalse(linea.pendiente_producto)
        self.assertEqual(linea.cantidad_calculada, Decimal("200.000000"))


# ── Test 6: Retiro de producto (DELETE) en componente diferido ───────────────

class RetiroProductoTest(_Base):

    def test_delete_resetea_cantidad_y_pendiente(self):
        comp = _crear_componente(
            self.subsistema,
            codigo="comp_dif",
            formula_texto="area_m2 / pres",
            requiere_presentacion_producto=True,
            variable_presentacion_producto="pres",
            categoria=self.categoria,
        )
        producto = _crear_producto(self.categoria, cantidad_presentacion=Decimal("5"))
        linea = _crear_linea(
            self.ps, comp,
            pendiente_producto=False,
            cantidad_calculada=Decimal("20"),
            presentacion_snapshot=Decimal("5"),
            producto=producto,
        )

        resp = self._delete(linea.pk)
        data = self._json(resp)

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertTrue(data["producto_retirado"])
        self.assertIsNone(data["cantidad_calculada"])
        self.assertTrue(data["pendiente_producto"])
        self.assertIsNone(data["presentacion_snapshot"])
        self.assertEqual(data["dependientes"], [])

        linea.refresh_from_db()
        self.assertIsNone(linea.producto_id)
        self.assertIsNone(linea.cantidad_calculada)
        self.assertTrue(linea.pendiente_producto)


# ── Test 7: Invalidación de dependientes tras retiro ────────────────────────

class InvalidacionDependientesTest(_Base):

    def test_delete_invalida_lineas_dependientes(self):
        comp_a = _crear_componente(
            self.subsistema,
            codigo="comp_a",
            formula_texto="area_m2 / pres",
            requiere_presentacion_producto=True,
            variable_presentacion_producto="pres",
            variable_salida="val_a",
            categoria=self.categoria,
            orden=1,
        )
        comp_b = _crear_componente(
            self.subsistema,
            codigo="comp_b",
            formula_texto="val_a * 3",
            requiere_presentacion_producto=False,
            categoria=self.categoria,
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

        resp = self._delete(linea_a.pk)
        data = self._json(resp)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(data["dependientes"]), 1)
        dep = data["dependientes"][0]
        self.assertEqual(dep["componente_codigo"], "comp_b")
        self.assertIsNone(dep["cantidad_calculada"])
        self.assertTrue(dep["pendiente_producto"])

        linea_b.refresh_from_db()
        self.assertIsNone(linea_b.cantidad_calculada)
        self.assertTrue(linea_b.pendiente_producto)


# ── Test 8: Bloqueo por APU aprobado ────────────────────────────────────────

class BloqueoAPUTest(_Base):

    def setUp(self):
        super().setUp()
        from apps.presupuestos.models import APUProyecto
        from apps.common.choices import TipoAPU
        from django.utils import timezone

        self.apu = APUProyecto.objects.create(
            proyecto_sistema=self.ps,
            tipo_apu=TipoAPU.MATERIALES,
            fecha_aprobacion=timezone.now(),
        )
        comp = _crear_componente(self.subsistema, codigo="comp_blq", categoria=self.categoria)
        self.linea = _crear_linea(self.ps, comp)
        self.producto = _crear_producto(self.categoria)

    def test_post_bloqueado_retorna_403(self):
        resp = self._post(self.linea.pk, {"producto_id": self.producto.pk})
        self.assertEqual(resp.status_code, 403)
        data = self._json(resp)
        self.assertIn("error", data)

    def test_delete_bloqueado_retorna_403(self):
        from apps.presupuestos.models import DespieceLinea
        self.linea.producto = self.producto
        self.linea.save(update_fields=["producto"])

        resp = self._delete(self.linea.pk)
        self.assertEqual(resp.status_code, 403)


# ── Test 9: JSON con cantidad_calculada=null ─────────────────────────────────

class JSONNullCantidadTest(_Base):

    def test_delete_diferido_retorna_null_en_cantidad(self):
        """El JSON de retiro de un diferido tiene cantidad_calculada: null (no 0)."""
        comp = _crear_componente(
            self.subsistema,
            codigo="comp_dif",
            formula_texto="area_m2 / pres",
            requiere_presentacion_producto=True,
            variable_presentacion_producto="pres",
            categoria=self.categoria,
        )
        producto = _crear_producto(self.categoria, cantidad_presentacion=Decimal("5"))
        linea = _crear_linea(
            self.ps, comp,
            pendiente_producto=False,
            cantidad_calculada=Decimal("20"),
            producto=producto,
        )

        resp = self._delete(linea.pk)
        raw = json.loads(resp.content)

        # Debe ser None (null en JSON), NO 0
        self.assertIsNone(raw["cantidad_calculada"])
        self.assertTrue(raw["pendiente_producto"])
