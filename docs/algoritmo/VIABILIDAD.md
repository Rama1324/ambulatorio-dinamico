# Viabilidad — Algoritmo decisor "rúbrica + fórmula fija"

Fecha: 15-10-2026. Fuentes de AWS y legales: `INVESTIGACION.md` e insumos consultados el mismo día. Cifras de costo y
latencia **medidas** en la cuenta del evento con `us.anthropic.claude-sonnet-5` (1.227 lecturas reales, ver `EVALUACION.md`).

## Decisión: **sigue con cambios**
Se construye y queda listo detrás de `ALGORITMO=rubrica`, pero **no se activa por defecto** hasta tener etiquetas
médicas (ver regla de decisión en `EVALUACION.md`). Cambios respecto de la propuesta original:
1. Salida estructurada por **tool use forzado + validación Pydantic + reintento**, porque la ficha de Sonnet 5 en Bedrock
   marca *structured outputs* como "Not Supported". Probado: 2 × 1.227 lecturas reales, 0 fallidas.
2. La pregunta del evento es por **descompensación** (como la tabla del HLF); la **gravedad la decide el código** con el
   registro citado (v1.1).
3. Ventanas de vigencia **por tipo de evento** con PMID verificado; sin fuente para ese tipo, el evento no vence.
4. Sin LACE en el orden (cascada del Ord. 536 pura).

## Técnica

| Pregunta | Respuesta | Evidencia |
|---|---|---|
| ¿Bedrock devuelve JSON confiable? | Sí, con *tool use* forzado (`toolChoice`) y esquema sin `$ref`. Con `$ref` el modelo a veces envolvía la respuesta en una clave `valor` (5 de ~15 lecturas); con esquema plano, 0 de 1.227. | Pruebas en la cuenta; ficha Sonnet 5: structured outputs "Not Supported" |
| Latencia por paciente | Por lectura (v1.1, 1.227 lecturas): mediana 3,7 s, p95 6,0 s, máx. 11,3 s. Las 3 lecturas van en paralelo: ~4–6 s por paciente. KPI de 72 h: holgadísimo; cabe en la Lambda de la API (30 s). | Medido (1.227 lecturas) |
| Cuotas | Sonnet 5 (geo): 6.000.000 tokens/min. Una evaluación usa ~9.100 tokens → ~650 evaluaciones/min antes de topar. | Service quotas de Bedrock (doc) |
| Barrido de 26.356 pacientes | No cabe en la Lambda de la API → función aparte (timeout 900 s) disparada por **EventBridge Scheduler** cada noche, por tandas. Inferencia por **lote** (50 %) no existe para Sonnet 5; sí para Haiku 4.5 y Sonnet 4.6. | `template.yaml` (`BarridoFunction`, apagada) |

## Costo (USD, tokens medidos con la rúbrica v1.1: 8.309 de entrada y 1.120 de salida por evaluación de 3 lecturas)

| Modelo | Por evaluación (3 lecturas) | Lista de 409 | Barrido de 26.356 |
|---|---|---|---|
| Sonnet 5 on-demand (perfil `us.`; 2,20 / 11,00 por M) | 0,0306 | 12,52 | 806 |
| Haiku 4.5 on-demand (1,10 / 5,50) | 0,0153 | 6,26 | 403 |
| Haiku 4.5 por lote (50 %) | 0,0076 | 3,13 | 202 |
| Haiku 5.5 on-demand (0,11 / 0,55; confirmar en consola) | 0,0015 | 0,63 | 40 |

Con disparo por evento (solo se reevalúa quien tiene un dato nuevo) el gasto diario real es una fracción del barrido.
EventBridge Scheduler: 14 millones de invocaciones gratis al mes.

## Datos
- **Tabla SSMSO 2025:** PDF oficial descargado (111 págs.); 17 diagnósticos verificados a mano en págs. 84–111.
  8 con fila "descompensado" (3 equivalencias a validar), 4 con fila candidata ambigua (solo revisión), 5 sin fila.
- **Ord. 536:** solo por fuente secundaria (Manual de Gestión de la Demanda SSMSO 2025, pág. 13). Ojo: otro documento del
  SSMSO lo cita como Ord. 539 del mismo día. **Pendiente: el texto original.**
- **Umbrales de las mediciones** (7 de 8 con fuente): HbA1c ≥ 7 % (guía GES DM2), PHQ-9 ≥ 10 (Kroenke 2001), PAS ≥ 160
  (guía GES HTA), SatO2 < 92 % EPOC (GOLD 2026), EVA ≥ 7 (Serlin 1995), glicemia (ADA). **Peak flow:** la guía usa % del
  teórico y el registro trae L/min → no aplicable, a validar.
- **Ventanas tras un evento** (12 con PMID verificado): IC y EPOC 90 d, cirrosis 90 d, angina 45 d, asma 28–30 d, DM2 30 d,
  epilepsia 30 d, depresión 30–90 d. Sin fuente: urgencia sin hospitalización en IC, EPOC y cirrosis.
- **17 pendientes para médicos** en `lambda/conocimiento/rubrica_v1.json → pendientes_medicos`.

## Clínica y legal
- **Subtriage:** el algoritmo nunca baja a nadie solo (control `bajaria` + test de propiedad sobre 150 pacientes con
  respuestas aleatorias). Si las ventanas con evidencia dicen que un evento ya no está vigente, el paciente **no baja**:
  queda para revisión humana.
- **Requiere médico:** bajar una prioridad; validar equivalencias (K70, I20, G40); filas ambiguas (I10, K21, G43, F32);
  ventanas sin fuente; definición de "refractario".
- **ISP (Regla 18):** un software que entrega información para decisiones diagnósticas o terapéuticas es clase II o más.
  Proponer con la base visible y decisión humana es más defendible que reordenar sin aprobación.
- **FDA CDS (ene-2026, referencia):** fuera de dispositivo si recomienda a un profesional, muestra la base y los datos
  faltantes y no dirige su juicio. Un reordenamiento automático se acerca a "directive".
- **Ley 21.719 (vigente 1-dic-2026):** art. 16 bis e) permite tratar datos de salud para gestión de servicios sanitarios;
  art. 8° bis da derecho a intervención humana ante decisiones automatizadas; art. 15 ter exige evaluación de impacto;
  arts. 27–28: Bedrock en EE.UU. requiere cláusulas contractuales. **Ley 20.584:** la ficha es dato sensible.
- **Consecuencia de diseño:** el algoritmo **sube solo** cuando todo cuadra (lo que piden los médicos del HLF) y **nunca
  baja solo**; cada cambio queda registrado con su base. Para datos reales: perfil `us.` (no `global.`), seudonimizar RUT y
  nombre, contrato de encargo.

## Abogado del diablo
**El mejor argumento para no construirlo:** con datos estructurados, cada pregunta de la rúbrica se puede responder con
código exacto, gratis y siempre igual. El LLM agrega costo, latencia y variabilidad sin información nueva.

**Respuesta con datos (ver `EVALUACION.md`):** el argumento se confirma para el registro actual. La rúbrica respondida por
código (brazo R) y por el LLM (E+F) dan **la misma categoría final** en los 409 pacientes (κ = 1,0). En cambio, Claude
decidiendo solo (E0) concuerda con la tabla oficial en κ 0,09: el diseño 'el LLM lee, el código decide' es el que funciona. El LLM fue **más literal** que las
reglas (detectó descompensaciones moderadas y pacientes sin ningún registro), lo que ayudó a corregir la rúbrica, pero no
cambió el resultado. El valor del LLM aparece cuando entra **texto libre** (epicrisis, informes de urgencia, interconsultas
escritas): ahí el código no puede leer y el LLM sí, con citas verificables. La base de conocimiento, la fórmula y los
controles **sí aportan** desde ya: ventanas con evidencia, umbrales con fuente y la garantía de no bajar a nadie solo.
