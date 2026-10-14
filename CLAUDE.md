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
- `front/`: React + Vite + framer-motion + Tailwind (CDN). Hosting en AWS Amplify (deploy automático desde `main`).
- `lambda/`: Python sin dependencias externas. `puntaje.py` = motor de priorización con reglas oficiales (ver docs/criterios_oficiales.md).
- AWS: Amplify → API Gateway → Lambda → S3 (perfiles.json, box.json) + DynamoDB (eventos, revisiones, contactos, novedades, importaciones) + Bedrock (leer informes/fotos y redactar).
- Contrato de la API en `contrato.md`. **No cambiar campos sin avisar al equipo.**

## Cómo se prioriza (sin pesos inventados)
1. Categoría: prioridad inicial de la SIC; sube a la fila "descompensada" de la Tabla SSMSO 2025 del HLF si hay descompensación posterior. Nunca baja sola.
2. Orden MINSAL Ord. 536/2025: categoría → riesgo vital → puntaje LACE (van Walraven 2010) → grupo de especial protección → antigüedad > 1 año → llegada.
3. Banderas: GES vencida, causal 8 (2 inasistencias seguidas), revisión sugerida (examen alterado, aumento de dosis), ACG.
4. Una revisión clínica vale hasta el próximo evento. "Contactar hoy" se apaga registrando el contacto.

## Estado actual — todo funciona en local, falta deploy
- 30 tests (`python -m pytest -q tests`). API: pacientes, eventos, informe (texto/foto), revisión, contacto, novedad, historia, box, KPIs, importar Excel/CSV, plantillas.
- Front: Hoy (contactar hoy + mapa de box + asignación de cupos), Lista, ficha en pestañas, Indicadores (kappa), Cargar datos, Criterios.

## Pendiente
1. Push a GitHub y deploy en AWS (DEPLOY.md) con Model ID de Bedrock.
2. Validar con el HLF las filas de "descompensado" y recalibrar LACE con datos reales.
3. Pitch y video de respaldo.

## Reglas para el asistente
- No cambies la lógica de `lambda/puntaje.py` sin avisar: los tests dependen de ella. Toda regla nueva debe citar su fuente.
- Corre `python -m pytest -q tests` y `npm run build` después de cada cambio.
- Cambios chicos y que no rompan lo que funciona. Si propones algo grande, avisa antes.
- No agregues librerías nuevas sin preguntar.
- Explica brevemente lo que cambias: hay que saber defender el código en la pre-evaluación.
- Responde en español chileno, directo, sin relleno.
