"""
apps/ingenieria/system_defs/base.py — Estructuras de datos para definiciones de sistemas.

Clases de datos (dataclasses) que representan la "receta técnica" de un sistema.
Estas clases son instanciadas en los archivos de cada sistema (ej: powergrip.py)
y registradas en registry.py para ser consumidas por DespieceService.

No hay lógica de negocio aquí — solo la estructura de datos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class VariableRequerida:
    """
    Variable de entrada que el presupuestador debe ingresar para este sistema.

    opciones: si se provee, la UI renderiza un <select> en vez de <input type="number">.
              Formato: lista de (value, label), ej: [(4, "4 fijaciones"), (8, "8 fijaciones")].

    Ejemplo:
        VariableRequerida(
            variable="total_powergrip",
            label="Total de PowerGrips a instalar",
            unidad="und",
            default=0.0,
        )
    """
    variable: str                       # Clave en el contexto (snake_case)
    label:    str                       # Texto para mostrar en el formulario
    unidad:   str  = "und"              # Unidad de medida (solo informativa)
    default:  Optional[float] = None
    descripcion: str = ""
    opciones: Optional[list] = None     # [(value, label), ...] → renderiza dropdown


@dataclass
class ComponenteDef:
    """
    Define un componente del conjunto técnico con su fórmula de cálculo.

    La fórmula es un callable Python que recibe el contexto acumulado y
    devuelve la cantidad como float. El contexto incluye las variables
    del proyecto (area_m2, perimetro_ml) más las variables de entrada
    ingresadas por el presupuestador.

    variable_salida: si se especifica, el resultado de este componente
    queda disponible en el contexto con ese nombre para que componentes
    posteriores puedan usarlo (ej: limpiador → estopa usa ctx["limpiador"]).

    Ejemplo:
        ComponenteDef(
            codigo="fijaciones",
            nombre='Fijaciones Heavy Duty 3"',
            categoria_slug="Fijaciones",
            formula=lambda ctx: (ctx["total_powergrip"] * ctx["tornilleria_u7"]) * ctx["desperdicio"],
            unidad="und",
            orden=2,
        )
    """
    codigo:              str
    nombre:              str
    categoria_slug:      str                      # Debe coincidir con CategoriaProducto.nombre
    formula:             Callable[[dict], float]  # fn(contexto) → cantidad
    unidad:              str   = "und"
    orden:               int   = 0
    variable_salida:     Optional[str] = None     # Inyecta el resultado al contexto
    pendiente_seleccion: bool  = True             # True = usuario elige producto de la categoría
    descripcion:         str   = ""


@dataclass
class SubsistemaDef:
    """
    Receta técnica completa de un subsistema.

    codigo debe coincidir con Subsistema.codigo en la DB para que
    DespieceService pueda encontrar la definición.

    Las variables se muestran como formulario al presupuestador.
    Los componentes se ejecutan en orden ascendente de `ComponenteDef.orden`.
    """
    codigo:      str
    nombre:      str
    variables:   list[VariableRequerida]  = field(default_factory=list)
    componentes: list[ComponenteDef]      = field(default_factory=list)


@dataclass
class SistemaDef:
    """
    Definición completa de un sistema con todos sus subsistemas.

    codigo debe coincidir con Sistema.codigo en la DB.
    """
    codigo:      str
    nombre:      str
    subsistemas: list[SubsistemaDef] = field(default_factory=list)
