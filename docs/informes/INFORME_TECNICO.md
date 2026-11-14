# Informe técnico — Ambulatorio Dinámico HLF (MVP, noviembre 2026)

Para el equipo de AWS, TI del hospital y quien mantenga el código. Describe la arquitectura, las herramientas de AWS, las
integraciones, los flujos de datos, cómo se prioriza y cómo aprende de los especialistas, las decisiones técnicas y cómo
ejecutar y verificar todo. Fuente de verdad: rama `mvp/priorizacion-ia-trazable`. Detalle de cada decisión, con
alternativas y mediciones: [`docs/DECISIONES.md`](../DECISIONES.md). Contrato de diseño:
[`docs/diseno/ESPECIFICACION_MVP.md`](../diseno/ESPECIFICACION_MVP.md).

> **Estado de verificación.** Todo lo de este informe corre y está probado **en local** (API completa, almacén en
> memoria, IA en modo simulado, front) y con emulación de AWS (`moto`: DynamoDB, S3, SQS, SNS). **Nada se desplegó en
> AWS**: la cuenta del hackatón ya no existe y no hubo credenciales. La plantilla pasa `cfn-lint` y un validador propio,
> pero no se ha creado un stack. Bedrock y Textract no se llamaron en esta etapa. La §10 lista qué falta verificar y cómo.

---

## 1. Qué resuelve

La lista de espera de especialidad asigna una prioridad al llegar la interconsulta y la deja fija, aunque el paciente
empeore mientras espera. El sistema mantiene la lista **activa**: cada evento clínico nuevo (urgencia, hospitalización,
examen, cambio de tratamiento, informe) se recibe por cualquier canal, se evalúa con criterios definidos por el equipo
médico (con apoyo de IA para leer), la decisión queda **documentada con sus fuentes y versiones**, un especialista la
revisa y su veredicto **mejora las decisiones siguientes**.

```
recepción (app · Excel/CSV · API · zona de carga S3 · informe)
  └─► ingesta: valida, resuelve el paciente, deduplica, guarda                 lambda/ingesta.py
        └─► evaluación: reglas con fuente + IA que lee y cita                    puntaje.py · rubrica.py · decisor.py
              └─► dictamen: qué cambió, por qué, con qué información y fuentes   lambda/bitacora.py
                    └─► lista actualizada                                         lambda/lista.py
                          └─► revisión del especialista: adecuada / incorrecta    acciones.post_revision
                                └─► aprendizaje: precedente → criterio propuesto → aprobación → regla versionada
                                                                                  lambda/aprendizaje.py
```

## 2. Arquitectura

**Serverless en AWS** (se mantuvo la opción A del anexo técnico: la más barata y simple de operar).

| Capa | Servicio | Qué hace aquí |
|---|---|---|
| Página | AWS Amplify Hosting | React + Vite. Login opcional con Cognito (PKCE). |
| API | API Gateway HTTP API | Una ruta `ANY /{proxy+}` con autorizador JWT opcional; `GET /health` y `OPTIONS` libres; límite de solicitudes; registro de accesos. |
| Cómputo | AWS Lambda (Python 3.12, arm64) | `ApiFunction` (`app.handler`), `TrabajadorFunction` (`ingesta.cola_handler`), `IngestaArchivoFunction` (`ingesta.s3_handler`), `BarridoFunction` (`app.barrido_handler`, apagada). Única dependencia: `pydantic`. |
| Datos | Amazon DynamoDB (on-demand) | Única fuente de verdad. Un paciente = una partición. Índice `PorDia` para leer solo lo nuevo. TTL, PITR, sin permisos de borrado. |
| Archivos | Amazon S3 | Zona de carga `entrada/` → resultado en `procesados/` o `errores/`. Versionado, cifrado, TLS obligatorio. |
| Cola | Amazon SQS + cola de fallidos | Desacopla la evaluación con IA de la recepción en cargas grandes. Respuesta parcial de lotes. |
| IA | Amazon Bedrock (Converse) | Claude lee con rúbricas cerradas y cita. Perfil de inferencia `us.` por parámetro. Guardrail opcional. |
| OCR | Amazon Textract | `DetectDocumentText` para fotos de informes. |
| Identidad | Amazon Cognito (opcional) | Grupos `gestion`, `especialista`, `jefatura`; cliente de máquina con scope `ambulatorio/ingesta`. |
| Operación | CloudWatch + SNS + EventBridge Scheduler | 11 alarmas, logs con retención, métrica de IA por llamada, barrido nocturno apagado. |
| Infraestructura | AWS SAM / CloudFormation | `template.yaml` (63 recursos posibles), `samconfig.toml` con ambientes `prueba` y `prod`. |

### Módulos del backend (`lambda/`)

| Módulo | Responsabilidad |
|---|---|
| `app.py` | Enrutador. Identidad y permisos, CORS, gzip, registro de accesos, errores sin detalle. Delega en el `rutear()` de cada módulo. |
| `seguridad.py` | Identidad desde el JWT (persona o máquina), tabla de permisos por ruta y rol, denegación por defecto. |
| `datos.py`, `almacen_dynamo.py` | Almacén: ítems normalizados, perfiles armados, copia por contenedor, lectura incremental, escritura condicional, control de edición (`rev`). Backend en memoria para local y tests (mismo código). |
| `ingesta.py` | Tubería única de recepción (todos los canales), idempotencia, registro de lotes, cola. |
| `puntaje.py` | Motor de reglas con fuente (Tabla SSMSO 2025 del HLF, Ord. 536, GES, criterios oficiales, letalidad). Capas al final (criterios locales). |
| `rubrica.py`, `decisor.py`, `controles.py`, `algoritmo.py`, `evaluacion_ia.py` | IA que lee el historial con una rúbrica cerrada; fórmula fija; controles; 3 lecturas; vigencia por huella. |
| `lector_documento.py`, `criterios.py`, `combinaciones.py`, `informe.py`, `lectura_informe.py` | Lectura de informes y fotos (Textract + IA o reglas), criterios por enfermedad y combinaciones de riesgo, con citas verificadas. |
| `cliente_ia.py` | Configuración de IA: modo simulado, lecturas, modelo de redacción, guardrail, caché, reintento con `toolChoice` automático, métricas. |
| `bitacora.py` | Dictámenes: documentación de cada decisión, cola de revisión. |
| `aprendizaje.py` | Veredictos, precedentes, criterios locales, enmiendas, indicadores de concordancia. |
| `base_conocimiento.py` | Servicio de conocimiento médico versionado: manifiesto, consulta por diagnóstico, fuentes de cada razón. |
| `lista.py`, `indicadores.py`, `catalogo.py`, `acciones.py`, `ingreso.py`, `explicar.py`, `privacidad.py` | Lista priorizada, KPI, vocabularios, acciones del equipo, ingreso, resumen para el equipo, ocultar nombre y RUT antes de la IA. |

## 3. Datos: estructura, almacenamiento, actualización y consulta

### 3.1 Antecedentes de pacientes (DynamoDB)

Tabla única, clave `id_paciente` (partición) + `sk` (orden). Solo se agrega: nada se pisa ni se borra.

| `sk` | Contenido |
|---|---|
| `perfil` | Datos del paciente y de su interconsulta; contador `rev`; `perfil_base` si se modificó el original |
| `evento#<fecha>#<id>` · `medicion#…` · `cita#…` | Cada registro clínico con identidad propia (se puede citar, enmendar y deduplicar) |
| `revision#` · `decision#` · `contacto#` · `gestion#` · `orden#` · `novedad#` · `evaluacion#` · `dictamen#` · `enmienda#` | Lo que registran el equipo y el sistema, con marca de tiempo |

Particiones reservadas: `_kb` (criterios locales), `_ingesta` (lotes), `_idem` (claves de idempotencia, con TTL),
`_meta` (marcador de frescura). Todo ítem lleva `ts` y `dia` (para el índice `PorDia`).

**Lectura.** Cada contenedor carga la tabla una vez (Scan en paralelo) y trabaja con una copia en memoria indexada.
En cada solicitud lee el marcador (`GetItem` consistente, 1 unidad). Si cambió, trae solo lo nuevo por `PorDia`. Un
proceso que solo necesita un paciente (la cola) hace una `Query` a su partición. **Ya no hay Scan por solicitud.**

**Escritura.** `PutItem`/`UpdateItem` condicionales (idempotentes). El rol IAM no tiene `DeleteItem` ni
`BatchWriteItem`. Si dos personas actúan sobre el mismo paciente, la segunda recibe **409** (`rev_vista`).

**Carga del registro del hospital.** `scripts/cargar_registro.py` convierte `perfiles.json` en ítems (idempotente).
Después, todo entra por la ingesta.

### 3.2 Criterios y fuentes del equipo médico (conocimiento versionado)

| Fuente (`lambda/conocimiento/`) | Qué es |
|---|---|
| `diagnosticos_tabla_hlf`, `ssmso_hlf_2025` | Tabla de priorización SSMSO 2025, sección del HLF (págs. 84–111), verificada página por página |
| `ord536` | Orden de la lista no GES (MINSAL Ord. 536/2025) |
| `ges_especialista` | 8 garantías GES de atención por especialista, con cita de auge.minsal.cl |
| `criterios_registro`, `criterios_especialidad` | Criterios por diagnóstico (Queensland CPC, NICE) y por enfermedad (46 enfermedades) |
| `combinaciones_riesgo` | 44 combinaciones de riesgo (35 verificadas) |
| `pubmed_evidencia`, `guias_umbrales`, `rubrica_v1` | Ventanas de riesgo con PMID, umbrales de guías, rúbrica consolidada |

- **Manifiesto** (`manifiesto.json`, lo genera `scripts/empaquetar_conocimiento.py`): por fuente, versión, estado de
  verificación y **huella del contenido** (independiente del formato); huella del motor de reglas; etiqueta del paquete.
  Un test y el CI fallan si una fuente cambia sin regenerarlo; el generador rechaza un cambio de contenido con la misma
  versión. La API informa si lo desplegado coincide con el manifiesto (`paquete.integro`).
- **Consulta por clave**, no por similitud: `GET /conocimiento/diagnostico/{cie10}` entrega todo lo que el sistema sabe
  y aplica para ese diagnóstico, cada bloque con su fuente y versión. A la IA solo va la parte de su diagnóstico.
- **Criterios locales** (los que nacen de la retroalimentación) en DynamoDB `_kb`, con historial de estados.
- Cada dictamen guarda el paquete y las **fuentes exactas** (id, versión, huella) que respaldan sus razones.

Por qué no búsqueda vectorial: el corpus es chico (~400 entradas) y estructurado; la recuperación por clave es exacta,
reproducible y auditable. Conviene sumar una Knowledge Base solo si se agregan guías en texto libre, y aun así para
**citar pasajes**, no para decidir (D4).

### 3.3 Escala y costo (medidos y de lista)

| Medición local (`scripts/medir_escala.py`) | 500 | 4.000 | 26.000 |
|---|---:|---:|---:|
| Lista de una especialidad | 5 ms | 55 ms | 339 ms |
| Lista completa | 30 ms | 275 ms | 1,9 s |
| JSON de una especialidad (sin / con gzip) | 0,4 / 0,02 MB | 2,9 / 0,07 MB | 18,7 / 0,32 MB |

Infraestructura (anexo técnico + ficha de precios oficial): decenas de USD al mes en piloto. La IA es el costo variable:
~0,0015 USD por evaluación con Claude Haiku 5.5 y ~0,031 USD con Claude Sonnet 5.5 (3 lecturas, tokens medidos en
octubre). Se evalúa **solo a quien recibe un dato nuevo** y se reutiliza la lectura si nada cambió (huella). Detalle en
D6, D7 y D10 de `DECISIONES.md`; precios en `docs/investigacion/Ficha_AWS_2026-11.md`.

## 4. Integraciones y flujo de eventos

Todos los canales terminan en `ingesta.registrar()`: validar con el vocabulario del registro → resolver el paciente
(id o RUT) → deduplicar → foto del estado anterior → guardar → registro del lote → evaluar → dictámenes.

| Canal | Entrada | Autenticación (con `cognito`) | Evaluación |
|---|---|---|---|
| App | `POST /eventos`, `POST /importar` (Excel/CSV), `POST /pacientes/{id}/informe` | Persona, rol `gestion` | En la solicitud |
| Sistemas del hospital | `POST /ingesta/eventos` con `Idempotency-Key` | Máquina, scope `ambulatorio/ingesta` | En la solicitud (≤ 25 pacientes) o cola |
| Carga programada | Archivo en `s3://<bucket>/entrada/…` | Política de carga del bucket | Cola |
| Consulta | `GET /pacientes?campos=resumen&limite=&desde=` | Cualquier autenticado | — |

Ejemplo de envío de un sistema:

```bash
curl -X POST "$API/ingesta/eventos" -H "authorization: Bearer $TOKEN" -H "content-type: application/json" \
  -H "idempotency-key: urg-2026-10-12-0001" \
  -d '{"origen": "urgencia-hlf", "eventos": [{"rut": "12.345.678-5", "fecha_evento": "2026-10-12",
       "tipo_evento": "visita_urgencia", "subtipo": "triage ESI 2", "motivo": "disnea"}]}'
```

Propiedades: idempotente (por contenido y por clave); la severidad sale del subtipo, no del remitente; un evento de
alguien que no está en la lista se cuenta y **no se guarda**; cada evento guarda cuándo llegó, por qué canal, de qué
sistema y en qué lote (`GET /ingesta/lotes`). HL7 FHIR queda como siguiente adaptador cuando MINSAL defina perfiles.

## 5. Priorización

1. **Categoría** (alta / media / baja): parte de la prioridad de la SIC y **solo sube** por reglas con fuente: fila
   "descompensado" de la tabla del HLF, regla oncológica, criterios oficiales calculables con el registro (asma con UCI,
   EPOC con > 3 urgencias, HbA1c > 10 % que empeora…), criterios por enfermedad y combinaciones de riesgo leídos en
   textos, y **criterios locales aprobados**. Nunca baja sola.
2. **Orden** (Ord. 536/2025): categoría → urgencia "derivar hoy" → descompensación grave → letalidad → agudeza →
   descompensado → grupo de especial protección → antigüedad > 1 año → LACE (desempate) → días de espera.
3. **IA** (`ALGORITMO=rubrica`): ante un evento, Claude lee los antecedentes del paciente con la rúbrica de su
   diagnóstico y responde con citas exactas; el código verifica cada cita en el registro; una fórmula fija aplica la
   tabla; controles (cita inválida, lecturas distintas, bajaría, discrepancia, falla) hacen que rijan las reglas. Lo que
   **bajaría** a alguien va al especialista. Sin IA (`reglas`) el resultado es el mismo con datos estructurados; la IA
   aporta al leer **texto libre** (informes, epicrisis, motivo de la interconsulta).
4. **Modo simulado** (`MODEL_ID=simulado`): lector determinista para demostrar y probar sin AWS; queda rotulado.

## 6. Documentación de cada decisión (dictamen)

Cada evaluación gatillada por un disparador deja un **dictamen** (`dictamen#`), que no se modifica:

| Campo | Contenido |
|---|---|
| `disparador` | Tipo (evento, ingreso, novedad, informe, importación, criterio local, enmienda), canal, evento, lote, usuario |
| `motor` | `ia_rubrica`, `reglas` o `reglas_respaldo` (la IA falló o un control la frenó) |
| `resultado` | Prioridad y puesto antes → después, cambio, alerta nueva, `requiere_revision` |
| `fundamento` + `explicacion` | Razones con fuente; texto simple por plantilla (sin IA, reproducible) |
| `informacion_utilizada.antecedentes` | Cuántos eventos y mediciones, período, firma, **registros concretos citados** |
| `informacion_utilizada.conocimiento` | Paquete, **cada fuente con versión y huella**, criterios locales aplicados y propuestos |
| `informacion_utilizada.precedentes` | Qué dijeron los especialistas en casos del mismo patrón |
| `informacion_utilizada.ia` | Modelo, versión de rúbrica y de base, huella del prompt, lecturas, controles, tokens |

Rutas: `GET /decisiones?estado=pendiente|revisada|todas`, `GET /decisiones/{id}`, `GET /pacientes/{id}/decisiones`.
La cola de revisión ordena primero las alertas nuevas y luego los patrones con más desacuerdo histórico.

## 7. Revisión del especialista y retroalimentación

- **Veredicto** (`POST /pacientes/{id}/revision`): `adecuada` / `incorrecta`, prioridad corregida, motivo de una lista
  cerrada (`criterio_faltante`, `criterio_no_aplica`, `evento_no_relacionado`, `lectura_incorrecta`,
  `informacion_no_registrada`, `otro`) y explicación. Queda atado al dictamen juzgado, con nombre y rol.
- **Precedente**: cada veredicto se agrega al historial de su **patrón** (diagnóstico | tipo de evento | gravedad).
- **Criterio local**: "falta un criterio" propone una regla para el patrón. **Propuesta, no cambia a nadie**: los casos
  que calzan la muestran y van a la cola del especialista. **Jefatura la aprueba** (`POST /criterios-locales/{id}/resolver`)
  y desde ese día el motor la aplica (solo sube), en reglas y en IA por igual, citando quién la aprobó y en cuántas
  revisiones se basa. Retirarla no baja a nadie.
- **Correcciones hacia abajo** (`criterio_no_aplica`): nunca se vuelven regla automática; la regla objetada aparece en
  "reglas a validar con el equipo médico" (cambiarla es editar la fuente oficial, con revisión y versión nueva).
- **Enmiendas** (`POST /pacientes/{id}/eventos/{id_evento}/enmienda`): anular un evento o marcarlo sin relación, sin
  borrarlo.
- **Indicadores** (`GET /aprendizaje`, `GET /kpis`): concordancia global, por diagnóstico, por patrón y por regla (con
  su n), kappa contra la meta 0,70, decisiones pendientes y tiempo desde que llega un evento hasta su dictamen.

## 8. Seguridad y normativa

- Identidad del JWT (validado por API Gateway); roles por grupo; la identidad del navegador se ignora con token; ruta
  sin regla = denegada; cualquier valor de `AUTH` distinto de `ninguna` exige token.
- CORS solo desde el sitio; errores 500 genéricos con id de solicitud; registro de accesos sin datos clínicos.
- A la IA no se envía nombre ni RUT. Guardrail opcional (no revisa argumentos de herramientas ni reconoce el RUT).
- Datos: cifrado, PITR, versionado, protección de borrado en prod, llave KMS propia opcional, ciclo de vida sin
  expiración (fichas clínicas ≥ 15 años).
- Pendiente antes de datos reales (no es del stack): evaluación de impacto (Ley 21.719), contrato con AWS y cláusulas
  de transferencia, exclusión de uso de contenido para Textract en AWS Organizations, WAF, cuentas separadas.

## 9. Ejecución y verificación

### 9.1 Local (sin AWS)

Requisitos: Python 3.11+, `pip install -r lambda/requirements.txt` (pydantic), Node.js 20+.

```bash
python scripts/demo.py
```

Levanta la API (http://localhost:3001) con IA **simulada** y la página (http://localhost:5174). Opciones: `--reglas`
(sin IA), `--bedrock <perfil>` (IA real con credenciales AWS), `--hoy` (fecha real). Los datos viven en memoria: al
reiniciar, la demo vuelve a su estado inicial. Escenarios: `python scripts/generar_escenarios.py` (deja `data/demo/` y
su `ESPERADO.md`).

### 9.2 Pruebas automáticas

```bash
pip install -r requirements-dev.txt
python -m pytest -q tests
python scripts/empaquetar_conocimiento.py --verificar
python scripts/validar_plantilla.py
cd front && npm ci && npm run build
```

**Resultado al cierre: 327 tests pasan**, el manifiesto está al día, la plantilla valida en sus 110.592 combinaciones
de parámetros y el front compila. Los tests cubren: reglas y orden (MINSAL, tabla del HLF), los cinco pacientes de
demo, el almacén contra memoria y contra DynamoDB emulado (incluida la sincronización entre contenedores y el 409),
ingesta por los cinco canales (S3 y SQS emulados), idempotencia, dictámenes, el ciclo completo de aprendizaje (12
escenarios, incluida la propiedad "con criterios locales cualesquiera nadie baja"), seguridad (matriz completa de
permisos, CORS, gzip, errores) y los clientes de IA (simulado, reintentos, lecturas, caché).

### 9.3 Recorrido de verificación de punta a punta (por la API)

Con la API local corriendo (`python scripts/demo.py --solo-api`):

| Paso | Llamada | Resultado esperado |
|---|---|---|
| 1 | `POST /eventos` urgencia ESI 2 a PAC-HLF-00027 (hipertensión, baja) | Se mantiene en baja (la tabla no tiene fila); dictamen con fuentes y `requiere_revision: true` |
| 2 | `GET /decisiones?estado=pendiente` | Aparece el dictamen |
| 3 | `POST /pacientes/PAC-HLF-00027/revision` incorrecta → alta, `criterio_faltante` | `aprendizaje.criterio_local` = CL-0001 propuesto; nadie más cambia |
| 4 | `POST /criterios-locales/CL-0001/resolver` aprobar | Los pacientes del patrón suben, con su dictamen `criterio_local` |
| 5 | `POST /eventos` misma urgencia a PAC-HLF-00181 (hipertensión, baja) | Sube solo a alta; la razón cita CL-0001, quién lo aprobó y en cuántas revisiones se basa |
| 6 | `POST /ingesta/eventos` con `data/demo/eventos_api.json` y `Idempotency-Key` | 9 registrados, 7 dictámenes; repetir con la misma clave no procesa nada |
| 7 | `GET /conocimiento` | Paquete `kb-2026.11.0`, 10 fuentes con versión y huella |

Verificado el 14-11-2026 con IA simulada: los 7 pasos dan lo esperado.

### 9.4 Despliegue en AWS (cuando haya cuenta)

```bash
scripts/desplegar.sh prueba          # o: powershell -File scripts/deploy_aws.ps1 -Ambiente prueba
```

Verifica identidad → tests → paquete (pydantic arm64) → `sam deploy` → carga del registro sintético → `/health` y
`/pacientes` → publica la página. Paso a paso, CI/CD con OIDC y vuelta atrás en [`DEPLOY.md`](../../DEPLOY.md);
operación en [`docs/operacion/RUNBOOK.md`](../operacion/RUNBOOK.md).

## 10. Qué quedó implementado y qué falta verificar

| Componente | Implementado | Verificado | Falta verificar (cómo) |
|---|---|---|---|
| Almacén DynamoDB | Sí | Memoria y `moto` | Contra DynamoDB real: consistencia del índice y arranque en frío con 26.000 pacientes (medir con `scripts/cargar_registro.py` + `/health`) |
| Ingesta (5 canales) | Sí | Local, S3/SQS/SNS con `moto` | Notificación S3 real, cola real con la bitácora, 2.000 filas dentro de 30 s |
| IA con Bedrock | Sí | Con cliente simulado | Reintento con `toolChoice` auto en Sonnet 5.5, caché efectiva, guardrail; repetir `scripts/evaluar_algoritmo.py` con el modelo elegido |
| Textract | Sí (sin cambios) | Antes, en la cuenta del evento | Que el rol solo tenga `DetectDocumentText` |
| Cognito + JWT | Sí | Con eventos armados a mano | Formato real de los grupos en el autorizador; login PKCE en la página |
| Plantilla y despliegue | Sí | `cfn-lint`, validador, empaquetado | `sam deploy` real; reglas de `prod`; alarmas; workflows de GitHub |
| Bitácora y aprendizaje | Sí | Tests y recorrido local | Con especialistas reales: regla de la cola y gobierno de criterios locales |

## 11. Diferencias con el anexo técnico (PDF de noviembre 2026)

| Anexo dice | Implementación | Motivo |
|---|---|---|
| "Mantener serverless y reforzarlo" | Se hizo, con todas las brechas P1 del stack cerradas en la plantilla | Coincide |
| P1 sin autenticación / usuario como texto libre / CORS `*` / errores al cliente | Cognito + JWT opcional, identidad del token, CORS por parámetro, errores genéricos | Cerradas (verificación real pendiente) |
| P1 cifrado con llave de AWS, sin PITR | KMS propia opcional, PITR, versionado, protección de borrado en prod | Cerrada |
| P1 permisos `*` para Bedrock | Limitado a perfiles y modelos de Anthropic | Cerrada (Textract no admite restricción por recurso) |
| P1 script que borra la tabla | El rol de la app no puede borrar; `limpiar_demo.py` es de administración y solo borra lo de la demo | Cerrada |
| P2 Scan por solicitud; `perfiles.json` en memoria | Ítems normalizados + marcador + índice `PorDia`; carga a la tabla | Cerrada. El anexo sugería índice por especialidad o vista materializada: se dejó la vista para cuando el p95 lo exija (D6) |
| P2 sin control de edición simultánea | Contador `rev` y 409 | Cerrada en el almacén; conectada a revisión y enmienda |
| P2 despliegue manual solo Windows; IA definida distinto en cada lugar | `samconfig.toml` con modo de IA por ambiente, bash/PowerShell/Python, CI/CD con OIDC | Cerrada |
| P2 sin alarmas | 11 alarmas → SNS | Cerrada |
| Zona de carga + Lambda de ingesta (fase 2) | Implementada ya, más API de eventos con idempotencia | Adelantada |
| P3 Tailwind por CDN, fechas del dataset en el código | Sin cambio | No bloquea la demo |
| Modelo `us.anthropic.claude-sonnet-5` | Por defecto `us.anthropic.claude-sonnet-5-5`; Haiku 5.5 como alternativa barata | Sonnet 5.5 es el actual; rechaza `toolChoice` forzado: el cliente reintenta en automático |
| "La IA lee y redacta; el código decide" | Igual, más dictamen, veredicto y criterios locales | Requisito nuevo del flujo |
| Región por definir | `us-east-1` por parámetro | Región Chile no abierta al 13-11-2026; Textract no está en São Paulo |
| Costo "decenas de USD al mes" | Coincide para la infraestructura; IA según modelo (D10) | — |
| Fuentes de conocimiento | Igual, más manifiesto con huella; se detectaron 5 fuentes que cambiaron sin versión y una alerta (PHQ-9 ≥ 16) que nunca se emitía (corregida) | Trazabilidad de versiones |

## 12. Preguntas abiertas para el hospital y AWS

1. ¿Las 72 h son para revisar la prioridad (como quedó) o para que un médico evalúe al paciente?
2. ¿Quién aprueba un criterio local: jefatura de la especialidad, comité, o con un mínimo de precedentes?
3. ¿La categorización C1–C5 de urgencia equivale al ESI del registro? (hoy no se mapea, para no inventar)
4. ¿Un evento de una persona debe valer para todas sus interconsultas? (hoy sí)
5. ¿Qué sistema es la fuente de cada evento, con qué identificador y frecuencia? (define el canal: API o carga programada)
6. Modelo de IA: medir Haiku 5.5 frente a Sonnet 5.5 con los mismos casos antes de elegir.
7. Región: ¿conviene migrar a la región de Chile cuando abra? Con la plantilla es redespliegue + traslado de datos.
