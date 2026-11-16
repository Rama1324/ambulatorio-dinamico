# Cómo correr y desplegar — Ambulatorio Dinámico HLF

> **Estado (noviembre 2026): escrito y validado sin AWS; no desplegado.**
> La cuenta AWS del hackatón ya no existe. La plantilla pasa `cfn-lint` sin errores ni advertencias y el script de
> despliegue se probó de punta a punta con dobles de `aws` y `sam` (Windows: PowerShell 5.1, PowerShell 7 y Git Bash).
> Nada de esto se ha creado en una cuenta real. La [sección 11](#11-qué-quedó-sin-verificar-y-cómo-comprobarlo) dice
> qué falta comprobar y cómo, el día que haya cuenta. Para operar el sistema: [`docs/operacion/RUNBOOK.md`](docs/operacion/RUNBOOK.md).

## 0. Mapa

| Archivo | Para qué |
|---|---|
| `template.yaml` | Toda la infraestructura (SAM/CloudFormation), comentada bloque por bloque |
| `samconfig.toml` | **Única fuente** del nombre del stack, la región y el modo de IA de cada ambiente |
| `scripts/desplegar.py` | La lógica del despliegue. La lanzan `scripts/desplegar.sh` (Linux, macOS, CloudShell, Git Bash) y `scripts\deploy_aws.ps1` (PowerShell) |
| `scripts/validar_plantilla.py` | Valida plantilla y `samconfig.toml` sin AWS (corre antes de cada despliegue y en CI) |
| `scripts/demo.py` | Demo local sin AWS (`scripts\iniciar_demo.ps1` solo lo llama) |
| `infra/github-oidc.yaml` | Rol de AWS para el pipeline de GitHub, sin llaves guardadas |
| `.github/workflows/` | `ci.yml` (cada pull request) y `desplegar.yml` (al juntar en `main`) |
| `requirements-dev.txt` | Dependencias para probar y desplegar (no van dentro de la Lambda) |

**Qué crea el stack** (63 recursos como máximo; 49 en `prueba`, 61 en `prod`):

| Pieza | Recursos | Notas |
|---|---|---|
| Datos | Tabla DynamoDB `RegistrosTable` (índice `PorDia`, TTL `expira`, PITR) · bucket S3 con versionado y zona de carga `entrada/` · cola SQS de evaluación + cola de fallidos | Nada de esto se borra al eliminar el stack |
| Cómputo | 4 funciones Lambda (Python 3.12, arm64) del mismo paquete: API, trabajador de la cola, ingesta de archivos, barrido nocturno | Un rol IAM por función |
| API | API Gateway HTTP API: CORS, límite de solicitudes, registro de accesos y autorizador JWT opcional | Recursos nativos `AWS::ApiGatewayV2::*` |
| Login (opcional) | Cognito: usuarios, grupos `gestion` / `especialista` / `jefatura`, cliente web (PKCE) y cliente para sistemas del hospital | Solo con `Autenticacion=cognito` |
| Cifrado (opcional) | Llave KMS propia con rotación | Solo con `LlavePropia=si` |
| Página | Aplicación de Amplify Hosting | El script le sube la página compilada |
| Operación | 5 grupos de logs con retención · 12 alarmas · tema SNS con correo opcional · alerta de gasto opcional | |

**Dos ambientes**, definidos en `samconfig.toml`:

| | `prueba` | `prod` |
|---|---|---|
| Stack | `ambulatorio-hlf-prueba` | `ambulatorio-hlf-prod` |
| Datos | Sintéticos (se cargan solos) | Reales (entran por los canales de ingesta) |
| Login | No (`Autenticacion=ninguna`) | Sí, con segundo factor obligatorio |
| Origen web (CORS) | `*` | Solo el sitio del stack |
| Cifrado | Llaves administradas por AWS | Llave propia del hospital |
| Borrado | Se puede eliminar | Tabla y usuarios protegidos; versiones del bucket no se pueden borrar |
| Modo de IA | `rubrica` con `us.anthropic.claude-sonnet-5-5` | `reglas` (Bedrock solo redacta); pasar a `rubrica` es decisión del equipo clínico |
| Logs | 90 días | 731 días (lo define el hospital) |

La plantilla **rechaza** un `prod` sin login o con origen `*` (sección `Rules`): no se puede desplegar por descuido.

## 1. Requisitos

| Herramienta | Versión | Para qué |
|---|---|---|
| Python | 3.11 o superior (ideal 3.12, el de la Lambda) | Tests, validación, empaquetado y scripts |
| `python -m pip install -r requirements-dev.txt` | — | pytest, boto3, moto, cfn-lint |
| Node.js | 20.19+ o 22.12+ (lo pide Vite 8) | Compilar la página |
| AWS CLI v2 y AWS SAM CLI | recientes, en el `PATH` | Solo para desplegar |
| `data/perfiles.json` | dataset sintético del hospital | Tests y demo. **No va en git** |

Funciona en Windows (PowerShell o Git Bash), macOS, Linux y AWS CloudShell. En CloudShell el Python del sistema es
antiguo: `sudo dnf install -y python3.12 python3.12-pip` y luego `PYTHON=python3.12 scripts/desplegar.sh …`.
Si el computador tiene varios Python, los lanzadores eligen el que tiene instaladas las dependencias y el script
muestra cuál usó.

## 2. Correr en local (sin AWS)

```bash
python -m pip install -r requirements-dev.txt
python scripts/demo.py                 # API en localhost:3001 + página en localhost:5174, IA simulada
python scripts/demo.py --reglas        # solo reglas, sin IA
python scripts/demo.py --bedrock us.anthropic.claude-sonnet-5-5   # IA real: necesita credenciales de AWS vigentes
```

En PowerShell también sirve `scripts\iniciar_demo.ps1` (mismas opciones: `-Reglas`, `-Bedrock`, `-Hoy`, `-SoloApi`…).
Lo registrado vive en memoria: al reiniciar, la demo vuelve a su estado inicial.

Antes de entregar un cambio:

```bash
python -X utf8 -m pytest -q tests          # deben pasar todas
python scripts/validar_plantilla.py        # plantilla + samconfig.toml
cd front && npm ci && npm run build
```

## 3. Desplegar en una cuenta nueva, paso a paso

### 3.1 Entrar a la cuenta

Los scripts usan las credenciales activas de AWS CLI; no tienen perfil ni cuenta fijos.

```bash
aws configure sso          # una vez: URL del portal, cuenta, rol y nombre de perfil
aws sso login --profile hlf-prueba
aws sts get-caller-identity --profile hlf-prueba     # debe mostrar la cuenta correcta
```

Lo recomendado es **una cuenta por ambiente** (la alerta de gasto y los permisos quedan aislados). El script muestra la
cuenta, la identidad y la región antes de tocar nada, y en `prod` pide escribir `prod` para continuar.

### 3.2 Región

El punto de partida es **`us-east-1`**, y está escrito en un solo lugar: `region` de cada ambiente en `samconfig.toml`.

- Hoy no es condición que los datos estén en Chile, y la región de AWS en Chile todavía no abre.
- São Paulo (`sa-east-1`) no sirve tal cual: Amazon Textract no existe ahí, y los perfiles de inferencia `us.` de
  Claude procesan en `us-east-1`, `us-east-2` y `us-west-2`.
- Si se cambia la región del stack, `BedrockRegion` debe seguir apuntando a una región con el modelo y con Textract
  (el código usa la misma para ambos). Los datos clínicos que lee la IA viajan a esa región sin nombre ni RUT.

### 3.3 Habilitar el modelo en Bedrock (una vez por cuenta)

Sin este paso el sistema funciona igual, pero la IA cae al respaldo por reglas sin avisar a nadie.

Los modelos de terceros se activan en la cuenta con la **primera invocación**, y quien la hace necesita permisos de AWS
Marketplace (`aws-marketplace:Subscribe`, `Unsubscribe` y `ViewSubscriptions`). El rol de la Lambda no los tiene, a
propósito: por eso una persona administradora invoca el modelo una vez (el *playground* de la consola de Bedrock o el
comando de abajo). Después cualquier rol con permiso para invocar puede usarlo.

```bash
aws bedrock-runtime converse --region us-east-1 --model-id us.anthropic.claude-sonnet-5-5 \
  --messages '[{"role":"user","content":[{"text":"Responde solo: ok"}]}]' --inference-config '{"maxTokens":20}'
aws bedrock get-foundation-model-availability --model-id <id del modelo base> --region us-east-1   # debe decir AVAILABLE
```

- La activación puede tardar hasta 15 minutos; mientras tanto las llamadas pueden responder `AccessDeniedException`.
- La cuenta necesita un medio de pago válido para AWS Marketplace.
- El formulario de caso de uso de Anthropic solo se pide para modelos anteriores a Claude Opus 4.7; los actuales no lo
  exigen.

Fuente: documentación de Amazon Bedrock, "Request access to models" (noviembre de 2026). Si todavía no hay acceso a
Bedrock, se puede desplegar igual con el lector simulado: `--parametros "ModelId=simulado"`.

### 3.4 Primer despliegue de `prueba`

```bash
scripts/desplegar.sh prueba --perfil hlf-prueba
```
```powershell
powershell -ExecutionPolicy Bypass -File scripts\deploy_aws.ps1 -Ambiente prueba -Perfil hlf-prueba
```

Qué hace, en orden. Si un paso falla, se detiene ahí:

| Paso | Qué hace | Se detiene si… |
|---|---|---|
| 1. Identidad | Muestra cuenta, identidad, región y stack | No hay credenciales vigentes |
| 2. Verificación | `validar_plantilla.py` y `pytest` | Falla la plantilla o **falla un test** |
| 3. Paquete | Copia `lambda/` e instala `pydantic` para Linux arm64 / Python 3.12 | El paquete trae binarios de otra plataforma |
| 4. Stack | `sam deploy` con los valores del ambiente | CloudFormation rechaza o revierte el cambio |
| 5. Datos | Solo `prueba`, y solo si la tabla está vacía: `python scripts/cargar_registro.py --archivo data/perfiles.json --tabla <tabla> --region <región> --perfil ""` | Falla la carga |
| 6. Comprobación | `/health` responde; `/pacientes` entrega la lista (sin login) o responde 401 sin token (con login); un origen ajeno no recibe permiso de CORS | Cualquiera de las tres falla |
| 7. Página | Compila el front con la dirección de la API y lo publica en Amplify | El build falla, queda vacío o no trae la dirección de la API: **nunca publica un sitio vacío** |

Al final muestra las direcciones de la API y de la página. Las salidas del stack se pueden volver a ver con:

```bash
aws cloudformation describe-stacks --stack-name ambulatorio-hlf-prueba --region us-east-1 \
  --query "Stacks[0].Outputs[].[OutputKey,OutputValue]" --output table
```

`ApiUrl`, `BucketName`, `TableName`, `ColaEvaluacionUrl`, `ColaFallidosUrl`, `TemaAlertasArn`, `PoliticaCargaArn`,
`Autenticacion`, `SitioAppId`, `SitioUrl` y, cuando aplica, `LlaveDatosArn`, `UsuariosId`, `ClienteWebId`,
`ClienteIntegracionId`, `LoginUrl`, `EmisorTokens`.

### 3.5 Opciones del script

| Bash | PowerShell | Efecto |
|---|---|---|
| `prueba` \| `prod` | `-Ambiente` | Ambiente de `samconfig.toml` (por defecto `prueba`) |
| `--solo-front` | `-SoloFront` | Solo compila y publica la página |
| `--solo-backend` | `-SoloBackend` | No publica la página |
| `--parametros "Clave=Valor …"` | `-Parametros` | Pisa parámetros de `samconfig.toml` **en este despliegue** (también variable `PARAMETROS_EXTRA`) |
| `--sin-datos` / `--recargar-datos` | `-SinDatos` / `-RecargarDatos` | No cargar / volver a cargar el registro sintético |
| `--sin-tests` | `-SinTests` | Salta los tests. Solo para volver atrás a una versión ya probada |
| `--region`, `--perfil`, `--app-amplify` | `-Region`, `-Perfil`, `-AppAmplify` | Región, perfil de AWS CLI, otra aplicación de Amplify |
| `--si` | `-Si` | No pedir confirmación (pipeline con aprobación previa) |
| `--solo-paquete` | — | Solo arma el paquete de la Lambda; no usa AWS |

Un parámetro que deba quedar para siempre se escribe en `samconfig.toml`, no en la línea de comandos: el próximo
despliegue sin `--parametros` vuelve al valor del archivo.

### 3.6 Desplegar `prod`

Antes: revisar en `samconfig.toml` la fecha `RegistroAl` (cuándo se extrajo el registro real) y decidir el correo de
alertas y el presupuesto.

```bash
scripts/desplegar.sh prod --perfil hlf-prod --parametros "CorreoAlertas=ti@hospital.cl PresupuestoMensualUSD=150"
```

`sam deploy` muestra los cambios y pide confirmarlos. Después: confirmar el correo de suscripción que llega a
`CorreoAlertas`, dar de alta a los usuarios (RUNBOOK) y entregar al hospital la política de la zona de carga
(sección 6).

## 4. Activar la IA

El modo de IA se define **solo** en `samconfig.toml`, con tres parámetros:

| Parámetro | Valores | Efecto |
|---|---|---|
| `Algoritmo` | `reglas` \| `rubrica` | `reglas`: solo el motor de reglas oficiales. `rubrica`: la IA lee con rúbrica cerrada, el código verifica cada cita y decide con criterios con fuente; si la IA falla, rigen las reglas |
| `ModelId` | perfil de inferencia · `simulado` · vacío | Perfil de Bedrock · lector determinista sin Bedrock · sin IA (explicaciones por plantilla) |
| `BarridoActivo` | `DISABLED` \| `ENABLED` | Reevaluación nocturna (04:00, hora de Chile). Apagada por defecto: gasta Bedrock aunque nadie use la aplicación |

La plantilla exige `ModelId` cuando `Algoritmo=rubrica` y `Algoritmo=rubrica` cuando el barrido está encendido.

- **Modelos.** Los modelos Claude actuales en Bedrock (Haiku 5.5, Sonnet 5.5) solo se invocan a través de un perfil de
  inferencia: `us.` (procesa en `us-east-1`, `us-east-2` y `us-west-2`) o `global.`. `samconfig.toml` usa
  `us.anthropic.claude-sonnet-5-5` (identificador de la ficha del modelo en Bedrock, `docs/investigacion/Ficha_AWS_2026-11.md`).
  El algoritmo se midió con `us.anthropic.claude-sonnet-5`: antes de usar `rubrica` con datos reales hay que repetir la
  medición con el modelo nuevo (`python scripts/evaluar_algoritmo.py`). Sonnet 5.5 no acepta `toolChoice` forzado (solo
  `auto`): el código reintenta con `auto` y valida igual la respuesta. Alternativa más barata: `us.anthropic.claude-haiku-5-5`.
  Para cambiarlo, copiar el identificador exacto del perfil desde la consola de Bedrock (*Inference profiles*) y ponerlo en `ModelId`.
- **Permisos.** Solo existen si hay un modelo real configurado, y cubren únicamente perfiles y modelos de Anthropic: el
  perfil en la región de IA y los modelos base en las regiones a las que el perfil enruta. No hay que tocar IAM para
  cambiar entre modelos de Anthropic.
- **Otros ajustes:** `ModelIdRedaccion` (otro modelo solo para redactar), `LecturasIA` (1 a 3 lecturas por paciente),
  `GuardrailId` + `GuardrailVersion` (guardrail de Bedrock), `ConcurrenciaTrabajador` y `LoteTrabajador` (cuántos
  pacientes se evalúan a la vez desde la cola; por defecto 2, es decir, hasta 6 llamadas simultáneas a Bedrock).
- **Comprobar que la IA responde de verdad** (si no hay acceso, el sistema sigue funcionando con las reglas):
  `POST /pacientes/{id}/explicar` debe responder con fuente `bedrock` y no `plantilla`; y en los logs de la función de
  la API no debe aparecer `AccessDenied` ni `Bedrock falló`.

## 5. Activar el login (Cognito)

`prod` ya lo trae. Para probarlo en `prueba`: `--parametros "Autenticacion=cognito OrigenPermitido=sitio"`.

Qué cambia con `Autenticacion=cognito`:

- API Gateway valida el token **antes** de invocar a la Lambda. Toda ruta exige `Authorization: Bearer <token de acceso>`,
  salvo `GET /health` y las consultas previas del navegador (`OPTIONS`).
- Se crean los usuarios (nadie se registra solo), los tres grupos que el código usa como roles y la pantalla de login
  alojada por Cognito (`LoginUrl`).
- `MfaCognito`: `OFF`, `OPTIONAL` o `ON` (segundo factor con aplicación autenticadora). En `prod` va `ON`.
- La sesión dura un turno: el token de acceso vence a los 60 minutos y se renueva solo hasta por 12 horas.

**Usuarios y roles:** alta, baja y cambio de rol están en el RUNBOOK (sección 3).

**Página.** El script compila el front con estas variables, tomadas de las salidas del stack:
`VITE_API_URL`, `VITE_AUTH` (`ninguna` o `cognito`), `VITE_COGNITO_DOMINIO` (`LoginUrl`), `VITE_COGNITO_CLIENTE`
(`ClienteWebId`) y `VITE_COGNITO_REDIRECCION` (`SitioUrl`). El flujo es código de autorización con PKCE; la página debe
enviar el **token de acceso** (trae `cognito:groups`), no el de identidad. Si el front usa otros nombres de variable,
hay que alinearlos en `publicar_pagina()` de `scripts/desplegar.py`.

**Sistemas del hospital.** Usan el cliente `ClienteIntegracionId` con su secreto (cómo obtenerlo: RUNBOOK) y piden el
token directo, sin usuario:

```bash
curl -s -X POST "<LoginUrl>/oauth2/token" -u "<ClienteIntegracionId>:<secreto>" \
  -d "grant_type=client_credentials&scope=ambulatorio/ingesta"
```

**Dominio propio.** Si la página se sirve desde un dominio del hospital, poner `OrigenPermitido=https://lista.hospital.cl`
y `UrlsRetorno=https://lista.hospital.cl,https://lista.hospital.cl/` en `samconfig.toml`. Para desarrollar en local
contra un stack con login, agregar `http://localhost:5174` a `UrlsRetorno`.

## 6. Cargar datos

**Registro sintético (`prueba`).** Lo carga el script la primera vez (tabla vacía). A mano:

```bash
python scripts/cargar_registro.py --archivo data/perfiles.json --tabla <TableName> --region us-east-1 --perfil ""
```

`--perfil ""` usa las credenciales activas (o `AWS_PROFILE`); sin él, el cargador busca el perfil `hack` del hackatón.
**La aplicación ya no lee `perfiles.json` desde S3**: la única fuente es la tabla. Sin esta carga, la lista sale vacía.

Nunca se carga en `prod`.

**Datos del hospital.** Tres canales, todos terminan en la misma tubería de ingesta (idempotente: reenviar no duplica):

| Canal | Cómo | Evaluación |
|---|---|---|
| Aplicación | Pestaña "Cargar datos" (Excel/CSV) o registro manual | En la misma solicitud |
| API para sistemas | `POST /ingesta/eventos` con token de `ClienteIntegracionId` | Hasta 25 pacientes en la solicitud; más, por la cola |
| **Zona de carga** | Dejar el archivo en `s3://<BucketName>/entrada/` | Por la cola |

Para la zona de carga, adjuntar la política `PoliticaCargaArn` al usuario o rol con que el hospital sube archivos: solo
permite **escribir en `entrada/`** (no puede leer ni borrar). Con credenciales de ese usuario:

```bash
aws s3 cp eventos_2026-11-20.csv s3://<BucketName>/entrada/
```

El resultado de cada archivo queda en `procesados/` o `errores/` y en la aplicación. Qué hacer si un archivo trae
errores: RUNBOOK, sección 4. Los formatos aceptados son los de `GET /plantillas/{tabla}`.

Al cargar el registro real por primera vez, poner en `samconfig.toml` (`prod`) `RegistroAl` = fecha de extracción.

## 7. Verificación

El script ya comprueba lo esencial (paso 6). A mano:

```bash
API=<ApiUrl>
curl -s "$API/health"                                   # {"ok": true, "pacientes": 500, ...}
curl -s -o /dev/null -w "%{http_code}\n" "$API/pacientes"   # 200 sin login · 401 con login
curl -s -o /dev/null -D - -H "Origin: https://otro-sitio.example" "$API/health" | grep -i access-control
                                                        # con origen restringido no debe aparecer nada
```

Lista de comprobación después de un despliegue: la página abre y muestra la lista · un evento de prueba reordena la
lista · llegó (y se confirmó) el correo de suscripción a las alertas y una alarma forzada a mano llega por correo
(`aws cloudwatch set-alarm-state`, ver sección 11) · en `prod`, un usuario de cada grupo puede entrar y solo hace lo
que su rol permite · un archivo de prueba en `entrada/` aparece en `procesados/`.

## 8. Publicar la página

**Mecanismo actual (zip manual).** El stack crea la aplicación de Amplify (`SitioAppId`); el script compila el front y
le sube el resultado. Solo la página: `scripts/desplegar.sh prueba --solo-front`. Mientras el build no termine bien, la
página anterior sigue en línea.

**Alternativa por Git (`amplify.yml`).** Amplify compila solo en cada `git push`:

1. Consola de Amplify → *Create new app* → GitHub → el repositorio y la rama `main` → marcar monorepo con carpeta
   `front` (usa `amplify.yml` de la raíz).
2. Variable de entorno `VITE_API_URL` = `ApiUrl` del stack. Node 20.19 o superior en la imagen de build (si falla por
   versión: fijarla en *Build settings* o agregar `nvm install 22 && nvm use 22` al `preBuild`).
3. En `samconfig.toml`: `SitioAmplify="no"`, `OrigenPermitido="https://main.<id>.amplifyapp.com"` y, con login,
   `UrlsRetorno` con esa misma dirección. Desplegar con `--solo-backend`.

No usar los dos mecanismos sobre la misma aplicación.

## 9. Volver atrás

| Qué falló | Cómo se vuelve |
|---|---|
| `sam deploy` falla a medias | CloudFormation revierte solo y deja el stack como estaba. Si era la **primera** creación, el stack queda en `ROLLBACK_COMPLETE`: eliminarlo (`aws cloudformation delete-stack`) y volver a desplegar |
| Una versión desplegada tiene un error | `git checkout <etiqueta o commit anterior>` y `scripts/desplegar.sh <ambiente>`. Con el pipeline: *Actions → Desplegar → Run workflow* eligiendo la etiqueta. Conviene etiquetar cada versión que llega a `prod` (`git tag prod-AAAA-MM-DD`) |
| Hay que volver atrás **ya** y no está el dataset para los tests | `--sin-tests`, solo hacia una versión que ya estuvo desplegada |
| Solo la página quedó mal | Volver al commit anterior y `--solo-front` |
| Un parámetro quedó mal | Corregir `samconfig.toml` y desplegar con `--solo-backend` |
| Se dañaron o borraron datos | Restauración a un punto en el tiempo: RUNBOOK, sección 2 |

Volver atrás el código **no** deshace lo que se escribió en la tabla: los registros solo se agregan.

## 10. CI/CD con GitHub Actions

**`ci.yml` — en cada pull request, sin AWS.** `cfn-lint`, `scripts/validar_plantilla.py`,
`scripts/empaquetar_conocimiento.py --verificar`, armado del paquete arm64, `pytest` y `npm ci && npm run build`.

Los tests necesitan el dataset, que no está en git. Si el secreto `DATASET_URL` no está configurado (o el pull request
viene de un fork), **los tests no corren**: el trabajo "Tests (pytest)" aparece como omitido, queda una advertencia y
todo lo demás corre igual. Para activarlos:

| En GitHub (Settings → Secrets and variables → Actions) | Valor |
|---|---|
| Secreto `DATASET_URL` | Enlace HTTPS de descarga directa de `perfiles.json` (almacenamiento privado; el dataset pesa 1 MB, no cabe en un secreto) |
| Variable `DATASET_SHA256` (opcional) | Huella del archivo: detecta un enlace vencido o un archivo cambiado |

**`desplegar.yml` — al juntar en `main`.** Despliega `prueba` y, si todo pasa, deja `prod` esperando la aprobación de
una persona. Usa el mismo `scripts/desplegar.sh`. **Todavía no está activo.** Para activarlo:

*En AWS* (una vez por ambiente, con un usuario administrador):

```bash
aws cloudformation deploy --template-file infra/github-oidc.yaml --stack-name ambulatorio-hlf-github-prueba \
  --capabilities CAPABILITY_NAMED_IAM --region us-east-1 \
  --parameter-overrides Repositorio=<organizacion>/<repositorio> Ambiente=prueba \
                        PoliticaPermisos=arn:aws:iam::aws:policy/AdministratorAccess
```

Para `prod`: `Ambiente=prod`, otro nombre de stack y, si es la misma cuenta, `CrearProveedor=no`. La salida `RolArn` es
el rol que asume el pipeline: solo confía en ejecuciones de ese repositorio dentro de ese *environment*, y sus
credenciales duran una hora. `AdministratorAccess` es el punto de partida (el mismo de `sam pipeline bootstrap`) y solo
es aceptable en una cuenta dedicada: **antes de `prod` hay que reemplazarla por una política acotada**, acordada con el
equipo de AWS.

*En GitHub* (Settings → Environments):

| Environment | Configurar |
|---|---|
| `prueba` | Variable `AWS_ROLE_ARN` = `RolArn` del stack de prueba |
| `prod` | Variable `AWS_ROLE_ARN` = `RolArn` de prod · **Required reviewers** (quién aprueba) · limitar a la rama `main` |
| Ambos (opcional) | Variable `PARAMETROS_EXTRA` (por ejemplo `CorreoAlertas=ti@hospital.cl PresupuestoMensualUSD=150`) · variable `DATASET_S3_URI` (`s3://…/perfiles.json` en un bucket que el rol pueda leer; si no está, se usa `DATASET_URL`) |

Endurecimiento pendiente antes de `prod`: fijar las *actions* por hash de commit en vez de por versión y proteger la
rama `main` (revisión obligatoria y CI en verde).

## 11. Qué quedó sin verificar y cómo comprobarlo

Lo que **sí** se hizo: `cfn-lint` sin errores ni advertencias sobre `template.yaml` e `infra/github-oidc.yaml`; la misma
revisión sobre la plantilla expandida (para que corran las reglas que cfn-lint omite con SAM); las 110.592 combinaciones
de parámetros que cambian la estructura, sin referencias a recursos inexistentes; `samconfig.toml` contra los parámetros
y reglas de la plantilla; y un despliegue simulado completo con dobles de `aws` y `sam`, incluidos los casos de falla
(tests en rojo, sin dataset, `sam` falla, `/health` caído, API sin protección, CORS abierto, build roto).

Lo que **no** se pudo verificar sin una cuenta:

| # | Sin verificar | Cómo comprobarlo |
|---|---|---|
| 1 | Que el stack se cree en AWS. cfn-lint revisa esquema y referencias, no el comportamiento de cada servicio | `scripts/desplegar.sh prueba` en una cuenta de prueba: debe terminar en `CREATE_COMPLETE` |
| 2 | La transformación real de SAM y que conserve la sección `Rules` | El mismo despliegue; y `--parametros "Ambiente=prod Autenticacion=ninguna"` debe ser **rechazado** con el mensaje de la regla |
| 3 | Que SAM CLI lea `samconfig.toml` como se espera (`parameter_overrides` en varias líneas) | En el paso 4 del script, `sam deploy` debe listar los parámetros del ambiente con sus valores |
| 4 | Permisos de Bedrock: perfil + modelos base, con la condición `bedrock:InferenceProfileArn` | Sección 4, "Comprobar que la IA responde de verdad" |
| 5 | Llave propia: tabla, bucket, colas, logs y tema cifrados; política de la llave (incluida la condición que limita su uso a las alarmas de la cuenta) | Desplegar `prueba` con `--parametros "LlavePropia=si CorreoAlertas=…"`, registrar un evento, subir un archivo y forzar una alarma: `aws cloudwatch set-alarm-state --alarm-name <nombre> --state-value ALARM --state-reason prueba`. **Debe llegar el correo**; si no llega, el historial de la alarma muestra el error de KMS |
| 6 | Cognito: pantalla de login con segundo factor obligatorio, PKCE, tokens con `cognito:groups`, cliente de sistemas | Entrar con un usuario de cada grupo; pedir un token con el `curl` de la sección 5 y llamar a `POST /ingesta/eventos` |
| 7 | API Gateway: 401 sin token, `OPTIONS` sin token, CORS restringido, 429 al pasar el límite, registro de accesos con el usuario | Paso 6 del script; revisar el grupo de logs `/aws/vendedlogs/apigateway/<stack>` |
| 8 | Zona de carga: aviso de S3 → ingesta → `procesados/` o `errores/`; fallos a la cola de fallidos | Subir un archivo válido y uno inválido a `entrada/` |
| 9 | Cola → trabajador: concurrencia máxima, respuesta parcial y paso a fallidos al quinto intento | Carga de más de 25 pacientes por la API; ver la cola vaciarse |
| 10 | Aplicación de Amplify creada por CloudFormation + publicación por zip (antes la creaba el script con la CLI) | Paso 7 del script |
| 11 | Scripts en Linux, macOS y CloudShell (solo se probaron en Windows) y contra AWS real | Correr `scripts/desplegar.sh prueba` en esos sistemas |
| 12 | Los workflows de GitHub nunca corrieron (sintaxis YAML revisada; versiones de *actions*, OIDC y *environments* sin probar) | Abrir un pull request y juntarlo en `main` con todo configurado |
| 13 | Alerta de gasto (`AWS::Budgets::Budget`) y barrido nocturno (EventBridge Scheduler) | Desplegar con `PresupuestoMensualUSD` y con `BarridoActivo=ENABLED` en `prueba` |
| 14 | El código que estas piezas invocan (`ingesta.cola_handler`, `ingesta.s3_handler`, `app.barrido_handler`, `scripts/cargar_registro.py`) está en integración | Tests de esos módulos y los puntos 8 y 9 |
| 15 | La página todavía no tiene pantalla de login: solo lee `VITE_API_URL`. El script ya le pasa `VITE_AUTH`, `VITE_COGNITO_DOMINIO`, `VITE_COGNITO_CLIENTE` y `VITE_COGNITO_REDIRECCION` | Con `Autenticacion=cognito` la API responde 401 a la página hasta que el front implemente el login con PKCE |
| 16 | Carga inicial de la tabla en cada contenedor (`SEGMENTOS_SCAN`, parámetro `SegmentosScan`, por defecto 4) | Ver en los logs de la API cuánto demora la primera solicitud tras desplegar |

## 12. Eliminar un ambiente de prueba

Lo que guarda datos queda a propósito aunque se elimine el stack; hay que borrarlo a mano.

```bash
aws cloudformation delete-stack --stack-name ambulatorio-hlf-prueba --region us-east-1
aws cloudformation wait stack-delete-complete --stack-name ambulatorio-hlf-prueba --region us-east-1
# quedan: la tabla, el bucket, los grupos de logs y, si existían, la llave y los usuarios
aws dynamodb delete-table --table-name <TableName> --region us-east-1
python -c "import boto3; boto3.resource('s3').Bucket('<BucketName>').object_versions.delete()"   # vacía todas las versiones
aws s3 rb s3://<BucketName>
aws logs delete-log-group --log-group-name /aws/vendedlogs/apigateway/ambulatorio-hlf-prueba --region us-east-1
```

Si no se borra el bucket (o ese grupo de logs), el próximo despliegue falla con "already exists": llevan nombre fijo.
En `prod` nada de esto aplica: la tabla y los usuarios tienen protección contra borrado y las versiones del bucket no
se pueden eliminar.

## 13. Si algo falla

| Síntoma | Causa probable y salida |
|---|---|
| "no encuentro en el PATH: aws, sam" | Instalar la herramienta y abrir una terminal nueva |
| "no hay credenciales de AWS vigentes" | `aws sso login --profile …` y pasar `--perfil` |
| "Falta yaml / cfn-lint en este Python" | Instalar con el comando exacto que muestra el mensaje (trae la ruta del Python que se está usando) |
| "no está el dataset sintético" | Copiar `perfiles.json` a `data/` o apuntar `DATA_DIR` |
| CloudFormation: "Ambiente=prod exige…" u otra regla | La combinación de parámetros está prohibida; el mensaje dice cuál corregir |
| CloudFormation: "… already exists" | Quedó un bucket o grupo de logs de un stack anterior (sección 12) |
| Cognito: el dominio ya existe | Otro stack usa ese prefijo: definir `PrefijoDominioLogin` |
| Lambda: errores de concurrencia en una cuenta nueva | Las cuentas nuevas parten con un límite bajo: pedir aumento de "Concurrent executions" en Service Quotas |
| La página abre pero no carga la lista (error de red o de CORS en la consola del navegador) | `OrigenPermitido` no coincide exacto con la dirección de la página (sin barra final), o la página se compiló con otra `VITE_API_URL` |
| Todo responde 401 | Falta `Authorization: Bearer <token de acceso>` o el token venció |
| La IA siempre cae a reglas / "Fuente: plantilla" | Sección 3.3 (acceso al modelo) o `BedrockRegion` equivocada; mirar los logs de la función |
| No llegan los correos de alarma | Falta confirmar la suscripción que envía SNS |
| Un archivo en `entrada/` no se procesa | La ruta debe empezar con `entrada/`; revisar la cola de fallidos (RUNBOOK, sección 4) |
| `aws cloudformation validate-template --template-body` rechaza por tamaño | La plantilla supera 51.200 bytes: se valida con `python scripts/validar_plantilla.py` y se despliega con `sam deploy`, que la sube a S3 |
