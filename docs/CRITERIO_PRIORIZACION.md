# Criterio de priorización de "Ambulatorio Dinámico HLF": cómo decide y cómo debe razonar

Contexto para un asistente de IA que va a trabajar en este proyecto. Describe **qué buscamos**, **con qué criterio
decide hoy el sistema**, **de dónde sale cada regla**, **qué nos pidió el hospital** y **cuánto mejora frente a la lista
actual**. Al 16-10-2026, rama `main` del repo `Rama1324/ambulatorio-dinamico` (es la versión publicada en AWS, con
`ALGORITMO=rubrica`). Los detalles técnicos están en `docs/CONTEXTO_PARA_CLAUDE.md` y `docs/algoritmo/`.

> **Si eres una IA que lee esto sin el código:** este documento basta para entender y criticar el criterio. Cada regla
> dice de qué fuente sale y en qué archivo está. Si propones un cambio, di qué regla cambia, con qué fuente y si podría
> **bajar** a alguien (eso nunca lo hace el sistema solo).

---

## 1. El objetivo: que nadie se muera ni se dañe mientras espera
El Hospital Clínico Dra. Eloísa Díaz La Florida (HLF) tiene una lista de espera para consultas de especialidad (más de
26.000 personas). Cuando llega una interconsulta (SIC), el especialista **lee el texto que escribió el médico que
deriva** y la prioriza en alta, media o baja. Esa prioridad **queda congelada**, y el especialista **no ve** lo que pasa
después: urgencias, hospitalizaciones, exámenes alterados, cambios de fármacos. "La lista de espera es una foto; la salud
de las personas, una película."

**La pregunta que responde el sistema:** de todas las personas que esperan, ¿quién tiene más riesgo de morir o de sufrir
un daño grave e irreversible si sigue esperando? Esa persona va primero. Todo lo demás (tiempo de espera, grupos de
protección, orden de llegada) solo ordena a personas con el **mismo** riesgo clínico.

Consecuencias de este objetivo:
- **Subtriage (dejar abajo a alguien grave) es el peor error.** Sobretriage (subir a alguien de más) es preferible. Por
  eso el sistema **sube solo, pero nunca baja solo**: bajar una prioridad siempre lo decide una persona.
- **Gravedad no es lo mismo que urgencia administrativa.** Que alguien lleve mucho tiempo esperando importa, pero no lo
  vuelve clínicamente grave. Esperar no cambia la categoría; ordena dentro de ella.
- **Si el dato no alcanza para decidir, no se asume que el paciente está bien.** La falta de información nunca baja a
  nadie.

## 2. Principios no negociables
1. **La IA lee; el código decide.** Un modelo de IA (Claude, en Amazon Bedrock) lee textos clínicos y responde
   preguntas cerradas, citando la frase exacta. El código verifica esa cita en el registro y aplica reglas escritas con
   fuente. La IA **nunca** pone la prioridad. Cuando la dejamos decidir sola, coincidió con la tabla oficial apenas
   κ = 0,09.
2. **Cada decisión es explicable y tiene fuente**: página de la tabla oficial, ordinario MINSAL, guía clínica o PMID.
3. **La herramienta propone y el equipo clínico decide.** Puede confirmar o cambiar cualquier prioridad, con un motivo
   obligatorio.
4. **Nunca bajar a nadie sin una persona.** Esto incluye quitarle a alguien la alerta de descompensación grave.
5. **Fallecidos y atendidos salen de la lista.** Las inasistencias no bajan la prioridad; solo generan un aviso para la
   gestión.
6. **Solo cuenta lo que ya pasó.** El sistema no predice: decide con hechos registrados hasta la fecha de corte.

## 3. Fuentes (en orden de autoridad)
1. **Tabla de priorización SSMSO 2025, sección del HLF (págs. 84–111).** Prioridad oficial por especialidad y
   diagnóstico. La capa de texto del PDF engaña (celdas combinadas), así que **toda prioridad se verifica en la imagen de
   la página**. Ejemplo: "antecedente de neoplasia en remisión" parecía ALTA en el texto y es BAJA (pág. 102).
2. **Ord. MINSAL 536/2025**, citado en el Manual de Gestión de la Demanda SSMSO, pág. 13. Fija el orden dentro de la
   lista no GES: criterio médico → grupos de especial protección → antigüedad mayor a 1 año → orden de llegada.
3. **Proceso de priorización de la SIC del HLF** (documento del hospital) y Norma Técnica 118 (MINSAL, 2024).
4. **Guías GES y MINSAL** para los umbrales: HbA1c ≥ 7 % (DM2), PAS ≥ 160 (HTA), SatO2 < 92 % (EPOC), PHQ-9 ≥ 10.
5. **PubMed**, para las ventanas de riesgo tras un evento: cuántos días sigue siendo relevante una hospitalización. Hay
   15 PMID verificados en NCBI.
6. **Criterios clínicos por enfermedad** (`dataset_gravedad_por_especialidad.json`): 46 enfermedades de Oftalmología,
   ORL, Psiquiatría, Reumatología y Urología, con criterios alta/media/baja **dentro** de cada enfermedad y 16
   excepciones de urgencia. Su origen no está confirmado: se usa **solo para subir**, nunca para bajar de lo que dice la
   tabla oficial.

## 3b. Diagnósticos que se pueden ingresar (16-10-2026)
Solo las **7 especialidades del registro** (Cardiología, Broncopulmonar, Gastroenterología, Endocrinología, Neurología,
Salud Mental y Traumatología). Por especialidad se puede elegir:
- los **17 diagnósticos CIE-10** que tienen pacientes en el registro;
- los **176 diagnósticos y síntomas de la tabla oficial del HLF** para esas especialidades (SSMSO 2025, secciones de
  adulto, págs. 85, 94–96, 103, 110 y 111; `lambda/conocimiento/diagnosticos_tabla_hlf.json`, códigos `HLF-…`).
  La prioridad de cada fila se leyó con dos métodos independientes (orden del texto y color de la celda); coincidieron en
  162 de 176 y las 14 diferencias se revisaron en la imagen de la página.
  Al ingresar un paciente con una de esas filas, **la prioridad de la tabla es el piso**: si quien prioriza puso una
  menor, el sistema la sube y lo explica con la página; si puso una mayor, se respeta.
La lista se ve **por especialidad** (al entrar, Cardiología): el N° es el puesto dentro de esa especialidad y la
comparación con los vecinos también. "Todas" queda como vista de coordinación.

## 4. Cómo decide hoy, paso a paso

### 4.1 Prioridad (alta / media / baja)
Parte de la **prioridad que asignó el especialista** al leer la SIC. Después puede **subir** (nunca bajar) por:

| Motivo | Regla | Fuente |
|---|---|---|
| **Descompensación de su enfermedad** (urgencia u hospitalización grave por esa enfermedad, sin estabilización posterior) | Sube a la prioridad de la fila "descompensado" de su diagnóstico en la tabla | Tabla SSMSO: I50 IC descompensada ALTA p85 · I20 angina inestable ALTA p85 · J44 EPOC grave no controlado ALTA p95 · J45 asma grave no controlada ALTA p95 · K70 cirrosis descompensada ALTA p95 · F32 episodio depresivo ALTA p110 · E11 DM2 descontrolada MEDIA p101 · E03 hipotiroidismo sintomático MEDIA p94 · G40 crisis mensuales MEDIA p103 |
| **Cáncer confirmado o sospecha** (leído en un informe o biopsia) | Sube a ALTA | En la sección HLF, toda fila de cáncer activo o sospechoso es ALTA (págs. 88, 94, 95, 111). Antecedente en remisión = BAJA (p102), no sube |
| **Medición clave que empeora y supera el umbral** (solo si la tabla define el estado por esa medición: HbA1c en DM2) | Sube a la fila correspondiente | Guía GES DM2 + tabla p101 |
| **Criterio clínico de su enfermedad** (las 46 del JSON) | Sube al nivel del criterio que cumple el texto | JSON de criterios |
| **Excepción de urgencia** (torsión testicular, desprendimiento de retina agudo, riesgo suicida con plan, hipoacusia súbita de menos de 72 h…) | ALTA + **"Derivar hoy a urgencia"**, primero en la lista | JSON de criterios |

### 4.2 El motivo del evento importa
- **Si el evento no tiene relación con la enfermedad por la que espera, no la descompensa.** Ejemplo: una amputación
  traumática en un paciente que espera cardiología no sube su prioridad de cardiología. Queda como alerta: "evento grave
  sin relación: revisar si requiere otra derivación".
- **La gravedad de la urgencia sale de su triage**, no de que haya ido a urgencia: ESI 1–2 (C1–C2) es grave, ESI 3 es
  moderada y ESI 4–5 es leve. Un dolor de dedo (C5) no sube a nadie.
- **Sin dato sobre la relación, se asume que el evento sí tiene que ver con su enfermedad** (la opción segura). Así viene
  el registro actual del hospital, que no trae el motivo de cada evento.

### 4.3 Vigencia de un evento
Una descompensación cuenta mientras esté dentro de su **ventana de riesgo**, en días con fuente PubMed: IC y EPOC 90 días
tras una hospitalización, asma 28–30, DM2 30, epilepsia 30, depresión 30–90. **Si no hay fuente, el evento no vence**,
porque es lo conservador. Si vence, el sistema no baja al paciente solo: avisa al especialista.

### 4.4 Orden dentro de cada prioridad (Ord. 536)
1. **Urgencia "derivar hoy"** (criterios de su enfermedad o combinaciones de riesgo).
2. **Descompensación grave sin revisar.** La lista se recalcula al instante. La alerta "revisar prioridad" queda abierta
   hasta que el especialista registra una revisión. El KPI del hospital (reevaluar en menos de 72 h) se cumple en cuanto
   entra el dato.
3. **Letalidad del diagnóstico** (1 = más mortal, 4 = menos), con la cifra y el PMID (§6.3).
4. **Agudeza del evento:** UCI o ESI/C1 = 3; hospitalización, ESI/C2 o descompensación grave = 2; moderada = 1.
5. **Cualquier paciente descompensado.** Va antes que un paciente estable, aunque ese paciente sea de un grupo de
   protección.
6. **Grupos de especial protección:** PRAIS, NNA bajo protección del Estado, Valech, Rettig.
7. **Antigüedad mayor a 1 año.**
8. **Más días esperando**, y el índice LACE (experimental) solo como último desempate.

El punto 5 se agregó por un **reclamo real del hospital**: una paciente Rettig estable quedó sobre una hipertensa recién
hospitalizada. El criterio médico va antes que el grupo de protección.

## 5. Dónde entra la IA y cómo se controla
| Tarea de la IA | Qué responde | Control del código |
|---|---|---|
| Leer el historial del paciente (rúbrica) | ¿Hubo descompensación? ¿Se estabilizó después? ¿Empeora su medición clave? ¿Cambió el tratamiento por mal control? Cada respuesta con su cita. | La cita debe existir en el registro y **decir lo que la IA afirma** (que sea de verdad una descompensación, que la estabilización sea posterior). Si la IA no sabe, **responde el registro**. 3 lecturas iguales. |
| Leer un informe, epicrisis, biopsia o DAU | Hallazgos de una lista cerrada (cáncer, UCI, hospitalización, descompensación, urgencia leve, estabilización…), con el **motivo** y si **tiene relación** con su enfermedad | La frase debe estar textual en el documento. Si hay una negación cerca ("se descarta neoplasia"), las lecturas no coinciden, el documento es de otro paciente o el hallazgo podría bajar a alguien (estabilización), lo confirma una persona. |
| Clasificar con los criterios de su enfermedad | El **código** del criterio cumplido (alta.0, media.1…), una urgencia o "no determinable" | Lista cerrada (la IA no puede inventar criterios). Cita verificada. 2 de 3 lecturas iguales. Solo sube. "No determinable" no asigna baja. |

**Cuándo se pide a una persona:** solo cuando el resultado, con datos verificados, **bajaría** a alguien (3 de 409
pacientes en la evaluación). Si la IA lee mal o falla, se usan las reglas y queda registrado, sin molestar a nadie.

**Resultados medidos con Claude real:**
- Historial de 409 pacientes: 2.454 lecturas, 0 fallidas, 100 % de estabilidad, nadie baja sin una persona.
- Criterios por enfermedad: 154 notas, 97,8 % correcto, 0 casos clasificados más bajo de lo debido, 16 de 16 urgencias
  detectadas, 0 urgencias falsas.

## 6. Lo que pidió el hospital (implementado el 15-10-2026)
Estas observaciones vienen directamente del HLF. Ya están implementadas, con tests y evaluadas con Claude real; lo que
sigue describe el razonamiento y cómo quedó.

### 6.1 Razonar con combinaciones de enfermedades
Una condición leve en una persona sana puede ser grave en otra. **El riesgo está en la combinación**, no en cada
diagnóstico por separado. Ejemplos del tipo de razonamiento que se espera:
- **Diabetes + uña encarnada, herida o infección en el pie** → pie diabético: riesgo de infección profunda y amputación.
  Para un no diabético es un problema menor.
- **Anticoagulado + caída o golpe en la cabeza** → riesgo de hemorragia intracraneal.
- **Inmunosuprimido (quimioterapia, corticoides en dosis altas, trasplante) + fiebre** → riesgo de sepsis.
- **Insuficiencia cardíaca o EPOC + neumonía** → riesgo de descompensación grave.
- **Insuficiencia renal + fármacos que dañan el riñón o hiperkalemia** → riesgo de arritmia.
- **Embarazo + hipertensión** → preeclampsia.
- **Adulto mayor frágil + caída** → fractura de cadera y pérdida de la autonomía.
- **Depresión + consumo de alcohol, o + pérdida reciente** → mayor riesgo suicida.

**Cómo quedó** (`lambda/combinaciones.py` + `lambda/conocimiento/combinaciones_riesgo.json`):
- **44 combinaciones**, cada una con su fuente. 35 están verificadas en el texto oficial (tabla del HLF en imagen, NICE
  NG232, CG151, NG234, CG124, CG103, CG150, NG12, GINA, entre otras): 25 llevan a urgencia "derivar hoy" y 10 a
  prioridad alta. Las otras 9 no están verificadas y **solo generan una alerta** visible; no mueven a nadie.
- **Verificación:** la IA marca la combinación copiando la frase. El código exige que la condición de base esté en el
  registro del paciente (diagnóstico, comorbilidades, edad) o en una frase verificada del texto; que la frase del
  gatillo esté textual, no negada y con un término obligatorio del gatillo; y que 2 de 3 lecturas coincidan.
- **Efecto:** urgencia (derivar hoy) o prioridad alta. Nunca baja.
- **Red de seguridad:** si la IA ve una combinación peligrosa que no está en la lista, queda una alerta visible para el
  equipo. Si la IA falla, queda una alerta "no se pudo revisar este texto".
- **Evaluación con Claude real** en 45 casos escritos a mano: 26 de 26 urgencias detectadas y 10 de 10 casos trampa sin
  falsa alarma (`docs/algoritmo/EVALUACION_COMBINACIONES.md`).
- **Límite:** solo se revisan textos (informes, motivo de la interconsulta). Los eventos del registro del hospital no
  traen texto ni fármacos, así que una combinación con un dato que solo está en otro sistema no se ve hasta que llega un
  texto.

### 6.2 Los signos vitales no justifican la prioridad
El hospital dijo que, en las razones de por qué una persona cambia de lugar en la lista, **los signos vitales sirven de
poco: en 30 minutos pueden ser otros**. Una presión o una saturación tomadas un día no describen el riesgo de las
semanas que la persona va a esperar.

**Cómo quedó:** los signos vitales ya no son razón de prioridad. Solo cuentan HbA1c y PHQ-9 cuando las dos últimas
mediciones están fuera de rango (`puntaje.MEDICIONES_ESTABLES`).

**Qué sí sirve:**
- mediciones **estables** o **tendencias** (HbA1c, que refleja 3 meses; PHQ-9; función renal; FEV1);
- **eventos** (urgencias, hospitalizaciones, diagnósticos);
- **hallazgos** (biopsia, imagen).

Un signo vital aislado solo puede servir como parte de un evento, por ejemplo "SatO2 85 % en urgencia que motivó una
hospitalización".

### 6.3 Saber qué urgencia es más mortal
No todas las urgencias "graves" pesan igual. Entre dos pacientes con la misma prioridad, **va primero el que tiene más
riesgo de morir o de un daño irreversible**:
- **Ejemplos de riesgo vital o de pérdida irreversible inmediata:** dolor torácico con sospecha coronaria, IC
  descompensada con edema pulmonar, EPOC con insuficiencia respiratoria, riesgo suicida con plan, torsión testicular,
  desprendimiento de retina agudo, sepsis, sangrado digestivo.
- **Ejemplos de urgencias graves pero de menor mortalidad:** dolor intenso no complicado, crisis de ansiedad, cólico
  renal sin infección.

**Cómo quedó:**
- **Orden:** el de §4.4. La letalidad está en `puntaje.LETALIDAD_DX` (10 diagnósticos con cifra y PMID; por ejemplo,
  K70 = 1: hemorragia variceal 16 % de mortalidad a 6 semanas) y en el campo `letalidad` de cada combinación.
- **Salida del carril de urgencia:** sale cuando el especialista registra una decisión, una revisión o un ajuste
  posterior. Sigue en alta, porque nunca baja.
- **Pendiente:** ordenar por mortalidad específica de cada diagnóstico, con datos chilenos.

## 6b. Evidencia oficial integrada (15-10-2026)
Informe completo: `docs/investigacion/Priorizacion_clinica_listas_de_espera.md`. Cada dato está marcado como [V]
verificado en la fuente original o [S] secundario.
- **Sin plazo de 72 h:** la lista se recalcula al instante cuando entra un paciente, un evento o un informe. La alerta de
  descompensación grave queda "revisar prioridad" hasta que el especialista revisa.
- **Criterios oficiales por diagnóstico** (`lambda/conocimiento/criterios_registro.json`): Queensland Clinical
  Prioritisation Criteria para 16 diagnósticos del registro (emergencia, Cat 1 ≤30 → alta, Cat 2 ≤90 → media, Cat 3
  ≤365 → baja) y NICE para ansiedad; F32 usa los criterios de psiquiatría del JSON. La IA los aplica sobre textos, y
  el código aplica sin IA las reglas que se pueden calcular con el registro (`puntaje.aplicar_registro`):
  - asma con UCI en 12 meses → alta;
  - asma hospitalizada en 6 meses → media;
  - EPOC con más de 3 urgencias u hospitalizaciones en 12 meses → media;
  - HbA1c >10% que empeora → alta, y 8–10% que empeora → media;
  - piso media para cirrosis y reflujo ("No category 3 criteria");
  - PHQ-9 ≥16 → alerta (NICE NG222).
- **Letalidad** (`puntaje.LETALIDAD_DX` y el campo `letalidad` de cada combinación): entre pacientes de la misma
  prioridad va primero el evento más mortal (1 a 4), con la cifra y su PMID en la razón.
- **Plazo de referencia** (30/90/365 días según la prioridad, Queensland): si se supera, se muestra con su riesgo (Sobolev
  2006, OR 1,66; Hanna 2020). No mueve a nadie, porque la norma chilena No GES no fija plazos.
- **Combinaciones:** 44 en total, 35 verificadas en una fuente oficial (25 de urgencia y 10 de prioridad alta). Las 9 no
  verificadas (asplenia + fiebre, VIH + cefalea febril, litio o clozapina, entre otras) solo generan una alerta visible.
- **Cada razón trae `riesgo`** ("qué puede pasar"), con la cifra y la fuente.

## 7. Cómo debe razonar una IA que ayude a mejorar estos criterios
1. **Piensa en desenlaces:** ¿qué le puede pasar a esta persona si espera semanas o meses? (muerte, amputación, ceguera,
   suicidio, pérdida de la autonomía). Eso define la gravedad, no el nombre del diagnóstico.
2. **Busca interacciones:** revisa siempre las comorbilidades y los fármacos junto con el motivo. Si la combinación
   aumenta el riesgo, dilo y cita la fuente.
3. **Desconfía de los datos transitorios:** un signo vital aislado no es una razón; un evento, una tendencia o un
   hallazgo sí.
4. **Distingue relación y gravedad:** ¿el evento es por la enfermedad que espera? ¿Qué tan mortal es?
5. **No inventes umbrales ni criterios:** si no hay fuente, márcalo "a validar por médico" y propón la pregunta concreta
   para el especialista.
6. **Ante la duda, protege al paciente:** prefiere subir o alertar antes que bajar, y nunca trates "no sé" como "está
   bien".
7. **Explica en lenguaje clínico corto,** con la fuente, para que un médico lo pueda verificar en segundos.

## 8. Dónde está cada cosa en el código
- `lambda/puntaje.py`: reglas y filas de la tabla oficial, regla oncológica, regla de "evento sin relación", criterios
  clínicos aplicados (`aplicar_registro`), letalidad, orden del Ord. 536 (`clave_orden`).
- `lambda/lista.py`: arma la lista que ve el equipo: revisiones, alerta de descompensación grave, ajustes manuales.
- `lambda/evaluacion_ia.py`: activa la rúbrica con IA (`ALGORITMO=rubrica`) y el barrido nocturno.
- `lambda/lectura_informe.py` e `ingreso.py`: leen informes y el motivo de la interconsulta; registran solo lo verificado
  que sube al paciente y dejan el resto como propuesta.
- `lambda/combinaciones.py`: combinaciones de riesgo.
- `lambda/decisor.py`, `lambda/controles.py`, `lambda/algoritmo.py`: fórmula fija, controles y combinación de las 3
  lecturas.
- `lambda/rubrica.py`: lectura del historial por la IA (preguntas cerradas con citas).
- `lambda/lector_documento.py`: lectura de informes por la IA (hallazgos, motivo, relación).
- `lambda/criterios.py` y `lambda/conocimiento/criterios_especialidad.json`: criterios clínicos de las 46 enfermedades.
- `lambda/conocimiento/`: tabla SSMSO verificada, ventanas con PMID, umbrales, rúbrica.
- `docs/algoritmo/`: requisitos, evaluación con datos reales, revisión adversaria, evaluación de criterios.
- Tests: `tests/` (133, todos pasan). Ninguno llama a Bedrock.

## 9. Cuánto mejora frente a la lista actual (medido el 16-10-2026)
Comparación con la **lista actual** (prioridad inicial y después orden de llegada, sin reevaluar) sobre el registro
sintético del HLF (500 pacientes). En cada fecha se usaron solo los datos que existían a esa fecha. Informe completo:
`Informe_pruebas_Ambulatorio_Dinamico.pdf`.

| Indicador | Lista actual | Ambulatorio Dinámico |
|---|---|---|
| Reacción el mismo día a una urgencia u hospitalización grave (135 eventos) | 0 % | 100 % (19 % sube, 39 % ya estaba en alta, 41 % queda con alerta "revisar prioridad" porque la tabla no tiene fila para ese diagnóstico) |
| Puesto mediano de los 15 fallecidos, 7 días antes de morir | 133 | 11 |
| Fallecidos en el 10 % superior de la lista | 3 de 15 | 9 de 15 |
| Simulación con la misma capacidad (2 atenciones por semana, 1 año): fallecidos antes de la consulta | 11 | 6 |
| Eventos graves ocurridos mientras esperaban | 112 | 92 |
| Días desde el primer evento grave hasta la consulta (mediana) | 84 | 37 |
| Pacientes con evento grave en el 20 % superior, 60 días **antes** del evento | 29 % | 34 % |

**Cómo leer estos números:**
- El sistema **reacciona**: lo que cambia es el mismo día del evento. **No predice** eventos futuros (última fila).
- Con la misma capacidad, 40 pacientes que no empeoraron (28 con prioridad inicial alta y 12 media) esperan más. Ese
  costo es explícito, y por eso decide el equipo clínico.
- Con solo 15 fallecidos, es un resultado indicativo. Los datos son sintéticos.
- Falta la concordancia con médicos (κ ≥ 0,70): no hay casos etiquetados por especialistas.
