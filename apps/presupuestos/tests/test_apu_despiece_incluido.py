"""
Tests mínimos para APUDespieceIncluido y APUConsolidadoOrigen.

Verifica:
  - Importación correcta desde apps.presupuestos.models
  - db_table y unique_together correctos
  - Creación y consulta básica (APUDespieceIncluido)
  - Restricción unique_together (APUDespieceIncluido)
  - Creación y consulta básica (APUConsolidadoOrigen)
  - Restricción unique_together (APUConsolidadoOrigen)
  - CalculoConsumoLinea importable
"""
from __future__ import annotations

from django.db import IntegrityError
from django.test import TestCase


# ---------------------------------------------------------------------------
# Helpers de fixture
# ---------------------------------------------------------------------------

def _crear_proyecto():
    from apps.comercial.models import Proyecto, TipoProyecto
    tipo = TipoProyecto.objects.first() or TipoProyecto.objects.create(nombre="Tipo Test ADI")
    return Proyecto.objects.create(
        consecutivo="P-ADI-TEST",
        nombre="Proyecto Test APUDespieceIncluido",
        tipo_proyecto=tipo,
    )


def _crear_sistema_subsistema():
    from apps.ingenieria.models import Sistema, Subsistema
    from apps.common.choices import LineaNegocio, TipoSistema
    sistema = Sistema.objects.create(
        codigo="SIS_ADI",
        nombre="Sistema ADI",
        linea_negocio=LineaNegocio.CUBIERTAS,
        tipo_sistema=TipoSistema.CONSTRUCTIVO,
    )
    subsistema = Subsistema.objects.create(
        sistema=sistema, codigo="SUB_ADI", nombre="Subsistema ADI",
    )
    return sistema, subsistema


def _crear_ps(proyecto, sistema, subsistema):
    from apps.presupuestos.models import ProyectoSistema
    return ProyectoSistema.objects.create(
        proyecto=proyecto, sistema=sistema, subsistema=subsistema,
        parametros_entrada={},
    )


def _crear_apu(nombre="APU Test", ps=None):
    from apps.presupuestos.models import APUProyecto
    return APUProyecto.objects.create(nombre=nombre, proyecto_sistema=ps)


def _crear_despiece(proyecto, subsistema):
    from apps.ingenieria.models import DespieceMaestro
    return DespieceMaestro.objects.create(
        proyecto=proyecto,
        subsistema=subsistema,
        estado=DespieceMaestro.GUARDADO,
    )


# ---------------------------------------------------------------------------
# Tests de importación y metadatos
# ---------------------------------------------------------------------------

class ImportacionTest(TestCase):
    def test_importacion_apu_despiece_incluido(self):
        from apps.presupuestos.models import APUDespieceIncluido
        self.assertEqual(APUDespieceIncluido._meta.db_table, "apu_despieces_incluidos")

    def test_importacion_apu_consolidado_origen(self):
        from apps.presupuestos.models import APUConsolidadoOrigen
        self.assertEqual(APUConsolidadoOrigen._meta.db_table, "apu_consolidado_origenes")

    def test_importacion_calculo_consumo_linea(self):
        from apps.presupuestos.models import CalculoConsumoLinea
        self.assertEqual(CalculoConsumoLinea._meta.db_table, "calculo_consumo_lineas")

    def test_unique_together_apu_despiece(self):
        from apps.presupuestos.models import APUDespieceIncluido
        ut = APUDespieceIncluido._meta.unique_together
        self.assertIn(("apu", "despiece_maestro"), ut)

    def test_unique_together_apu_consolidado(self):
        from apps.presupuestos.models import APUConsolidadoOrigen
        ut = APUConsolidadoOrigen._meta.unique_together
        self.assertIn(("apu_consolidado", "apu_origen"), ut)

    def test_tipo_apu_consolidacion_choices(self):
        from apps.presupuestos.models import APUProyecto
        self.assertEqual(APUProyecto.TipoAPUConsolidacion.INDIVIDUAL, "INDIVIDUAL")
        self.assertEqual(APUProyecto.TipoAPUConsolidacion.CONSOLIDADO, "CONSOLIDADO")


# ---------------------------------------------------------------------------
# Tests de APUDespieceIncluido
# ---------------------------------------------------------------------------

class APUDespieceIncluidoTest(TestCase):
    def setUp(self):
        self.proyecto = _crear_proyecto()
        self.sistema, self.sub = _crear_sistema_subsistema()
        self.ps = _crear_ps(self.proyecto, self.sistema, self.sub)
        self.apu = _crear_apu(ps=self.ps)
        self.dm = _crear_despiece(self.proyecto, self.sub)

    def test_crear_y_consultar(self):
        from apps.presupuestos.models import APUDespieceIncluido
        inc = APUDespieceIncluido.objects.create(
            apu=self.apu,
            despiece_maestro=self.dm,
            orden=0,
            activo=True,
        )
        from_db = APUDespieceIncluido.objects.get(pk=inc.pk)
        self.assertEqual(from_db.apu, self.apu)
        self.assertEqual(from_db.despiece_maestro, self.dm)
        self.assertTrue(from_db.activo)

    def test_relacion_inversa_despieces_incluidos(self):
        from apps.presupuestos.models import APUDespieceIncluido
        APUDespieceIncluido.objects.create(
            apu=self.apu, despiece_maestro=self.dm, orden=0,
        )
        self.assertEqual(self.apu.despieces_incluidos.count(), 1)

    def test_relacion_inversa_apus_incluidos(self):
        from apps.presupuestos.models import APUDespieceIncluido
        APUDespieceIncluido.objects.create(
            apu=self.apu, despiece_maestro=self.dm, orden=0,
        )
        self.assertEqual(self.dm.apus_incluidos.count(), 1)

    def test_unique_together_constraint(self):
        from apps.presupuestos.models import APUDespieceIncluido
        APUDespieceIncluido.objects.create(
            apu=self.apu, despiece_maestro=self.dm, orden=0,
        )
        with self.assertRaises(IntegrityError):
            APUDespieceIncluido.objects.create(
                apu=self.apu, despiece_maestro=self.dm, orden=1,
            )

    def test_filtro_activo(self):
        from apps.presupuestos.models import APUDespieceIncluido
        APUDespieceIncluido.objects.create(
            apu=self.apu, despiece_maestro=self.dm, orden=0, activo=False,
        )
        self.assertEqual(
            APUDespieceIncluido.objects.filter(apu=self.apu, activo=True).count(), 0
        )


# ---------------------------------------------------------------------------
# Tests de APUConsolidadoOrigen
# ---------------------------------------------------------------------------

class APUConsolidadoOrigenTest(TestCase):
    def setUp(self):
        self.proyecto = _crear_proyecto()
        self.sistema, self.sub = _crear_sistema_subsistema()
        self.ps = _crear_ps(self.proyecto, self.sistema, self.sub)
        self.apu_individual = _crear_apu(nombre="APU Individual", ps=self.ps)
        self.apu_consolidado = _crear_apu(nombre="APU Consolidado")

    def test_crear_y_consultar(self):
        from apps.presupuestos.models import APUConsolidadoOrigen
        origen = APUConsolidadoOrigen.objects.create(
            apu_consolidado=self.apu_consolidado,
            apu_origen=self.apu_individual,
            orden=0,
            incluido_en_pdf_cliente=True,
        )
        from_db = APUConsolidadoOrigen.objects.get(pk=origen.pk)
        self.assertEqual(from_db.apu_consolidado, self.apu_consolidado)
        self.assertEqual(from_db.apu_origen, self.apu_individual)

    def test_relacion_inversa_origenes_consolidado(self):
        from apps.presupuestos.models import APUConsolidadoOrigen
        APUConsolidadoOrigen.objects.create(
            apu_consolidado=self.apu_consolidado,
            apu_origen=self.apu_individual,
            orden=0,
        )
        self.assertEqual(self.apu_consolidado.origenes_consolidado.count(), 1)

    def test_unique_together_constraint(self):
        from apps.presupuestos.models import APUConsolidadoOrigen
        APUConsolidadoOrigen.objects.create(
            apu_consolidado=self.apu_consolidado,
            apu_origen=self.apu_individual,
            orden=0,
        )
        with self.assertRaises(IntegrityError):
            APUConsolidadoOrigen.objects.create(
                apu_consolidado=self.apu_consolidado,
                apu_origen=self.apu_individual,
                orden=1,
            )
