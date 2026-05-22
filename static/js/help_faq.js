/**
 * help_faq.js — Preguntas frecuentes contextuales de Andicost.
 *
 * Estructura por view_name de Django (request.resolver_match.view_name).
 * Cada entrada tiene: titulo, tips (array), preguntas (array de {q, a}).
 * La respuesta `a` admite HTML básico: <code>, <strong>, <br>.
 * La clave "_default" se usa cuando la pantalla no tiene entrada propia.
 */

/* global */ var HELP_FAQ = {

  /* ══════════════════════════════════════════════════════
     SUBSISTEMA — crear / editar
     ══════════════════════════════════════════════════════ */
  "ingenieria:subsistema_create": {
    titulo: "Ayuda — Nuevo Subsistema",
    tips: [
      "Usa punto (.) como separador decimal en todas las fórmulas. La coma (,) causa error de cálculo.",
      "Los nombres de variables no deben tener espacios. Usa guión bajo: <code>area_techo</code>, <code>largo_muro</code>.",
      "Guarda el subsistema antes de salir, incluso si aún no está completo."
    ],
    preguntas: [
      {
        q: "¿Qué es una variable de entrada?",
        a: "Son los parámetros que el usuario ingresa al momento de calcular un despiece. Por ejemplo: <code>area</code>, <code>largo</code>, <code>alto</code>. Las fórmulas de componentes usan estas variables para calcular cantidades automáticamente."
      },
      {
        q: "¿Cómo debo escribir los nombres de variables?",
        a: "Sin espacios y solo con letras, números y guión bajo. Ejemplos válidos: <code>area_cubierta</code>, <code>largo</code>, <code>n_paños</code>. Inválidos: <code>área cubierta</code>, <code>largo-muro</code>, <code>2do_piso</code>."
      },
      {
        q: "¿Cómo debo escribir valores decimales?",
        a: "Siempre con punto, nunca con coma. Correcto: <code>1.5</code>, <code>0.25</code>. Incorrecto: <code>1,5</code>, <code>0,25</code>. La coma en fórmulas produce un error de cálculo."
      },
      {
        q: "¿Qué es un subconjunto?",
        a: "Un subconjunto es una agrupación lógica de componentes dentro de la receta técnica de un subsistema. Ejemplo: un subsistema «Cubierta metálica» puede tener los subconjuntos «Estructura», «Cubierta» y «Fijaciones»."
      },
      {
        q: "¿Qué es un componente?",
        a: "Un componente es un material o insumo individual dentro de un subconjunto. Tiene un código, nombre, fórmula de cantidad y unidad. La fórmula usa las variables de entrada para calcular cuánto se necesita de ese material."
      },
      {
        q: "¿Cómo se escriben las fórmulas de los componentes?",
        a: "Las fórmulas son expresiones matemáticas que usan las variables definidas. Ejemplos:<br><code>area * 1.05</code> — área con un 5% de desperdicio.<br><code>largo * alto / 4</code> — cálculo derivado.<br><code>ceil(area / 2.89)</code> — redondeo hacia arriba.<br>Usa solo punto decimal, nunca coma."
      },
      {
        q: "¿Qué son las Reglas APU?",
        a: "Las reglas APU definen cómo se generan las líneas de mano de obra, herramientas y transporte en el Análisis de Precios Unitarios. Si el subsistema no tiene reglas APU, el análisis económico solo incluirá materiales."
      },
      {
        q: "¿Por qué no puedo activar el subsistema?",
        a: "Un subsistema requiere al menos: código, nombre, sistema asociado y al menos un subconjunto con componentes válidos. Revisa el panel de Checkpoints (botón en la esquina inferior derecha) para ver exactamente qué falta."
      },
      {
        q: "¿Qué diferencia hay entre subsistema CONSTRUCTIVO y CONSUMO?",
        a: "<strong>Constructivo:</strong> tiene receta técnica con variables, subconjuntos y componentes. Se calcula el despiece con fórmulas.<br><strong>Consumo:</strong> el cálculo es por m², m³ u otra unidad de área/volumen directa, sin receta técnica detallada. Es más simple y rápido de configurar."
      },
      {
        q: "¿Puedo agregar la imagen técnica después?",
        a: "Sí. La imagen técnica es opcional y puede agregarse o cambiarse en cualquier momento editando el subsistema. No bloquea el guardado ni el uso del subsistema."
      }
    ]
  },

  "ingenieria:subsistema_update": {
    titulo: "Ayuda — Editar Subsistema",
    tips: [
      "Usa punto (.) como separador decimal en todas las fórmulas. La coma (,) causa error de cálculo.",
      "Al modificar variables o fórmulas, los despieces anteriores conservan su snapshot y no se ven afectados.",
      "El panel de Checkpoints (esquina inferior derecha) muestra el estado de completitud del subsistema."
    ],
    preguntas: [
      {
        q: "¿Qué es una variable de entrada?",
        a: "Son los parámetros que el usuario ingresa al momento de calcular un despiece. Por ejemplo: <code>area</code>, <code>largo</code>, <code>alto</code>. Las fórmulas de componentes usan estas variables para calcular cantidades automáticamente."
      },
      {
        q: "¿Cómo debo escribir los nombres de variables?",
        a: "Sin espacios y solo con letras, números y guión bajo. Ejemplos válidos: <code>area_cubierta</code>, <code>largo</code>, <code>n_paños</code>. Inválidos: <code>área cubierta</code>, <code>largo-muro</code>, <code>2do_piso</code>."
      },
      {
        q: "¿Cómo debo escribir valores decimales?",
        a: "Siempre con punto, nunca con coma. Correcto: <code>1.5</code>, <code>0.25</code>. Incorrecto: <code>1,5</code>, <code>0,25</code>. La coma en fórmulas produce un error de cálculo."
      },
      {
        q: "¿Qué es un subconjunto?",
        a: "Un subconjunto es una agrupación lógica de componentes dentro de la receta técnica de un subsistema. Ejemplo: un subsistema «Cubierta metálica» puede tener los subconjuntos «Estructura», «Cubierta» y «Fijaciones»."
      },
      {
        q: "¿Qué es un componente?",
        a: "Un componente es un material o insumo individual dentro de un subconjunto. Tiene un código, nombre, fórmula de cantidad y unidad. La fórmula usa las variables de entrada para calcular cuánto se necesita de ese material."
      },
      {
        q: "¿Cómo se escriben las fórmulas de los componentes?",
        a: "Las fórmulas son expresiones matemáticas que usan las variables definidas. Ejemplos:<br><code>area * 1.05</code> — área con un 5% de desperdicio.<br><code>largo * alto / 4</code> — cálculo derivado.<br><code>ceil(area / 2.89)</code> — redondeo hacia arriba.<br>Usa solo punto decimal, nunca coma."
      },
      {
        q: "¿Cambiar el subsistema afecta los despieces ya calculados?",
        a: "No. Los despieces guardados tienen un snapshot inmutable de la receta técnica al momento de guardar. Los cambios al subsistema solo afectan <em>nuevos</em> cálculos de despiece."
      },
      {
        q: "¿Por qué no puedo activar el subsistema?",
        a: "Un subsistema requiere al menos: código, nombre, sistema asociado y al menos un subconjunto con componentes válidos. Revisa el panel de Checkpoints (botón en la esquina inferior derecha) para ver exactamente qué falta."
      },
      {
        q: "¿Qué son las Reglas APU?",
        a: "Las reglas APU definen cómo se generan las líneas de mano de obra, herramientas y transporte en el Análisis de Precios Unitarios. Si el subsistema no tiene reglas APU, el análisis económico solo incluirá materiales."
      }
    ]
  },

  /* ══════════════════════════════════════════════════════
     DESPIECE MAESTRO
     ══════════════════════════════════════════════════════ */
  "ingenieria:despiece_maestro": {
    titulo: "Ayuda — Despiece Maestro",
    tips: [
      "Ingresa los valores de las variables y haz clic en «Calcular» para ver las cantidades de materiales.",
      "Debes guardar el despiece para que quede registrado y puedas generar un APU desde él.",
      "La consolidación te permite agrupar varios materiales similares en una sola línea de presupuesto."
    ],
    preguntas: [
      {
        q: "¿Qué significa calcular el despiece?",
        a: "Calcular el despiece es ejecutar las fórmulas del subsistema con los valores que ingresaste en las variables. El resultado es una lista de materiales con sus cantidades calculadas para ese proyecto específico."
      },
      {
        q: "¿Qué es la cantidad redondeada?",
        a: "Es la cantidad calculada redondeada hacia arriba al entero siguiente (<code>math.ceil</code>). Representa las unidades comerciales reales que debes comprar. Ejemplo: si necesitas 4.2 planchas, la cantidad redondeada es 5."
      },
      {
        q: "¿Cuándo debo consolidar materiales?",
        a: "La consolidación es útil cuando varios componentes son del mismo tipo de material y quieres presupuestar una sola línea. Ejemplo: tuercas M10 de distintos subconjuntos se consolidan en una sola línea «Tuercas M10» con cantidad total sumada."
      },
      {
        q: "¿La consolidación es obligatoria?",
        a: "No. Puedes guardar y generar APU sin consolidar. La consolidación es opcional y sirve para simplificar el presupuesto y facilitar la selección de productos del catálogo."
      },
      {
        q: "¿Qué significa seleccionar un producto?",
        a: "Asociar una línea del despiece a un producto del catálogo. Esto captura el precio unitario y la fecha de ese precio, quedando registrado en el snapshot del despiece guardado para trazabilidad histórica."
      },
      {
        q: "¿Por qué debo guardar el despiece?",
        a: "Al guardar, se crea un snapshot inmutable del resultado. Esto permite consultar los materiales y precios en el futuro aunque la receta técnica del subsistema cambie. También es requisito para generar un APU desde el despiece."
      },
      {
        q: "¿Puedo recalcular después de guardar?",
        a: "Sí, pero si cambias las variables y recalculas, el nuevo resultado reemplaza el snapshot anterior si decides guardar nuevamente. El historial de despieces anteriores está en la lista de despieces guardados."
      },
      {
        q: "¿Qué pasa si el subsistema no tiene receta técnica completa?",
        a: "El cálculo puede producir resultados vacíos o incompletos si faltan componentes o fórmulas. Asegúrate de que el subsistema esté completo (verde en todos los checkpoints) antes de calcular."
      }
    ]
  },

  /* ══════════════════════════════════════════════════════
     APU — Análisis de Precios Unitarios
     ══════════════════════════════════════════════════════ */
  "presupuestos:apu_detail": {
    titulo: "Ayuda — APU",
    tips: [
      "El APU se compone de: materiales, mano de obra, herramientas, transporte y costos administrativos.",
      "Puedes ajustar los precios de cada línea sin modificar el despiece original.",
      "Usa «Enviar a revisión» solo cuando el APU esté completo."
    ],
    preguntas: [
      {
        q: "¿Qué es un APU?",
        a: "El Análisis de Precios Unitarios (APU) es el cálculo detallado del costo total de un sistema o subsistema, desglosado en materiales, mano de obra, herramientas, transporte y costos administrativos."
      },
      {
        q: "¿Cómo se generan las líneas de materiales?",
        a: "Las líneas de materiales se generan desde el despiece maestro guardado. Cada componente del despiece se convierte en una línea del APU con su cantidad y precio unitario."
      },
      {
        q: "¿Puedo editar los precios del APU?",
        a: "Sí. Cada línea del APU tiene un precio editable. Los precios iniciales vienen del catálogo de productos al momento de generar el APU, pero puedes ajustarlos manualmente."
      },
      {
        q: "¿Qué significa enviar a revisión?",
        a: "Enviar el APU a revisión lo marca como pendiente de aprobación. Un usuario con rol de revisión puede aprobarlo o rechazarlo. Una vez aprobado, el APU queda bloqueado para edición."
      },
      {
        q: "¿Cómo se calcula el precio total?",
        a: "El precio total incluye: suma de materiales + mano de obra + herramientas + transporte + costos administrativos (overhead). El porcentaje de cada ítem indirecto se configura en la Configuración APU."
      }
    ]
  },

  "presupuestos:apu_revisar": {
    titulo: "Ayuda — Revisar APU",
    tips: [
      "Revisa cada sección antes de aprobar: materiales, mano de obra, herramientas y transporte.",
      "Puedes dejar comentarios en el campo de observaciones antes de rechazar.",
      "Una vez aprobado, el APU no puede modificarse sin una nueva revisión."
    ],
    preguntas: [
      {
        q: "¿Qué debo verificar al revisar un APU?",
        a: "Verifica: que los materiales corresponden al subsistema, que las cantidades son coherentes, que los precios están actualizados, y que las partidas de mano de obra, herramientas y transporte son razonables para el proyecto."
      },
      {
        q: "¿Puedo editar el APU durante la revisión?",
        a: "No. Durante la revisión el APU está en modo solo lectura. Si necesitas correcciones, recházalo para que el equipo de presupuestos lo modifique y reenvíe."
      },
      {
        q: "¿Qué pasa si rechazo el APU?",
        a: "El APU vuelve al estado Borrador y el equipo de presupuestos puede editarlo y reenviarlo a revisión."
      }
    ]
  },

  /* ══════════════════════════════════════════════════════
     CALCULADOR DE SISTEMAS
     ══════════════════════════════════════════════════════ */
  "ingenieria:calculador_sistemas": {
    titulo: "Ayuda — Calculador de Sistemas",
    tips: [
      "Selecciona un sistema y luego un subsistema para iniciar el cálculo de despiece.",
      "Solo aparecen subsistemas activos y con receta técnica completa."
    ],
    preguntas: [
      {
        q: "¿Qué es el calculador de sistemas?",
        a: "Es la herramienta para seleccionar un sistema y subsistema, ingresar las variables del proyecto y calcular el despiece de materiales necesarios."
      },
      {
        q: "¿Por qué no veo algunos subsistemas?",
        a: "Solo se muestran subsistemas que están activos y tienen receta técnica completa. Si un subsistema no aparece, es porque está inactivo o le faltan componentes."
      },
      {
        q: "¿Puedo calcular sin asociar un proyecto?",
        a: "Sí. El despiece rápido te permite calcular sin asociar un proyecto comercial. El resultado se guarda igualmente y puedes acceder desde la lista de despieces guardados."
      }
    ]
  },

  /* ══════════════════════════════════════════════════════
     SISTEMA — crear / editar
     ══════════════════════════════════════════════════════ */
  "ingenieria:sistema_create": {
    titulo: "Ayuda — Nuevo Sistema",
    tips: [
      "Un sistema agrupa subsistemas relacionados. Por ejemplo: «Cubierta», «Muros», «Pisos».",
      "El tipo del sistema (CONSTRUCTIVO o CONSUMO) determina cómo se calculan sus subsistemas."
    ],
    preguntas: [
      {
        q: "¿Qué es un sistema?",
        a: "Un sistema es la categoría técnica que agrupa subsistemas relacionados. Ejemplo: el sistema «Cubierta» puede tener subsistemas «Cubierta simple», «Cubierta con aislación», etc."
      },
      {
        q: "¿Qué diferencia hay entre tipo CONSTRUCTIVO y CONSUMO?",
        a: "<strong>Constructivo:</strong> los subsistemas tienen receta técnica con fórmulas por componente.<br><strong>Consumo:</strong> el cálculo es por tasa de consumo por m², m³ u otra unidad. Más simple pero menos detallado."
      }
    ]
  },

  "ingenieria:sistema_update": {
    titulo: "Ayuda — Editar Sistema",
    tips: [
      "Cambiar el tipo del sistema puede afectar cómo se evalúan sus subsistemas.",
      "El código del sistema es único y se usa como referencia en fórmulas y reportes."
    ],
    preguntas: [
      {
        q: "¿Puedo cambiar el tipo del sistema?",
        a: "Sí, pero ten en cuenta que si cambias de CONSTRUCTIVO a CONSUMO (o viceversa), los subsistemas existentes pueden quedar inconsistentes. Se recomienda solo cambiar el tipo si el sistema es nuevo o no tiene despieces guardados."
      },
      {
        q: "¿El código del sistema puede repetirse?",
        a: "No. El código del sistema debe ser único en toda la base de datos. Es el identificador técnico que aparece en reportes y referencias cruzadas."
      }
    ]
  },

  /* ══════════════════════════════════════════════════════
     SOLICITUDES — crear / editar / detalle
     ══════════════════════════════════════════════════════ */
  "comercial:solicitud_create": {
    titulo: "Ayuda — Nueva Solicitud",
    tips: [
      "La referencia Salesforce es el vínculo con el CRM. Registra el número de oportunidad para trazabilidad.",
      "Adjunta los documentos del cliente (planos, especificaciones) desde el inicio para tenerlos disponibles al calcular.",
      "El estado de la solicitud avanza automáticamente a medida que se completan proyectos y despieces."
    ],
    preguntas: [
      {
        q: "¿Qué es una solicitud?",
        a: "Una solicitud es el punto de entrada de un nuevo requerimiento comercial. Agrupa los datos del cliente, los documentos adjuntos y los proyectos que se generen a partir de ella."
      },
      {
        q: "¿Es obligatoria la referencia Salesforce?",
        a: "No es obligatoria técnicamente, pero se recomienda registrarla para mantener trazabilidad entre el CRM y el sistema de presupuestos. Facilita el seguimiento de oportunidades."
      },
      {
        q: "¿Qué documentos debo adjuntar?",
        a: "Adjunta planos, especificaciones técnicas, memorias descriptivas o cualquier documento que el equipo técnico necesite para calcular el presupuesto. Los formatos aceptados son PDF, DWG, imágenes y Excel."
      },
      {
        q: "¿Puedo agregar más documentos después de crear la solicitud?",
        a: "Sí. Puedes editar la solicitud en cualquier momento y agregar o eliminar archivos adjuntos sin afectar los proyectos asociados."
      },
      {
        q: "¿Cuántos proyectos puede tener una solicitud?",
        a: "Una solicitud puede tener múltiples proyectos. Esto es útil cuando el cliente tiene varios sistemas o fases que se presupuestan por separado."
      }
    ]
  },

  "comercial:solicitud_update": {
    titulo: "Ayuda — Editar Solicitud",
    tips: [
      "Editar la solicitud no afecta los proyectos ni despieces ya calculados.",
      "Si cambias el cliente, verifica que los proyectos asociados sigan siendo correctos.",
      "Puedes agregar archivos adjuntos en cualquier momento desde esta vista."
    ],
    preguntas: [
      {
        q: "¿Editar la solicitud afecta los proyectos existentes?",
        a: "No. Los proyectos, despieces y APUs asociados a la solicitud no se ven afectados por cambios en los datos generales de la solicitud."
      },
      {
        q: "¿Puedo cambiar el cliente de una solicitud?",
        a: "Sí, pero hazlo con cuidado. Si la solicitud ya tiene proyectos avanzados, el cambio de cliente puede generar inconsistencias en reportes y documentos ya generados."
      },
      {
        q: "¿Cómo elimino un archivo adjunto?",
        a: "En la sección de archivos adjuntos, cada archivo tiene un botón de eliminar. La eliminación es inmediata al guardar el formulario."
      }
    ]
  },

  "comercial:solicitud_detail": {
    titulo: "Ayuda — Detalle de Solicitud",
    tips: [
      "Desde aquí puedes crear proyectos asociados a esta solicitud.",
      "El estado de la solicitud se actualiza automáticamente según el avance de sus proyectos.",
      "Usa el botón «Calcular despiece» del proyecto para iniciar el proceso técnico."
    ],
    preguntas: [
      {
        q: "¿Cómo creo un proyecto desde la solicitud?",
        a: "Usa el botón «Nuevo proyecto» en la sección de proyectos. El proyecto quedará asociado automáticamente a esta solicitud."
      },
      {
        q: "¿Qué significa cada estado de la solicitud?",
        a: "<strong>Solicitud:</strong> solo datos generales, sin proyectos activos.<br><strong>Despiece:</strong> al menos un proyecto tiene despieces en proceso.<br><strong>APU generado:</strong> el APU está completo.<br><strong>Cerrado:</strong> la solicitud fue aprobada o descartada."
      },
      {
        q: "¿Puedo tener múltiples proyectos activos simultáneamente?",
        a: "Sí. Una solicitud puede tener varios proyectos en diferentes estados al mismo tiempo. Cada proyecto avanza de forma independiente."
      }
    ]
  },

  /* ══════════════════════════════════════════════════════
     PROYECTOS — crear / editar
     ══════════════════════════════════════════════════════ */
  "comercial:proyecto_create": {
    titulo: "Ayuda — Nuevo Proyecto",
    tips: [
      "La TRM y el margen comercial se usan para calcular el precio final en COP. Ingrésalos correctamente.",
      "El número de personas y días de duración afecta el cálculo de mano de obra en el APU.",
      "Puedes cambiar las variables financieras después de crear el proyecto sin perder los despieces."
    ],
    preguntas: [
      {
        q: "¿Qué es un proyecto en Andicost?",
        a: "Un proyecto es la unidad de presupuestación. Agrupa los sistemas a calcular, los despieces y el APU final para un contrato o propuesta específica."
      },
      {
        q: "¿Para qué sirve la TRM?",
        a: "La TRM (Tasa Representativa del Mercado) es el tipo de cambio COP/USD que se usa para convertir precios de productos en dólares a pesos colombianos. Se registra al momento de crear el proyecto para fijarlo en el tiempo."
      },
      {
        q: "¿Qué es el AIU?",
        a: "El AIU (Administración, Imprevistos y Utilidad) es el porcentaje adicional que el contratista agrega sobre los costos directos. Se incluye en el cálculo del precio total del APU."
      },
      {
        q: "¿Qué es la exención de IVA?",
        a: "Para algunos contratos con el Estado o proyectos especiales, los materiales pueden estar exentos de IVA. Activa esta opción si el proyecto tiene ese beneficio fiscal."
      },
      {
        q: "¿Puedo cambiar el margen comercial después de crear el proyecto?",
        a: "Sí. Las variables financieras (TRM, margen, IVA, AIU) se pueden modificar en cualquier momento editando el proyecto. Los APUs ya generados conservan los valores al momento de su generación."
      }
    ]
  },

  "comercial:proyecto_update": {
    titulo: "Ayuda — Editar Proyecto",
    tips: [
      "Cambiar la TRM o el margen afecta el cálculo de nuevos APUs, no los ya generados.",
      "El nombre del proyecto aparece en todos los documentos y reportes generados.",
      "Las observaciones son visibles para todo el equipo que accede al proyecto."
    ],
    preguntas: [
      {
        q: "¿Editar el proyecto afecta los APUs ya generados?",
        a: "No. Los APUs ya generados tienen un snapshot de los parámetros al momento de su creación. Solo los nuevos APUs usarán los valores actualizados."
      },
      {
        q: "¿Puedo cambiar el cliente del proyecto?",
        a: "No directamente desde aquí. El cliente se hereda de la solicitud. Para cambiar el cliente, edita la solicitud asociada."
      },
      {
        q: "¿Para qué sirven las observaciones?",
        a: "Las observaciones son notas internas del proyecto visibles para todo el equipo. Úsalas para registrar condiciones especiales, acuerdos con el cliente o restricciones técnicas."
      }
    ]
  },

  /* ══════════════════════════════════════════════════════
     CALCULADOR — selección de subsistema y subconjuntos
     ══════════════════════════════════════════════════════ */
  "ingenieria:calculador_seleccionar": {
    titulo: "Ayuda — Configurar Despiece",
    tips: [
      "Selecciona el subsistema y marca los subconjuntos que aplican a tu proyecto.",
      "Si no seleccionas subconjuntos, el cálculo incluirá todos los componentes del subsistema.",
      "El nombre del despiece es opcional pero ayuda a identificarlo en la lista de despieces guardados."
    ],
    preguntas: [
      {
        q: "¿Qué son los subconjuntos?",
        a: "Los subconjuntos son agrupaciones de componentes dentro de un subsistema. Por ejemplo, un subsistema «Cubierta metálica» puede tener: «Estructura», «Paneles» y «Fijaciones». Puedes seleccionar solo los que apliquen a tu proyecto."
      },
      {
        q: "¿Qué pasa si no selecciono ningún subconjunto?",
        a: "Si el subsistema tiene subconjuntos definidos y no seleccionas ninguno, el cálculo usará todos los componentes del subsistema. Se mostrará una advertencia en el panel de progreso."
      },
      {
        q: "¿Para qué sirve el nombre del despiece?",
        a: "El nombre permite identificar el despiece en la lista de resultados. Es especialmente útil cuando tienes múltiples despieces del mismo subsistema para distintas zonas o fases del proyecto."
      },
      {
        q: "¿Puedo cambiar el subsistema después de calcular?",
        a: "No directamente. Si necesitas calcular con otro subsistema, vuelve al paso anterior con «Volver» y selecciona el sistema correcto. Cada combinación sistema/subsistema genera un despiece independiente."
      },
      {
        q: "¿Qué son las variables de entrada?",
        a: "Son los parámetros geométricos o técnicos del proyecto (área, largo, alto, etc.) que el calculador usará para determinar las cantidades de materiales. Las verás en el siguiente paso."
      }
    ]
  },

  /* ══════════════════════════════════════════════════════
     DEFAULT — fallback para cualquier otra pantalla
     ══════════════════════════════════════════════════════ */
  "_default": {
    titulo: "Ayuda rápida",
    tips: [
      "Navega con el menú lateral para acceder a todos los módulos.",
      "Los cambios no guardados se pierden al salir de la página. Guarda antes de navegar."
    ],
    preguntas: [
      {
        q: "¿Cómo navego entre módulos?",
        a: "Usa el menú lateral izquierdo para acceder a Solicitudes, Clientes, Calculador, Catálogos, APU, Sistemas y Configuración."
      },
      {
        q: "¿Dónde veo los proyectos activos?",
        a: "En el Dashboard o en la sección Solicitudes. Cada solicitud puede tener uno o más proyectos asociados."
      },
      {
        q: "¿Cómo busco un producto en el catálogo?",
        a: "En el módulo Catálogos puedes buscar productos por nombre, código o categoría. También puedes filtrar por proveedor."
      },
      {
        q: "¿Qué hacer si encuentro un error?",
        a: "Anota el mensaje de error y la pantalla en que ocurrió, luego repórtalo al administrador del sistema con esa información."
      },
      {
        q: "¿Cómo cierro sesión?",
        a: "Haz clic en «Cerrar sesión» en la esquina superior derecha de la pantalla, dentro del área de usuario."
      }
    ]
  }

};
