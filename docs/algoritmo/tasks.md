# Tareas — Algoritmo decisor

| # | Tarea | Requisitos | Estado |
|---|---|---|---|
| T1 | Extraer y verificar filas de la Tabla SSMSO 2025 (págs. 84–111) para los 17 diagnósticos | R7, R12 | Hecho (`ssmso_hlf_2025.json`) |
| T2 | Cascada Ord. 536 sin LACE | R9 | Hecho (`ord536.json`, `decisor.clave_orden_536`) |
| T3 | Evidencia PubMed (ventanas) y guías (umbrales), PMID verificados | R12, R13 | Ver `pubmed_evidencia.json` / `guias_umbrales.json` |
| T4 | Consolidar `rubrica_v1.json` con pendientes para médicos | R12 | Hecho (`scripts/consolidar_rubrica.py`) |
| T5 | Esquemas Pydantic, historial, prompt, validador de citas | R2, R14, R16 | Hecho (`rubrica.py`) |
| T6 | Fórmula pura rúbrica → categoría | R3, R6, R7, R13 | Hecho (`decisor.py`) |
| T7 | Cliente Bedrock (tool use, timeouts) + cliente falso | R5 | Hecho |
| T8 | Controles | R2–R6, R8 | Hecho (`controles.py`) |
| T9 | Orquestador con 3 corridas en paralelo y registro auditable | R4, R17 | Hecho (`algoritmo.py`) |
| T10 | Integración en `app.py` detrás de `ALGORITMO`; evaluación al llegar un evento | R1, R10, R11 | Hecho |
| T11 | Barrido (`barrido_handler`) + EventBridge Scheduler en `template.yaml` | R18 | Código hecho; despliegue pendiente de aprobación |
| T12 | Evaluación offline (A, R, E+F, E0) y kappa con IC95 | — | Hecho (`scripts/evaluar_algoritmo.py`, `EVALUACION.md`) |
| T13 | Revisión adversaria con contexto limpio | todos | Ver `EVALUACION.md` |
