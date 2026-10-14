# Contexto del proyecto — Ambulatorio Dinámico HLF

## Qué es
Hackatón AWS Breaking Barriers Chile 2026 (14–16 oct, FCFM UChile). Desafío del Hospital Clínico Dra. Eloísa Díaz La Florida (HLF): **priorización clínica evolutiva** de la lista de espera de consultas de especialidad.
Frase del hospital: "La lista de espera es una foto; la salud de las personas, una película."
Problema: la prioridad se asigna una vez y queda congelada, aunque el paciente empeore mientras espera (urgencias, hospitalizaciones, exámenes alterados).

## Plazos (no negociables)
- Miércoles 21:00: todo deployado de punta a punta, aunque sea feo.
- Jueves 15:00: se congelan las features. Después solo pulir, ensayar y grabar el video de respaldo.
- Viernes 10:15: cierre del código. 12:00 pre-evaluación técnica. 15:00 pitch de los finalistas.
Prioridad absoluta: **demo que funcione** > features nuevas.

## Rúbrica
Innovación técnica 25% · Impacto social 25% · Factibilidad y sustentabilidad 20% · Escalabilidad 15% · Presentación 15%.
KPIs del hospital: reevaluación < 72 h tras un evento clínico · concordancia con experto kappa ≥ 0,70 · cobertura 100% de la lista con criterio común.

## Principios de diseño (obligatorios)
1. **El puntaje lo calculan reglas explicables, NO el LLM.** El LLM (Amazon Bedrock) solo redacta la explicación a partir de las razones del puntaje.
2. **La herramienta propone y explica; el equipo clínico decide** (confirmar/ajustar, con trazabilidad).
3. Fallecidos → salen de la lista (control de exclusión).
4. Las inasistencias NO bajan la prioridad clínica; solo encienden la bandera `riesgo_inasistencia` para la gestión de box.
5. Recalcular a una `fecha_corte` usando solo registros con fecha ≤ corte.

## Datos
Dataset sintético del hospital: 500 pacientes, fecha de referencia 2026-10-13, 7 especialidades. Archivo principal: `perfiles.json` (un objeto por paciente con lista_espera, eventos_clinicos, mediciones y citaciones anidados). Va en S3, **nunca en el repo** (`data/` está en .gitignore).
Pacientes de demo: 00002 (salta del puesto 312 al 18 tras urgencia + hospitalización), 00001 (deterioro progresivo, PHQ-9 de 4 a 19), 00028 (mejora y baja), 00020 (2 inasistencias), 00009 (fallece y sale de la lista).

## Stack
- `front/`: React + Vite + framer-motion. Hosting en AWS Amplify (deploy automático desde `main`).
- `lambda/`: Python. `puntaje.py` contiene la lógica del puntaje (ya probada).
- AWS: API Gateway → Lambda → S3 (perfiles.json) + DynamoDB (revisiones/eventos) + Bedrock (explicaciones).
- Contrato de la API y del JSON en `contrato.md`. **No cambiar campos sin avisar al equipo.**

## Estado actual (miércoles 16:30) — TODO funciona en local, falta deploy
- `lambda/app.py`: API completa (GET /pacientes, GET /pacientes/{id}, POST /eventos, POST /pacientes/{id}/revision, POST /pacientes/{id}/explicar, GET /boxes). 9 tests pytest pasando.
- `lambda/explicar.py`: Bedrock Converse con fallback a plantilla si falla.
- `lambda/local_server.py`: corre la API en localhost:3001 sin AWS.
- `template.yaml` (SAM): S3 + DynamoDB + Lambda + HTTP API. Validado con cfn-lint. `amplify.yml` para el front.
- `front/`: lista con slider, Explicar con IA, Confirmar/Ajustar, Simular evento con "Reevaluado en X ms", pestaña Uso de box, excluidos. Probado end-to-end contra la API local.
- Pasos de deploy en DEPLOY.md.

## Pendiente
1. Deploy en AWS (DEPLOY.md pasos 2–5) y elegir modelo Bedrock.
2. Validar pesos de puntaje con Víctor Arancibia (HLF) y medir concordancia (kappa).
3. Pulido visual y pitch.

## Reglas para el asistente
- No cambies la lógica de `lambda/puntaje.py` sin avisar: los tests dependen de ella.
- Corre `python -m pytest -q tests` y `npm run build` después de cada cambio.
- Cambios chicos y que no rompan lo que funciona. Si propones algo grande, avisa antes.
- No agregues librerías nuevas sin preguntar.
- Explica brevemente lo que cambias: hay que saber defender el código en la pre-evaluación.
- Responde en español chileno, directo, sin relleno.
