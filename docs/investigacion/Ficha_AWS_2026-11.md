# Ficha de datos AWS verificados — MVP serverless (lista de espera repriorizada con IA)

- **Fecha de verificación:** 2026-11-13. **Región de referencia:** us-east-1 (N. Virginia). Columna **sa-east-1** (São Paulo) donde difiere. Precios en USD, sin impuestos.
- **Método:** documentación oficial (docs.aws.amazon.com) y páginas oficiales de precios. Las tablas de precios de AWS se cargan dinámicamente: los valores se leyeron del feed que usa la misma página (`b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/...`, publicado entre 2026-10-20 y 2026-11-12) para ambas regiones.
- **Confianza:** **VO** = `verificado en fuente oficial` · **FS** = `fuente secundaria` · **NV** = `no pude verificarlo`.
- **Formato:** coma decimal, punto de miles. Las claves entre corchetes apuntan a la URL listada bajo cada tabla.

## 1. DynamoDB on-demand

| Dato | us-east-1 | sa-east-1 | Fuente | Conf. |
|---|---|---|---|---|
| Escritura (WRU) | 0,625 USD por millón (1 WRU por KB; transaccional 2) | 0,9375 | [D1] | VO |
| Lectura (RRU) | 0,125 USD por millón (por 4 KB: eventual ½, fuerte 1, transaccional 2) | 0,1875 | [D1] | VO |
| Almacenamiento (tabla Standard) | 0,25 USD/GB-mes; primeros 25 GB gratis | 0,375 | [D1] | VO |
| PITR | 0,20 USD/GB-mes sobre tabla + LSI; acortar la retención no lo abarata | 0,30 | [D1] | VO |
| Respaldo on-demand / restauración | 0,10 USD/GB-mes / 0,15 USD/GB | 0,15 / 0,225 | [D1] | VO |
| Costo de un GSI | Sin tarifa propia. Cada escritura que afecta al índice consume escritura del índice (2 si cambia el valor de la clave del índice; 0 si no toca atributos del índice); lecturas y almacenamiento del índice se cobran aparte | igual | [D2] | VO |
| Rebaja vigente | −50 % en on-demand y −67 % en escrituras replicadas, desde 2024-11-01 | — | [D3] | VO |
| Nivel gratuito | 25 GB + 25 WCU/25 RCU; "uses provisioned capacity": no cubre solicitudes on-demand | — | [D1] | VO |
| Tamaño máximo de ítem | 400 KB (cuenta nombres y valores de atributos) | — | [D4] | VO |
| `TransactWriteItems` | Máx. 100 ítems únicos y 4 MB; no dos acciones sobre el mismo ítem; una sola cuenta y región | — | [D4] | VO |
| Lotes y consultas | `BatchWriteItem` 25 operaciones / 16 MB; `BatchGetItem` 100 ítems / 16 MB; `Query` y `Scan` 1 MB por llamada | — | [D4] | VO |
| Rendimiento por partición | 3.000 unidades de lectura/s y 1.000 de escritura/s | — | [D5] | VO |
| Tabla on-demand | Nueva: hasta 4.000 escrituras/s y 12.000 lecturas/s; absorbe al instante el doble del peak previo; cuota por defecto 40.000 RRU y 40.000 WRU por tabla (ajustable) | — | [D6] [D7] | VO |
| Índices por tabla | 20 GSI (ajustable) y 5 LSI | — | [D7] | VO |
| ¿Lectura consistente en un GSI? | **No**: "Strongly consistent reads from a global secondary index or a DynamoDB stream are not supported". Solo tabla base y LSI; el GSI se actualiza de forma asíncrona | — | [D8] [D2] | VO |
| Novedad: búsqueda vectorial nativa | GA 2026-08-05, solo on-demand; hasta 4.096 dimensiones, TopK 100, 5 índices vectoriales por tabla; escritura 0,52 USD/GB, búsqueda 0,002 USD/GB procesado | 0,78 / 0,003 | [D9] [D7] [D1] | VO |

Fuentes: [D1] https://aws.amazon.com/dynamodb/pricing/on-demand/ · [D2] https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GSI.html · [D3] https://aws.amazon.com/about-aws/whats-new/2024/11/amazon-dynamo-db-reduces-prices-on-demand-throughput-global-tables/ · [D4] https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Constraints.html · [D5] https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-partition-key-design.html · [D6] https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/on-demand-capacity-mode.html · [D7] https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/ServiceQuotas.html · [D8] https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadConsistency.html · [D9] https://aws.amazon.com/about-aws/whats-new/2026/08/amazon-dynamodb-vector-search/

## 2. Lambda (arm64) y API Gateway HTTP API

| Dato | us-east-1 | sa-east-1 | Fuente | Conf. |
|---|---|---|---|---|
| Lambda: duración arm64 | 0,0000133334 USD por GB-segundo (primeros 7.500 millones GB-s/mes); x86: 0,0000166667 | igual | [L1] | VO |
| Lambda: solicitudes | 0,20 USD por millón | igual | [L1] | VO |
| Lambda: nivel gratuito | 1 millón de solicitudes + 400.000 GB-s al mes | — | [L1] | VO |
| Lambda: fase INIT | Se factura desde 2025-08-01 también en funciones ZIP con runtime administrado (antes no se cobraba) | — | [L2] | VO |
| Lambda: payload síncrono | 6 MB la solicitud y 6 MB la respuesta; respuesta en streaming hasta 200 MB; invocación asíncrona 1 MB | — | [L3] | VO |
| Lambda: timeout máximo | 900 s (15 min); memoria 128 a 10.240 MB | — | [L3] | VO |
| HTTP API: precio | 1,00 USD por millón (primeros 300 millones), luego 0,90; medido en tramos de 512 KB | 1,59 / 1,43 | [A1] | VO |
| HTTP API: timeout de integración | 30 s, no ampliable | — | [A2] | VO |
| HTTP API: payload máximo | 10 MB, no ampliable | — | [A2] | VO |
| HTTP API: ¿comprime sola? | **No.** La compresión (`minimumCompressionSize`) está documentada solo para REST API y el recurso `Api` de apigatewayv2 no tiene propiedad de compresión | — | [A3] [A4] | VO (por ausencia; no hay frase explícita) |
| HTTP API: cómo comprimir | En la Lambda: gzip + base64 + cabecera `Content-Encoding` (artículo de 2020) | — | [A5] | FS |
| HTTP API: otras ausencias | Sin WAF, caché, validación de solicitudes, API keys, cuotas por cliente, X-Ray ni streaming de respuesta | — | [A6] | VO |

Fuentes: [L1] https://aws.amazon.com/lambda/pricing/ · [L2] https://aws.amazon.com/blogs/compute/aws-lambda-standardizes-billing-for-init-phase/ · [L3] https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html · [A1] https://aws.amazon.com/api-gateway/pricing/ · [A2] https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-quotas.html · [A3] https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-gzip-compression-decompression.html · [A4] https://docs.aws.amazon.com/apigatewayv2/latest/api-reference/apis-apiid.html · [A5] https://medium.com/@vanbergstephane/gzip-aws-lambda-http-api-gateway-6b9c6431c564 · [A6] https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-vs-rest.html

## 3. SQS, S3 y EventBridge Scheduler

| Dato | us-east-1 | sa-east-1 | Fuente | Conf. |
|---|---|---|---|---|
| SQS estándar | Primer millón de solicitudes al mes gratis; luego 0,40 USD por millón. Cada 64 KB de payload cuenta como 1 solicitud; payload máximo 1 MiB | 0,40 | [S1] | VO |
| S3 Standard | 0,023 USD/GB-mes (primeros 50 TB) | 0,0405 | [S2] | VO |
| S3 solicitudes | PUT/COPY/POST/LIST 0,005 USD por 1.000; GET 0,0004 USD por 1.000 | 0,007 / 0,00056 | [S2] | VO |
| S3 Event Notifications | Sin cargo adicional de S3; solo se paga el destino (SQS, SNS o Lambda) | igual | [S3] | VO |
| EventBridge Scheduler | 14 millones de invocaciones gratis al mes; luego 1,00 USD por millón | 1,70 | [S4] | VO |

Fuentes: [S1] https://aws.amazon.com/sqs/pricing/ · [S2] https://aws.amazon.com/s3/pricing/ · [S3] https://aws.amazon.com/s3/faqs/ · [S4] https://aws.amazon.com/eventbridge/pricing/

## 4. Amazon Bedrock con modelos Claude

**Modelos Claude listados hoy** ([B1], VO). 5.x: Fable 5.2, Mythos 5.2 (acceso restringido), Haiku 5.5, Sonnet 5.5, Opus 5.5, Fable 5.1, Mythos 5.1, Opus 5, Sonnet 5, Mythos 5, Fable 5. 4.x: Opus 4.8, Opus 4.7, Opus 4.6, Sonnet 4.6, Haiku 4.5, Opus 4.5, Sonnet 4.5, Sonnet 4, Opus 4.1. 3.x: Claude 3 Haiku.

| Modelo (lanzamiento) | ID de modelo | Perfil geográfico EE. UU. | Perfil global | Fuente | Conf. |
|---|---|---|---|---|---|
| Haiku 5.5 (2026-10-07) | `anthropic.claude-haiku-5-5` | `us.anthropic.claude-haiku-5-5` | `global.anthropic.claude-haiku-5-5` | [B2] | VO |
| Sonnet 5.5 (2026-09-28) | `anthropic.claude-sonnet-5-5` | `us.anthropic.claude-sonnet-5-5` | `global.anthropic.claude-sonnet-5-5` | [B3] | VO |
| Opus 5.5 (2026-09-22) | `anthropic.claude-opus-5-5` | `us.anthropic.claude-opus-5-5` | `global.anthropic.claude-opus-5-5` | [B4] | VO |
| Sonnet 4.6 (2026-02-17) | `anthropic.claude-sonnet-4-6` | `us.anthropic.claude-sonnet-4-6` | `global.anthropic.claude-sonnet-4-6` | [B5] | VO |
| Haiku 4.5 (2025-10-16) | `anthropic.claude-haiku-4-5-20251001-v1:0` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | `global.anthropic.claude-haiku-4-5-20251001-v1:0` | [B6] | VO |
| Otros IDs | `anthropic.claude-fable-5-2`, `anthropic.claude-opus-5`, `anthropic.claude-sonnet-5`, `anthropic.claude-opus-4-8`, `anthropic.claude-opus-4-7`, `anthropic.claude-opus-4-6-v1`, `anthropic.claude-opus-4-5-20251101-v1:0` | — | — | [B7] | VO |

Precio on-demand por millón de tokens, llamando desde us-east-1 ([B8], VO):

| Modelo | Perfil global: entrada / salida | Perfil `us.`: entrada / salida | Batch |
|---|---|---|---|
| Haiku 5.5 (prompt de hasta 100.000 tokens) | 0,10 / 0,50 | 0,11 / 0,55 | No disponible |
| Haiku 5.5 "Long Context" (prompt sobre 100.000 tokens) | 0,50 / 2,50 | 0,55 / 2,75 | No disponible |
| Sonnet 5.5 | 2,00 / 10,00 | 2,20 / 11,00 | No disponible |
| Opus 5.5 | 4,00 / 20,00 | 4,40 / 22,00 | No disponible |
| Haiku 4.5 | 1,00 / 5,00 | 1,10 / 5,50 | 0,50 / 2,50 (global) |
| Sonnet 4.6 | 3,00 / 15,00 | 3,30 / 16,50 | 1,50 / 7,50 (global) |

| Dato | Valor | Fuente | Conf. |
|---|---|---|---|
| ¿Existe batch? | Sí, "at a 50% lower price compared to on-demand". Pero Haiku 5.5, Sonnet 5.5, Opus 5.5 y Sonnet 5 **no** lo tienen (ficha: Batch no soportado; tampoco Flex ni Priority). Sí lo tienen Haiku 4.5, Sonnet 4.5/4.6, Opus 4.5/4.6 y Opus 5 | [B8] [B9] [B2] [B3] | VO |
| Límites del batch | Con formato Converse no acepta `toolConfig` (error 400; usar formato InvokeModel); no admite prompt caching | [B10] [B7] | VO |
| ¿Los perfiles procesan fuera de la región de origen? | **Sí.** `us.` desde us-east-1 enruta a us-east-1, us-east-2 y us-west-2. `global.` puede procesar en cualquier región comercial soportada del mundo y cuesta aprox. 10 % menos. El precio es el de la región de origen | [B2] [B12] [B13] | VO |
| Trazabilidad | CloudTrail y CloudWatch registran en la región de origen; `additionalEventData.inferenceRegion` indica dónde se procesó. Tráfico cifrado por red de AWS | [B12] [B13] | VO |
| Sin opción de una sola región | En el endpoint `bedrock-runtime` (el de Converse y Guardrails), Haiku 5.5, Sonnet 5.5, Haiku 4.5 y Sonnet 4.6 no tienen "In-Region" en us-east-1: exigen perfil geo o global, que "don't provide single-Region data residency" | [B2] [B3] [B5] [B6] | VO |
| Desde sa-east-1 | Solo perfil **global** para todos estos modelos, al mismo precio global; no existe perfil geográfico de Sudamérica | [B2] [B3] [B8] | VO |
| Residencia de datos | AWS advierte: no confiar en el prefijo del perfil; revisar destinos con `GetInferenceProfile` | [B14] | VO |
| Acceso del proveedor | Los proveedores de modelos no acceden a prompts ni respuestas. Entre los Claude, Bedrock solo declara retención (hasta 30 días, detección de abuso) para los modelos Fable; no la declara para Haiku, Sonnet ni Opus | [B15] [B16] | VO |
| Ciclo de vida | Haiku 4.5: "EOL no sooner than Oct 16, 2026" (fecha ya cumplida; sigue activo). Sonnet 4.6: no antes de 2027-02-17. Haiku 5.5: no antes de 2027-10-07 | [B6] [B5] [B2] | VO |
| Facturación | Los modelos de terceros se cobran vía AWS Marketplace y aparecen bajo el proveedor, no bajo "Amazon Bedrock" | [B2] | VO |

Fuentes: [B1] https://docs.aws.amazon.com/bedrock/latest/userguide/model-cards.html · [B2] https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-5-5.html · [B3] https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5-5.html · [B4] https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-opus-5-5.html · [B5] https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-4-6.html · [B6] https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-4-5.html · [B7] https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html · [B8] https://aws.amazon.com/bedrock/pricing/ · [B9] https://docs.aws.amazon.com/bedrock/latest/userguide/batch-inference-supported.html · [B10] https://docs.aws.amazon.com/bedrock/latest/userguide/batch-inference.html · [B12] https://docs.aws.amazon.com/bedrock/latest/userguide/cross-region-inference.html · [B13] https://docs.aws.amazon.com/bedrock/latest/userguide/global-cross-region-inference.html · [B14] https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-support.html · [B15] https://docs.aws.amazon.com/bedrock/latest/userguide/data-protection.html · [B16] https://docs.aws.amazon.com/bedrock/latest/userguide/abuse-detection.html

## 5. Bedrock Converse API

| Dato | Valor | Fuente | Conf. |
|---|---|---|---|
| `cachePoint` | `{"cachePoint": {"type": "default"}}` en `system`, `messages` y `tools`; máx. 4 por solicitud; orden de evaluación tools → system → messages | [C1] | VO |
| Modelos con caché explícita | Fable 5.2/5.1/5, Mythos 5.2/5.1/5, Haiku 5.5, Sonnet 5.5, Opus 5.5, Opus 5, Opus 4.8/4.7/4.6/4.5, Sonnet 5, Sonnet 4.6, Haiku 4.5 | [C1] | VO |
| Mínimo de tokens del prefijo | 512: Haiku 5.5, Sonnet 5.5, Opus 5.5, Opus 5, Fable, Mythos. 1.024: Sonnet 5, Sonnet 4.6, Opus 4.8. 4.096: Haiku 4.5, Opus 4.7/4.6/4.5. Bajo el mínimo la llamada funciona, pero no se guarda | [C1] | VO |
| TTL | 5 minutos por defecto (se renueva con cada acierto) o 1 hora con `"ttl": "1h"` | [C1] | VO |
| Precio de caché | Escritura 5 min = 1,25× la entrada; escritura 1 h = 2×; lectura = 0,1× en Haiku 5.5, Haiku 4.5 y Sonnet 4.6, y 0,05× en Sonnet 5.5 (desde 2026-10-07) y Opus 5.5. Perfil global, USD por millón (escritura 5 min / escritura 1 h / lectura): Haiku 5.5 0,125 / 0,20 / 0,01; Sonnet 5.5 2,50 / 4,00 / 0,10; Haiku 4.5 1,25 / 2,00 / 0,10 | [C2] | VO |
| Caché automática | `additionalModelRequestFields={"cache_control": {"type": "ephemeral"}}`; soportada en Haiku 4.5, Sonnet 4.6, Opus 4.7 en adelante, Sonnet 5/5.5 y Haiku 5.5 | [C1] | VO |
| Advertencias de caché | El acierto no está garantizado; con inferencia entre regiones puede haber más escrituras; `inputTokens` excluye los tokens de caché (sumar `cacheReadInputTokens` y `cacheWriteInputTokens`) | [C1] | VO |
| `toolChoice` forzado | Converse define `auto`, `any` y `tool`. **Sonnet 5.5 y Opus 5.5 solo aceptan `auto` y `none`.** Las fichas de Haiku 5.5, Haiku 4.5 y Sonnet 4.6 no indican restricción | [C3] [B3] [B4] [B2] | VO |
| `toolChoice` en Haiku 5.5 | La tabla de Anthropic asigna tokens de sistema para `any`/`tool` en Haiku 5.5 y deja la celda vacía en Sonnet 5.5 y Opus 5.5 | [C4] | VO (fuente oficial de Anthropic, no de AWS) |
| Alternativa a forzar herramienta | `outputConfig.textFormat` (salida estructurada) existe en la solicitud de Converse | [C5] | VO |
| `guardrailConfig` | Campos `guardrailIdentifier`, `guardrailVersion`, `trace`. Sin bloques `guardContent` evalúa todos los mensajes; `stopReason` puede ser `guardrail_intervened`. Guardrails no funciona en el endpoint `bedrock-mantle` | [C5] [B2] | VO |

Fuentes: [C1] https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html · [C2] https://aws.amazon.com/bedrock/pricing/ · [C3] https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ToolChoice.html · [C4] https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview · [C5] https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html

## 6. Bedrock Guardrails

| Dato | Valor | Fuente | Conf. |
|---|---|---|---|
| Filtros de contenido (texto) | 0,15 USD por 1.000 unidades de texto (1 unidad = hasta 1.000 caracteres); mismo precio en niveles Standard y Classic | [G1] | VO |
| Temas denegados | 0,15 USD por 1.000 unidades de texto | [G1] | VO |
| Información sensible (PII) | 0,10 USD por 1.000 unidades de texto; expresiones regulares y filtro de palabras: gratis | [G1] | VO |
| Otros | Grounding contextual 0,10; razonamiento automatizado 0,17 por política. API `InvokeGuardrailChecks`: contenido 0,07, ataque de prompt 0,08, PII 0,10 | [G1] | VO |
| ¿Enmascara PII en español? | **Sí.** Español figura como "Optimized and supported" en filtros de información sensible. Acciones: `BLOCK`, `ANONYMIZE` (reemplaza por `{NAME}`, `{EMAIL}`...) o `NONE` | [G2] [G3] | VO |
| Sin RUT chileno | Los tipos predefinidos son generales (nombre, dirección, teléfono, email, edad) más identificadores de EE. UU., Canadá y Reino Unido; el RUT requiere regex propia | [G3] | VO |
| Qué no cubre | Es un modelo probabilístico. No evalúa argumentos de herramientas (`toolUse.input`), `toolResult` ni definiciones de herramientas. Los logs de invocación y el campo `match` del trace conservan el valor original | [G3] | VO |

Fuentes: [G1] https://aws.amazon.com/bedrock/pricing/ · [G2] https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-supported-languages.html · [G3] https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-sensitive-filters.html

## 7. Knowledge Bases y almacenes vectoriales

| Dato | us-east-1 | sa-east-1 | Fuente | Conf. |
|---|---|---|---|---|
| OpenSearch Serverless: precio OCU | 0,24 USD por OCU-hora | 0,381 | [K1] | VO |
| Colecciones **Classic** | Mínimo 2 OCU en la primera colección (1 de indexación + 1 de búsqueda) = 350,40 USD/mes; modo dev-test sin réplicas: 1 OCU = 175,20 USD/mes (cálculo propio: OCU × 0,24 × 730 h). Las colecciones vectoriales no comparten OCU con las de búsqueda. Almacenamiento 0,024 USD/GB-mes | 556 / 278 | [K1] | VO (monto mensual derivado) |
| Colecciones **NextGen** | GA 2026-05-28. "There is no minimum OCU requirement": escalan a cero tras 10 minutos sin actividad. Almacenamiento hot 0,30 USD/GB-mes | 0,57 | [K1] [K2] | VO |
| S3 Vectors: estado | GA desde 2025-12-02, incluida su integración con Knowledge Bases. Disponible en us-east-1 y sa-east-1 | disponible | [K3] [K4] [K5] | VO |
| S3 Vectors: precio | Almacenamiento 0,06 USD/GB-mes; PUT 0,20 USD/GB; consultas 0,0025 USD por 1.000 más 0,004 USD/TB procesado (primeros 100.000 vectores); GET/LIST 0,055 USD por 1.000 | 0,11 / 0,35 / 0,0044 + 0,007 / 0,097 | [K6] | VO |
| S3 Vectors: límites | 2.000 millones de vectores por índice, 10.000 índices por bucket, 1 a 4.096 dimensiones; latencia bajo 1 s (cerca de 100 ms en consultas frecuentes). En Knowledge Bases: máx. 1 KB de metadata propia y 35 claves por vector; solo embeddings de punto flotante | igual | [K7] [K3] [K5] | VO |
| Managed Knowledge Base | GA 2026-06-17. 5,00 USD por GB de datos crudos al mes + 1,00 USD por 1.000 llamadas `Retrieve`; parsing, embeddings y rerank incluidos. Regiones: us-east-1, us-west-2, Sídney, Tokio, Dublín, Fráncfort, Londres, GovCloud | no disponible | [K8] [K9] | VO |
| Almacenes para KB autogestionada | OpenSearch Serverless, OpenSearch administrado, S3 Vectors, Aurora PostgreSQL, Neptune Analytics, Pinecone, Redis Enterprise Cloud, MongoDB Atlas | — | [K5] | VO |

**Ojo para el informe (lectura mía, no un dato):** el argumento "la búsqueda vectorial tiene un piso de ~350 USD/mes" hoy solo vale para colecciones Classic. Con S3 Vectors, NextGen, Managed KB o DynamoDB vectorial no hay costo fijo; la justificación para ~400 criterios estructurados tiene que apoyarse en otra cosa (búsqueda exacta por clave, trazabilidad, el corpus cabe en un prompt con caché).

Fuentes: [K1] https://aws.amazon.com/opensearch-service/pricing/ · [K2] https://aws.amazon.com/about-aws/whats-new/2026/05/amazon-opensearch-serverless-next-generation-generally-available/ · [K3] https://aws.amazon.com/blogs/aws/amazon-s3-vectors-now-generally-available-with-increased-scale-and-performance/ · [K4] https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-regions-quotas.html · [K5] https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-setup.html · [K6] https://aws.amazon.com/s3/pricing/ · [K7] https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-limitations.html · [K8] https://aws.amazon.com/bedrock/pricing/ · [K9] https://aws.amazon.com/about-aws/whats-new/2026/06/amazon-bedrock-managed-knowledge-base/

## 8. Amazon Textract

| Dato | Valor | Fuente | Conf. |
|---|---|---|---|
| `DetectDocumentText` | 1,50 USD por 1.000 páginas (primer millón de páginas al mes); 0,60 USD por 1.000 después | [T1] | VO |
| Regiones | **No está en sa-east-1.** Endpoints: us-east-1, us-east-2, us-west-1, us-west-2, ca-central-1, eu-west-1/2/3, eu-central-1/2, eu-south-2, ap-south-1, ap-northeast-1/2, ap-southeast-1/2 y GovCloud | [T2] | VO |
| Uso del contenido por defecto | Textract puede almacenar y usar las entradas para mejorar el servicio y otras tecnologías de IA de Amazon, y guardar parte en otra región, salvo exclusión | [T3] [T4] | VO |
| Cómo excluirse | Política de exclusión de servicios de IA de AWS Organizations (tipo `AISERVICES_OPT_OUT_POLICY`), creada desde la cuenta de administración o un administrador delegado y adjunta a la raíz, una OU o una cuenta. Claves válidas: `textract` o `default` (todos los servicios actuales y futuros). En consola: "Opt out from all services" | [T4] [T5] [T6] [T7] | VO |
| Efecto de excluirse | Se borra el contenido histórico guardado para mejora y deja de almacenarse en otra región; la preferencia se registra en todas las regiones | [T4] [T3] | VO |
| Idiomas | Texto impreso en más de 40 idiomas (incluye español). Manuscrito: "English only" | [T3] | VO |

```json
{"services": {"default": {"opt_out_policy": {"@@assign": "optOut"}}}}
```

Fuentes: [T1] https://aws.amazon.com/textract/pricing/ · [T2] https://docs.aws.amazon.com/general/latest/gr/textract.html · [T3] https://aws.amazon.com/textract/faqs/ · [T4] https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_ai-opt-out.html · [T5] https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_ai-opt-out_syntax.html · [T6] https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_ai-opt-out_all.html · [T7] https://docs.aws.amazon.com/organizations/latest/APIReference/API_EnablePolicyType.html

## 9. Amazon Cognito (plan vigente: niveles Lite, Essentials y Plus)

| Dato | Valor (igual en sa-east-1) | Fuente | Conf. |
|---|---|---|---|
| Essentials (por defecto en pools nuevos) | Primeros 10.000 MAU gratis; luego 0,015 USD por MAU | [N1] | VO |
| Lite | Primeros 10.000 MAU gratis; 0,0055 USD (10.001 a 100.000), 0,0046 (hasta 1 millón), 0,00325 (hasta 10 millones), 0,0025 después | [N1] | VO |
| Plus | 0,02 USD por MAU, sin nivel gratuito | [N1] | VO |
| Nivel gratuito | Indefinido (no vence a los 12 meses), por cuenta u organización. Usuarios federados SAML/OIDC: solo 50 MAU gratis, luego 0,015 | [N1] | VO |
| Tokens M2M (client credentials) | 2,25 USD por 1.000 solicitudes de token (0,00225 c/u) hasta 250.000 al mes; 1,50 por 1.000 hasta 5 millones; 1,125 después. Sin nivel gratuito | [N1] | VO |
| Cargo por app client M2M | **Eliminado el 2025-11-03**: "There is no additional charge for the number of app clients" | [N1] [N2] | VO |
| Mensajería | SMS (SNS) y correo (SES) se cobran aparte | [N1] | VO |

Fuentes: [N1] https://aws.amazon.com/cognito/pricing/ · [N2] https://aws.amazon.com/about-aws/whats-new/2025/11/amazon-cognito-removes-machine-machine-app-client-price-dimension

## 10. Región AWS en Chile (Santiago)

| Dato | Valor | Fuente | Conf. |
|---|---|---|---|
| ¿Ya abrió? | **No, al 2026-11-13.** La lista oficial tiene 34 regiones y ninguna en Chile; en Sudamérica solo sa-east-1. El feed de precios de DynamoDB (2026-11-11) tampoco trae región chilena | [R1] [D1] | VO |
| Estado oficial | "announced plans for 7 more Availability Zones and 2 more AWS Regions in the Kingdom of Saudi Arabia, and Chile" | [R2] | VO |
| Anuncio | 2025-05-07: "AWS South America (Chile) Region", lanzamiento "by the end of 2026", 3 zonas de disponibilidad | [R3] | VO |
| Página de AWS Chile | "A new AWS Region is coming to Chile in 2026!"; inversión de más de 4.000 millones USD en 15 años | [R4] | VO |
| Infraestructura actual en Chile | Local Zone en Santiago (2023), Direct Connect (2023), CloudFront (2019), Ground Station en Punta Arenas (2021), Outposts | [R3] | VO |
| Servicios al inicio (Bedrock, Textract) | No publicado. El anuncio solo dice que traerá "advanced cloud technologies, including artificial intelligence (AI)" | [R3] | NV |
| Fecha exacta y código de región | No publicados | — | NV |

Fuentes: [R1] https://docs.aws.amazon.com/global-infrastructure/latest/regions/aws-regions.html · [R2] https://aws.amazon.com/about-aws/global-infrastructure/regions_az/ · [R3] https://aws.amazon.com/blogs/aws/coming-soon-aws-south-america-chile-region · [R4] https://aws.amazon.com/local/chile/

## 11. AWS HealthLake / FHIR

- **Qué es y dónde está:** servicio elegible HIPAA para almacenar, analizar y compartir datos de salud con la especificación **FHIR R4** (servidor FHIR transaccional, SMART on FHIR, exportación masiva). Regiones: us-east-1, us-east-2, us-west-2, ca-central-1, eu-west-1, eu-west-2, ap-south-1 y ap-southeast-2; **no está en sa-east-1**. Fuentes: https://docs.aws.amazon.com/healthlake/latest/devguide/what-is.html · https://docs.aws.amazon.com/general/latest/gr/Amazon-HealthLake.html — VO.
- **Ley 21.668:** publicada en el Diario Oficial el 2024-05-28; modifica la Ley 20.584 para establecer la interoperabilidad de las fichas clínicas. Fuente: https://www.bcn.cl/leychile/navegar?i=1203827 — FS (leí el resumen del buscador, no el texto legal).

## Lo que no pude verificar

1. **Región de Chile:** fecha exacta de apertura, código de región y servicios disponibles al inicio (en particular Bedrock y Textract). AWS no los ha publicado.
2. **Knowledge Bases + OpenSearch Serverless NextGen:** si Bedrock Knowledge Bases acepta colecciones NextGen como almacén vectorial; los anuncios de lanzamiento no lo mencionan.
3. **HTTP API y compresión:** no encontré una frase oficial explícita de que HTTP API no comprime; lo concluyo por ausencia en la guía y en la referencia de API.
4. **GSI en modo on-demand:** la guía describe el consumo de escritura del índice en términos de capacidad aprovisionada; no hallé una frase oficial específica para on-demand (la FAQ no lo trata).
5. **`toolChoice` forzado en Haiku 5.5 vía Converse:** no lo probé. Se apoya en que la ficha de AWS no lista restricción y en la tabla de Anthropic. La referencia de Converse aún dice que `tool` es "Only supported by Anthropic Claude 3 and Amazon Nova models", texto que quedó desactualizado.
6. **Tablas de precios renderizadas:** no pude ver la tabla final de cada página (carga dinámica); leí su feed de datos. Coincide con los ejemplos en texto de las mismas páginas (DynamoDB, Lambda x86, HTTP API, Scheduler, Cognito M2M).
7. **Ley 21.668 y FHIR:** si la ley o su reglamento exigen específicamente HL7 FHIR, y la fecha de entrada en vigencia de los estándares del Minsal.
8. **No revisado:** impuestos (IVA), descuentos por volumen o acuerdos, transferencia de datos saliente, latencia desde Chile, y el ID de modelo de Opus 4.1 y de los modelos Claude 3.x antiguos.
