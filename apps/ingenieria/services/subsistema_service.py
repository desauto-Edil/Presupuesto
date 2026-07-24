"""
apps/ingenieria/services/subsistema_service.py
==============================================

Service layer del Subsistema. Contiene las rutinas de persistencia que
antes vivían como helpers `_guardar_*` en `apps/ingenieria/views/__init__.py`.

Migración Fase 2 (mover-tal-cual, cero cambio funcional):
    - `_guardar_variables`        →  `guardar_variables`
    - `_guardar_subconjuntos_componentes`
                                  →  `guardar_subconjuntos_componentes`
    - `_guardar_reglas_apu`       →  `guardar_reglas_apu`
    - `_guardar_m2m_consumo`      →  `guardar_m2m_consumo`
    - `_guardar_productos_tecnicos_componentes_quimicos`
                                  →  `guardar_productos_tecnicos_componentes_quimicos`
    - `_parsear_opciones`         →  `parsear_opciones`        (helper interno)
    - `_proximo_codigo_numerico`  →  `proximo_codigo_numerico` (helper interno)

Reglas:
    - No cambia el comportamiento visible.
    - No introduce reglas nuevas de validación.
    - No reorganiza la API en una clase única todavía (eso es Fase 3).
    - Las vistas (`SubsistemaCreateView`, `SubsistemaUpdateView`) llaman
      a estas funciones desde `form_valid` envuelto en `transaction.atomic`.
"""

from __future__ import annotations

import json

from apps.ingenieria.models import (
    ComponenteSubsistema,
    VariableSubsistema,
    SubconjuntoRecetaTecnica,
    ComponenteQuimico,
    ProductoTecnicoAsociado,
    VariableDependenciaSubsistema,
)


# ── Helpers internos ─────────────────────────────────────────────────────────

def parsear_opciones(raw: str) -> list:
    """
    Parsea un string de opciones separadas por punto y coma.
    Ej: "4; 6"  →  ["4", "6"]
    Limpia espacios y filtra entradas vacías.
    """
    if not raw:
        return []
    return [o.strip() for o in raw.split(";") if o.strip()]


def proximo_codigo_numerico(en_uso: set) -> str:
    """Devuelve el menor entero positivo (como string) que NO esté en `en_uso`.
    Replica el comportamiento del helper JS `generarCodigoComponente` del template.
    Códigos alfanuméricos legacy (ej. "fijaciones_plus") se consideran ocupados
    como string pero no afectan la numeración: se busca el primer hueco numérico
    libre desde 1.
    """
    n = 1
    while str(n) in en_uso:
        n += 1
    return str(n)


# ── Guardado de variables de entrada ─────────────────────────────────────────

def guardar_variables(subsistema, post):
    """
    Guarda las variables de entrada del subsistema desde arrays POST.
    POST arrays: var_variable[], var_label[], var_unidad[], var_default[],
                 var_tipo[], var_opciones[]

    - tipo_entrada: NUMERO | TEXTO | OPCION_UNICA (default: NUMERO)
    - opciones: string "4; 6" → lista ["4", "6"] (solo para OPCION_UNICA)
    - valor_default: se guarda siempre; debe ser numérico para NUMERO/OPCION_UNICA
    """
    var_variables = post.getlist("var_variable[]")
    var_labels    = post.getlist("var_label[]")
    var_unidades  = post.getlist("var_unidad[]")
    var_defaults  = post.getlist("var_default[]")
    var_tipos     = post.getlist("var_tipo[]")
    var_opciones  = post.getlist("var_opciones[]")
    # Sub-fase D — flag por variable: ¿suma a area_base_apu?
    var_base_apu  = post.getlist("var_base_apu[]")

    VariableSubsistema.objects.filter(subsistema=subsistema).delete()
    for idx, (variable, label) in enumerate(zip(var_variables, var_labels)):
        variable = variable.strip()
        label    = label.strip()
        if not (variable and label):
            continue
        raw_default = var_defaults[idx].strip() if idx < len(var_defaults) else ""
        try:
            default_val = float(raw_default) if raw_default else 0
        except ValueError:
            default_val = 0

        tipo = (var_tipos[idx].strip() if idx < len(var_tipos) else "").upper()
        if tipo not in ("NUMERO", "TEXTO", "OPCION_UNICA"):
            tipo = VariableSubsistema.NUMERO

        raw_ops = var_opciones[idx].strip() if idx < len(var_opciones) else ""
        opciones = parsear_opciones(raw_ops) if tipo == VariableSubsistema.OPCION_UNICA else []

        flag_base_apu = False
        if idx < len(var_base_apu):
            flag_base_apu = str(var_base_apu[idx]).strip().lower() in ("1", "true", "on", "yes")

        VariableSubsistema.objects.create(
            subsistema=subsistema,
            variable=variable,
            label=label,
            unidad=var_unidades[idx].strip() if idx < len(var_unidades) else "",
            valor_default=default_val,
            tipo_entrada=tipo,
            opciones=opciones,
            participa_en_base_apu=flag_base_apu,
            orden=idx + 1,
        )


# ── Guardado de dependencias entre variables (Fase 2B) ───────────────────────

def guardar_dependencias_variables(subsistema, post):
    """
    Guarda las dependencias entre variables del subsistema desde arrays POST.
    POST arrays paralelos:
        dep_var_origen[]   — nombre interno de la variable origen
        dep_val_origen[]   — valor concreto que dispara la regla
        dep_var_destino[]  — nombre interno de la variable destino
        dep_val_destino[]  — valor que se asignará a la destino
        dep_activa[]       — "1" / "0" (precedido de hidden "0" para checkboxes desmarcados)
        dep_notas[]        — opcional

    Usa los nombres de variable (no PKs) porque el flujo del formulario borra y
    recrea las VariableSubsistema en cada save, así que las PKs no son estables
    entre saves consecutivos.

    Se ejecuta DESPUÉS de guardar_variables, así que las variables nuevas ya
    existen y se pueden resolver por nombre.

    Si alguna fila falla validación (`full_clean`), TODO el guardado de
    dependencias se revierte (savepoint) y se devuelve la lista de errores
    como strings. Las dependencias preexistentes se conservan en ese caso.
    Si todas las filas son válidas, se borran las existentes y se crean las
    nuevas — devolviendo lista vacía.

    Devuelve: list[str] con errores acumulados (vacía si todo OK).
    """
    from django.core.exceptions import ValidationError
    from django.db import transaction

    var_origenes = post.getlist("dep_var_origen[]")
    val_origenes = post.getlist("dep_val_origen[]")
    var_destinos = post.getlist("dep_var_destino[]")
    val_destinos = post.getlist("dep_val_destino[]")
    activas      = post.getlist("dep_activa[]")
    notas        = post.getlist("dep_notas[]")

    # Sin filas en POST → borrar todas las existentes (consistente con variables).
    n = max(len(var_origenes), len(var_destinos))
    if n == 0:
        VariableDependenciaSubsistema.objects.filter(subsistema=subsistema).delete()
        return []

    # Index de variables del subsistema por nombre interno.
    vars_map = {
        v.variable: v
        for v in VariableSubsistema.objects.filter(subsistema=subsistema)
    }

    # Construir las instancias en memoria, filtrando filas incompletas.
    instancias = []
    errores = []
    for idx in range(n):
        var_o = (var_origenes[idx] if idx < len(var_origenes) else "").strip()
        val_o = (val_origenes[idx] if idx < len(val_origenes) else "").strip()
        var_d = (var_destinos[idx] if idx < len(var_destinos) else "").strip()
        val_d = (val_destinos[idx] if idx < len(val_destinos) else "").strip()
        if not (var_o and val_o and var_d and val_d):
            continue  # fila incompleta — se ignora silenciosamente

        v_o = vars_map.get(var_o)
        v_d = vars_map.get(var_d)
        if v_o is None:
            errores.append(f"Dependencia #{idx + 1}: variable origen '{var_o}' no existe en el subsistema.")
            continue
        if v_d is None:
            errores.append(f"Dependencia #{idx + 1}: variable destino '{var_d}' no existe en el subsistema.")
            continue

        activa = True
        if idx < len(activas):
            activa = str(activas[idx]).strip().lower() in ("1", "true", "on", "yes")
        nota = (notas[idx].strip() if idx < len(notas) else "")[:200]

        instancias.append((
            idx + 1,
            VariableDependenciaSubsistema(
                subsistema=subsistema,
                variable_origen=v_o,
                valor_origen=val_o,
                variable_destino=v_d,
                valor_destino=val_d,
                activa=activa,
                orden=idx + 1,
                notas=nota,
            ),
        ))

    if errores:
        # Errores de mapping antes de tocar la BD: preservar existentes.
        return errores

    # Savepoint anidado: si una validación falla, rollback solo de esta unidad
    # de trabajo y devolvemos errores. La transacción externa (form_valid)
    # continúa intacta y el resto del subsistema queda guardado.
    try:
        with transaction.atomic():
            VariableDependenciaSubsistema.objects.filter(subsistema=subsistema).delete()
            for fila_num, inst in instancias:
                try:
                    inst.full_clean()
                except ValidationError as exc:
                    detalle = _format_validation_error(exc)
                    errores.append(f"Dependencia #{fila_num}: {detalle}")
                    raise  # forzar rollback del savepoint
                inst.save()
    except ValidationError:
        # Rollback ya ocurrió; preservamos las existentes y devolvemos errores.
        return errores

    return []


def _format_validation_error(exc):
    if hasattr(exc, "message_dict") and exc.message_dict:
        partes = []
        for campo, mensajes in exc.message_dict.items():
            if isinstance(mensajes, (list, tuple)):
                partes.append(f"{campo}: {'; '.join(str(m) for m in mensajes)}")
            else:
                partes.append(f"{campo}: {mensajes}")
        return " | ".join(partes)
    return str(exc)


# ── Guardado de subconjuntos y componentes ───────────────────────────────────

def guardar_subconjuntos_componentes(subsistema, post):
    """
    Guarda los subconjuntos de receta técnica y sus componentes.

    Espera el campo POST 'subconjuntos_json' con estructura JSON:
    [
      {
        "nombre": "Estructura metálica",
        "descripcion": "Descripción opcional",
        "componentes": [
          {
            "codigo": "viga",
            "nombre": "Viga principal",
            "categoria_id": 3,          // null si sin categoría
            "formula_texto": "longitud * 1.05",
            "variable_salida": "",
            "unidad": "ml",
            "variable_referencia_apu": "",
            "unidad_apu": ""
          }
        ]
      }
    ]

    Si el JSON está vacío o ausente, no modifica los componentes existentes.
    Compatibilidad: si un subsistema antiguo tiene componentes sin subconjunto,
    se eliminan también al guardar con la nueva estructura.
    """
    from apps.catalogos.models import CategoriaProducto

    raw = post.get("subconjuntos_json", "").strip()
    if not raw:
        return []

    try:
        subconjuntos_data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return []

    if not isinstance(subconjuntos_data, list):
        return []

    errores_validacion: list[str] = []

    # Eliminar todos los subconjuntos y componentes existentes (incluye legacy)
    SubconjuntoRecetaTecnica.objects.filter(subsistema=subsistema).delete()
    ComponenteSubsistema.objects.filter(subsistema=subsistema, subconjunto__isnull=True).delete()

    # Set acumulativo de códigos ya asignados en este subsistema (defensa backend
    # ante un código vacío o duplicado proveniente del frontend).
    codigos_en_uso: set[str] = set()

    for sq_idx, sq_data in enumerate(subconjuntos_data):
        nombre_sq = str(sq_data.get("nombre", "")).strip()
        if not nombre_sq:
            continue

        subconjunto = SubconjuntoRecetaTecnica.objects.create(
            subsistema=subsistema,
            nombre=nombre_sq,
            descripcion=str(sq_data.get("descripcion", "")).strip(),
            orden=sq_idx + 1,
            activo=True,
        )

        componentes = sq_data.get("componentes", [])
        if not isinstance(componentes, list):
            continue

        for comp_idx, comp_data in enumerate(componentes):
            codigo  = str(comp_data.get("codigo", "")).strip()
            nombre  = str(comp_data.get("nombre", "")).strip()
            formula = str(comp_data.get("formula_texto", "")).strip()
            if not (nombre and formula):
                continue
            # Red de seguridad: si no llegó código, o si colisiona con otro
            # componente del mismo subsistema (unique_together), asignar el
            # próximo entero libre.
            if not codigo or codigo in codigos_en_uso:
                codigo = proximo_codigo_numerico(codigos_en_uso)
            codigos_en_uso.add(codigo)

            cat_id = comp_data.get("categoria_id")
            categoria = None
            if cat_id:
                try:
                    categoria = CategoriaProducto.objects.get(pk=int(cat_id))
                except (CategoriaProducto.DoesNotExist, ValueError, TypeError):
                    pass

            req_pres = bool(comp_data.get("requiere_presentacion_producto", False))
            var_pres = str(comp_data.get("variable_presentacion_producto", "")).strip()

            import re as _re
            if req_pres:
                if not var_pres:
                    errores_validacion.append(
                        f"Componente «{nombre}» (cód. {codigo}): se marcó «Calcular tras producto» "
                        "pero falta la variable de presentación."
                    )
                elif not _re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', var_pres):
                    errores_validacion.append(
                        f"Componente «{nombre}» (cód. {codigo}): "
                        f"«{var_pres}» no es un identificador Python válido."
                    )

            ComponenteSubsistema.objects.create(
                subsistema=subsistema,
                subconjunto=subconjunto,
                codigo=codigo,
                nombre=nombre,
                categoria=categoria,
                formula_texto=formula,
                variable_salida=str(comp_data.get("variable_salida", "")).strip(),
                unidad=str(comp_data.get("unidad", "")).strip(),
                variable_referencia_apu=str(comp_data.get("variable_referencia_apu", "")).strip(),
                unidad_apu=str(comp_data.get("unidad_apu", "")).strip(),
                requiere_presentacion_producto=req_pres,
                variable_presentacion_producto=var_pres,
                orden=comp_idx + 1,
            )

    return errores_validacion


# ── Guardado de reglas APU ───────────────────────────────────────────────────

def guardar_reglas_apu(subsistema, post):
    """
    Procesa las reglas APU enviadas desde el form del subsistema.
    Reemplaza todos los registros existentes con los nuevos valores.
    POST arrays: regla_tipo_apu[], regla_formula[]
    """
    from apps.presupuestos.models import ReglaAPUSubsistema

    tipos    = post.getlist("regla_tipo_apu[]")
    formulas = post.getlist("regla_formula[]")

    ReglaAPUSubsistema.objects.filter(subsistema=subsistema).delete()
    for idx, (tipo, formula) in enumerate(zip(tipos, formulas)):
        tipo    = tipo.strip()
        formula = formula.strip()
        if tipo and formula:
            ReglaAPUSubsistema.objects.create(
                subsistema=subsistema,
                tipo_apu=tipo,
                formula_costo_unitario=formula,
                orden=idx + 1,
            )


# ── Guardado de ítems APU predeterminados (Fase 6L-C) ────────────────────────

def guardar_items_apu_subsistema(subsistema, post):
    """
    Persiste los ítems APU predeterminados del subsistema en SubsistemaItemAPU.

    Reemplaza completamente las asociaciones existentes con las nuevas
    seleccionadas en el formulario. Solo aplica a las categorías
    no-Materiales (Herramientas, Transporte, Mano de obra, Administración).
    Materiales NO se persiste aquí: se genera siempre desde el despiece.

    POST arrays esperados (uno por categoría):
        sia_HERRAMIENTAS_EQUIPOS_item_id[]   sia_HERRAMIENTAS_EQUIPOS_cantidad[]
        sia_TRANSPORTE_item_id[]             sia_TRANSPORTE_cantidad[]
        sia_MANO_DE_OBRA_item_id[]           sia_MANO_DE_OBRA_cantidad[]
        sia_ADMINISTRACION_item_id[]         sia_ADMINISTRACION_cantidad[]

    Cada checkbox marcado emite un valor en sia_<TIPO>_item_id[]; el input
    de cantidad asociado se envía en sia_<TIPO>_cantidad[] alineado por
    índice (gracias a hidden inputs paralelos).

    Reglas:
      - Se borran TODAS las SubsistemaItemAPU del subsistema y se recrean.
      - Si no llega ningún item para un tipo, la categoría queda vacía
        (regla 6L-D: APUService no rellena con catálogo completo).
      - Cantidad inválida (<1) → 1.
    """
    from apps.presupuestos.models import SubsistemaItemAPU, ItemCatalogoAPU
    from apps.common.choices import TipoAPU

    TIPOS = [
        TipoAPU.HERRAMIENTAS_EQUIPOS,
        TipoAPU.TRANSPORTE,
        TipoAPU.MANO_DE_OBRA,
        TipoAPU.ADMINISTRACION,
    ]

    # Reemplazo completo
    SubsistemaItemAPU.objects.filter(subsistema=subsistema).delete()

    for tipo in TIPOS:
        items_raw     = post.getlist(f"sia_{tipo}_item_id[]")
        cantidades    = post.getlist(f"sia_{tipo}_cantidad[]")
        rendimientos  = post.getlist(f"sia_{tipo}_rendimiento[]")

        # El frontend emite checkboxes + un hidden de cantidad por cada ítem
        # mostrado. Para mantener el alineamiento por índice, se procesa por
        # par (item_id, cantidad) — solo se persisten los marcados.
        orden = 0
        for idx, item_pk_raw in enumerate(items_raw):
            item_pk_raw = (item_pk_raw or "").strip()
            if not item_pk_raw.isdigit():
                continue
            item_pk = int(item_pk_raw)
            try:
                item = ItemCatalogoAPU.objects.get(pk=item_pk, activo=True)
            except ItemCatalogoAPU.DoesNotExist:
                continue

            raw_cant = cantidades[idx].strip() if idx < len(cantidades) else ""
            try:
                cant = int(raw_cant) if raw_cant else 1
            except (TypeError, ValueError):
                cant = 1
            if cant < 1:
                cant = 1

            raw_rend = rendimientos[idx].strip().replace(",",".") if idx < len(rendimientos) else ""
            try:
                # Guardar como factor (10% -> 0.10)
                rend = float(raw_rend) / 100.0 if raw_rend else None
            except (TypeError, ValueError):
                rend = None

            orden += 1
            SubsistemaItemAPU.objects.update_or_create(
                subsistema=subsistema,
                item_catalogo=item,
                tipo=tipo,
                defaults={
                    "cantidad": cant,
                    "rendimiento_override": rend,
                    "orden": orden,
                    "activo": True,
                },
            )


# ── Guardado de M2M de catálogo de consumo ───────────────────────────────────

def guardar_m2m_consumo(subsistema, post):
    """
    Guarda los M2M de catálogo consumo: funciones, problemas_resuelve, superficies_compatibles.
    Los checkboxes llegan como: funciones[], problemas_resuelve[], superficies_compatibles[]
    con los PKs seleccionados.
    """
    funciones_pks   = [int(pk) for pk in post.getlist("funciones[]") if pk.strip().isdigit()]
    problemas_pks   = [int(pk) for pk in post.getlist("problemas_resuelve[]") if pk.strip().isdigit()]
    superficies_pks = [int(pk) for pk in post.getlist("superficies_compatibles[]") if pk.strip().isdigit()]

    subsistema.funciones.set(funciones_pks)
    subsistema.problemas_resuelve.set(problemas_pks)
    subsistema.superficies_compatibles.set(superficies_pks)


# ── Guardado de productos técnicos / componentes químicos ────────────────────

def guardar_productos_tecnicos_componentes_quimicos(subsistema, post):
    """
    Procesa ProductoTecnicoAsociado y ComponenteQuimico desde el form del subsistema.

    POST arrays para productos técnicos:
        pt_nombre[], pt_estado_fisico[], pt_consumo_min[], pt_consumo_max[], pt_unidad[]

    POST arrays para componentes químicos:
        cq_nombre[], cq_porcentaje[], cq_estado_fisico[], cq_categoria[]
    """
    from apps.catalogos.models import CategoriaProducto

    # ── Productos técnicos asociados ──────────────────────────────────────────
    pt_nombres        = post.getlist("pt_nombre[]")
    pt_estados_fisico = post.getlist("pt_estado_fisico[]")
    pt_consumos_min   = post.getlist("pt_consumo_min[]")
    pt_consumos_max   = post.getlist("pt_consumo_max[]")
    pt_unidades       = post.getlist("pt_unidad[]")

    ProductoTecnicoAsociado.objects.filter(subsistema=subsistema).delete()
    for idx, nombre in enumerate(pt_nombres):
        nombre = nombre.strip()
        if not nombre:
            continue

        def _decimal_or_none(lst, i):
            try:
                v = lst[i].strip() if i < len(lst) else ""
                return float(v) if v else None
            except ValueError:
                return None

        ProductoTecnicoAsociado.objects.create(
            subsistema=subsistema,
            nombre=nombre,
            estado_fisico=pt_estados_fisico[idx].strip() if idx < len(pt_estados_fisico) else "",
            consumo_min_g_m2=_decimal_or_none(pt_consumos_min, idx),
            consumo_max_g_m2=_decimal_or_none(pt_consumos_max, idx),
            unidad=pt_unidades[idx].strip() if idx < len(pt_unidades) else "kg",
            orden=idx + 1,
        )

    # ── Componentes químicos ──────────────────────────────────────────────────
    cq_nombres        = post.getlist("cq_nombre[]")
    cq_porcentajes    = post.getlist("cq_porcentaje[]")
    cq_estados_fisico = post.getlist("cq_estado_fisico[]")
    cq_categorias     = post.getlist("cq_categoria[]")

    ComponenteQuimico.objects.filter(subsistema=subsistema).delete()
    for idx, nombre in enumerate(cq_nombres):
        nombre = nombre.strip()
        if not nombre:
            continue
        try:
            porcentaje = float(cq_porcentajes[idx].strip()) if idx < len(cq_porcentajes) and cq_porcentajes[idx].strip() else 0
        except ValueError:
            porcentaje = 0
        cat_pk = cq_categorias[idx].strip() if idx < len(cq_categorias) else ""
        categoria = None
        if cat_pk:
            try:
                categoria = CategoriaProducto.objects.get(pk=int(cat_pk))
            except (CategoriaProducto.DoesNotExist, ValueError):
                pass
        ComponenteQuimico.objects.create(
            subsistema=subsistema,
            nombre=nombre,
            porcentaje=porcentaje,
            estado_fisico=cq_estados_fisico[idx].strip() if idx < len(cq_estados_fisico) else "",
            categoria=categoria,
            orden=idx + 1,
        )
