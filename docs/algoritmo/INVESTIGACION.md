# Investigación: LLM que lee con rúbrica cerrada + código que decide

Fecha de consulta: 2026-10-15. Convención: **[H]** = lo que dice la fuente (cifra o frase verificada al abrirla). **[I]** = inferencia nuestra. Si algo no se pudo abrir o no aparece, se dice.

---

## (a) Verificación de la tabla de evidencia

### 1. LLM con prompt genérico: κ 0,47–0,50 y sobretriaje 27–53 % en 2.000 casos de urgencia; en derivaciones ambulatorias κ 0,47–0,61 y sobretriaje 51–74 %

**Fuente A: Benning et al., medRxiv 2026 (preprint, sin revisión por pares).** "Performance evaluation and benchmarking across 16 LLMs on a real-world ED triage dataset". https://www.medrxiv.org/content/10.64898/2026.05.28.26353935v1.full
- [H] Retrospectivo, una urgencia académica alemana, 16.107 consultas adultas; los modelos se compararon en las primeras 2.000. 14 LLM (incluye Claude Opus 4.5), un "Council of Models" y un enfoque "ESI stepwise". Referencia: ESI asignado por enfermería.
- [H] κ ponderado cuadrático entre las 16 configuraciones: **0,180 a 0,747**. Sin el enfoque stepwise, el máximo es 0,516 (Council of Models). Claude Opus 4.5: **κ_qw = 0,4809** (IC95 % 0,4443–0,5163). GPT 5.1: 0,4692 en las 2.000 y 0,5031 en la cohorte completa.
- [H] "The extent of over-triage ranged from **26.7 %** in the full cohort analysis to **52.5 %** of cases assessed by Kimi 2." 13 de 16 configuraciones sobretriaron.
- [I] **Corrección:** el rango "κ 0,47–0,50" es solo el de los mejores modelos. El rango real con prompt genérico va de 0,18 a 0,52. El sobretriaje 27–53 % sí calza, pero el 26,7 % sale de la cohorte completa, no de las 2.000.
- [H] Fiabilidad publicada del ESI entre enfermeras entrenadas (citada por los autores): κ_qw 0,70–0,87.

**Fuente B: Paris et al., *Eye* 2026 (Brief Communication, con revisión por pares).** "Can large language models accurately triage oculoplastic referrals?" https://www.nature.com/articles/s41433-026-04766-w
- [H] 100 viñetas **hipotéticas** de derivación a oculoplástica; 5 LLM (ChatGPT 5.4, ChatGPT 5.5, Claude Opus 4.8 Thinking, Claude Sonnet 4.6 Thinking, Gemini 3.1 Pro Thinking); referencia: 2 cirujanos oculoplásticos.
- [H] "exact agreement rates of 24–41% and quadratic weighted κ values of **0.47–0.61**", "over-triage rates of **51–74%**". ChatGPT 5.5 κ = 0,61 con el mayor subtriaje (8 %). Claude Opus κ = 0,58.
- [H] No reporta κ entre los dos cirujanos.
- [I] La cifra es correcta, pero son viñetas de una sola subespecialidad, no derivaciones reales. Conviene decir "viñetas de derivación".

### 2. Algoritmo ESI paso a paso en el prompt: κ de 0,47 a 0,75; algoritmo local de 5 niveles: κ 0,82 en 1.960 casos; el paso a paso dio 38 % de subtriaje

- [H] medRxiv (Fuente A): "The 'ESI stepwise' approach used GPT 5.1 with a stepwise prompted decision-tree approach"; "Only a structured stepwise prompting strategy achieved substantial agreement (**κ_qw = 0.747**)". También: "it exhibited the lowest over-triage rate (**3.8 %**) but the highest under-triage rate (**38.4 %**)".
- [I] El salto "0,47 → 0,75" es válido si se compara el mismo modelo (GPT 5.1 genérico, 0,469 en las 2.000, contra GPT 5.1 stepwise, 0,747). **El 38 % de subtriaje viene de este preprint, no del artículo PMC.**
- **Fuente C: Halıcı, Cesur, Çelik. *Med Sci Monit* 2026;32:e953573 (con revisión por pares).** https://pmc.ncbi.nlm.nih.gov/articles/PMC13529296/
  - [H] Retrospectivo, urgencia terciaria, **1.960** visitas adultas, ChatGPT 5.2 por interfaz web sin ajuste fino, con un algoritmo local de 5 niveles basado en el ESI incluido en el prompt. Concordancia con el triaje de rutina: "**κ = 0.824**, 95% CI: 0.807–0.840". Repetición: κ 0,976 (500 visitas).
  - [H] Dice explícitamente que **no** hubo "iterative prompting, feedback, chain of thought elicitation". Asignación de menor agudeza que el triaje de rutina: 9,8 %.
  - [I] Lo de "algoritmo local en el prompt da κ 0,82" se sostiene. Lo de "paso a paso con 38 % de subtriaje" no corresponde a este artículo.

### 3. Extracción + reglas 99,4 % vs agente completo 99,6 %; nunca respondió con datos faltantes (el agente sí, 2,7 %); "faltante = normal" causó 8,5 % de subtriaje

**Fuente D: Vera Zúñiga, arXiv 2026 (preprint, autor independiente, Chile).** "Unknown is not normal: separating language-model extraction from rule-based decision logic for clinical risk scores". https://arxiv.org/html/2609.34112
- [H] Simulación con 6 calculadoras (HEART, CURB-65, qSOFA, PERC, Wells, Cockcroft-Gault), 1.200 casos sintéticos (200 por calculadora) y un clínico simulado; análisis aparte con casos reales de MedCalc-Bench (584 de entrenamiento, 100 de prueba). Extracción con Claude Haiku 4.5.
- [H] Política "bounds" (extracción + reglas) con clínico ideal: "matched ask-all accuracy (**99.4%** vs 99.4%) with half the questions". Agente completo: "equally accurate under ideal conditions (**99.6%**)". Con clínico ruidoso: agente 83,5 % vs bounds 87,0 % (p<0,001).
- [H] Con clínico ruidoso el agente "committed prematurely in **2.7%** of cases (bounds: 0%)".
- [H] "Treating missing as normal dropped accuracy to 91.2% and under-triaged **8.5%** of patients (95% CI 7.1–10.2)".
- [I] Las cifras calzan. Ojo: es una simulación de un solo autor, sin revisión por pares, y con calculadoras de urgencia, no con priorización ambulatoria.

### 4. En 100 corridas, 23 % de los pacientes no tuvo una categoría dominante en ≥70; el voto mayoritario no mejoró la exactitud (41,2 % → 41,5 %)

- [H] medRxiv (Fuente A): "GPT 5.1 (high reasoning effort) was queried 100 times with identical input for each of the first 100 patients", "using most deterministic available temperature settings". "23 % of patients received their most common ESI classification in fewer than 70 of 100 runs." "41.2 % for a single run and 41.5 % for majority vote over all 100 runs".
- [I] Verificado. Es un solo modelo (GPT 5.1) y 100 pacientes.

### 5. En Bedrock solo Claude 3 Haiku (us-west-2) admite fine-tuning, y requiere Provisioned Throughput

- [H] https://docs.aws.amazon.com/bedrock/latest/userguide/custom-model-fine-tuning.html: el único modelo Anthropic de la tabla es "Claude 3 Haiku | anthropic.claude-3-haiku-20240307-v1:0:200k | us-west-2".
- [H] https://docs.aws.amazon.com/bedrock/latest/userguide/deploy-custom-model-on-demand.html: la inferencia on-demand de modelos personalizados solo está disponible para Nova Lite, Nova 2 Lite, Nova Micro, Nova Pro y Llama 3.3 70B. La otra vía es "Purchase Provisioned Throughput" (https://docs.aws.amazon.com/bedrock/latest/userguide/model-customization-use.html).
- [I] Correcto: como Claude 3 Haiku no está en la lista on-demand, un Haiku ajustado solo se puede servir con Provisioned Throughput.

### 6. La inferencia batch de Bedrock cuesta 50 % menos que on-demand

- [H] Blog de AWS del 10-jun-2025 (https://aws.amazon.com/blogs/machine-learning/effective-cost-optimization-strategies-for-amazon-bedrock/): "for batch inference at a 50% lower price compared to On-Demand inference pricing", **para modelos seleccionados**.
- [H] La lista de precios de AWS (us-east-1, 12-oct-2026) lo confirma para Haiku 4.5 (1,00 → 0,50 USD/M de entrada en global) y Sonnet 4.6 (3,00 → 1,50).
- [H] **No hay precio batch** para Sonnet 5, Sonnet 5.5 ni Haiku 5.5, y esos modelos no aparecen en la tabla de modelos con batch (detalle en `viabilidad_insumos.md`).
- [I] El 50 % aplica solo a modelos con batch. Con Sonnet 5 no hay batch.

---

## (b) Trabajos similares 2023–2026

| Trabajo | Diseño | n | Métrica | κ entre humanos | Revisión por pares | URL |
|---|---|---|---|---|---|---|
| Vera Zúñiga 2026, "Unknown is not normal" | LLM extrae, reglas deciden; política explícita para datos faltantes; simulación | 1.200 casos sintéticos + 100 reales (MedCalc-Bench) | Exactitud 99,4 % (bounds) vs 99,6 % (agente); 91,2 % y 8,5 % de subtriaje si faltante = normal | No aplica | No (arXiv) | https://arxiv.org/html/2609.34112 |
| Pipeline de puntajes cardiovasculares (medRxiv, nov-2025) | Definiciones curadas + extracción con LLM + motor de fórmulas (CHA₂DS₂-VASc, HAS-BLED, EuroSCORE II) | No verificado | Según el resumen del buscador, supera al LLM solo y a los médicos. **No pude abrir el texto (HTTP 403); cifras no verificadas.** | — | No | https://www.medrxiv.org/content/10.1101/2025.11.11.25340002v1 |
| Deng et al. 2026, CPGPrompt (JAMIA) | Guías convertidas en árboles de decisión que el LLM recorre | Viñetas sintéticas en 3 dominios (n no indicado en el resumen) | Derivación binaria F1 0,85–1,00 (recall 1,00); multiclase F1 0,47 (cefalea), 0,72 (lumbago), 0,77 (próstata) | No | Sí | PMID 41746783 · https://doi.org/10.1093/jamia/ocag026 |
| Halıcı et al. 2026 (Med Sci Monit) | Algoritmo local de 5 niveles en el prompt, ChatGPT 5.2 | 1.960 visitas a urgencia | κ_qw 0,824; repetición κ 0,976 | No | Sí | https://pmc.ncbi.nlm.nih.gov/articles/PMC13529296/ |
| Benning et al. 2026 (medRxiv) | 16 configuraciones de LLM; prompt genérico vs árbol ESI paso a paso | 2.000 (16.107 en total) | κ_qw 0,18–0,52 genérico; 0,747 paso a paso (subtriaje 38,4 %) | Citado: ESI 0,70–0,87 | No | https://www.medrxiv.org/content/10.64898/2026.05.28.26353935v1.full |
| Clackett et al. 2026 (Scott Med J) | 3 LLM, prompts con guías clínicas y ejemplos para validar derivaciones ambulatorias a RM lumbar | 120 derivaciones | Exactitud 0,86 (Claude Opus, prompt completo); κ con radiólogo 0,76 (resultado) y 0,68 (contraindicaciones); todos detectaron los urgentes | No en el resumen | Sí | PMID 41989203 · https://doi.org/10.1177/00369330261441582 |
| Roberts 2026 (medRxiv) | 23 LLM, derivaciones a reumatología, prompt simple vs avanzado (criterios australianos, CoT, ejemplos) | 20 derivaciones construidas | Sin κ LLM–consenso. La varianza entre modelos bajó de 0,014 a 0,003 con el prompt avanzado y persistió subtriaje | Cita κ_w ≈ 0,6 entre clínicos (Harding 2010/2011) | No | https://www.medrxiv.org/content/10.64898/2026.08.05.26359488v1.full |
| Paris et al. 2026 (Eye) | 5 LLM, derivaciones a oculoplástica | 100 viñetas | κ_qw 0,47–0,61; sobretriaje 51–74 % | No reportado | Sí | https://www.nature.com/articles/s41433-026-04766-w |
| Nedos et al. 2026 (J Clin Med) | 7 LLM en urgencia; incluye derivación a policlínico | 39.375 | ESI κ_w ≈ 0,467 (Claude Sonnet 4, DeepSeek); derivación a policlínico 67,1 %, κ 0,619 (Claude Sonnet 4) | No | Sí | PMID 41753200 · https://www.mdpi.com/2077-0383/15/4/1512 (403 al abrir; datos del resumen en Europe PMC) |
| Liu et al. 2025/2026, "Do LLMs Triage Like Clinicians?" | Derivación ambulatoria a especialidad, estática vs diálogo | No visible en el resumen | Cualitativa: en derivación estática los LLM ofrecen "limited advantages" frente a clasificadores tradicionales; en diálogo los superan | No | No (arXiv) | https://arxiv.org/abs/2503.08292 |
| Abdel-Hafez et al. 2023 (Front Digit Health) | ML (no LLM) sobre Clinical Prioritisation Criteria de Queensland, derivaciones a ORL | 17.378 | 53,8 % de acuerdo con la categoría | No | Sí | https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10642163/ |
| Fung et al. 2026 (Front Health Serv) | Revisión sistemática de NLP para triar derivaciones ambulatorias | 10 estudios | 7 de 10 informan "high levels of accuracy"; sin métrica agregada | — | Sí | PMID 42065034 |
| Foley et al. 2026 (PLoS One) | Protocolo de revisión sistemática: IA para triar cartas de derivación | — | Sin resultados | — | Sí (protocolo) | https://doi.org/10.1371/journal.pone.0355476 |

**Sistemas de priorización dinámica o por criterios (sin LLM):**

| Sistema | Qué es | Evidencia verificada | URL |
|---|---|---|---|
| WCWL (Canadá occidental) | Criterios con puntaje para cirugía general, cadera/rodilla, cataratas, RM y salud mental infantil | [H] Cirugía general: 561 pacientes, R² ajustado 64,1 %; fiabilidad "appeared to be good" sin κ/ICC en el resumen. Puntaje de derivación cadera/rodilla para médicos de APS: ICC test-retest 0,84 e intraevaluador 0,79 (De Coster 2007). [H] RM: la mayoría de los ítems con fiabilidad interevaluador pobre (según el resumen del buscador; no abrí el artículo). | https://www.canjsurg.ca/content/45/5/351.abstract · PMID 17378864 |
| CPAC (Nueva Zelanda) | Criterios de priorización quirúrgica | [H] Doughty 2005: 38 traumatólogos, 50 viñetas; "the extent of inter-surgeon variability was striking", menor con el sistema integrado (ISS); **sin κ en el resumen**. MacCormick y Parry 2006: 60 cirujanos generales, "Agreement between surgeons was poor (ra=0.48)". | https://boneandjoint.org.uk/Article/10.1302/0301-620X.87BSUPP_I.0870028 · PMID 16751324 |
| Cataluña (CAHTA) | Puntajes de prioridad para artroplastia y cataratas | [H] Allepuz 2008: fiabilidad interobservador (ICC) 0,79 para artroplastia y 0,79 para cataratas. [H] Tebé 2011, evaluación del impacto: el orden de intervención "appears to not differ from a first in first out (FIFO) system" (implementación pobre). | https://pmc.ncbi.nlm.nih.gov/articles/PMC2373288 · https://database.inahta.org/article/11783 |
| MINSAL, Sistema de Gestión de Pacientes con Enfoque de Riesgo (2019) | Índice con algoritmo que ordena dentro de cada grupo por riesgo clínico (comorbilidades, hospitalizaciones); el médico priorizador decide. Piloto en SS Valparaíso, Metropolitano Sur, **Sur Oriente** y Occidente. | [H] Sin resultados publicados en la nota. | https://www.minsal.cl/minsal-presenta-sistema-de-gestion-de-pacientes-con-enfoque-de-riesgo-para-apoyar-priorizacion-de-las-listas-de-espera/ |
| MINSAL, Ord. 536 (21-mar-2025) | Orden: 1) criterio médico (progresión, complicaciones, discapacidad); 2) grupos de protección especial (NNA bajo protección del Estado, PRAIS, Valech, Rettig); 3) antigüedad > 1 año | [H] Citado como "Ord. 536" en el Manual de Gestión de la Demanda del SSMSO y como "**Ordinario C N° 539**" del 21-mar-2025 en el documento de priorización del SSMSO. **El número difiere entre los documentos; no encontré el ordinario original.** | https://redsalud.ssmso.cl/wp-content/uploads/2026/01/Manual-de-Gestion-de-la-Demanda-SSMSO.pdf |
| SSMSO, Priorización de diagnósticos No GES (jun-2025, Res. Ex. 1232 del 02-07-2025) | Tabla por establecimiento × especialidad × diagnóstico → Alta/Mediana/Baja, definida por subdirectores médicos y jefes de especialidad; incluye al Hospital Dra. Eloísa Díaz (p. 84) | [H] Documento revisado | https://redsalud.ssmso.cl/wp-content/uploads/2025/07/PRIORIZACION-SSMSO-02.07.2025-I-ETAPA.pdf |
| PrimedIA (UCM, Fondecyt) | IA "explicable" de riesgo y vulnerabilidad para listas quirúrgicas No GES; piloto en ORL del Hospital San Borja Arriarán (mar-2026) | [H] Sin resultados cuantitativos; el modelo no se describe. | https://www.tourinnovacion.cl/tecnologia-ciencia/avanza-implementacion-de-sistema-con-ia-para-optimizar-la-priorizacion-de-cirugias/ |
| Gobierno de Chile, Presupuesto 2027 | Anuncio de "inteligencia artificial para priorizar la atención de los pacientes de mayor gravedad" junto a una ficha clínica compartida | [H] Sin detalle técnico (1-oct-2026) | https://medicalpress.cl/2026/10/01/presupuesto-2027-gobierno-apuesta-por-ia-y-ficha-clinica-compartida-publico-privada-para-ordenar-las-listas-de-espera/ |

---

## (c) κ entre médicos para priorizar listas de espera ambulatorias

No encontré un κ médico–médico publicado específicamente para la **priorización de interconsultas a consulta nueva de especialidad** (el caso HLF). Lo más cercano que verifiqué:

| Contexto | Cifra [H] | Fuente |
|---|---|---|
| Prioridad de endoscopía: médico de APS vs especialista (Italia, 438 pacientes ambulatorios) | Gastroscopía κ 0,31 (**κ_w 0,47**); colonoscopía κ 0,44 (**κ_w 0,46**) | Mariotti et al., J Health Serv Res Policy 2008. PMID 18573763 |
| Triaje de derivaciones a rehabilitación comunitaria (214 derivaciones) | **κ_w 0,60** global; 0,25 en postoperatorio ortopédico; desacuerdo en 30 % | Harding et al., Clin Rehabil 2010. PMID 20576668 |
| Triaje de derivaciones musculoesqueléticas de APS con herramienta (29 clínicos, 5 casos) | Fleiss **κ 0,385**; rango por caso −0,014 a 0,786 | Shorthouse et al., Prim Health Care Res Dev 2023. https://pmc.ncbi.nlm.nih.gov/articles/PMC10790367/ |
| Priorización quirúrgica de cirujanos generales (NZ) | Acuerdo "poor (ra=0.48)" | MacCormick y Parry, Med Decis Making 2006. PMID 16751324 |
| Instrumentos con puntaje (Cataluña) | ICC interobservador 0,79 | Allepuz et al., BMC HSR 2008 |
| Puntaje de derivación WCWL cadera/rodilla | ICC test-retest 0,84; intraevaluador 0,79 (en el resumen no aparece el interevaluador) | De Coster et al., J Eval Clin Pract 2007. PMID 17378864 |
| CPAC (NZ) | Variabilidad "striking" entre cirujanos; sin κ en el resumen | Doughty et al., 2005 |
| Referencia de urgencia (ESI) | κ_qw 0,70–0,87 entre enfermeras entrenadas (citado) | Benning et al., 2026 |

[I] Entre clínicos que priorizan derivaciones sin un instrumento estructurado, el acuerdo suele quedar en κ_w ≈ 0,45–0,60. Con instrumento de puntaje sube a ICC ≈ 0,8. **La meta del hospital (κ ≥ 0,70 con el experto) está por encima del acuerdo habitual entre humanos sin rúbrica**, así que la comparación justa es contra dos médicos usando la misma tabla del SSMSO.

---

## (d) Conclusiones para el diseño

1. **Rúbrica explícita en el prompt; el LLM no clasifica libremente.** Con prompt genérico el κ queda en 0,18–0,61. Con un algoritmo local en el prompt sube a 0,75–0,82 (Benning, Halıcı). Nuestra separación "el LLM contesta sí/no/desconocido por criterio y el código mapea a la categoría" lleva esto al extremo: el LLM nunca elige la categoría.
2. **"Desconocido" es un valor de primera clase y nunca se trata como "no".** Tratar faltante como normal produjo 8,5 % de subtriaje (Vera Zúñiga). La función pura debe tener una regla explícita para "desconocido" (por ejemplo, no bajar de categoría y marcar "requiere revisión") y la interfaz debe mostrar qué faltó (coincide con el criterio 4 d de la FDA).
3. **Vigilar el subtriaje, no solo κ.** El árbol paso a paso llegó a κ 0,75 pero con 38,4 % de subtriaje. Hay que reportar sensibilidad para la categoría Alta y la tasa de subtriaje junto al κ ponderado.
4. **No confiar en el voto mayoritario para estabilizar.** 23 % de los casos fue inestable entre corridas y votar no mejoró la exactitud. Mejor: temperatura mínima, preguntas atómicas, cache del resultado por versión de la ficha y que la inestabilidad cuente como señal de revisión humana.
5. **Cada "sí" debe venir con cita textual de la ficha.** Es lo que permite al clínico revisar la base de la recomendación y la auditoría. En Bedrock, la función nativa de *citations* de Anthropic es incompatible con *structured outputs*: la cita va como campo del JSON (ver viabilidad).
6. **La comparación honesta para la meta κ ≥ 0,70 es contra dos médicos con la misma tabla SSMSO.** No hay κ publicado entre médicos para interconsultas ambulatorias; la literatura cercana da 0,45–0,60 sin instrumento. Conviene medir κ médico–médico en una muestra piloto antes de prometer la cifra.
7. **Mismo orden que el Ord. 536/539.** Primero criterio clínico (tabla SSMSO), después grupos de protección y después antigüedad > 1 año. Es determinista y explicable. El número exacto del ordinario debe confirmarse con el hospital (536 vs 539).
8. **No hacer fine-tuning.** En Bedrock solo Claude 3 Haiku es ajustable y exige Provisioned Throughput. La rúbrica en el prompt es la palanca con mejor evidencia.

---

## Referencias

1. Benning L, et al. Performance evaluation and benchmarking across 16 LLMs on a real-world ED triage dataset. medRxiv 2026 (preprint). https://www.medrxiv.org/content/10.64898/2026.05.28.26353935v1.full
2. Paris J, Agarwal A, Chan WO, Selva D, et al. Can large language models accurately triage oculoplastic referrals? Eye 2026. https://www.nature.com/articles/s41433-026-04766-w
3. Halıcı A, Cesur E, Çelik F. Subgroup Differences in Agreement Between an Algorithm Guided Large Language Model and Routine Emergency Department Triage. Med Sci Monit 2026;32:e953573. https://pmc.ncbi.nlm.nih.gov/articles/PMC13529296/
4. Vera Zúñiga N. Unknown is not normal: separating language-model extraction from rule-based decision logic for clinical risk scores. arXiv 2026 (preprint). https://arxiv.org/html/2609.34112
5. AWS. Customize a model with fine-tuning in Amazon Bedrock. https://docs.aws.amazon.com/bedrock/latest/userguide/custom-model-fine-tuning.html
6. AWS. Deploy a custom model for on-demand inference. https://docs.aws.amazon.com/bedrock/latest/userguide/deploy-custom-model-on-demand.html
7. AWS ML Blog. Effective cost optimization strategies for Amazon Bedrock (10-jun-2025). https://aws.amazon.com/blogs/machine-learning/effective-cost-optimization-strategies-for-amazon-bedrock/
8. Roberts L. Automating the triage of rheumatology outpatient referrals… medRxiv 2026 (preprint). https://www.medrxiv.org/content/10.64898/2026.08.05.26359488v1.full
9. Clackett W, et al. Evaluation of large language models with clinical guidance for vetting outpatient MRI lumbar spine referrals. Scott Med J 2026. PMID 41989203.
10. Deng R, et al. CPGPrompt: translating clinical guidelines into LLM-executable decision support. JAMIA 2026. PMID 41746783.
11. Nedos I, et al. Is Artificial Intelligence Ready for Emergency Department Triage? J Clin Med 2026. PMID 41753200.
12. Liu X, et al. Do LLMs Triage Like Clinicians? A Dynamic Study of Outpatient Referral. arXiv 2025. https://arxiv.org/abs/2503.08292
13. Abdel-Hafez A, et al. Artificial intelligence in medical referrals triage based on Clinical Prioritization Criteria. Front Digit Health 2023. https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10642163/
14. Fung AL, et al. Systematic literature review… NLP to triage outpatient referrals. Front Health Serv 2026. PMID 42065034.
15. Foley J, et al. AI models for interpretation and triage of clinical referral letters: protocol. PLoS One 2026. https://doi.org/10.1371/journal.pone.0355476
16. Taylor MC, Hadorn DC. Developing priority criteria for general surgery: results from the WCWL Project. Can J Surg 2002;45:351-7. https://www.canjsurg.ca/content/45/5/351.abstract
17. De Coster C, et al. The WCWL Project: development of a priority referral score for hip and knee arthroplasty. J Eval Clin Pract 2007. PMID 17378864.
18. Doughty C, et al. Reliability of Clinical Priority Tools in Orthopaedic Surgery. Orthop Proc 2005;87-B(Supp I):28. https://boneandjoint.org.uk/Article/10.1302/0301-620X.87BSUPP_I.0870028
19. MacCormick AD, Parry BR. Judgment analysis of surgeons' prioritization of patients for elective general surgery. Med Decis Making 2006. PMID 16751324.
20. Allepuz A, et al. Prioritisation of patients on waiting lists for hip and knee arthroplasties and cataract surgery: instruments validation. BMC Health Serv Res 2008;8:76. https://pmc.ncbi.nlm.nih.gov/articles/PMC2373288
21. Tebé C, et al. Impacto de un sistema de priorización… artroplastias y cataratas (Cataluña). https://database.inahta.org/article/11783
22. Mariotti G, et al. Improving the appropriateness of referrals and waiting times for endoscopic procedures. J Health Serv Res Policy 2008;13:146-51. PMID 18573763.
23. Harding KE, et al. Prioritizing patients for Community Rehabilitation Services: do clinicians agree on triage decisions? Clin Rehabil 2010;24:929-37. PMID 20576668.
24. Shorthouse FM, et al. Agreement and consistency in the triaging of MSK primary care referrals… Prim Health Care Res Dev 2023;24:e63. https://pmc.ncbi.nlm.nih.gov/articles/PMC10790367/
25. MINSAL. Sistema de Gestión de Pacientes con Enfoque de Riesgo (4-feb-2019). https://www.minsal.cl/minsal-presenta-sistema-de-gestion-de-pacientes-con-enfoque-de-riesgo-para-apoyar-priorizacion-de-las-listas-de-espera/
26. SSMSO. Manual de Gestión de la Demanda (2026). https://redsalud.ssmso.cl/wp-content/uploads/2026/01/Manual-de-Gestion-de-la-Demanda-SSMSO.pdf
27. SSMSO. Priorización Diagnósticos Especialidades Médicas y Odontológicas No GES, v1.0, jun-2025. https://redsalud.ssmso.cl/wp-content/uploads/2025/07/PRIORIZACION-SSMSO-02.07.2025-I-ETAPA.pdf
28. Tour Innovación. PrimedIA, UCM (19-mar-2026). https://www.tourinnovacion.cl/tecnologia-ciencia/avanza-implementacion-de-sistema-con-ia-para-optimizar-la-priorizacion-de-cirugias/
29. Medical Press. Presupuesto 2027: IA y ficha clínica compartida (1-oct-2026). https://medicalpress.cl/2026/10/01/presupuesto-2027-gobierno-apuesta-por-ia-y-ficha-clinica-compartida-publico-privada-para-ordenar-las-listas-de-espera/

**No verificado o no abierto:** el texto completo del pipeline cardiovascular de medRxiv (HTTP 403); el texto completo de Nedos 2026 en MDPI (403; se usó el resumen de Europe PMC); el texto original del Ord. 536/539 del MINSAL; los κ de los artículos WCWL de RM y cataratas (solo resúmenes); los κ numéricos del CPAC.
