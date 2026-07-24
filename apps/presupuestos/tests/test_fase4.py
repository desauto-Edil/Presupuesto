"""
Tests Fase 4 — Interfaz de configuración del subsistema y bloqueo del APU.

Cubre los 12 escenarios requeridos:
  1.  Renderizado de nuevos campos en subsistema_form (checkbox + variable).
  2.  Fila nueva serializa requiere_presentacion_producto y variable_presentacion_producto.
  3.  Validación: checkbox activo y variable vacía → error de servicio (mensaje de advertencia).
  4.  Campo variable_presentacion_producto oculto/visible según checkbox (servicio acepta ambos estados).
  5.  AJAX: asignación de producto actualiza cantidad_calculada en respuesta JSON.
  6.  AJAX: dependientes se actualizan en respuesta JSON.
  7.  Cantidad None se representa como — en el template GET.
  8.  DELETE retira producto con CSRF correcto (200 + ok=True).
  9.  Error 422 devuelve error visible en respuesta JSON.
 10.  APUGenerarView bloquea generación cuando hay pendiente_producto=True.
 11.  APUEnviarRevisionView y APUAprobarModalidadView bloquean con pendiente_producto=True.
 12.  pendiente_seleccion no bloquea la generación de APU (comportamiento existente preservado).
"""
from __future__ import annotations

import json
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse


# ── Helpers ──────────────────────────────────────────────────────────────────

_seq = 0


def _uniq(prefix: str) -> str:
    global _seq
    _seq += 1
    return f"{prefix}_{_seq}"


def _cfg_usuario(rol: str = "PRESUPUESTOS"):
    from apps.configuracion.models import ConfiguracionSistema
    return ConfiguracionSistema.objects.create(
        email=f"{_uniq('usr')}@test.com",
        nombre_completo="Usuario Test",
        rol=rol,
        activo=True,
    )


def _crear_sistema():
    from apps.ingenieria.models import Sistema
    from apps.common.choices import LineaNegocio, TipoSistema
    return Sistema.objects.create(
        codigo=_uniq("SF4"), nombre="Sistema F4",
        linea_negocio=LineaNegocio.CUBIERTAS,
        tipo_sistema=TipoSistema.CONSTRUCTIVO,
    )


def _crear_subsistema(sistema):
    from apps.ingenieria.models import Subsistema
    return Subsistema.objects.create(
        sistema=sistema, codigo=_uniq("SUF4"), nombre="Sub F4"
    )


def _crear_categoria():
    from apps.catalogos.models import CategoriaProducto
    return CategoriaProducto.objects.create(nombre=_uniq("Cat F4"))


def _crear_componente(subsistema, categoria=None, **kw):
    from apps.ingenieria.models import ComponenteSubsistema
    d = dict(
        subsistema=subsistema,
        codigo=_uniq("comp_f4"),
        nombre="Comp F4",
        formula_texto="x * 1",
        orden=1,
    )
    if categoria:
        d["categoria"] = categoria
    d.update(kw)
    return ComponenteSubsistema.objects.create(**d)


def _crear_proyecto():
    from apps.comercial.models import Proyecto, TipoProyecto
    tipo = TipoProyecto.objects.first() or TipoProyecto.objects.create(nombre="Tipo F4")
    return Proyecto.objects.create(consecutivo=_uniq("P-F4"), nombre="Proy F4", tipo_proyecto=tipo)


def _crear_ps(proyecto, sistema, subsistema, params=None):
    from apps.presupuestos.models import ProyectoSistema
    return ProyectoSistema.objects.create(
        proyecto=proyecto,
        sistema=sistema,
        subsistema=subsistema,
        parametros_entrada=params or {"x": "10"},
    )


def _crear_linea(ps, comp, pendiente=True, **kw):
    from apps.presupuestos.models import DespieceLinea
    d = dict(
        proyecto=ps.proyecto,
        proyecto_sistema=ps,
        componente_codigo=comp.codigo,
        pendiente_producto=pendiente,
        cantidad_calculada=None if pendiente else Decimal("5.0"),
    )
    d.update(kw)
    return DespieceLinea.objects.create(**d)


def _crear_producto(categoria, cantidad_presentacion=None):
    from apps.catalogos.models import Producto, UnidadMedida
    unidad = UnidadMedida.objects.first() or UnidadMedida.objects.create(
        codigo=_uniq("UND"), nombre="Unidad"
    )
    return Producto.objects.create(
        nombre=_uniq("Prod F4"),
        codigo=_uniq("PF4"),
        categoria=categoria,
        unidad=unidad,
        activo=True,
        cantidad_presentacion=cantidad_presentacion,
    )


def _crear_apu(ps):
    from apps.presupuestos.models import APUProyecto
    return APUProyecto.objects.create(
        proyecto_sistema=ps,
        nombre=f"APU {ps.pk}",
    )


def _set_session(client: Client, usuario_id: int, rol: str = "PRESUPUESTOS"):
    session = client.session
    session["usuario_id"] = usuario_id
    session["rol"] = rol
    session.save()


# ── Clase base ────────────────────────────────────────────────────────────────

class _Base(TestCase):
    def setUp(self):
        self.usuario = _cfg_usuario("PRESUPUESTOS")
        self.sistema = _crear_sistema()
        self.subsistema = _crear_subsistema(self.sistema)
        self.categoria = _crear_categoria()
        self.proyecto = _crear_proyecto()
        self.ps = _crear_ps(self.proyecto, self.sistema, self.subsistema)

        self.user = User.objects.create_user(username=_uniq("u"), password="x")
        self.client.login(username=self.user.username, password="x")
        _set_session(self.client, self.usuario.pk, "PRESUPUESTOS")


# ══════════════════════════════════════════════════════════════════════════════
# Grupo 1 — Template y servicio subsistema_form
# ══════════════════════════════════════════════════════════════════════════════

class TestSubsistemaFormRenderizado(_Base):
    """Test 1 — Renderizado de nuevos campos en subsistema_form."""

    def test_subsistema_form_contiene_campos_presentacion(self):
        url = reverse("ingenieria:subsistema_update", args=[self.subsistema.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("comp-f-requiere-pres", html)
        self.assertIn("comp-f-var-pres", html)
        self.assertIn("Cálculo diferido", html)


class TestGuardarComponenteConPresentacion(_Base):
    """Tests 2 y 4 — Guardar componente con requiere_presentacion_producto."""

    def _post_subsistema(self, componente_data: dict):
        subconjuntos = [
            {"nombre": "SC1", "descripcion": "", "componentes": [componente_data]}
        ]
        url = reverse("ingenieria:subsistema_update", args=[self.subsistema.pk])
        return self.client.post(url, {
            "codigo": self.subsistema.codigo,
            "nombre": self.subsistema.nombre,
            "sistema": self.sistema.pk,
            "subconjuntos_json": json.dumps(subconjuntos),
            "variables_json": "[]",
        }, follow=True)

    def test_guarda_componente_con_requiere_presentacion(self):
        """Test 2 — Datos nuevos se persisten correctamente en ComponenteSubsistema."""
        from apps.ingenieria.models import ComponenteSubsistema
        resp = self._post_subsistema({
            "codigo": "comp_test",
            "nombre": "Comp Test",
            "formula_texto": "x * 1",
            "variable_salida": "",
            "unidad": "",
            "variable_referencia_apu": "",
            "unidad_apu": "",
            "requiere_presentacion_producto": True,
            "variable_presentacion_producto": "var_pres",
        })
        comp = ComponenteSubsistema.objects.filter(
            subsistema=self.subsistema, nombre="Comp Test"
        ).first()
        self.assertIsNotNone(comp, "El componente debería haberse creado")
        self.assertTrue(comp.requiere_presentacion_producto)
        self.assertEqual(comp.variable_presentacion_producto, "var_pres")

    def test_guarda_componente_sin_requiere_presentacion(self):
        """Test 4 (parcial) — Componente sin checkbox: campo ignorado silenciosamente."""
        from apps.ingenieria.models import ComponenteSubsistema
        resp = self._post_subsistema({
            "codigo": "comp_normal",
            "nombre": "Comp Normal",
            "formula_texto": "x * 2",
            "variable_salida": "",
            "unidad": "",
            "variable_referencia_apu": "",
            "unidad_apu": "",
            "requiere_presentacion_producto": False,
            "variable_presentacion_producto": "",
        })
        comp = ComponenteSubsistema.objects.filter(
            subsistema=self.subsistema, nombre="Comp Normal"
        ).first()
        self.assertIsNotNone(comp)
        self.assertFalse(comp.requiere_presentacion_producto)
        self.assertEqual(comp.variable_presentacion_producto, "")


class TestValidacionRequierePresentacionSinVariable(_Base):
    """Test 3 — Checkbox activo y variable vacía → mensaje de advertencia."""

    def test_guardar_sin_variable_muestra_warning(self):
        from apps.ingenieria.models import ComponenteSubsistema
        subconjuntos = [{
            "nombre": "SC1",
            "descripcion": "",
            "componentes": [{
                "codigo": "comp_err",
                "nombre": "Comp Error",
                "formula_texto": "x * 1",
                "variable_salida": "",
                "unidad": "",
                "variable_referencia_apu": "",
                "unidad_apu": "",
                "requiere_presentacion_producto": True,
                "variable_presentacion_producto": "",
            }],
        }]
        url = reverse("ingenieria:subsistema_update", args=[self.subsistema.pk])
        resp = self.client.post(url, {
            "codigo": self.subsistema.codigo,
            "nombre": self.subsistema.nombre,
            "sistema": self.sistema.pk,
            "subconjuntos_json": json.dumps(subconjuntos),
            "variables_json": "[]",
        }, follow=True)
        mensajes = [str(m) for m in resp.context["messages"]]
        self.assertTrue(
            any("variable de presentación" in m or "falta" in m.lower() for m in mensajes),
            f"Se esperaba advertencia sobre variable vacía. Mensajes: {mensajes}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# Grupo 2 — AJAX assign/delete API (Tests 5, 6, 7, 8, 9)
# ══════════════════════════════════════════════════════════════════════════════

class TestAJAXAsignarProducto(_Base):
    """Tests 5, 6, 8, 9 — Respuesta JSON del endpoint de asignación."""

    URL = "presupuestos:despiece_api_asignar_producto"

    def setUp(self):
        super().setUp()
        self.comp = _crear_componente(
            self.subsistema, self.categoria,
            requiere_presentacion_producto=True,
            variable_presentacion_producto="var_pres",
            formula_texto="var_pres * 2",
        )
        self.linea = _crear_linea(self.ps, self.comp, categoria_producto=self.categoria)
        self.producto = _crear_producto(self.categoria, cantidad_presentacion=Decimal("10"))

    def _post(self, pk, body):
        return self.client.post(
            reverse(self.URL, args=[pk]),
            data=json.dumps(body),
            content_type="application/json",
        )

    def _delete(self, pk):
        return self.client.delete(
            reverse(self.URL, args=[pk]),
            content_type="application/json",
        )

    def test_asignacion_devuelve_cantidad_calculada(self):
        """Test 5 — POST devuelve cantidad_calculada actualizada."""
        resp = self._post(self.linea.pk, {"producto_id": self.producto.pk})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data.get("ok"))
        self.assertIn("cantidad_calculada", data)
        self.assertFalse(data["pendiente_producto"])

    def test_asignacion_devuelve_dependientes(self):
        """Test 6 — Respuesta incluye clave dependientes (lista, puede estar vacía)."""
        resp = self._post(self.linea.pk, {"producto_id": self.producto.pk})
        data = json.loads(resp.content)
        self.assertIn("dependientes", data)
        self.assertIsInstance(data["dependientes"], list)

    def test_delete_retira_producto(self):
        """Test 8 — DELETE retira producto y devuelve ok=True."""
        self._post(self.linea.pk, {"producto_id": self.producto.pk})
        resp = self._delete(self.linea.pk)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data.get("ok"))
        self.assertTrue(data.get("pendiente_producto"))

    def test_error_422_devuelve_mensaje(self):
        """Test 9 — Producto sin cantidad_presentacion → 422 con error legible."""
        prod_sin_pres = _crear_producto(self.categoria, cantidad_presentacion=None)
        resp = self._post(self.linea.pk, {"producto_id": prod_sin_pres.pk})
        self.assertEqual(resp.status_code, 422)
        data = json.loads(resp.content)
        self.assertIn("error", data)
        self.assertIsInstance(data["error"], str)
        self.assertGreater(len(data["error"]), 0)


# ══════════════════════════════════════════════════════════════════════════════
# Grupo 3 — Template GET: cantidad None → —  (Test 7)
# ══════════════════════════════════════════════════════════════════════════════

class TestGetPendientesProductoTemplate(_Base):
    """Test 7 — GET APUGenerarView: cantidad None se muestra como —."""

    def setUp(self):
        super().setUp()
        self.comp = _crear_componente(
            self.subsistema, self.categoria,
            requiere_presentacion_producto=True,
            variable_presentacion_producto="var_pres",
            formula_texto="var_pres * 1",
        )
        self.linea = _crear_linea(
            self.ps, self.comp,
            pendiente=True,
            cantidad_calculada=None,
            categoria_producto=self.categoria,
        )

    def test_get_muestra_guion_para_cantidad_none(self):
        url = reverse("presupuestos:apu_generar", args=[self.ps.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("—", html)
        self.assertIn(self.linea.componente_codigo, html)


# ══════════════════════════════════════════════════════════════════════════════
# Grupo 4 — Bloqueo APU (Tests 10, 11, 12)
# ══════════════════════════════════════════════════════════════════════════════

class TestAPUBloqueoGeneracion(_Base):
    """Test 10 — APUGenerarView.post bloquea cuando hay pendiente_producto=True."""

    def setUp(self):
        super().setUp()
        self.comp = _crear_componente(self.subsistema, self.categoria)
        self.linea = _crear_linea(
            self.ps, self.comp,
            pendiente=True,
            categoria_producto=self.categoria,
        )

    def test_post_apu_generar_redirige_a_get_cuando_hay_pendientes(self):
        url = reverse("presupuestos:apu_generar", args=[self.ps.pk])
        resp = self.client.post(url)
        self.assertRedirects(resp, url, fetch_redirect_response=False)

    def test_post_apu_generar_sin_pendientes_genera_apu(self):
        self.linea.pendiente_producto = False
        self.linea.cantidad_calculada = Decimal("5.0")
        self.linea.save()
        url = reverse("presupuestos:apu_generar", args=[self.ps.pk])
        resp = self.client.post(url, follow=True)
        from apps.presupuestos.models import APUProyecto
        self.assertTrue(
            APUProyecto.objects.filter(proyecto_sistema=self.ps).exists(),
            "Debería haberse generado un APU.",
        )


class TestAPUBloqueoEnviarRevision(_Base):
    """Test 11a — APUEnviarRevisionView bloquea con pendiente_producto=True."""

    def setUp(self):
        super().setUp()
        self.comp = _crear_componente(self.subsistema, self.categoria)
        linea = _crear_linea(
            self.ps, self.comp,
            pendiente=True,
            categoria_producto=self.categoria,
        )
        self.apu = _crear_apu(self.ps)

    def test_enviar_revision_bloqueado(self):
        url = reverse("presupuestos:apu_enviar_revision", args=[self.apu.pk])
        resp = self.client.post(url, follow=True)
        mensajes = [str(m) for m in resp.context["messages"]]
        self.assertTrue(
            any("pendiente" in m.lower() or "producto" in m.lower() for m in mensajes),
            f"Se esperaba mensaje de bloqueo por pendiente_producto. Mensajes: {mensajes}",
        )


class TestAPUBloqueoAprobar(_Base):
    """Test 11b — APUAprobarModalidadView bloquea con pendiente_producto=True."""

    def setUp(self):
        super().setUp()
        self.comp = _crear_componente(self.subsistema, self.categoria)
        _crear_linea(
            self.ps, self.comp,
            pendiente=True,
            categoria_producto=self.categoria,
        )
        self.apu = _crear_apu(self.ps)
        self.apu.revisor = self.usuario
        self.apu.save(update_fields=["revisor"])
        # ADMINISTRADOR para pasar el gate de puede_aprobar_apu
        _set_session(self.client, self.usuario.pk, "ADMINISTRADOR")

    def test_aprobar_modalidad_bloqueado(self):
        url = reverse("presupuestos:apu_aprobar_modalidad", args=[self.apu.pk])
        resp = self.client.post(url, {"modalidad_aiu": "1"}, follow=True)
        mensajes = [str(m) for m in resp.context["messages"]]
        self.assertTrue(
            any("pendiente" in m.lower() or "producto" in m.lower() for m in mensajes),
            f"Se esperaba mensaje de bloqueo por pendiente_producto. Mensajes: {mensajes}",
        )
        from apps.presupuestos.models import APUProyecto
        self.apu.refresh_from_db()
        self.assertIsNone(self.apu.fecha_aprobacion, "No debe quedar aprobado.")


class TestPendienteSeleccionNoBloquea(_Base):
    """Test 12 — pendiente_seleccion=True no bloquea la generación de APU."""

    def setUp(self):
        super().setUp()
        self.comp = _crear_componente(self.subsistema, self.categoria)
        # Línea con pendiente_seleccion (tiene categoría pero no producto y
        # pendiente_producto=False — el flujo original omite estas líneas en el APU).
        from apps.presupuestos.models import DespieceLinea
        self.linea = DespieceLinea.objects.create(
            proyecto=self.ps.proyecto,
            proyecto_sistema=self.ps,
            componente_codigo=self.comp.codigo,
            categoria_producto=self.categoria,
            producto=None,
            pendiente_producto=False,
            cantidad_calculada=Decimal("3.0"),
        )

    def test_apu_generar_no_bloqueado_por_pendiente_seleccion(self):
        url = reverse("presupuestos:apu_generar", args=[self.ps.pk])
        resp = self.client.post(url)
        # pendiente_seleccion no bloquea — la vista redirige al APU detail, no vuelve al GET.
        self.assertNotEqual(resp.status_code, 200, "No debería renderizar la vista GET.")
        # Verifica que se redirigió hacia el APU detail (no hacia la propia URL de pendientes).
        location = resp.get("Location", "")
        self.assertNotEqual(location, url)
