# Revisión adversaria del algoritmo decisor

Fecha: 15-10-2026. Un agente independiente revisó el diff completo de la rama buscando una sola cosa: caminos para que
un paciente **baje sin una persona**, o para que la demo se caiga. Reprodujo varios hallazgos con datos locales y
`ClienteFalso`. Todos quedaron corregidos y cada uno tiene su test en `tests/test_algoritmo.py`.

| # | Hallazgo | Severidad | Arreglo | Test |
|---|---|---|---|---|
| A1 | Un "no" del LLM (que no exige cita) apagaba la marca de descompensación grave sin cambiar la categoría: el paciente bajaba bajo los graves y desaparecía la alerta de 72 h. | Alta | Perder la marca grave es "bajar": control `bajaria` en cualquiera de las 3 lecturas. | `test_a1_…`, propiedad sobre 150 pacientes ahora también revisa la marca |
| A2 | Si la rúbrica marcaba grave y las reglas no, `/pacientes` caía con 500 en fechas históricas (slider). | Alta | La evaluación lleva la fecha del evento; la alerta usa esa fecha y nunca compara con un valor vacío. | `test_a2_…`, recorrido del slider en 6 fechas sin errores |
| A3 | Un ajuste humano antiguo tapaba una subida nueva de la rúbrica sin pedir revisión. | Alta/media | Si la rúbrica sube a alguien, se genera una señal que pide revisar la decisión anterior. | `test_a3_a4_…` |
| A4 | Una falla de Bedrock o una nota de la rúbrica anulaba una subida hecha por el especialista (el paciente bajaba). | Media | Las notas y controles del algoritmo se muestran pero no anulan decisiones humanas; si el algoritmo sube pero el equipo lo tenía más arriba, se conserva lo del equipo. | `test_a3_a4_…` |
| A5 | Una evaluación vieja se aplicaba a otra fecha con razones falsas ("dentro de la ventana" con 68 días); tampoco vencía al cambiar la rúbrica. | Media | Se guarda la lectura y la fórmula se **reaplica a cada fecha de corte** (sin LLM). Vigencia exige misma firma, versión de rúbrica, hash del prompt y versión de la base. | `test_a5_…`, `test_r11_…` |
| A6 | El barrido nunca reintentaba las evaluaciones fallidas y lanzaba 18 llamadas simultáneas. | Media | Reintenta las fallidas; 3 pacientes × 3 lecturas = 9 llamadas; un error en un paciente no corta el barrido. | `test_r18_…` |
| A7 | Un número mal escrito por el LLM ("9,5 %") lanzaba una excepción: 500 en el evento y barrido cortado. | Media | No se decide con lecturas de citas inválidas; la fórmula usa los valores registrados; cualquier error queda como `error_formula` y se usan las reglas. | `test_a7_…`, `test_medicion_…` |
| A8 | El LLM decidía qué es una descompensación: bastaba citar un control de rutina. | Media | El código verifica en el registro que el evento citado sea una descompensación, que la estabilización sea posterior y que la medición realmente empeore. Si no, `cita_no_respalda` / `contradice_registro` → revisión humana. | `test_a8_…` |
| A9 | "Desconocido" en la tendencia y en el cambio de tratamiento se trataba como "no". | Baja | Nota `sin_dato` para revisión. | `test_a9_…` |
| A10 | Ventanas I20 (45 d) y K70 (90 d) no salen tal cual de la fuente; la equivalencia HbA1c ≥ 7 = "DM2 descontrolada" no estaba marcada. | Media | Ventanas marcadas `a_validar_por_medico` (no vencen mientras tanto); la subida por HbA1c queda con nota `fila_a_validar`. 17 pendientes para médicos. | `test_cada_valor_…`, `test_medicion_…` |
| A11 | Las comorbilidades registradas después del corte entraban al prompt. | Baja | Se filtran por fecha. | `test_a11_…` |
| R10 | Con `ALGORITMO=reglas`, `/evaluar` y `/algoritmo/barrido` igual llamaban a Bedrock (costo sin autenticación). | Baja | Responden 409 si el algoritmo no está activo. | `test_r10_…` |
| — | La Δ de posición comparaba el orden con LACE contra el del Ord. 536. | Baja | En modo rúbrica, la posición anterior se calcula con la misma vara. | recorrido del slider |
| — | Con 3 llamadas a Bedrock, el evento podía pasar los 30 s de la API. | Baja | En la API: timeout de 12 s y sin reintento (si falla, reglas y el barrido lo reintenta de noche). | — |

**Efecto en la evaluación con Bedrock real (mismas 1.227 lecturas, desde la caché):** la categoría final de los 409
pacientes no cambió (κ con R = 1,0; 0 bajan). Aparecieron 2 inestables (con las ventanas de I20/K70 ya sin vencer, una
de las 3 lecturas dijo "desconocido") y 1 cita que no respalda (el LLM citó una saturación de 98 % como
"estabilización"): los tres quedan con las reglas y para revisión humana, que es lo correcto.
