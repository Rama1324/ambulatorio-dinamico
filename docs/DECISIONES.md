# Decisiones de arquitectura — Ambulatorio Dinámico HLF (MVP, noviembre 2026)

Cada decisión dice **qué problema resuelve, qué se evaluó, qué se eligió y cuándo conviene revisarla**. Los números
propios se midieron con `scripts/medir_escala.py` sobre el registro sintético; los precios y límites de AWS están en
[`docs/investigacion/Ficha_AWS_2026-11.md`](investigacion/Ficha_AWS_2026-11.md), con su fuente oficial y fecha.
Son órdenes de magnitud con precios de lista de us-east-1: no reemplazan una cotización.

| N° | Decisión | En una línea |
|---|---|---|
| D1 | [La IA lee y cita; el código decide](#d1) | La prioridad sale de criterios con fuente; la IA aporta lectura verificable |
| D2 | [Cada decisión es un dictamen que no se modifica](#d2) | Qué se usó, qué versión de cada fuente y por qué, guardado al decidir |
| D3 | [El especialista juzga la decisión y el sistema aprende con gobierno](#d3) | Veredicto → precedente → criterio propuesto → aprobación → conocimiento versionado |
| D4 | [Conocimiento médico por clave, versionado con huella](#d4) | Sin búsqueda vectorial: corpus chico y estructurado; exacto y auditable |
| D5 | [Antecedentes: un paciente = una partición de DynamoDB](#d5) | Ítems normalizados; evaluar un evento cuesta una consulta |
| D6 | [Leer la lista sin recorrer la tabla](#d6) | Copia por contenedor + marcador + índice por fecha de registro |
| D7 | [Respuestas comprimidas y paginables](#d7) | La lista de una especialidad real no cabe en 6 MB sin gzip |
| D8 | [Una sola tubería de ingesta para todos los canales](#d8) | App, archivo, API, zona de carga S3; idempotente y con registro de lote |
| D9 | [Seguridad: identidad del token, roles y "solo agrega"](#d9) | JWT validado por API Gateway; la Lambda no puede borrar |
| D10 | [Costo de la IA bajo control](#d10) | Se evalúa por evento, se reutiliza por huella, modelo y lecturas por parámetro |
| D11 | [Región y residencia de los datos](#d11) | us-east-1 como punto de partida, por parámetro |
| D12 | [Lo que se dejó fuera, y por qué](#d12) | Vista materializada, FHIR, WAF, cuentas separadas |

---

<a id="d1"></a>
## D1 · La IA lee y cita; el código decide

**Problema.** El flujo pide que, ante cada evento, un modelo de IA determine la prioridad con los antecedentes del
paciente y la información médica definida por el equipo, y que cada decisión quede explicada con sus fuentes.

**Qué se evaluó.**
1. *El modelo asigna la prioridad directamente.* El equipo lo midió en octubre con Claude real sobre 409 pacientes: la
   concordancia con la tabla oficial fue κ = 0,115 (`docs/algoritmo/EVALUACION.md`, brazo E0). Además, la explicación de
   un modelo no es una fuente: no se puede auditar contra la norma.
2. *Solo reglas, sin IA.* Funciona con datos estructurados, pero no puede leer texto libre (epicrisis, informes,
   interconsultas), que es donde está buena parte de la información clínica.
3. *El modelo lee con una rúbrica cerrada y cita; una fórmula fija decide; controles verifican* (lo elegido).

**Decisión.** Se mantiene y se completa la opción 3. Ante un evento, el modelo recibe los antecedentes del paciente y
la rúbrica de su diagnóstico; responde preguntas cerradas citando el registro exacto; el código comprueba que la cita
exista y diga lo que el modelo afirma; una fórmula con la tabla del HLF y el Ord. 536 determina la prioridad. Si la IA
falla o algo no cuadra, rigen las reglas y queda anotado. **El sistema sube solo y nunca baja solo.**

**Consecuencias.** Toda prioridad es reproducible y cada razón tiene fuente. La IA agrega costo solo donde aporta
(lectura). El modelo se puede cambiar sin cambiar el criterio clínico.

**Revisar cuando** existan casos etiquetados por especialistas (el equipo fijó la regla: volver a solo reglas si la
variante con IA no supera a las reglas en κ ≥ 0,10 contra médicos, es inestable en más del 10 % o produce subtriage grave).

<a id="d2"></a>
## D2 · Cada decisión es un dictamen que no se modifica

**Problema.** "Cada decisión debe quedar documentada y explicada, indicando la información utilizada, sus fuentes y
cómo fundamenta la prioridad." Antes existían las razones de la prioridad vigente, pero se recalculaban al leer: no
quedaba registro de **qué se decidió en cada momento ni con qué versión del conocimiento**.

**Qué se evaluó.** (a) Reconstruir la decisión al consultarla: imposible de garantizar si cambian las fuentes o el
código. (b) Dejarlo en los logs: no es consultable por paciente ni lo ve el especialista. (c) Un registro propio por
decisión (lo elegido).

**Decisión.** Cada evaluación gatillada por un disparador (evento, ingreso, novedad, informe, carga, criterio local,
enmienda) guarda un **dictamen**: disparador y canal; prioridad y puesto antes y después; fundamento (razones con
fuente); explicación en lenguaje simple por plantilla; e **información utilizada**: cuántos antecedentes y cuáles
registros concretos sostienen la decisión, el paquete de conocimiento con la versión y huella de cada fuente, los
criterios locales aplicados, los precedentes del mismo tipo de caso y, si hubo IA, modelo, versión de la rúbrica, huella
del prompt, lecturas, controles y tokens. El dictamen solo se agrega; el veredicto del especialista vive en la revisión
que lo cita.

**Consecuencias.** Se puede responder "por qué este paciente subió el 13-10 y con qué criterio vigente ese día". El
KPI del hospital (reevaluar en menos de 72 h tras un evento) se mide de verdad: tiempo entre la llegada del evento y su
dictamen. Cuesta unas pocas unidades de escritura por evento.

**Revisar cuando** el volumen de dictámenes haga conveniente archivarlos (S3 + Athena) pasado un plazo.

<a id="d3"></a>
## D3 · El especialista juzga la decisión y el sistema aprende con gobierno

**Problema.** El especialista debe poder decir si una decisión fue adecuada o incorrecta, con su motivo, y esa
retroalimentación debe mejorar las decisiones siguientes.

**Qué se evaluó.**
1. *Reentrenar o ajustar el modelo con las correcciones.* Opaco, lento, caro y sin trazabilidad; además el modelo no
   decide (D1), así que no es ahí donde está el error.
2. *Aplicar automáticamente cada corrección a los casos parecidos.* Una sola opinión cambiaría la lista de todos.
3. *Meter las correcciones en el prompt como ejemplos.* No determinista y difícil de auditar.
4. *Convertir la corrección en conocimiento explícito, con aprobación* (lo elegido).

**Decisión.**
- El veredicto (`adecuada` / `incorrecta` + motivo de una lista cerrada + explicación) queda atado al dictamen juzgado.
- Cada veredicto es un **precedente** de su patrón (diagnóstico + tipo y gravedad del evento determinante). Toda
  decisión nueva muestra el historial de su patrón.
- "Falta un criterio" genera un **criterio local propuesto**. Mientras está propuesto no cambia a nadie: los casos que
  calzan lo muestran y pasan a la cola del especialista.
- Una persona con rol de jefatura lo **aprueba**. Desde ese día el motor lo aplica (solo sube), cada decisión lo cita
  con quién lo aprobó y en cuántas revisiones se basa, y la versión de la capa local queda en cada dictamen.
- Las correcciones "hacia abajo" (la regla no debió subir) **nunca se vuelven regla automática**: quedan como
  precedente y la regla objetada aparece en "reglas a validar con el equipo médico". Cambiarla es editar la fuente
  oficial (D4), con revisión.
- Un evento mal leído o sin relación se corrige con una **enmienda** (no se borra): es una decisión humana sobre ese
  paciente.

**Consecuencias.** El aprendizaje es visible, reversible (retirar un criterio no baja a nadie: deja a los afectados con
revisión pendiente) y auditable. La concordancia con los especialistas se mide por diagnóstico, por patrón y por regla.

**Revisar cuando** el hospital defina su gobierno clínico: quién aprueba, si exige más de un precedente o comité.

<a id="d4"></a>
## D4 · Conocimiento médico por clave, versionado con huella

**Problema.** La información médica que usa el sistema estaba en JSON sueltos y constantes del código, con una versión
escrita a mano. La auditoría encontró **cinco fuentes que cambiaron de contenido sin cambiar de versión**: una decisión
no podía decir con exactitud qué usó.

**Qué se evaluó.**

| Opción | A favor | En contra para este caso |
|---|---|---|
| Búsqueda vectorial (Bedrock Knowledge Bases con S3 Vectors u OpenSearch) | Sirve para miles de páginas de texto libre; hoy hay opciones que escalan a cero | Recuperación por similitud: no es exacta ni reproducible; cuesta explicar por qué se usó un pasaje y no otro; para ~400 entradas estructuradas no aporta |
| Base relacional (Aurora) | SQL, reportería | Servidor, red privada y costo fijo para datos que caben en un archivo |
| Todo el conocimiento dentro del prompt | Simple | Se paga en cada llamada y el modelo decidiría qué aplica (contradice D1) |
| **Archivos estructurados versionados + recuperación por clave** | Exacto, gratis, en microsegundos, auditable; se revisa como código | Cambiar una fuente oficial exige despliegue (es deliberado) |

**Decisión.**
- El conocimiento oficial (tabla SSMSO/HLF, Ord. 536, GES, criterios, combinaciones, evidencia) vive en
  `lambda/conocimiento/*.json`, junto al código. Un **manifiesto** generado (`scripts/empaquetar_conocimiento.py`)
  registra por fuente su versión, estado de verificación y **huella del contenido** (independiente del formato), más
  la huella del motor de reglas. Un test falla si una fuente cambia sin regenerarlo, y el generador rechaza un cambio
  de contenido con la misma versión.
- Se recupera **por clave** (CIE-10, especialidad, tipo de evento): `base_conocimiento.para_diagnostico()` entrega todo
  lo que el sistema sabe y aplica para un diagnóstico, cada bloque con su fuente y versión. A la IA solo se le envía
  la parte de su diagnóstico.
- El conocimiento que nace de la retroalimentación (criterios locales) vive en DynamoDB, con su historial (D3).
- Cada dictamen guarda el paquete y las fuentes exactas que respaldan sus razones.

**Consecuencias.** Miles de consultas al día no cuestan nada adicional: el conocimiento está en memoria e indexado.
Cambiar una fuente oficial es un cambio revisado, probado y desplegado, con versión nueva.

**Revisar cuando** el hospital quiera sumar guías o protocolos en texto libre (cientos de páginas): ahí conviene una
Knowledge Base **para encontrar y citar pasajes**, manteniendo la decisión en criterios estructurados.

<a id="d5"></a>
## D5 · Antecedentes: un paciente = una partición de DynamoDB

**Problema.** El registro base era un único `perfiles.json` en S3 cargado entero en memoria (~1 MB con 500 pacientes;
~55 MB estimados con 26.000), y lo que llegaba después se guardaba como el perfil completo de cada paciente en un solo
ítem. Evaluar un evento exigía tener a todos los pacientes en memoria, y un historial largo podía pasar el límite de
400 KB por ítem.

**Decisión.** DynamoDB es la única fuente de verdad, con **ítems normalizados**: `perfil`, `evento#…`, `medicion#…`,
`cita#…`, y los registros del equipo (`revision#`, `decision#`, `dictamen#`…), todos bajo la clave del paciente. El
registro del hospital se carga una vez a la tabla (`scripts/cargar_registro.py`) y de ahí en adelante entra por la
ingesta (D8). En local, el mismo código corre sobre un almacén en memoria con los mismos ítems.

**Consecuencias.**
- Los antecedentes de un paciente se leen con **una consulta a su partición** (pocos KB): es lo que necesita la
  evaluación de un evento, sin tocar al resto.
- Cada evento, medición y cita tiene identidad propia: se puede enmendar, citar y deduplicar.
- Solo se agrega. El rol de la Lambda no tiene permiso para borrar (D9).
- Control de edición simultánea con un contador por paciente (`rev`): si dos personas deciden sobre el mismo paciente,
  la segunda recibe un 409 y recarga.

**Revisar cuando** se necesite reportería SQL: exportar a S3 y consultar con Athena antes que sumar una base relacional.

<a id="d6"></a>
## D6 · Leer la lista sin recorrer la tabla

**Problema.** Cada solicitud hacía un `Scan` completo de la tabla. Con historial acumulado y flujo continuo de eventos,
el costo y la latencia crecen sin límite.

**Qué se evaluó.**
1. *Vista materializada*: un estado de prioridad por paciente, actualizado por DynamoDB Streams, y la lista como una
   consulta a un índice ordenado. Es el patrón más escalable, pero obliga a rehacer el cálculo de la lista (posición,
   comparación con vecinos, ajustes manuales por puesto, vigencia de revisiones y la vista a una fecha anterior, que
   hoy se calculan al leer) y cambia la consistencia: la lista se actualizaría segundos después del evento.
2. *Copia en memoria por contenedor con invalidación exacta* (lo elegido para el MVP y el piloto).

**Decisión.** Cada contenedor de la Lambda mantiene una copia de los ítems y de los perfiles armados. En cada
solicitud lee un marcador (`GetItem` consistente, 1 unidad de lectura). Si nada cambió, no lee más. Si cambió, trae
**solo lo nuevo** por el índice `PorDia` (fecha y hora de registro) y lo mezcla. La lista se sigue calculando al leer,
con las mismas reglas y en cualquier fecha de corte.

**Medición** (este computador; una Lambda arm64 de 1 GB será algo más lenta):

| Pacientes en el registro | Lista de una especialidad | Lista completa | Memoria del registro |
|---:|---:|---:|---:|
| 500 (registro sintético) | 5 ms (84 pacientes) | 30 ms | ~1 MB |
| 4.000 | 55 ms (672) | 275 ms | ~10 MB |
| 26.000 (toda la red) | 339 ms (4.368) | 1,9 s | ~70 MB |

**Consecuencias.** Alcanza con holgura para el piloto (una especialidad) y, por especialidad, para toda la red. El
límite conocido es el arranque en frío (cargar la copia) y la memoria del contenedor. Un proceso que no necesita la
lista (el trabajador que evalúa eventos de la cola) lee solo la partición del paciente.

**Revisar cuando** el p95 de la lista de una especialidad pase de 1 s o el arranque en frío moleste: entonces, la
vista materializada con Streams (la tabla y los ítems ya están preparados para eso).

<a id="d7"></a>
## D7 · Respuestas comprimidas y paginables

**Problema.** Una Lambda no puede responder más de 6 MB y API Gateway HTTP API no comprime. La lista de una
especialidad de 4.368 pacientes pesa 18,7 MB en JSON.

**Decisión.** La Lambda comprime con gzip cuando el cliente lo acepta (18,7 MB → 0,32 MB; la lista completa de 26.000,
92 MB → 1,6 MB). `GET /pacientes` acepta además `limite`, `desde` y `campos=resumen` para integraciones. La app
muestra las listas largas por tramos.

**Revisar cuando** se adopte la vista materializada (D6): la paginación pasa a ser del índice.

<a id="d8"></a>
## D8 · Una sola tubería de ingesta para todos los canales

**Problema.** Los eventos entraban por la app o subiendo un CSV a mano; la carga de archivos no dejaba registro de qué
llegó ni disparaba la evaluación con IA. El hospital va a enviar eventos de forma continua desde varios sistemas.

**Decisión.** Todos los canales terminan en `ingesta.registrar()`: validar con el vocabulario del registro → resolver
el paciente (por id o por RUT) → deduplicar → guardar ítems → registro del lote → evaluar → dictámenes.

| Canal | Cómo entra | Evaluación |
|---|---|---|
| App (evento o simulación) | `POST /eventos` | En la misma solicitud |
| App (Excel o CSV) | `POST /importar` | En la misma solicitud |
| Sistemas del hospital | `POST /ingesta/eventos` (JSON, token de máquina, `Idempotency-Key`) | En la solicitud o por cola |
| Carga programada | Archivo en `s3://…/entrada/` → Lambda de ingesta | Por cola (SQS) |
| Informe o foto | `POST /pacientes/{id}/informe` (Textract + IA) | En la misma solicitud |

- **Idempotencia** por contenido: reenviar un archivo o un mensaje no duplica.
- **Minimización**: un evento de alguien que no está en la lista se cuenta y no se guarda.
- **SQS desacopla la evaluación con IA, no la recepción**: lo recibido queda guardado antes de responder, las reglas
  rigen de inmediato y el dictamen con IA llega segundos después. Los mensajes que fallan van a una cola aparte con alarma.
- Cada evento guarda cuándo llegó, por qué canal, desde qué sistema y en qué lote.

**Revisar cuando** MINSAL publique los perfiles de interoperabilidad de la Ley 21.668: HL7 FHIR entra como un
adaptador más hacia la misma tubería. No se implementó ahora porque, sin perfiles definidos, mapear triage o gravedad
sería inventar.

<a id="d9"></a>
## D9 · Seguridad: identidad del token, roles y "solo agrega"

**Problema.** La API no tenía autenticación, el "usuario" de cada registro era un texto del navegador, CORS estaba
abierto y los errores internos se devolvían al cliente.

**Decisión.**
- API Gateway valida un JWT de Amazon Cognito (parámetro `Autenticacion=cognito`). La Lambda toma la identidad del
  token e ignora la que mande el navegador. Roles por grupo: gestión, especialista, jefatura; los sistemas usan
  credenciales de cliente con un scope propio. Una ruta sin regla de permiso queda denegada.
- La demo con datos sintéticos corre con `Autenticacion=ninguna` y el rol declarado, dicho explícitamente en pantalla.
- CORS solo desde el dominio de la página. Errores con mensaje genérico e identificador; el detalle, al log.
- Un registro por solicitud (quién, qué ruta, qué paciente), sin datos clínicos: es el registro de accesos.
- El rol IAM de las funciones no tiene `DeleteItem` ni `BatchWriteItem`; Bedrock limitado a modelos de Anthropic.
- A la IA no se le envía nombre ni RUT (`privacidad.py`). Bedrock Guardrails queda como segunda capa opcional, sabiendo
  que no revisa argumentos ni resultados de herramientas y que no reconoce el RUT sin una expresión propia.

**Revisar antes de datos reales:** evaluación de impacto (Ley 21.719), contrato y cláusulas con AWS, exclusión de uso
de contenido para servicios de IA (Textract) en AWS Organizations, WAF, llave KMS propia y cuentas separadas.

<a id="d10"></a>
## D10 · Costo de la IA bajo control

**Problema.** La IA es el único costo variable relevante. La infraestructura de un evento evaluado cuesta centésimas
de centavo; la lectura con el modelo cuesta entre decenas y cientos de veces más, según el modelo.

**Decisión.**
- **Se evalúa por evento**, no por barrido: solo quien tiene un dato nuevo. El barrido nocturno queda apagado.
- **Se reutiliza por huella**: si los antecedentes, la rúbrica y la fuente no cambiaron, la lectura guardada sigue
  vigente y la fórmula se reaplica sin llamar al modelo.
- **A la IA solo va lo necesario**: los antecedentes de ese paciente y la rúbrica de su diagnóstico.
- **Modelo y número de lecturas por parámetro** (`ModelId`, `LecturasIA`). Con los tokens que el equipo midió en
  octubre (8.309 de entrada y 1.120 de salida por evaluación de 3 lecturas):

| Modelo (perfil `us.`) | Por evaluación | 100 al día (piloto) | 800 al día (red) | 5.000 al día |
|---|---:|---:|---:|---:|
| Claude Haiku 5.5 (0,11 / 0,55 USD por millón) | 0,0015 USD | ~5 USD/mes | ~37 USD/mes | ~230 USD/mes |
| Claude Sonnet 5.5 (2,20 / 11,00) | 0,031 USD | ~92 USD/mes | ~734 USD/mes | ~4.600 USD/mes |

- El cliente tolera modelos que rechazan la herramienta forzada (Sonnet 5.5 y Opus 5.5) y deja una métrica por
  llamada (tarea, modelo, tokens, latencia) para ver el gasto por tarea.
- **Modo simulado** (`MODEL_ID=simulado`): lector determinista para demostrar y probar sin AWS, rotulado en cada decisión.

**Pendiente de validar con una cuenta:** que un modelo más barato lea igual de bien (repetir
`scripts/evaluar_algoritmo.py` con ese modelo antes de cambiarlo) y el ahorro real del caché de prompts.

<a id="d11"></a>
## D11 · Región y residencia de los datos

**Decisión.** `us-east-1` como punto de partida, por parámetro. Motivos: la región de AWS en Chile está anunciada pero
no ha abierto (al 13-11-2026) y no se sabe qué servicios tendrá; Textract no existe en São Paulo; los modelos Claude
actuales solo se invocan con perfiles de inferencia entre regiones (`us.` procesa en tres regiones de EE. UU.;
`global.` en cualquiera; desde São Paulo solo existe el global).

**Consecuencias.** Hay transferencia internacional de datos: requiere la salvaguarda contractual que valide la jurídica
del hospital. Toda la infraestructura es una plantilla: migrar de región es volver a desplegar y trasladar los datos.

**Revisar cuando** abra la región de Chile y se conozcan sus servicios.

<a id="d12"></a>
## D12 · Lo que se dejó fuera, y por qué

| Tema | Por qué no ahora | Qué lo gatilla |
|---|---|---|
| Vista materializada de la lista (Streams) | El cálculo al leer alcanza para el piloto (D6) y cambiarlo arriesga reglas probadas | p95 de la lista > 1 s o arranque en frío molesto |
| HL7 FHIR | Sin perfiles definidos, sería inventar equivalencias clínicas | Perfiles de MINSAL (Ley 21.668) |
| Bajar prioridades por aprendizaje | Contradice "nunca baja solo" | Decisión del equipo médico sobre la fuente oficial |
| WAF, GuardDuty, Security Hub, Config, CloudTrail de organización, cuentas separadas | Son de la cuenta y la organización, no del stack de la aplicación | Fase 0–1 del plan con AWS |
| Evaluación con casos etiquetados por médicos | No existen las etiquetas | Las 30+ fichas etiquetadas por especialistas |
| Tailwind compilado (hoy por CDN) | No bloquea la demo; es requisito para una política de contenido estricta | Antes de producción |
