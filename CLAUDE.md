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
- `front/`: React + Vite + framer-motion + Tailwind (CDN). Hosting en AWS Amplify (deploy manual con `scripts/deploy_aws.ps1`).
- `lambda/`: Python 3.12 (única dependencia: pydantic). `puntaje.py` = motor de priorización con reglas oficiales (ver docs/criterios_oficiales.md).
- AWS: Amplify → API Gateway → Lambda → S3 (perfiles.json) + DynamoDB (eventos, revisiones, contactos, decisiones, gestión, ajustes, evaluaciones, novedades, importaciones) + Textract (fotos de informes) + Bedrock (redactar explicaciones; respaldo opcional al leer informes).
- `FECHA_REFERENCIA=hoy` en la Lambda → fecha real de Chile; `AAAA-MM-DD` para simular.
- Contrato de la API en `contrato.md`. **No cambiar campos sin avisar al equipo.**
- Contexto completo para otro asistente: `docs/CONTEXTO_PARA_CLAUDE.md`.

## Cómo se prioriza (sin pesos inventados)
1. Categoría: prioridad inicial de la SIC; sube a la fila "descompensada" de la Tabla SSMSO 2025 del HLF si hay descompensación posterior. Nunca baja sola. Equivalencias K70, I20 y G40 "a validar".
2. Orden MINSAL Ord. 536/2025: categoría → descompensación grave → grupo de especial protección → antigüedad > 1 año → LACE (experimental, solo desempate) → llegada.
3. Descompensación grave (`riesgo_vital`, nombre interno): requiere evaluación médica en 72 h (pendiente / atrasada / evaluada). El sistema no declara "riesgo vital": lo decide el médico. Se cierra con decisión clínica (`/decision`), revisión, cita reservada o derivación; llamar no basta.
4. Banderas: GES "posible incumplimiento: verificar", causal 8 (2 inasistencias seguidas), revisión sugerida (examen alterado, aumento de dosis), ACG.
5. Una revisión clínica vale hasta el próximo evento.
6. Citas: propuesta (no bloquea) → reservada → confirmada → atendida / no asistió; cancelada libera la hora; doble reserva = 409.

## Estado actual — MVP (rama `mvp/priorizacion-ia-trazable`, noviembre 2026)
- La cuenta AWS del hackatón ya no existe: nada está desplegado. Todo corre en local (`python scripts/demo.py`, IA
  simulada) y la plantilla (`template.yaml`, `samconfig.toml`) valida con `cfn-lint` y `scripts/validar_plantilla.py`.
- Datos: DynamoDB es la única fuente de verdad (ítems por paciente, `lambda/datos.py`); en local, almacén en memoria con
  el mismo código. `perfiles.json` se carga con `scripts/cargar_registro.py` (ya no se lee de S3).
- Flujo: ingesta única (`ingesta.py`) → reglas + IA que lee y cita → dictamen (`bitacora.py`) → veredicto del
  especialista → criterios locales con aprobación de jefatura (`aprendizaje.py`). Conocimiento versionado con manifiesto
  (`base_conocimiento.py`, `scripts/empaquetar_conocimiento.py`: regenerar al cambiar el motor o una fuente).
- Seguridad: `AUTH=ninguna` (demo) o `cognito` (JWT validado por API Gateway); permisos por ruta en `seguridad.REGLAS`.
- Documentación: `docs/informes/`, `docs/DECISIONES.md`, `DEPLOY.md`, `docs/operacion/RUNBOOK.md`.
- Pruebas: `python -m pytest -q tests` (327), `cd front && npm run build`.

## Pendiente
1. Desplegar en una cuenta AWS y verificar lo listado en `docs/informes/INFORME_TECNICO.md` §10.
2. Validar con el HLF: filas de "descompensado", quién aprueba criterios locales, C1–C5 vs ESI, 72 h.
3. Medir el modelo de IA elegido (Haiku 5.5 vs Sonnet 5.5) con `scripts/evaluar_algoritmo.py`.

## Reglas para el asistente
- No cambies la lógica de `lambda/puntaje.py` sin avisar: los tests dependen de ella. Toda regla nueva debe citar su fuente.
- Corre `python -m pytest -q tests` y `npm run build` después de cada cambio.
- Cambios chicos y que no rompan lo que funciona. Si propones algo grande, avisa antes.
- No agregues librerías nuevas sin preguntar.
- Explica brevemente lo que cambias: hay que saber defender el código en la pre-evaluación.
- Responde en español chileno, directo, sin relleno.
