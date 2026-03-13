"""
services.py — Capa de servicios del motor de presupuestos.

Contiene:
  1. DespieceService — algoritmos de despiece paramétrico (PowerGrip Universal 7 y Plus TPO)
  2. DependenciaService — inyección automática de dependencias
  3. APUService — motor de APU automático (Nivel 4)
  4. ProyectoService — orquestador del flujo de estados
"""

from __future__ import annotations

import math
import logging
from decimal import Decimal
from typing import Dict, List, Optional

from django.db import transaction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DESPIECE SERVICE
# ---------------------------------------------------------------------------

class DespieceService:
    """
    Motor de despiece paramétrico para el sistema PowerGrip.

    Soporta dos variantes:
      - Universal 7  (POWERGRIP-U7)
      - Plus TPO     (POWERGRIP-PLUS)

    Algoritmo:
      1. Obtener todas las ReglaCalculo activas del subsistema.
      2. Construir el contexto de variables.
      3. Evaluar cada regla en orden de ejecución.
      4. Registrar / actualizar DespieceLinea con cantidad calculada.
      5. Capturar precio_snapshot desde ProductoProveedor.
    """

    def __init__(self, proyecto_sistema):
        from .models import ProyectoSistema
        self.ps: ProyectoSistema = proyecto_sistema

    @transaction.atomic
    def ejecutar(self) -> List[dict]:
        """
        Ejecuta el despiece completo y retorna la lista de resultados.
        """
        from .models import ReglaCalculo, DespieceLinea

        subsistema = self.ps.subsistema
        if not subsistema:
            raise ValueError("El ProyectoSistema no tiene subsistema asignado.")

        reglas = ReglaCalculo.objects.filter(
            subsistema=subsistema, activa=True
        ).select_related("producto").order_by("orden_ejecucion")

        if not reglas.exists():
            logger.warning("No hay reglas de cálculo para subsistema %s", subsistema.codigo)
            return []

        contexto = self.ps.get_contexto()
        resultados = []

        for regla in reglas:
            try:
                cantidad = regla.evaluar(contexto)
            except ValueError as exc:
                logger.error("Error evaluando regla %s: %s", regla.codigo, exc)
                continue

            # Actualizar contexto con resultado para reglas derivadas
            # Usamos el código de la regla como clave primaria del contexto;
            # si hay producto concreto, también exponemos sus identificadores;
            # si la regla tiene variable_salida, la exponemos como alias semántico
            # (ej. Limpiador → Estopa puede usar "Limpiador / 2" directamente).
            contexto[regla.codigo] = cantidad
            if regla.variable_salida:
                contexto[regla.variable_salida] = cantidad
            if regla.producto_id:
                contexto[regla.producto.codigo] = cantidad
                contexto[regla.producto.nombre.replace(" ", "_")] = cantidad

            # update_or_create usando la regla como clave principal
            defaults = {
                "regla":                   regla,
                "cantidad_calculada":      Decimal(str(round(cantidad, 6))),
                "es_dependencia_automatica": False,
            }
            if regla.producto_id:
                defaults["producto"]           = regla.producto
                defaults["categoria_producto"] = None
            elif regla.categoria_producto_id:
                defaults["categoria_producto"] = regla.categoria_producto

            linea, _ = DespieceLinea.objects.update_or_create(
                proyecto=self.ps.proyecto,
                proyecto_sistema=self.ps,
                regla=regla,
                defaults=defaults,
            )
            linea.capturar_precio()

            resultados.append({
                "producto_codigo": regla.producto.codigo if regla.producto_id else None,
                "producto_nombre": (
                    regla.producto.nombre if regla.producto_id
                    else f"[{regla.categoria_producto}]" if regla.categoria_producto_id
                    else "—"
                ),
                "regla_codigo":    regla.codigo,
                "cantidad":        round(cantidad, 4),
                "unidad": (
                    regla.producto.unidad.abreviatura if regla.producto_id else "—"
                ),
                "precio_snapshot": float(linea.precio_snapshot or 0),
                "pendiente":       linea.pendiente_seleccion,
            })

        return resultados

    # ------------------------------------------------------------------
    # PowerGrip Universal 7 — algoritmo explícito
    # ------------------------------------------------------------------
    @staticmethod
    def calcular_universal7(total_powergip: float) -> Dict[str, float]:
        """
        Cálculo hardcodeado (POWERGRIP-U7) como respaldo si no hay ReglaCalculo.
        Fórmulas según MATRIZ CORE:
          Fijaciones : (8 × Total_PowerGrip) × 1.01
          Limpiador  : ((Total_PowerGrip × 0.04) / 50) × 1.01   [0.2×0.2=0.04]
          Estopa     : Limpiador / 2
          Sellador   : ((Total_PowerGrip × 0.56) / 12) × 1.01
        """
        tp = total_powergip
        fijaciones = (8 * tp) * 1.01
        limpiador  = ((tp * 0.04) / 50) * 1.01
        estopa     = limpiador / 2
        sellador   = ((tp * 0.56) / 12) * 1.01

        return {
            "Fijaciones": round(fijaciones, 4),
            "Limpiador":  round(limpiador, 4),
            "Estopa":     round(estopa, 4),
            "Sellador":   round(sellador, 4),
        }

    # ------------------------------------------------------------------
    # PowerGrip Plus TPO — algoritmo explícito
    # ------------------------------------------------------------------
    @staticmethod
    def calcular_plus_tpo(total_powergip: float) -> Dict[str, float]:
        """
        Cálculo hardcodeado (POWERGRIP-PLUS) como respaldo.
        Fórmulas según MATRIZ CORE:
          Fijaciones : (9 × Total_PowerGrip) × 1.01
          Limpiador  : ((Total_PowerGrip × 0.09) / 50) × 1.01   [0.3×0.3=0.09]
          Estopa     : Limpiador / 2
          Sellador   : ((Total_PowerGrip × 1.16) / 36.1) × 1.01
        """
        tp = total_powergip
        fijaciones = (9 * tp) * 1.01
        limpiador  = ((tp * 0.09) / 50) * 1.01
        estopa     = limpiador / 2
        sellador   = ((tp * 1.16) / 36.1) * 1.01

        return {
            "Fijaciones": round(fijaciones, 4),
            "Limpiador":  round(limpiador, 4),
            "Estopa":     round(estopa, 4),
            "Sellador":   round(sellador, 4),
        }


# ---------------------------------------------------------------------------
# DEPENDENCIA SERVICE
# ---------------------------------------------------------------------------

class DependenciaService:
    """
    Inyecta automáticamente las dependencias obligatorias de un subsistema
    al momento de seleccionarlo en el despiece.
    """

    def __init__(self, proyecto_sistema):
        self.ps = proyecto_sistema

    @transaction.atomic
    def inyectar(self) -> List[dict]:
        """
        Llama a ProyectoSistema.inyectar_dependencias() y retorna
        una lista descriptiva de lo que se creó.
        """
        lineas = self.ps.inyectar_dependencias()
        resultado = []
        for l in lineas:
            if l.producto_id:
                resultado.append({
                    "producto_codigo": l.producto.codigo,
                    "producto_nombre": l.producto.nombre,
                    "unidad":          l.producto.unidad.abreviatura,
                    "automatica":      True,
                    "pendiente":       False,
                })
            else:
                resultado.append({
                    "producto_codigo": None,
                    "producto_nombre": f"[{l.categoria_producto}]" if l.categoria_producto_id else "—",
                    "unidad":          "—",
                    "automatica":      True,
                    "pendiente":       l.pendiente_seleccion,
                })
        return resultado

    def dependencias_del_subsistema(self) -> List[dict]:
        """
        Retorna lista de dependencias obligatorias del subsistema
        sin necesariamente crearlas (para preview en UI).
        """
        from .models import DependenciaTecnica
        if not self.ps.subsistema:
            return []
        deps = DependenciaTecnica.objects.filter(
            subsistema=self.ps.subsistema, obligatoria=True
        ).select_related("producto_dependiente__unidad", "categoria_producto")
        resultado = []
        for d in deps:
            if d.producto_dependiente_id:
                resultado.append({
                    "producto_codigo": d.producto_dependiente.codigo,
                    "producto_nombre": d.producto_dependiente.nombre,
                    "unidad":          d.producto_dependiente.unidad.abreviatura,
                    "tipo_regla":      d.tipo_regla,
                    "obligatoria":     d.obligatoria,
                    "pendiente":       False,
                })
            else:
                resultado.append({
                    "producto_codigo": None,
                    "producto_nombre": d.nombre or f"[{d.categoria_producto}]",
                    "unidad":          "—",
                    "tipo_regla":      d.tipo_regla,
                    "obligatoria":     d.obligatoria,
                    "pendiente":       True,
                })
        return resultado


# ---------------------------------------------------------------------------
# APU SERVICE
# ---------------------------------------------------------------------------

class APUService:
    """
    Motor de APU automático (Nivel 4).

    Genera APUProyecto + APULineas a partir de:
      - Las DespieceLineas del ProyectoSistema (materiales)
      - Las variables de entrada del proyecto (mano de obra, equipos, transporte)
      - La ConfiguracionAPU activa como valores predeterminados
    """

    def __init__(self, proyecto_sistema):
        from .models import APUProyecto, ConfiguracionAPU
        self.ps = proyecto_sistema
        self.cfg = ConfiguracionAPU.activa_o_default()

        self.apu, _ = APUProyecto.objects.get_or_create(
            proyecto_sistema=proyecto_sistema,
            defaults={
                "factor_venta_pct":       self.cfg.porcentaje_ganancia,
                "aiu_contratista_pct":    self.cfg.aiu_contratista,
                "margen_contratista_pct": self.cfg.margen_ganancia_contratista,
                "iva_pct":                proyecto_sistema.proyecto.iva_pct,
                "aplica_iva":             not proyecto_sistema.proyecto.aplica_exencion_iva,
            }
        )

    @transaction.atomic
    def generar_materiales(self) -> List[dict]:
        """
        Genera APULineas de tipo MATERIALES desde las DespieceLineas.
        Fórmulas (MATRIZ CORE — DETALLE APU / MATERIALES):
          rendimiento_2    = Total_PowerGrip / cantidad_materiales
          costo_unitario   = (cantidad_despiece / rendimiento_2) * precio * IVA_factor
          → simplificado:  costo_unitario = precio * IVA_factor
          costo_total      = rendimiento_2 * costo_unitario  = cantidad_despiece * precio * IVA
          valor_unitario   = costo_unitario * (1 + factor_venta%)
          valor_total      = rendimiento_2 * valor_unitario
        """
        from .models import APULinea, TipoAPU

        lineas_despiece = self.ps.despiece_lineas.select_related(
            "producto__unidad", "categoria_producto"
        )
        creadas = []

        for dl in lineas_despiece:
            # Líneas pendientes de selección no pueden incluirse en el APU
            if dl.pendiente_seleccion:
                logger.warning(
                    "Línea %s omitida del APU: aún no tiene producto asignado (categoría: %s).",
                    dl.pk, dl.categoria_producto,
                )
                continue

            nombre = dl.producto.nombre if dl.producto_id else "—"
            precio = float(dl.precio_snapshot or 0)
            cantidad = float(dl.cantidad_final)
            tp = float(self.ps.total_powergip or 1) or 1

            rendimiento = tp / cantidad if cantidad > 0 else 1.0

            apu_linea, _ = APULinea.objects.update_or_create(
                apu=self.apu,
                tipo=TipoAPU.MATERIALES,
                despiece_linea=dl,
                defaults={
                    "descripcion":       nombre,
                    "rendimiento":       Decimal(str(round(rendimiento, 6))),
                    "precio_referencia": Decimal(str(precio)),
                    "iva_aplicado":      self.apu.aplica_iva,
                    "editable":          False,
                }
            )
            apu_linea.calcular()
            creadas.append({
                "descripcion":     nombre,
                "rendimiento":     round(rendimiento, 4),
                "precio":          precio,
                "costo_unitario":  float(apu_linea.costo_unitario),
                "valor_unitario":  float(apu_linea.valor_unitario),
                "costo_total":     float(apu_linea.costo_total),
                "valor_total":     float(apu_linea.valor_total),
            })

        return creadas

    @transaction.atomic
    def generar_mano_obra(
        self,
        hya_dia: float = 0,
        cuadrilla_dia: float = 0,
        dotacion_dia: float = 0,
        proteccion_dia: float = 0,
    ) -> dict:
        """
        Genera APULineas de tipo MANO_DE_OBRA.
        Fórmulas (MATRIZ CORE — MANO DE OBRA):
          dias = Total_PowerGrip / (personas * 40)
          AIU  = aiu_contratista_pct / 100
          MG   = margen_contratista_pct / 100

          CU_hya       = (hya_dia * (rend + personas) * dias * AIU * MG) / Total_PowerGrip
          CU_cuadrilla = (cuadrilla_dia * personas * AIU * MG) / Total_PowerGrip
          CU_dotacion  = (dotacion_dia * (rend + personas) * dias * AIU * MG) / Total_PowerGrip
          CU_proteccion = (proteccion_dia * (rend + personas) * dias * AIU * MG) / Total_PowerGrip
        """
        from .models import APULinea, TipoAPU

        self.apu.calcular_tiempo()
        tp       = float(self.ps.total_powergip or 1) or 1
        personas = float(self.ps.cuadrilla_personas or 1) or 1
        dias     = float(self.apu.dias_trabajo or (tp / (personas * 40)))
        rend     = float(self.apu.rendimiento_und_dia or 0)
        aiu      = 1 + float(self.apu.aiu_contratista_pct) / 100
        mg       = 1 + float(self.apu.margen_contratista_pct) / 100

        items_mo = [
            ("HYA — Herramientas y andamios", hya_dia,        (hya_dia * (rend + personas) * dias * aiu * mg) / tp),
            ("Cuadrilla de instalación",      cuadrilla_dia,  (cuadrilla_dia * personas * aiu * mg) / tp),
            ("Dotación",                      dotacion_dia,   (dotacion_dia * (rend + personas) * dias * aiu * mg) / tp),
            ("Protección",                    proteccion_dia, (proteccion_dia * (rend + personas) * dias * aiu * mg) / tp),
        ]

        creadas = []
        for desc, precio_base, cu in items_mo:
            if precio_base <= 0:
                continue
            apu_linea, _ = APULinea.objects.update_or_create(
                apu=self.apu,
                tipo=TipoAPU.MANO_DE_OBRA,
                descripcion=desc,
                defaults={
                    "rendimiento":       Decimal("1"),
                    "precio_referencia": Decimal(str(round(cu, 6))),
                    "iva_aplicado":      False,
                    "editable":          True,
                }
            )
            apu_linea.calcular()
            creadas.append({"descripcion": desc, "costo_unitario": float(apu_linea.costo_unitario)})

        return {"mano_obra": creadas, "dias": dias, "tiempo_meses": float(self.apu.tiempo_estimado_meses or 0)}

    @transaction.atomic
    def generar_herramientas(self, items: List[Dict]) -> List[dict]:
        """
        items: [{"descripcion": str, "precio_total": float, "es_insumo": bool}]
        CU = precio_total / Total_PowerGrip  (si no es insumo)
        Rendimiento = No. personas (si es herramienta) o input directo (si insumo)
        """
        from .models import APULinea, TipoAPU
        tp = float(self.ps.total_powergip or 1) or 1

        creadas = []
        for item in items:
            precio = float(item.get("precio_total", 0))
            cu = precio / tp
            apu_linea, _ = APULinea.objects.update_or_create(
                apu=self.apu,
                tipo=TipoAPU.HERRAMIENTAS_EQUIPOS,
                descripcion=item["descripcion"],
                defaults={
                    "rendimiento":       Decimal("1"),
                    "precio_referencia": Decimal(str(round(cu, 6))),
                    "iva_aplicado":      False,
                    "editable":          True,
                }
            )
            apu_linea.calcular()
            creadas.append({"descripcion": item["descripcion"], "costo_unitario": float(apu_linea.costo_unitario)})

        return creadas

    @transaction.atomic
    def generar_transporte(self, costo_total_transporte: float) -> dict:
        """CU_transporte = costo_total / Total_PowerGrip"""
        from .models import APULinea, TipoAPU
        tp = float(self.ps.total_powergip or 1) or 1
        cu = costo_total_transporte / tp

        apu_linea, _ = APULinea.objects.update_or_create(
            apu=self.apu,
            tipo=TipoAPU.TRANSPORTE,
            descripcion="Transporte",
            defaults={
                "rendimiento":       Decimal("1"),
                "precio_referencia": Decimal(str(round(cu, 6))),
                "iva_aplicado":      False,
                "editable":          True,
            }
        )
        apu_linea.calcular()
        return {"descripcion": "Transporte", "costo_unitario": float(apu_linea.costo_unitario)}

    @transaction.atomic
    def generar_administracion(self, costo_total_admin: float) -> dict:
        """CU_admin = costo_total / Total_PowerGrip"""
        from .models import APULinea, TipoAPU
        tp = float(self.ps.total_powergip or 1) or 1
        cu = costo_total_admin / tp

        apu_linea, _ = APULinea.objects.update_or_create(
            apu=self.apu,
            tipo=TipoAPU.ADMINISTRACION,
            descripcion="Administración",
            defaults={
                "rendimiento":       Decimal("1"),
                "precio_referencia": Decimal(str(round(cu, 6))),
                "iva_aplicado":      False,
                "editable":          True,
            }
        )
        apu_linea.calcular()
        return {"descripcion": "Administración", "costo_unitario": float(apu_linea.costo_unitario)}

    def finalizar(self):
        """Recalcula totales del APU y avanza estado del proyecto a APU en proceso."""
        self.apu.recalcular()
        proyecto = self.ps.proyecto
        # Solo avanzar si viene desde DESPIECE_VALIDADO; si ya está en APU, mantener
        if proyecto.estado not in ("APU", "APU_GENERADO"):
            proyecto.avanzar_a_apu()
        return {
            "total_costo":       float(self.apu.total_costo),
            "total_valor_venta": float(self.apu.total_valor_venta),
            "subtotales": {
                "materiales":    float(self.apu.subtotal_materiales),
                "herramientas":  float(self.apu.subtotal_herramientas),
                "transporte":    float(self.apu.subtotal_transporte),
                "mano_obra":     float(self.apu.subtotal_mano_obra),
                "administracion": float(self.apu.subtotal_administracion),
            }
        }


# ---------------------------------------------------------------------------
# PROYECTO SERVICE  (orquestador del flujo)
# ---------------------------------------------------------------------------

class ProyectoService:
    """
    Orquesta la creación de proyectos y las transiciones de estado.
    """

    @staticmethod
    @transaction.atomic
    def crear_desde_solicitud(
        solicitud_id: int,
        tipo_proyecto_id: int,
        creado_por,
        area_total_m2: Optional[float] = None,
        perimetro_ml:  Optional[float] = None,
        trm:           float = 4200,
        margen_comercial_pct: float = 20,
        iva_pct:       float = 19,
        aiu_pct:       float = 0,
        moneda:        str = "COP",
        aplica_exencion_iva: bool = False,
        observaciones: Optional[str] = None,
    ):
        from .models import Solicitud, Proyecto, TipoProyecto

        solicitud = Solicitud.objects.select_related("cliente").get(pk=solicitud_id)
        tipo_pry  = TipoProyecto.objects.get(pk=tipo_proyecto_id)

        proyecto = Proyecto.objects.create(
            consecutivo          = Proyecto.siguiente_consecutivo(),
            solicitud            = solicitud,
            cliente              = solicitud.cliente,
            creado_por           = creado_por,
            tipo_proyecto        = tipo_pry,
            nombre               = solicitud.nombre,
            descripcion          = solicitud.descripcion,
            area_total_m2        = area_total_m2,
            perimetro_ml         = perimetro_ml,
            trm                  = trm,
            margen_comercial_pct = margen_comercial_pct,
            iva_pct              = iva_pct,
            aiu_pct              = aiu_pct,
            moneda               = moneda,
            aplica_exencion_iva  = aplica_exencion_iva,
            observaciones        = observaciones,
            estado               = "SOLICITUD",
        )

        # Actualizar estado de solicitud → EN_GESTION si aplica
        if solicitud.estado == "EN_GESTION":
            pass  # ya está

        return proyecto

    @staticmethod
    @transaction.atomic
    def iniciar_despiece(proyecto_id: int, sistema_id: int, subsistema_id: int, total_powergip: float, cuadrilla: int = 1):
        """
        Crea ProyectoSistema, inyecta dependencias, ejecuta despiece paramétrico
        y avanza el proyecto a estado DESPIECE.
        """
        from .models import Proyecto, Sistema, Subsistema, ProyectoSistema

        proyecto   = Proyecto.objects.get(pk=proyecto_id)
        sistema    = Sistema.objects.get(pk=sistema_id)
        subsistema = Subsistema.objects.get(pk=subsistema_id)

        ps, _ = ProyectoSistema.objects.get_or_create(
            proyecto=proyecto,
            sistema=sistema,
            subsistema=subsistema,
            defaults={
                "total_powergip":     Decimal(str(total_powergip)),
                "cuadrilla_personas": cuadrilla,
            }
        )
        ps.total_powergip    = Decimal(str(total_powergip))
        ps.cuadrilla_personas = cuadrilla
        ps.save()

        # Inyectar dependencias obligatorias
        dep_service = DependenciaService(ps)
        deps = dep_service.inyectar()

        # Ejecutar despiece paramétrico
        desp_service = DespieceService(ps)
        lineas = desp_service.ejecutar()

        # Cambiar estado proyecto
        proyecto.avanzar_a_despiece()

        return {
            "proyecto_sistema_id": ps.id,
            "dependencias_inyectadas": deps,
            "lineas_despiece": lineas,
            "estado_proyecto": proyecto.estado,
        }

    @staticmethod
    @transaction.atomic
    def iniciar_apu(proyecto_sistema_id: int, **kwargs_apu):
        """
        Genera el APU completo para un ProyectoSistema.
        Solo se puede iniciar si el proyecto está en DESPIECE_VALIDADO o APU.
        kwargs_apu puede incluir: hya_dia, cuadrilla_dia, dotacion_dia,
          proteccion_dia, costo_transporte, costo_admin, herramientas_items
        """
        from .models import ProyectoSistema, EstadoProyecto

        ps      = ProyectoSistema.objects.get(pk=proyecto_sistema_id)
        proyecto = ps.proyecto

        estados_validos = (
            EstadoProyecto.DESPIECE_VALIDADO,
            EstadoProyecto.APU,
            EstadoProyecto.APU_GENERADO,
        )
        if proyecto.estado not in estados_validos:
            raise ValueError(
                f"El proyecto está en estado '{proyecto.get_estado_display()}'. "
                "Valide el despiece antes de generar el APU."
            )

        service = APUService(ps)

        materiales  = service.generar_materiales()
        mo_result   = service.generar_mano_obra(
            hya_dia        = kwargs_apu.get("hya_dia", 0),
            cuadrilla_dia  = kwargs_apu.get("cuadrilla_dia", 0),
            dotacion_dia   = kwargs_apu.get("dotacion_dia", 0),
            proteccion_dia = kwargs_apu.get("proteccion_dia", 0),
        )
        herramientas = service.generar_herramientas(kwargs_apu.get("herramientas_items", []))
        transporte   = service.generar_transporte(kwargs_apu.get("costo_transporte", 0))
        admin        = service.generar_administracion(kwargs_apu.get("costo_admin", 0))
        totales      = service.finalizar()

        return {
            "materiales":    materiales,
            "mano_obra":     mo_result,
            "herramientas":  herramientas,
            "transporte":    transporte,
            "administracion": admin,
            "totales":       totales,
        }
