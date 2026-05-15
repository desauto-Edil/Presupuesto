# Guía de pruebas — Sprint Mayo 2026

## Requisitos previos
- Servidor corriendo: `python manage.py runserver 8000`
- Al menos 1 solicitud, 1 cliente, 1 sistema/subsistema con líneas, 1 proyecto guardado con despiece

---

## TC-01: Clonar proyecto como versión
1. Abrir `proyecto_detail` de un proyecto vinculado a una solicitud.
2. Hacer clic en **Clonar versión** → confirmar el diálogo.
3. **Esperado:** se crea un nuevo proyecto con `version = anterior + 1`, `es_version_actual = True`. El anterior pasa a `es_version_actual = False`. Mensaje de éxito visible.

## TC-02: Filtrado de clientes por unidad de negocio
1. Iniciar sesión con una unidad de negocio configurada en sesión (p.ej. "IMPERCO").
2. Abrir el formulario de nueva solicitud (modal o página).
3. **Esperado:** el select de `Cliente` solo muestra clientes con `unidad_negocio = "IMPERCO"`. Intentar enviar con un cliente de otra unidad → error de validación.

## TC-03: Modal "Crear proyecto" desde solicitud_detail
1. Abrir `solicitud_detail` de cualquier solicitud.
2. Hacer clic en **+ Nuevo proyecto** (topbar o botón del panel Proyectos).
3. **Esperado:** se abre el modal Bootstrap con el formulario en 3 columnas financieras.
4. Rellenar campos mínimos → enviar.
5. **Esperado:** redirect a `proyecto_detail` del nuevo proyecto. Sin proyecto duplicado.

## TC-04: Tarjetas compactas en calculador de sistemas
1. Ir a `ingenieria:calculador_sistemas`.
2. **Esperado:** cards en grid `minmax(220px, 1fr)`, nombre truncado a 2 líneas, botón "Calcular" de 11.5px. Sin scroll horizontal en pantalla 1280px.

## TC-05: Layout dos columnas + imagen técnica en selección de subsistema
1. Seleccionar un sistema → click en un subsistema con subconjuntos.
2. **Esperado:** el cuerpo expandido muestra columna izquierda (subconjuntos) y columna derecha (imagen técnica o placeholder).
3. Verificar que sin imagen muestra el placeholder con ícono.

## TC-06: Barra de búsqueda en APU
1. Abrir `presupuestos:apu_detail` de cualquier APU con más de 5 líneas.
2. Escribir en el input de búsqueda.
3. **Esperado:** se filtran en tiempo real filas `tr[id^="apu-linea-"]`. Las filas que no coinciden se ocultan. Botón ✕ limpia el filtro.

## TC-07: Consolidación de múltiples despieces en APU
1. Desde un proyecto, crear y guardar 2 despieces distintos (mismos o distintos subsistemas) que incluyan el mismo producto.
2. Desde `solicitud_detail`, hacer click en **Gen. APU** en cualquiera de los despieces.
3. **Esperado:** el APU resultante tiene el producto sumado (cantidad = suma de ambos despieces). No aparece duplicado.

## TC-08: Sin duplicados al regenerar APU
1. Con un APU ya generado (TC-07), hacer click en **Gen. APU** nuevamente en el mismo despiece.
2. **Esperado:** las líneas de materiales se reemplazan (no se duplican). El total de líneas de tipo MATERIALES es el mismo o menor que antes.

## TC-09: Historial colapsable al fondo de solicitud_detail
1. Abrir `solicitud_detail` con al menos 4 eventos de log.
2. **Esperado:** el panel "Historial de actividad" aparece debajo del grid de dos columnas (ancho completo). Muestra 3 eventos. Botón "Ver N más" expande el resto. Click en el header colapsa todo.

## TC-10: Validación de subsistema obligatorio en calculador
1. Ir a `ingenieria:calculador_seleccionar` con un sistema que tenga múltiples subsistemas.
2. Sin seleccionar ninguno, hacer click en **Ir al calculador**.
3. **Esperado:** alert de navegador "Selecciona un subsistema antes de continuar." El form no se envía.

---

## Verificación de rutas (smoke test)
```
GET  /comercial/solicitudes/                     → 200
GET  /comercial/solicitudes/<pk>/                → 200
GET  /comercial/solicitudes/<pk>/crear-proyecto/ → 200
POST /comercial/proyectos/<pk>/clonar/           → 302
GET  /ingenieria/calculador/                     → 200
GET  /ingenieria/calculador/<pk>/nuevo/          → 200
GET  /presupuestos/apu/<pk>/                     → 200
POST /presupuestos/apu/generar-despiece/<pk>/    → 302
```
