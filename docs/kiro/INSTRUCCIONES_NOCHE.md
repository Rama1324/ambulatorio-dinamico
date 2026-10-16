# Instrucciones para Kiro: mejorar los criterios durante la noche (16-10-2026)

Eres un agente que va a trabajar solo durante la noche en el proyecto **Ambulatorio Dinámico HLF**. Es una herramienta que
reordena la lista de espera de consultas de especialidad del Hospital Clínico Dra. Eloísa Díaz Inzunza (La Florida, Chile)
cuando un paciente empeora. El cierre de código es hoy a las **10:15** y el equipo revisa tu trabajo a las **08:00**.
Antes de empezar, lee estos documentos:

- `docs/CRITERIO_PRIORIZACION.md`: qué buscamos, cómo decide el sistema y de dónde sale cada regla. **Léelo completo.**
- `docs/CONTEXTO_PARA_CLAUDE.md`: estructura del código.
- `lambda/conocimiento/criterios_registro.json` y `lambda/conocimiento/combinaciones_riesgo.json`: el formato que debes usar.
- `lambda/conocimiento/diagnosticos_tabla_hlf.json`: los 176 diagnósticos de la tabla oficial del HLF que todavía no tienen criterios internos.

## Objetivo

Que ningún paciente que empeora quede abajo en la lista por falta de un criterio. Lo hacemos con **reglas escritas, con
fuente oficial y verificables**, que el código aplica. No con un modelo que "aprende".

## Reglas que no puedes romper

1. **Trabaja solo en la rama `kiro/criterios-noche`.** No hagas commit en `main`. No publiques en AWS ni corras
   `scripts/deploy_aws.ps1`. No toques la base de datos (`limpiar_demo.py`, DynamoDB).
2. **Solo agrega archivos nuevos** de conocimiento (JSON), pruebas y tu informe. No modifiques `puntaje.py`, `lista.py`,
   `decisor.py` ni el front. Si crees que hay que cambiar código, escríbelo como propuesta en el informe.
3. **Cada regla lleva una fuente oficial con cita textual y URL:** NICE, Queensland Clinical Prioritisation Criteria,
   guías GES o MINSAL, sociedades científicas, o un artículo con PMID o DOI. Marca `"estado": "verificado"` solo si leíste
   la cita en la fuente original; si no, usa `"guia_citada"`. **No inventes umbrales ni criterios.** Si no hay fuente,
   no lo agregues y anótalo como pregunta para un médico.
4. **Las reglas solo pueden subir la prioridad o marcar urgencia. Nunca bajar.** Una regla que dice "baja" sirve solo
   como referencia.
5. **No uses datos de pacientes.** El registro (`data/perfiles.json`) es sintético y no debe salir a ningún servicio
   externo. No ajustes pesos ni "aprendas" con esos datos, porque aprenderías los patrones del generador sintético.
6. **Presupuesto de Amazon Bedrock: máximo USD 5** (unas 150 evaluaciones). Las credenciales están en el perfil AWS
   `hack`; si vencieron, no las pidas: trabaja sin Bedrock.
7. **No agregues librerías.** Escribe en español de Chile, claro y sin relleno.
8. **Las pruebas existentes deben seguir pasando:** `python -m pytest -q tests` (hoy pasan 147).

## Método (repítelo para cada regla)

1. **Investigar:** busca el criterio en la fuente oficial y copia la frase exacta.
2. **Redactar:** escribe la regla en el formato del archivo correspondiente.
3. **Probar:** escribe al menos 4 casos de prueba:
   - uno que cumple el criterio;
   - uno negado ("se descarta…", "sin…");
   - uno ambiguo, que no debe asignar el criterio;
   - uno con una trampa de fecha u otra persona (fecha de nacimiento, familiar).
4. **Medir:** si el presupuesto lo permite, corre los casos con el clasificador existente (`lambda/criterios.py`,
   `clasificar`) o con el de combinaciones (`lambda/combinaciones.py`).
5. **Corregir o descartar:** si una regla da falsos positivos o falsos negativos, ajusta los términos. Si no se puede
   hacer confiable, déjala fuera y anótala.
6. **Registrar** en el informe qué hiciste y por qué.

## Tareas, en orden de prioridad

### T1. Banderas rojas transversales (lo más importante)
Son síntomas o hallazgos que vuelven urgente a **cualquier** paciente, sin importar su diagnóstico. Por ejemplo:
- sangrado digestivo (hematemesis, melena);
- déficit neurológico agudo;
- dolor torácico en reposo;
- ideación suicida con plan;
- síntomas de sospecha de cáncer (NICE NG12: baja de peso inexplicada, disfagia progresiva, hemoptisis…);
- fiebre en paciente inmunosuprimido;
- síncope con esfuerzo;
- disnea en reposo.

Archivo nuevo: `lambda/conocimiento/banderas_rojas.json`, con el **mismo formato de una entrada de
`combinaciones_riesgo.json`** (`id`, `nombre`, `gatillo`, `gatillo_terminos`, `efecto` = `urgencia` o `alta`,
`desenlace`, `fuente` {documento, cita, url}, `estado`, `letalidad` 1–4, `riesgo`). Pon `"base": {"descripcion": "cualquier
paciente", "cie10": [], "terminos": []}` y `"transversal": true`. Meta: 25 a 40 banderas, todas con fuente.

### T2. Criterios internos para los diagnósticos de la tabla oficial
Archivo nuevo: `lambda/conocimiento/criterios_tabla_hlf.json`, con el **mismo formato de una enfermedad de
`criterios_registro.json`** (`id`, `enfermedad`, `niveles` {alta, media, baja} con `criterios_detallados` y
`justificacion`, `excepciones_de_urgencia`, `fuente_url`, `riesgo`). Usa como clave el `codigo` `HLF-…` de
`diagnosticos_tabla_hlf.json`. Empieza por las filas de **prioridad alta** y por los diagnósticos más comunes de cada
especialidad. Meta: entre 30 y 50 diagnósticos bien hechos; es mejor tener menos que tener alguno inventado.

### T3. Casos de prueba
Archivo nuevo: `tests/casos_criterios_noche.json`, con los casos del método (texto, regla esperada, nivel esperado y si
debe marcar urgencia). Agrega `tests/test_criterios_noche.py`, que valide **sin Bedrock** lo siguiente:
- que cada regla tenga fuente y URL;
- que ninguna regla baje la prioridad;
- que los términos del gatillo aparezcan en los casos positivos;
- que el JSON se cargue.

### T4. Informe para el equipo
Archivo nuevo: `docs/kiro/INFORME_NOCHE.md`, con:
- qué agregaste;
- cuántas reglas están verificadas en la fuente original y cuántas no;
- resultados de las pruebas y de la medición con Bedrock, si la hiciste;
- preguntas abiertas para médicos del HLF;
- qué recomiendas integrar antes de las 10:15 y qué dejar para después.

## Lo que el equipo hará a las 08:00

El equipo revisa tu rama, corre las pruebas y decide qué integra. La integración en el motor (que `combinaciones.py` lea
`banderas_rojas.json` y que `criterios.py` lea `criterios_tabla_hlf.json`) la hace el equipo, no tú.

## Riesgos legales que debes respetar (Ley 21.719 de datos personales; Ley 20.584 de derechos del paciente)

- Ningún dato de paciente, sintético o real, sale a un servicio externo distinto de Bedrock, que ya está en uso.
- Las reglas deben poder explicarse con su fuente, porque cada cambio de posición debe ser explicable (art. 8 bis).
- La inasistencia o el nivel socioeconómico **nunca** pueden subir ni bajar la prioridad clínica.
- No conviertas el GES en una regla de orden: hoy el cálculo de plazos GES es aproximado. Anótalo como propuesta.

Detente a las 07:45, haz commit en tu rama con un mensaje claro y deja el informe listo.
