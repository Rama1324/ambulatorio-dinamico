# Especificación del MVP — priorización con IA, trazable y con retroalimentación

> Documento de trabajo (noviembre 2026). Es el **contrato entre los módulos** que se construyen en paralelo.
> Lo que ya existe y no se menciona aquí **se mantiene igual** (ver `contrato.md` y `docs/CRITERIO_PRIORIZACION.md`).

## 1. Flujo objetivo

```
recepción (app · archivo · API · zona de carga S3 · informe)
   └─► ingesta: valida, deduplica y guarda ítems normalizados            (ingesta.py)
          └─► evaluación: reglas + IA (lee con rúbrica; el código decide) (evaluacion_ia.py, algoritmo.py)
                 └─► dictamen: decisión documentada (qué se usó, fuentes y versiones, fundamento)  (bitacora.py)
                        └─► lista actualizada (lista.py)
                               └─► revisión del especialista: veredicto adecuada / incorrecta + motivo  (acciones.post_revision)
                                      └─► aprendizaje: precedente → criterio local propuesto → aprobado → conocimiento versionado
                                             └─► las decisiones siguientes lo aplican y lo citan   (aprendizaje.py)
```

## 2. Invariantes (no se rompen)

1. La IA **lee y cita**; el código verifica la cita y **decide con criterios con fuente**. Si la IA falla, rigen las reglas.
2. El sistema **sube solo, nunca baja solo**. Bajar (o quitar una alerta) siempre lo hace una persona identificada.
3. Todo se calcula a una `fecha_corte` con registros de fecha ≤ corte. Un criterio local rige desde su fecha de aprobación.
4. **Solo se agrega**: ningún registro se pisa ni se borra (salvo el ítem `perfil`, que lleva contador `rev` y deja `novedad#`).
5. Cada razón lleva su `fuente`. Cada decisión guarda **qué versión de cada fuente** usó.
6. Fallecidos y atendidos salen de la lista; las inasistencias no bajan la prioridad.
7. Única dependencia de la Lambda: `pydantic` (boto3 viene en el runtime). Para desarrollo: `boto3`, `moto`, `cfn-lint`, `pytest`.
8. Los 155 tests existentes siguen pasando. Los campos y rutas de `contrato.md` no cambian; solo se agregan.

## 3. Almacén (`lambda/datos.py` + `lambda/almacen_dynamo.py`)

**Decisión:** DynamoDB es la única fuente de verdad, con ítems normalizados por paciente. `perfiles.json` deja de leerse en
cada contenedor: se carga una vez a la tabla (`scripts/cargar_registro.py`). En local (`LOCAL=1`) el almacén en memoria se
inicializa convirtiendo `DATA_DIR/perfiles.json` a los mismos ítems: **un solo camino de código**.

### 3.1 Ítems (tabla `pk = id_paciente`, `sk`)

| `sk` | Atributo con el contenido (JSON en texto) | Notas |
|---|---|---|
| `perfil` | `perfil` = `{"paciente": {...}, "lista_espera": {...}}` | más `especialidad` y `rev` (número) |
| `evento#<fecha_evento>#<id_evento>` | `evento` | ya existía |
| `medicion#<fecha_medicion>#<tipo>#<hash8>` | `medicion` | hash8 de fecha+tipo+valor |
| `cita#<fecha_cita>#<id_cita o hash8>` | `cita` | |
| `revision#`, `contacto#`, `decision#`, `gestion#`, `orden#`, `novedad#`, `evaluacion#` + marca de tiempo | igual que hoy | |
| `dictamen#<ts>` | `dictamen` | §5 |
| `enmienda#<ts>` | `enmienda` | corrige un evento: anula o cambia `relacionado` (§6.4) |

Particiones reservadas (su `pk` empieza con `_`): `_kb` (`criterio_local#<id>#<ts>`, §6), `_ingesta` (`lote#<ts>#<id>`, §7),
`_idem` (`<clave>`, con `expira` para TTL), `_meta` (`ultimo`: marcador de frescura).

Todo ítem lleva además `ts` (momento UTC de escritura, ISO con microsegundos) y `dia` (`AAAA-MM-DD` de `ts`).
`ts` es del almacén; **no** es `evento.registrado` (los eventos del registro base no tienen `registrado`, y así debe seguir:
de eso depende `llego_al_sistema` y la vigencia de las revisiones). Los ítems del registro base llevan `origen = "registro_base"`.

Ya no existe `sk = "paciente#"` (perfil completo). No hay datos desplegados que migrar.

### 3.2 Lectura sin Scan por solicitud

- Cada contenedor mantiene una **copia en memoria** (ítems + perfiles armados), cargada una vez (Scan paralelo al arrancar).
- En cada solicitud: `GetItem` consistente de `_meta/ultimo`. Si su `ts` es igual al de la copia, no se lee nada más.
  Si cambió: `Query` al índice **`PorDia`** (`dia` HASH, `ts` RANGE, proyección ALL) con `ts >` el último visto (con 5 s de
  traslape; la mezcla es idempotente por `(pk, sk)`), reintentando brevemente hasta alcanzar el `ts` del marcador.
  Si cambió `epoca` del marcador (limpieza de la demo), recarga completa.
- Toda escritura actualiza la copia local y el marcador.
- `registros_de(pid)` usa `Query` por partición (para procesos que no necesitan la lista: trabajador de la cola).

### 3.3 API pública de `datos.py`

Se mantienen (misma firma y semántica): `hoy`, `fecha_de`, `fecha_valida`, `ahora`, `posterior`, `EntradaInvalida`,
`REGISTRO_AL`, `TIEMPO_REAL`, `datos_hasta`, `nueva_solicitud`, `perfiles`, `perfiles_combinados`, `registros`, `guardar`,
`guardar_evento`, `contactos`, `decisiones`, `gestiones`, `ajustes_orden`, `evaluaciones`, `evaluaciones_por_paciente`.
`perfiles()` devuelve lo mismo que `perfiles_combinados()[0]` (ya no hay "base" separada).

Nuevas:

```python
class Conflicto(Exception): ...                       # el handler responde 409
registros_de(pid) -> list[dict]                       # ítems de un paciente
registros_tipo(prefijo, pid=None) -> list[dict]       # ítems cuyo sk empieza con prefijo (índice en memoria), ordenados por sk
globales(pk, prefijo="") -> list[dict]                # ítems de una partición reservada, ordenados por sk
guardar(item, *, si_no_existe=False, rev_vista=None) -> bool   # False si ya existía; Conflicto si rev_vista no coincide
guardar_lote(items) -> int                            # escritura por lotes (ingesta); cada ítem con si_no_existe
guardar_perfil(pid, perfil) -> None                   # ítem "perfil" (solo paciente + lista_espera)
guardar_medicion(pid, m) -> bool ; guardar_cita(pid, c) -> bool      # idempotentes
rev(pid) -> int                                       # sube con cada escritura del paciente
items_de_perfil(perfil, origen=None) -> list[dict]    # convierte un perfil completo (formato perfiles.json) en ítems
```

`rev_vista`: control de edición simultánea. La app manda el `rev` que tenía a la vista al registrar una revisión, decisión
u orden; si el paciente recibió algo después, se responde **409** y la app recarga. En DynamoDB se hace con una
actualización condicional del contador (`rev = :vista`), que es atómica.

Perfil armado = ítem `perfil` + sus `evento#` (sin los anulados; con `relacionado` corregido por la última `enmienda#`)
+ `medicion#` + `cita#`, cada lista ordenada por fecha. Los eventos anulados quedan en `perfil["eventos_anulados"]`.

## 4. Base de conocimiento (`lambda/base_conocimiento.py`, `lambda/conocimiento/`)

**Decisión:** el conocimiento oficial (tabla SSMSO/HLF, Ord. 536, GES, criterios, combinaciones, evidencia) es chico
(≈300 KB, ~400 entradas) y estructurado: se guarda como **archivos JSON versionados junto al código** y se recupera **por
clave** (CIE-10, especialidad, tipo de evento), no por similitud. El conocimiento que nace de la retroalimentación
(criterios locales) vive en DynamoDB (§6). Alternativa descartada para el MVP: búsqueda vectorial / Bedrock Knowledge
Bases. No por costo (hoy hay opciones que escalan a cero), sino porque con un corpus tan chico y estructurado la
recuperación por clave es exacta, reproducible y auditable, y una búsqueda por similitud no lo es.

- `lambda/conocimiento/manifiesto.json` (lo genera `scripts/empaquetar_conocimiento.py`): por cada fuente
  `{id, titulo, tipo, archivo, version, sha256, fecha, origen_url, estado, entradas}` y el **paquete**
  `{etiqueta: "kb-AAAA.MM.N", huella: sha256 corto del manifiesto, generado}`. También la huella del **motor**
  (`puntaje.py`, `decisor.py`, `controles.py`, `rubrica.py`): parte de las reglas son constantes en el código.
- Un test falla si un archivo cambia y el manifiesto no (no se puede cambiar una fuente sin cambiar su huella).
- Servicio:

```python
paquete() -> {"etiqueta", "huella", "generado", "motor": {...}}
fuentes() -> list[dict]                               # el manifiesto
para_diagnostico(cie10) -> dict                       # todo lo que el sistema sabe y aplica para ese diagnóstico, con su fuente@versión
fuentes_de(razones) -> list[dict]                     # fuentes (id, titulo, version, sha256) que respaldan esas razones
registrar_capa_local(fn)                              # aprendizaje.py agrega los criterios locales vigentes a para_diagnostico
rutear(method, partes, qs, body) -> (status, body) | None   # GET /conocimiento, GET /conocimiento/diagnostico/{cie10}
```

## 5. Bitácora de decisiones (`lambda/bitacora.py`)

Un **dictamen** documenta cada vez que el sistema evalúa a un paciente por un disparador. Se guarda como
`sk = dictamen#<ts>` (solo se agrega).

```json
{
  "id_dictamen": "DIC-20261113T142233-4F2A", "id_paciente": "PAC-HLF-00002", "fecha": "2026-11-13T14:22:33.120000+00:00",
  "fecha_corte": "2026-10-13", "especialidad": "Cardiología",
  "disparador": {"tipo": "evento", "canal": "api", "id_evento": "EV-…", "descripcion": "visita_urgencia · triage ESI 2 (grave)", "id_lote": null},
  "motor": "ia_rubrica",
  "resultado": {"categoria_antes": "baja", "categoria": "alta", "cambio": "sube", "riesgo_vital": true, "urgencia_hoy": false,
                "estado_clinico": "descompensado", "posicion_antes": 61, "posicion": 4, "total": 84, "requiere_revision": false},
  "fundamento": [{"factor": "tabla_oficial", "valor": "\"Angina inestable\" → prioridad alta", "fuente": "Tabla SSMSO 2025, HLF, pág. 85", "riesgo": "…"}],
  "explicacion": "Subió de baja a alta porque …",
  "informacion_utilizada": {
    "antecedentes": {"firma": "…", "eventos": 3, "mediciones": 6, "comorbilidades": 0, "desde": "2025-11-08", "hasta": "2026-10-13",
                     "citados": [{"id_evento": "EV-…", "fecha": "2026-08-06", "tipo": "hospitalizacion", "valor": "ingreso hospitalario"}]},
    "conocimiento": {"paquete": {"etiqueta": "kb-2026.11.0", "huella": "…"},
                     "fuentes": [{"id": "diagnosticos_tabla_hlf", "titulo": "…", "version": "tabla_hlf_2025_v1", "sha256": "…"}],
                     "criterios_locales": [{"id": "CL-0001", "version": 1}]},
    "precedentes": {"patron": "I20|visita_urgencia|grave", "adecuadas": 3, "incorrectas": 1, "ultimos": [{"veredicto": "…", "motivo": "…", "usuario": "…", "fecha": "…"}]},
    "ia": {"modelo": "…", "version_rubrica": "…", "hash_prompt": "…", "lecturas": 3, "tokens_entrada": 0, "tokens_salida": 0,
           "latencia_s": 0.0, "controles": [], "id_evaluacion": "evaluacion#…"}
  },
  "revision": null
}
```

- `motor`: `ia_rubrica` (la rúbrica movió o confirmó), `reglas` (`ALGORITMO=reglas`), `reglas_respaldo` (la IA falló o un control la bloqueó).
- `disparador.tipo`: `evento | ingreso | novedad | informe | importacion | criterio_local | enmienda | barrido | revision_directa`.
  `canal`: `app | archivo | api | s3 | informe`.
- `explicacion`: texto corto por plantilla, armado **solo** con el fundamento (sin IA; siempre disponible y reproducible).
- `revision`: no se guarda en el dictamen; se une al leerlo con la `revision#` que lo cita (`id_dictamen`).
- La carga inicial del registro base **no** crea dictámenes (es la "foto"). Si el especialista revisa a un paciente sin
  dictamen, `post_revision` crea uno `revision_directa` con el estado vigente y el veredicto queda atado a él.
- **Necesita revisión** (cola del especialista): dictamen sin veredicto y sin revisión posterior del paciente, cuyo resultado
  cambió la prioridad, abrió una alerta de descompensación grave/urgencia, o trae `requiere_revision`.

API del módulo (la usan ingesta, acciones, ingreso y lectura_informe):

```python
fotos(pids, corte) -> dict[pid, fila | None]          # estado ANTES (una lista por especialidad, no una por paciente)
registrar_lote(disparadores: dict[pid, dict], corte, antes: dict, *, canal="app", usuario=None, id_lote=None,
               evaluaciones: dict[pid, dict] | None = None) -> list[dict]   # arma y guarda un dictamen por paciente
registrar(pid, corte, disparador, antes, **kw) -> dict | None               # atajo de un paciente
de_paciente(pid) -> list[dict]                        # más reciente primero, con su revisión unida
buscar(especialidad=None, estado="pendiente", limite=50, desde=None) -> list[dict]
rutear(method, partes, qs, body) -> (status, body) | None
   # GET /decisiones?especialidad=&estado=pendiente|revisada|todas&limite=   GET /decisiones/{id_dictamen}
   # GET /pacientes/{id}/decisiones
```

Cada fila de `GET /pacientes` agrega: `rev` y `dictamen` (resumen del último: `id_dictamen, fecha, cambio, motor, necesita_revision`).

## 6. Retroalimentación y aprendizaje (`lambda/aprendizaje.py`, `acciones.post_revision`)

### 6.1 Veredicto

`POST /pacientes/{id}/revision` (se mantiene `accion: confirmar | ajustar`) acepta además:

| Campo | Valores | Por defecto |
|---|---|---|
| `veredicto` | `adecuada`, `incorrecta` | `confirmar` → adecuada · `ajustar` → incorrecta |
| `motivo_codigo` | ver tabla | obligatorio si `incorrecta` |
| `id_dictamen` | dictamen que se juzga | el último del paciente (o se crea `revision_directa`) |
| `rev_vista` | número | sin control de edición |

`motivo_codigo` (vocabulario cerrado, también en `GET /catalogo` → `motivos_veredicto`):

| Código | Significa | Efecto de aprendizaje |
|---|---|---|
| `criterio_faltante` | Falta un criterio: debió quedar más arriba | precedente + **criterio local propuesto** `subir_a` |
| `criterio_no_aplica` | La regla usada no corresponde a este caso: no debió subir | precedente + la regla entra a "reglas a validar"; **no baja a nadie sola** |
| `evento_no_relacionado` | El evento no es por la enfermedad por la que espera | sugiere la enmienda `no_relacionado` |
| `lectura_incorrecta` | La IA leyó mal el informe o el historial | sugiere anular el evento; cuenta contra ese tipo de hallazgo |
| `informacion_no_registrada` | Hay información clínica que no está en el registro | solo este paciente |
| `otro` | Otro (explicado, 20+ caracteres) | solo queda el precedente |

La respuesta agrega `aprendizaje`: `{precedente, criterio_local, mensaje}`.

### 6.2 Patrón y precedentes

`patron = "<CIE-10 base>|<tipo_evento determinante o *>|<severidad o *>"` (el evento determinante es la última
descompensación vigente; `*` si no hay). Cada veredicto queda como **precedente** de su patrón. Todo dictamen nuevo trae
el historial de su patrón (`informacion_utilizada.precedentes`): la decisión queda informada por lo que ya dijeron los
especialistas, y la cola de revisión puede ordenar primero los patrones con más desacuerdo.

### 6.3 Criterios locales

Registro en `pk = "_kb"`, `sk = "criterio_local#<id>#<ts>"` (historial; rige el último estado de cada id):

```json
{"id": "CL-0001", "version": 1, "estado": "propuesto", "patron": {"diagnostico": "I10", "tipo_evento": "visita_urgencia", "severidad": "grave"},
 "efecto": {"tipo": "subir_a", "categoria": "alta"}, "texto": "Hipertensión esencial con visita a urgencia grave → prioridad alta",
 "precedentes": [{"id_dictamen": "…", "id_paciente": "…", "usuario": "…", "fecha": "…", "motivo": "…"}],
 "propuesto_por": "…", "resuelto_por": null, "vigente_desde": null, "vigente_hasta": null, "motivo_resolucion": null, "fecha": "…"}
```

- Estados: `propuesto → vigente | rechazado`; `vigente → retirado`. Lo resuelve una persona con rol jefatura:
  `POST /criterios-locales/{id}/resolver` `{accion: aprobar | rechazar | retirar, motivo (20+), usuario}`.
- **Propuesto:** no cambia ninguna prioridad. Los casos que calzan muestran la sugerencia y quedan con `requiere_revision`.
- **Vigente:** el motor lo aplica (solo `subir_a`, solo sube) para fechas de corte ≥ `vigente_desde`, con la razón
  `{"factor": "criterio_local", "valor": "<texto>", "fuente": "Criterio local HLF CL-0001 v1 · aprobado por <quién> el <fecha> · basado en N revisión(es) de especialista"}`.
  Al aprobarlo se crea un dictamen (`disparador.tipo = "criterio_local"`) para cada paciente cuya prioridad cambia.
- Se aplica como **capa** al final de `puntaje.puntuar` y de `decisor.decidir` (misma función en ambos, para que reglas e IA
  coincidan). `puntaje.py` no importa el almacén: expone `puntaje.CAPAS` (lista de funciones `(resultado, perfil, corte) -> resultado`).
- La versión de la capa local = número de resoluciones registradas; va en cada dictamen y en `GET /conocimiento`.

### 6.4 Enmiendas de eventos

`POST /pacientes/{id}/eventos/{id_evento}/enmienda` `{accion: anular | no_relacionado | relacionado, motivo (20+), usuario}`.
No borra el evento: agrega `enmienda#`. Es una decisión humana sobre ese paciente (puede bajarlo). Crea dictamen.

### 6.5 Indicadores

`GET /aprendizaje?especialidad=` → `{concordancia: {global, por_diagnostico[], por_patron[], por_regla[]}, criterios_locales[],
precedentes_recientes[], reglas_a_validar[], capa_local: {version}}`. `GET /kpis` mantiene sus campos y agrega
`reevaluacion.mediana_segundos_evento_a_dictamen` y `decisiones: {total, pendientes, adecuadas, incorrectas}`.

## 7. Ingesta continua (`lambda/ingesta.py`)

Todos los canales terminan en **una sola función**:

```python
registrar(carga: dict, *, canal, usuario=None, origen=None, archivo=None, corte=None, evaluar="ahora"|"cola") -> dict
# carga = {"pacientes": [...], "lista_espera": [...], "eventos": [...], "mediciones": [...], "citaciones": [...]}  (filas ya normalizadas)
# → {"id_lote", "canal", "recibidos", "registrados", "duplicados", "rechazados": [{"tabla", "indice", "motivo"}],
#    "pacientes_afectados", "dictamenes": [resumen], "evaluacion": "sincrona" | "en_cola"}
```

- Valida con el vocabulario del registro (`modelos.SUBTIPOS`; la severidad sale del subtipo, no del archivo).
- **Idempotencia:** `id_evento` del sistema de origen si viene; si no, uno determinista por contenido. Escritura
  `si_no_existe`: reenviar el mismo archivo o mensaje no duplica (se informa como `duplicados`).
- Cada evento nuevo lleva `registrado` (momento en que llegó), `canal`, `origen` e `id_lote`.
- Deja un registro de lote en `pk = "_ingesta"`.
- Tras guardar: `bitacora.fotos` (antes) → evaluación (IA si `ALGORITMO=rubrica`) → `bitacora.registrar_lote`.

Canales:

| Canal | Entrada | Evaluación |
|---|---|---|
| App: simular / registrar evento | `POST /eventos` (igual que hoy) | en la misma solicitud |
| App: Excel/CSV | `POST /importar` (igual que hoy; agrega `id_lote`, `dictamenes`) | en la misma solicitud |
| **API para sistemas** | `POST /ingesta/eventos` `{origen, eventos[], mediciones[]?, citaciones[]?}` + cabecera `Idempotency-Key` opcional | hasta 25 pacientes: en la solicitud; más: cola |
| **Zona de carga S3** | objeto en `s3://<bucket>/entrada/…` → `ingesta.s3_handler` (reutiliza `importar.py`); deja el resultado en `procesados/` o `errores/` | cola |
| Informe o foto | `POST /pacientes/{id}/informe` (igual que hoy) | en la misma solicitud |

`ingesta.cola_handler(event)`: consume la cola SQS (`{id_paciente, id_lote, canal, disparador}`), evalúa y registra el dictamen.
En local no hay cola: se procesa en línea. `GET /ingesta/lotes?limite=` y `GET /ingesta/lotes/{id}` muestran los lotes.

## 8. Seguridad (`lambda/seguridad.py`, `app.handler`)

- `AUTH=ninguna` (demo y local): como hoy; el rol es declarado (cabecera `X-Rol`) y solo informativo.
- `AUTH=cognito`: API Gateway valida el JWT. La identidad sale de `requestContext.authorizer.jwt.claims`; el `usuario` que
  mande el navegador se ignora. Roles (grupos de Cognito): `gestion`, `especialista`, `jefatura`; máquinas (client
  credentials, scope `ambulatorio/ingesta`): `integracion`.

| Acción | Rol mínimo |
|---|---|
| Lecturas | cualquiera autenticado |
| Contacto, gestión, ingreso, eventos manuales, informes, importar | `gestion` |
| Revisión (veredicto), decisión clínica, orden manual, enmienda | `especialista` |
| Resolver criterios locales | `jefatura` |
| `POST /ingesta/eventos` | `integracion` (o `gestion`) |

- CORS: solo `ORIGEN_PERMITIDO` (por defecto `*` en la demo). Errores 500: mensaje genérico + `id_solicitud`; el detalle solo en el log.
- Un registro JSON por solicitud (quién, qué ruta, qué paciente, estado, ms), sin datos clínicos.
- Respuestas grandes comprimidas con gzip si el cliente lo acepta. `GET /pacientes` acepta `limite`, `desde` y `campos=resumen`.

## 9. IA (Amazon Bedrock)

- `MODEL_ID=simulado`: **lector determinista** (sin Bedrock) para demostrar el flujo completo sin AWS. Queda rotulado
  `modelo: "simulado"` en cada evaluación y dictamen.
- `MODEL_ID=<modelo o perfil de inferencia>`: Bedrock Converse con herramienta obligatoria; si el modelo rechaza el
  `toolChoice` forzado (modelos nuevos), se reintenta con `auto` + instrucción explícita; la respuesta se valida igual con Pydantic.
- `LECTURAS_IA` (1–3, por defecto 3), `MODEL_ID_REDACCION` (opcional), `GUARDRAIL_ID` / `GUARDRAIL_VERSION` (opcionales).
- Cada llamada deja una línea de métrica (tarea, modelo, tokens, latencia) para controlar el costo.

## 10. Infraestructura (`template.yaml`)

| Recurso | Para qué |
|---|---|
| `RegistrosTable` | claves `id_paciente` + `sk`; GSI `PorDia` (`dia`, `ts`, ALL); TTL `expira`; PITR; SSE-KMS opcional |
| `DataBucket` | versionado; prefijos `entrada/`, `procesados/`, `errores/`, `conocimiento/`; evento S3 de `entrada/` |
| `ApiFunction` (`app.handler`) | API |
| `TrabajadorFunction` (`ingesta.cola_handler`) | consume `ColaEvaluacion` (SQS) con su cola de mensajes fallidos |
| `IngestaArchivoFunction` (`ingesta.s3_handler`) | archivos que llegan a `entrada/` |
| `BarridoFunction` (`app.barrido_handler`) | reevaluación nocturna (EventBridge Scheduler) |
| Cognito (opcional, `Autenticacion=cognito`) | usuarios, grupos, cliente web y cliente de integración |
| Alarmas CloudWatch + tema SNS | errores, duración, 5xx, mensajes fallidos |

Variables de entorno: `TABLE`, `BUCKET`, `COLA_EVALUACION_URL`, `MODEL_ID`, `MODEL_ID_REDACCION`, `BEDROCK_REGION`, `ALGORITMO`,
`FECHA_REFERENCIA`, `REGISTRO_AL`, `AUTH`, `ORIGEN_PERMITIDO`, `LECTURAS_IA`, `GUARDRAIL_ID`, `GUARDRAIL_VERSION`,
`PREFIJO_ENTRADA` (`entrada/`), `TEMA_ALERTAS_ARN`.

## 11. Reglas para quien implementa

- Español chileno, directo. Código en el estilo del repo (funciones cortas, comentarios que dicen el porqué).
- Toda regla clínica nueva cita su fuente. No inventar umbrales ni prioridades.
- Correr `python -X utf8 -m pytest -q tests` antes de terminar. Los tests nuevos van en archivos nuevos `tests/test_<tema>.py`.
- No tocar archivos fuera de los asignados; si hace falta, avisar en el informe final en vez de editarlos.
- Nunca `Write` sobre un archivo existente que no sea propio: usar ediciones acotadas.
