# Evaluación offline del algoritmo decisor

Generado por `scripts/evaluar_algoritmo.py` · fecha de corte 2026-10-13 · modelo `us.anthropic.claude-sonnet-5` · 409 pacientes en lista · 3 corridas por paciente · duración 3 s.

## Brazos

- **A:** reglas actuales (`puntaje.py`).
- **R:** la misma rúbrica respondida por **código** (lector determinista) + fórmula + controles. Mide si el LLM aporta.
- **E+F:** rúbrica respondida por **Bedrock** (3 lecturas) + fórmula fija + controles. Es lo que se propone activar.
- **E+F sin controles:** lo que la fórmula habría hecho si no existieran los controles (para ver qué frenan).
- **E0:** Claude con un prompt genérico que asigna la prioridad directamente (control, sin rúbrica ni tabla).

## Resultados frente a las reglas actuales (A)

| Brazo | Alta / Media / Baja | Iguales a A | Suben | Bajan | κ ponderado vs A |
|---|---|---|---|---|---|
| A (reglas) | 92 / 186 / 131 | — | — | — | — |
| R (rúbrica por código) | 92 / 187 / 130 | 408 | 1 | 0 | 0.998 |
| **E+F (rúbrica por LLM + fórmula + controles)** | 92 / 187 / 130 | 408 | 1 | 0 | 0.998 |
| E+F sin controles | 76 / 197 / 136 | 391 | 1 | 17 | 0.922 |
| E0 (LLM decide solo) | 102 / 156 / 151 | 153 | 124 | 132 | 0.091 |

- κ entre E+F y R: **1.0**.
- Pacientes que la rúbrica movió sola (todo cuadró): **1**.
- Estabilidad: **100.0 %** de los pacientes con las 3 lecturas iguales (0.0 % inestables).
- Lecturas: 1227 · fallidas: **0** · respuesta envuelta corregida: 0.

## Controles (pacientes que NO se mueven solos y quedan para revisión humana)

Pacientes con un control bloqueante: **43**.

| Motivo | Pacientes |
|---|---|
| dato_desconocido | 42 |
| bajaria | 17 |
| discrepancia | 5 |

Ejemplos de `bajaria` (la fórmula los habría bajado; el control lo impidió):

- PAC-HLF-00002: reglas alta → rúbrica baja · la rúbrica daría baja y la categoría vigente es alta: bajar requiere un humano
- PAC-HLF-00046: reglas alta → rúbrica media · la rúbrica daría media y la categoría vigente es alta: bajar requiere un humano
- PAC-HLF-00069: reglas alta → rúbrica media · la rúbrica daría media y la categoría vigente es alta: bajar requiere un humano
- PAC-HLF-00086: reglas alta → rúbrica media · la rúbrica daría media y la categoría vigente es alta: bajar requiere un humano
- PAC-HLF-00113: reglas alta → rúbrica baja · la rúbrica daría baja y la categoría vigente es alta: bajar requiere un humano

## Lectura del LLM frente al lector por código (% de acuerdo por pregunta)

| Pregunta | Acuerdo |
|---|---|
| evento_grave | 100.0 % |
| estabilizado_despues | 90.5 % |
| tendencia_medicion | 94.4 % |
| cambio_tratamiento_por_mal_control | 57.2 % |

## Costo y latencia (medidos)

- Tokens por evaluación (3 lecturas): 8309 de entrada y 1120 de salida.
- Costo por evaluación: USD 0.0306 · esta corrida: USD 12.52 · barrido de 26.356 pacientes: USD 806.57 on-demand (el lote no existe para Sonnet 5; ver VIABILIDAD.md).
- Latencia por lectura (de la corrida con llamadas reales): ver VIABILIDAD.md (mediana 3,5 s, p95 5,5 s; las 3 lecturas van en paralelo).

## Concordancia con médicos (30 casos etiquetados)

**Pendiente:** no hay etiquetas médicas (`data/etiquetado_30.csv`). El script queda listo: calcula κ ponderado cuadrático contra cada médico y el consenso con IC95 por bootstrap, κ médico–médico, sobretriage, subtriage y errores graves. Con n = 30 el IC95 del κ es de ±0,22–0,24; para ±0,10 se necesitan 110–200 casos.

## Regla de decisión

Volver a `reglas` si E+F: (1) no supera a A por ≥ 0,10 de κ contra médicos; (2) es inestable en más del 10 % de los casos; o (3) produce algún subtriage grave.

- (1) **No evaluable sin etiquetas médicas.**
- (2) Inestabilidad: 0.0 % → cumple.
- (3) Subtriage frente a A: 0 pacientes bajan → cumple (los controles impiden bajar sin un humano).

**Recomendación:** mantener `ALGORITMO=reglas` en la demo publicada hasta tener las etiquetas de los 30 casos. E+F queda implementado, probado y medido, listo para activarse cuando el equipo lo decida.
