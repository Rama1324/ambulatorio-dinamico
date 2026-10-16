# Instrucciones para Kiro: investigar y completar los criterios durante la noche (16-10-2026)

Eres un agente que va a trabajar solo durante la noche en el proyecto **Ambulatorio Dinámico HLF**. Es una herramienta que
reordena la lista de espera de consultas de especialidad del Hospital Clínico Dra. Eloísa Díaz Inzunza (La Florida, Chile)
cuando un paciente empeora. El equipo revisa tu trabajo a las **08:00** y el cierre de código es a las **10:15**.

**Tu trabajo es investigar y producir información, no programar el sistema.** Queremos el conjunto de criterios clínicos
más completo y confiable posible para nuestras 7 especialidades, con pruebas que demuestren que funcionan.

## Lo más importante: no inventes nada

Esta información se usa para decidir a qué paciente se atiende primero. **Un dato inventado es peor que un dato que
falta.** Por eso:

1. **Todo lo que escribas debe venir de una fuente que abriste y leíste esta noche.** No escribas criterios, cifras,
   umbrales, citas, URLs, PMID ni DOI de memoria.
2. **Para cada dato guarda la evidencia de que lo leíste:**
   - `url`: la dirección exacta de la página;
   - `cita`: el fragmento copiado tal cual, en el idioma original;
   - `fecha_consulta`: la fecha y hora en que lo leíste;
   - `ubicacion`: la sección, página, tabla o párrafo.

   Sin esos cuatro campos, el dato no se acepta.
3. **`"estado": "verificado"` solo si la cita está textual en la página que abriste.** Si el dato viene de un documento
   que cita a otro y no abriste el original, usa `"guia_citada"` e indica cuál es el original.
4. **Si no tienes acceso a internet o no pudiste abrir una fuente, no la uses.** Escríbelo al inicio del informe:
   "sin acceso web: nada de esto está verificado". En ese caso, entrega solo la lista de preguntas y fuentes por revisar,
   no criterios.
5. **Antes de dar por buena una URL, comprueba que abre y que trae la cita.** Antes de dar por bueno un PMID o DOI,
   comprueba en PubMed o doi.org que el título y los autores coinciden con lo que afirmas.
6. **No completes huecos con "lo razonable".** Si una guía no define el nivel medio de una enfermedad, déjalo vacío y
   anótalo. No traduzcas de forma que cambie el sentido: si hay duda, deja también la frase original.
7. **Si encuentras que algo de lo que ya tenemos está mal o no tiene sustento, dilo en el informe**, con la fuente.

Al final, revisa una muestra al azar de 20 datos tuyos, vuelve a abrir sus fuentes y reporta cuántos estaban bien.

## Lee primero

- `docs/CRITERIO_PRIORIZACION.md`: qué buscamos, cómo decide hoy el sistema y de dónde sale cada regla. **Léelo completo.**
- `lambda/conocimiento/criterios_registro.json`: criterios de los 17 diagnósticos del registro (Queensland, NICE). Es el modelo de formato y de calidad.
- `lambda/conocimiento/combinaciones_riesgo.json`: 44 combinaciones de riesgo, con su fuente.
- `lambda/conocimiento/diagnosticos_tabla_hlf.json`: 176 diagnósticos y síntomas de la tabla oficial del HLF, sin criterios internos.
- `lambda/puntaje.py` (`LETALIDAD_DX`): mortalidad con PMID de 10 diagnósticos.
- `docs/investigacion/` y `docs/criterios_oficiales.md`: investigación ya hecha. No la repitas; compleméntala.

Las 7 especialidades son **Cardiología, Broncopulmonar, Gastroenterología, Endocrinología (con Diabetología), Neurología,
Salud Mental y Traumatología**, todas de adulto.

## Objetivo

Que ningún paciente que empeora quede abajo en la lista por falta de un criterio. Para cada especialidad queremos saber,
con fuente comprobable:

1. **Qué enfermedades y síntomas** llegan a esa consulta: todos los de la tabla del HLF y los demás frecuentes en derivaciones.
2. **Qué hace que cada uno sea alta, media o baja**, y qué lo vuelve **urgencia** ("derivar hoy").
3. **Qué signos de alarma** (banderas rojas) indican deterioro, para cualquier diagnóstico.
4. **Qué combinaciones** de enfermedades, fármacos o situaciones aumentan el riesgo (por ejemplo, anticoagulado + caída).
5. **Qué tan grave es cada descompensación**: mortalidad o daño irreversible, con cifra y fuente, idealmente de Chile o Latinoamérica.
6. **Cuándo un evento deja de ser relevante** (ventana de riesgo en días), con fuente.

## Reglas que no puedes romper

1. **No modifiques ningún archivo existente del repositorio:** ni código, ni JSON actuales, ni pruebas actuales, ni
   documentos. Solo puedes **crear archivos nuevos** en estas carpetas:
   - `lambda/conocimiento/propuestas_kiro/`: información, en JSON;
   - `tests/kiro/`: pruebas nuevas;
   - `scripts/kiro/`: scripts de evaluación nuevos;
   - `docs/kiro/`: informes.
2. **Trabaja solo en la rama `kiro/criterios-noche`.** No hagas commit en `main`. No publiques en AWS ni corras
   `scripts/deploy_aws.ps1`. No toques la base de datos (`limpiar_demo.py`, DynamoDB).
3. **Solo fuentes confiables y comprobables:**
   - guías NICE;
   - Queensland Clinical Prioritisation Criteria;
   - guías GES y normas MINSAL;
   - la tabla SSMSO 2025 del HLF;
   - guías de sociedades científicas (ESC, GOLD, GINA, ADA, AASLD, ILAE, APA, AAOS…);
   - artículos revisados por pares con **PMID o DOI**.

   Cada dato lleva **URL, cita textual, fecha de consulta y ubicación** (ver "No inventes nada"). Si no encuentras fuente,
   no lo agregues y anótalo como pregunta para un médico. No uses blogs, Wikipedia, sitios comerciales ni respuestas de
   otras IA como fuente.
4. **Las reglas solo pueden subir la prioridad o marcar urgencia. Nunca bajar.** Un criterio de "baja" sirve solo como referencia.
5. **No uses datos de pacientes.** El registro (`data/perfiles.json`) es sintético y no debe salir a ningún servicio
   externo. No ajustes pesos ni "aprendas" con esos datos, porque aprenderías los patrones del generador sintético.
   Tus casos de prueba son textos clínicos ficticios escritos por ti.
6. **Presupuesto de Amazon Bedrock: máximo USD 5** (unas 150 evaluaciones). Las credenciales están en el perfil AWS
   `hack`; si vencieron, no las pidas: haz todas las pruebas sin Bedrock.
7. **No instales librerías.** Escribe en español de Chile, claro y sin relleno.
8. **Las pruebas actuales deben seguir pasando sin cambios:** `python -m pytest -q tests` (hoy pasan 147).

## Método (repítelo para cada criterio)

0. **Casos primero:** antes de escribir la regla, escribe los casos de prueba a partir de ejemplos o viñetas de la propia
   guía, o de su texto. Aparta un 30 % de los casos en `tests/kiro/casos_reservados.json` y **no los mires al ajustar las
   reglas**: al final se miden solo una vez. Así las pruebas no son circulares (tú escribes la regla y también los casos).
1. **Investigar:** busca el criterio en la fuente oficial y copia la frase exacta con su URL, fecha de consulta y ubicación.
2. **Contrastar con lo que ya tenemos:** compáralo con `criterios_registro.json`, la tabla del HLF y
   `combinaciones_riesgo.json`.
   - Si coincide, anótalo como "confirma".
   - Si lo amplía, como "complementa".
   - Si lo contradice, como "contradice". Explica la diferencia y cuál fuente tiene más autoridad (orden en
     `docs/CRITERIO_PRIORIZACION.md` §3).
3. **Redactar:** escribe la regla en el mismo formato que los archivos actuales.
4. **Probar:** escribe al menos 5 casos de prueba por regla:
   - uno que cumple el criterio;
   - uno negado ("se descarta…", "sin…", "niega…");
   - uno ambiguo, que no debe asignar el criterio;
   - uno con trampa de fecha u otra persona (fecha de nacimiento, un familiar, un evento antiguo);
   - uno que debería caer en otro nivel.
5. **Medir:** corre los casos y calcula aciertos, falsos positivos y falsos negativos.
6. **Corregir o descartar:** si una regla falla, ajústala y vuelve a medir. Si no se puede hacer confiable, déjala fuera y
   explica por qué.
7. **Registrar** todo en el informe.

## Tareas, en orden de prioridad

### T1. Banderas rojas transversales (lo más importante)
Son síntomas o hallazgos que vuelven urgente o de alta prioridad a **cualquier** paciente, sin importar su diagnóstico.
Por ejemplo:
- sangrado digestivo;
- déficit neurológico agudo;
- dolor torácico en reposo;
- ideación suicida con plan;
- síntomas de sospecha de cáncer (NICE NG12);
- fiebre en inmunosuprimido;
- síncope con esfuerzo;
- disnea en reposo;
- síndrome de cauda equina.

Archivo: `lambda/conocimiento/propuestas_kiro/banderas_rojas.json`. Usa el mismo formato que una entrada de
`combinaciones_riesgo.json`, con `"base": {"descripcion": "cualquier paciente", "cie10": [], "terminos": []}` y
`"transversal": true`. Meta: 30 a 50 banderas.

### T2. Investigación completa por especialidad
Un archivo por especialidad: `lambda/conocimiento/propuestas_kiro/criterios_<especialidad>.json`. Usa el mismo formato
que una enfermedad de `criterios_registro.json`:
- `id`, `enfermedad`, `cie10`; si es una fila de la tabla del HLF, también su `codigo` `HLF-…`;
- `niveles` {alta, media, baja}, con `criterios_detallados` y `justificacion`;
- `excepciones_de_urgencia`, `fuente_url` y `riesgo`;
- `estado` y `relacion_con_lo_actual` (confirma, complementa o contradice).

Cubre **todas** las enfermedades y síntomas de la tabla del HLF de esa especialidad y los demás motivos frecuentes de
derivación. Empieza por los de prioridad alta. Prefiere pocos criterios bien hechos antes que muchos sin fuente.

### T3. Combinaciones, letalidad y ventanas de riesgo
- `propuestas_kiro/combinaciones_nuevas.json`: combinaciones que faltan en `combinaciones_riesgo.json`, en el mismo formato.
- `propuestas_kiro/letalidad.json`: por diagnóstico, nivel 1 a 4 (1 = más letal), con cifra, población y PMID/DOI.
- `propuestas_kiro/ventanas_riesgo.json`: días que un evento sigue siendo relevante, por diagnóstico y tipo de evento, con fuente.

### T4. Muchas pruebas que demuestren que funciona
1. **Casos:** `tests/kiro/casos.json`, con todos los casos del método (texto, regla esperada, nivel esperado, si debe
   marcar urgencia). Meta: más de 300 casos.
2. **Pruebas sin Bedrock:** `tests/kiro/test_propuestas.py`, que verifique:
   - que cada JSON se cargue y tenga el formato de los archivos actuales;
   - que cada regla tenga fuente con URL y cita;
   - que ninguna regla baje la prioridad;
   - que no haya `id` repetidos ni contradicciones sin explicar;
   - que los términos del gatillo aparezcan en los casos positivos y no disparen en los negados.
3. **Mismas pruebas que hacemos nosotros:** imita `tests/test_criterios.py` y `tests/test_combinaciones.py`. Usa
   `rubrica.ClienteFalso` para simular la IA, pero **cargando tus archivos** desde un script propio en `scripts/kiro/`,
   sin modificar `criterios.py` ni `combinaciones.py`.
4. **Medición con la IA real** (si el presupuesto lo permite): imita `scripts/evaluar_criterios.py` y
   `scripts/evaluar_combinaciones.py` en `scripts/kiro/evaluar_propuestas.py`. Clasifica una muestra de tus casos con
   Bedrock y reporta:
   - porcentaje de acierto;
   - casos clasificados más bajo de lo debido (el error más grave);
   - urgencias detectadas y urgencias falsas;
   - estabilidad entre 3 lecturas.
5. **Comparación con lo actual:** corre tus casos también contra los criterios que ya tenemos. Muestra cuántos casos
   resuelve lo actual y cuántos más resuelven tus propuestas.

### T5. Informe completo
Archivo: `docs/kiro/INFORME_NOCHE.md`. Debe incluir:
- **Al inicio:** si tuviste acceso web, cuántas fuentes abriste y el resultado de la revisión de la muestra de 20 datos.
- **Resumen** en 10 líneas: qué encontraste, cuánto mejora y qué recomiendas integrar antes de las 10:15.
- **Por especialidad:** enfermedades y síntomas cubiertos, criterios nuevos, fuentes y qué confirma, complementa o
  contradice lo actual.
- **Banderas rojas, combinaciones, letalidad y ventanas,** con sus fuentes.
- **Resultados de las pruebas,** con números: casos, aciertos, falsos positivos, falsos negativos, clasificaciones más
  bajas de lo debido, y comparación con lo actual. Reporta aparte el resultado en los **casos reservados**.
- **Lista de fuentes** con URL, marcando cuáles verificaste en el original.
- **Preguntas abiertas para médicos del HLF.**
- **Qué no recomiendas integrar** y por qué.

## Lo que hará el equipo a las 08:00

El equipo revisa tu rama, corre tus pruebas y las actuales, y decide qué integra. Conectar tus archivos al motor (que el
sistema lea las banderas rojas y los criterios nuevos) lo hace el equipo, no tú.

## Riesgos legales que debes respetar (Ley 21.719 de datos personales; Ley 20.584 de derechos del paciente)

- Ningún dato de paciente, sintético o real, sale a un servicio externo distinto de Bedrock, que ya está en uso.
- Cada regla debe poder explicarse con su fuente, porque cada cambio de posición de un paciente debe ser explicable (art. 8 bis).
- La inasistencia, la comuna, la previsión o el nivel socioeconómico **nunca** pueden cambiar la prioridad clínica.
- No conviertas el GES en una regla de orden: hoy el cálculo de plazos GES es aproximado. Anótalo como propuesta.

## Horario (con tope por tarea)

Es mejor terminar bien lo primero que dejar todo a medias.

| Bloque | Tarea |
|---|---|
| Primeros 90 min | T1, banderas rojas: es lo único que el equipo alcanza a integrar antes de las 10:15. |
| Siguientes 90 min | T2, solo los diagnósticos de **prioridad alta** de cada especialidad. |
| Siguientes 60 min | T3 y T4: pruebas, medición y comparación con lo actual. |
| Últimos 30 min | T5 (informe) y revisión de la muestra de 20 datos. |

Si sobra tiempo, sigue con los diagnósticos de prioridad media y baja. **Haz commit en tu rama cada hora** con un mensaje
claro. Detente a las **07:45**, corre todas las pruebas (las actuales y las tuyas) y deja el informe listo.
