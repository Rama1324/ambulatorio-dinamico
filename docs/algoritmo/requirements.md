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

**Revisión humana:** solo cuando el resultado verificado BAJARÍA a alguien (`requiere_revision`). Los controles técnicos
(cita inválida o que no respalda, lecturas distintas, falla de Bedrock o de la fórmula) usan las reglas y quedan
registrados (`respaldo_reglas`), sin pedirle nada al equipo clínico. En el registro: 2 de 409 pacientes.

| # | Requisito (EARS) | Test |
|---|---|---|
| R1 | CUANDO llega un evento nuevo de un paciente y `ALGORITMO=rubrica`, EL SISTEMA DEBE reevaluar a ese paciente en el mismo momento (muy por debajo de 72 h) y registrar la evaluación. | `test_evento_nuevo_dispara_la_reevaluacion` |
| R2 | CUANDO una `cita` del LLM no existe en el historial (o una respuesta "sí" no trae cita), EL SISTEMA DEBE mantener la categoría de las reglas y marcar `requiere_revision` con motivo `cita_invalida`. CUANDO la cita existe pero no respalda lo afirmado (un control de rutina citado como descompensación, una estabilización anterior al evento, "no se estabilizó" contra un registro que sí), motivo `cita_no_respalda` / `contradice_registro`. | `test_cita_inexistente_mantiene_reglas_y_pide_revision`, `test_si_sin_cita_es_cita_invalida`, `test_a8_el_codigo_verifica_lo_que_cita_el_llm` |
| R3 | CUANDO el resultado bajaría la categoría **o quitaría la marca de descompensación grave**, EL SISTEMA DEBE mantener lo vigente y pedir revisión humana (`bajaria`). Las notas o fallas del algoritmo no anulan una decisión humana. | `test_bajar_siempre_requiere_humano`, `test_evento_fuera_de_ventana_no_mantiene_descompensado`, `test_propiedad_ninguna_respuesta_baja_a_alguien_sin_humano`, `test_propiedad_nunca_se_pierde_la_marca_grave_sin_humano`, `test_a1_…`, `test_a3_a4_…` |
| R4 | CUANDO 3 corridas no coinciden en la categoría, EL SISTEMA DEBE marcar `requiere_revision` con motivo `inestable` y usar las reglas. | `test_tres_corridas_distintas_es_inestable` |
| R5 | CUANDO Bedrock falla, excede el tiempo o devuelve JSON inválido, o la fórmula lanza un error, EL SISTEMA DEBE usar las reglas actuales y registrarlo (`fallo_llm` / `error_formula`). | `test_bedrock_falla_usa_reglas_y_lo_registra`, `test_json_invalido_es_fallo`, `test_a7_una_excepcion_en_la_formula_cae_a_las_reglas`, `test_a2_marca_grave_sin_fecha_no_tumba_la_lista` |
| R6 | CUANDO un dato es "desconocido", EL SISTEMA NO DEBE tratarlo como normal: en el evento o la estabilización lo responde el registro estructurado (nota `resuelto_con_registro`); en la tendencia o el cambio de tratamiento deja la nota `sin_dato`. | `test_un_desconocido_no_es_normal_lo_responde_el_registro`, `test_a9_desconocido_en_las_otras_preguntas_no_es_no` |
| R7 | EL SISTEMA DEBE adjuntar a cada razón su `fuente` (página SSMSO, numeral del Ord. 536, PMID o guía). | `test_00002_sube_a_alta_por_angina_inestable` |
| R8 | CUANDO la categoría de la rúbrica difiere en más de 1 nivel de la de las reglas, EL SISTEMA DEBE pedir revisión (`discrepancia`). | `test_discrepancia_de_mas_de_un_nivel_pide_revision` |
| R9 | EL SISTEMA DEBE ordenar con la cascada del Ord. 536 (criterio médico → grupo de protección → antigüedad > 1 año → llegada), sin LACE. | `test_orden_536_no_usa_lace` |
| R10 | CUANDO `ALGORITMO=reglas`, LA API DEBE responder exactamente igual que antes; las rutas nuevas responden 409 y no llaman a Bedrock. | `test_api_con_rubrica_…`, `test_r10_con_reglas_las_rutas_nuevas_no_llaman_a_bedrock` + comparación de `/pacientes` antes/después |
| R11 | CUANDO `ALGORITMO=rubrica`, cada fecha de corte DEBE usar la evaluación vigente (mismo historial, misma rúbrica, misma base de conocimiento, hecha a un corte ≤) y **volver a aplicar la fórmula a esa fecha** (sin LLM); sin evaluación vigente, las reglas, marcado `reglas (sin evaluación vigente)`. | `test_a5_la_evaluacion_se_reaplica_…`, `test_r11_cada_fecha_de_corte_usa_su_evaluacion_vigente` |
| R12 | Cada valor de la base de conocimiento DEBE tener `fuente` o estado `a_validar_por_medico`; sin fuente directa (o extrapolado, como las ventanas de I20 y K70) se usa la opción conservadora (no vence, no baja a nadie). | `test_cada_valor_tiene_fuente_o_esta_a_validar` |
| R13 | La medición clave solo sube de categoría si su umbral tiene fuente **y el registro confirma** que empeora y que el último valor supera el umbral (el código usa los valores registrados, no los que escribe el LLM); la equivalencia queda marcada `fila_a_validar`. | `test_medicion_sube_solo_con_umbral_con_fuente_y_si_el_registro_lo_confirma` |
| R14 | Ninguna etapa del LLM ve etiquetas médicas (`prioridad_medico`, `comentario`, clave del motor) ni datos posteriores al corte. | `test_prompt_no_ve_etiquetas_medicas`, `test_a11_comorbilidad_registrada_despues_del_corte_no_entra_al_prompt` |
| R15 | Fallecidos y atendidos no se evalúan (salen de la lista). | `test_00009_fallecido_sale_de_la_lista` |
| R16 | La salida del LLM es JSON validado con Pydantic; si viene envuelta en una sola clave con las preguntas adentro, se desenvuelve y se registra. | `test_esquema_sin_referencias_y_envoltorio_corregido` |
| R17 | Cada evaluación DEBE guardar respuestas, citas, versión de rúbrica y de base de conocimiento, id del modelo, hash del prompt, controles y categoría final. | `algoritmo.evaluar_paciente` (campos verificados en `test_api_con_rubrica_…`) |
| R18 | Un barrido periódico DEBE reevaluar a quienes no tienen evaluación vigente **o cuya última evaluación falló** (EventBridge Scheduler → `barrido_handler`); un error en un paciente no corta el barrido. | `test_r18_barrido_reintenta_las_fallidas` (despliegue pendiente de aprobación) |
