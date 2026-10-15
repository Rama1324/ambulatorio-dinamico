# Requisitos — Algoritmo decisor "rúbrica + fórmula fija" (E+F)

Rama `feat/algoritmo-decisor`. Variable `ALGORITMO=reglas|rubrica` (por defecto `reglas`).
Criterios en formato EARS. Cada uno indica el test que lo cubre (`tests/test_algoritmo.py`, salvo que se diga otra cosa).

## Historias de usuario
- **H1.** Como especialista del HLF quiero que la prioridad de un paciente se reevalúe sola cuando llega un evento nuevo,
  para no depender de que alguien revise la lista a mano.
- **H2.** Como jefatura quiero que ningún paciente baje de prioridad sin una persona que lo decida, para no generar
  subtriage.
- **H3.** Como equipo clínico quiero ver por qué cambió cada prioridad, con la fuente de cada paso, para poder confiar y
  auditar.
- **H4.** Como equipo técnico quiero que el algoritmo nuevo no afecte lo que ya funciona hasta que se decida activarlo.

## Criterios de aceptación

| # | Requisito (EARS) | Test |
|---|---|---|
| R1 | CUANDO llega un evento nuevo de un paciente y `ALGORITMO=rubrica`, EL SISTEMA DEBE reevaluar a ese paciente en el mismo momento (muy por debajo de 72 h) y registrar la evaluación. | `test_evento_nuevo_dispara_la_reevaluacion` |
| R2 | CUANDO una `cita` del LLM no existe en el historial (o una respuesta "sí" no trae cita), EL SISTEMA DEBE mantener la categoría de las reglas y marcar `requiere_revision` con motivo `cita_invalida`. | `test_cita_inexistente_mantiene_reglas_y_pide_revision`, `test_si_sin_cita_es_cita_invalida` |
| R3 | CUANDO el resultado bajaría la categoría, EL SISTEMA DEBE mantener la categoría vigente y pedir revisión humana (`bajaria`). | `test_bajar_siempre_requiere_humano`, `test_evento_fuera_de_ventana_no_mantiene_descompensado`, `test_propiedad_ninguna_respuesta_baja_a_alguien_sin_humano` |
| R4 | CUANDO 3 corridas no coinciden en la categoría, EL SISTEMA DEBE marcar `requiere_revision` con motivo `inestable` y usar las reglas. | `test_tres_corridas_distintas_es_inestable` |
| R5 | CUANDO Bedrock falla, excede el tiempo o devuelve JSON inválido, EL SISTEMA DEBE usar las reglas actuales y registrarlo (`fallo_llm`). | `test_bedrock_falla_usa_reglas_y_lo_registra`, `test_json_invalido_es_fallo` |
| R6 | CUANDO un dato es "desconocido", EL SISTEMA NO DEBE tratarlo como normal: marca `dato_desconocido` y no mueve al paciente. | `test_un_desconocido_no_es_normal` |
| R7 | EL SISTEMA DEBE adjuntar a cada razón su `fuente` (página SSMSO, numeral del Ord. 536, PMID o guía). | `test_00002_sube_a_alta_por_angina_inestable` |
| R8 | CUANDO la categoría de la rúbrica difiere en más de 1 nivel de la de las reglas, EL SISTEMA DEBE pedir revisión (`discrepancia`). | `test_discrepancia_de_mas_de_un_nivel_pide_revision` |
| R9 | EL SISTEMA DEBE ordenar con la cascada del Ord. 536 (criterio médico → grupo de protección → antigüedad > 1 año → llegada), sin LACE. | `test_orden_536_no_usa_lace` |
| R10 | CUANDO `ALGORITMO=reglas`, LA API DEBE responder exactamente igual que antes. | `test_api_con_rubrica_aplica_evaluacion_vigente_y_reglas_sin_cambios` + comparación de `/pacientes` antes/después (ver EVALUACION.md) |
| R11 | CUANDO `ALGORITMO=rubrica` y un paciente no tiene evaluación vigente (cambió su historial), EL SISTEMA DEBE usar las reglas y marcarlo `reglas (sin evaluación vigente)`. | `test_api_con_rubrica_aplica_evaluacion_vigente_y_reglas_sin_cambios` |
| R12 | Cada valor de la base de conocimiento DEBE tener `fuente` o estado `a_validar_por_medico`; sin fuente se usa la opción conservadora (no baja a nadie). | `test_cada_valor_tiene_fuente_o_esta_a_validar` |
| R13 | La medición clave solo sube de categoría si su umbral tiene fuente; si no, solo genera revisión. | `test_medicion_sube_solo_con_umbral_con_fuente` |
| R14 | Ninguna etapa del LLM ve etiquetas médicas (`prioridad_medico`, `comentario`, clave del motor). | `test_prompt_no_ve_etiquetas_medicas` |
| R15 | Fallecidos y atendidos no se evalúan (salen de la lista). | `test_00009_fallecido_sale_de_la_lista` |
| R16 | La salida del LLM es JSON validado con Pydantic; si viene envuelta en una sola clave con las preguntas adentro, se desenvuelve y se registra. | `test_esquema_sin_referencias_y_envoltorio_corregido` |
| R17 | Cada evaluación DEBE guardar respuestas, citas, versión de rúbrica y de base de conocimiento, id del modelo, hash del prompt, controles y categoría final. | `algoritmo.evaluar_paciente` (campos verificados en `test_api_con_rubrica_…`) |
| R18 | Un barrido periódico DEBE reevaluar a quienes no tienen evaluación vigente (EventBridge Scheduler → `barrido_handler`). | `app.barrido` (probado en local; despliegue pendiente de aprobación) |
