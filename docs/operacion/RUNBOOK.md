# Guía de operación — Ambulatorio Dinámico HLF

Para el equipo de TI del hospital. Guía mínima: qué hacer en cada situación y con qué comando.

> **Estado (noviembre 2026):** el sistema todavía no se ha desplegado en una cuenta AWS real. Estos procedimientos
> están escritos a partir de la plantilla (`template.yaml`) y de la documentación de AWS, pero **ninguno se ha
> ejecutado contra el sistema**. Antes de depender de uno, ensáyelo en el ambiente `prueba`.
> Cómo desplegar y configurar: [`DEPLOY.md`](../../DEPLOY.md).

## 0. Datos del sistema y preparación de la terminal

| | `prueba` | `prod` |
|---|---|---|
| Stack de CloudFormation | `ambulatorio-hlf-prueba` | `ambulatorio-hlf-prod` |
| Región | `us-east-1` (definida en `samconfig.toml`) | igual |
| Datos | sintéticos | reales |

Todo se puede hacer desde **AWS CloudShell** (consola de AWS, ícono de terminal) sin instalar nada. Los comandos de esta
guía son para bash y usan estas ayudas; péguelas al abrir la terminal:

```bash
STACK=ambulatorio-hlf-prod
REGION=us-east-1
export AWS_DEFAULT_REGION=$REGION
# valor de una salida del stack (ApiUrl, TableName, BucketName, UsuariosId, ColaFallidosUrl…)
salida()  { aws cloudformation describe-stacks --stack-name "$STACK" --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
# nombre real de un recurso del stack (ApiFunction, ApiLogGroup, Api, ColaEvaluacion…)
recurso() { aws cloudformation describe-stack-resource --stack-name "$STACK" --logical-resource-id "$1" --query StackResourceDetail.PhysicalResourceId --output text; }
```

Dónde mirar:

| Qué | Dónde |
|---|---|
| Logs de una función | `aws logs tail "$(recurso ApiLogGroup)" --since 1h` (también `TrabajadorLogGroup`, `IngestaArchivoLogGroup`, `BarridoLogGroup`) |
| Registro de accesos (quién pidió qué) | `aws logs tail "/aws/vendedlogs/apigateway/$STACK" --since 1h` |
| Alarmas | Consola de CloudWatch → Alarmas (sus nombres empiezan con el nombre del stack) |
| Cambios de infraestructura | Consola de CloudFormation → el stack → Eventos |

## 1. Desplegar y volver atrás

Desplegar es correr un script (o aprobar el pipeline). El detalle está en `DEPLOY.md`, secciones 3 y 9.

```bash
scripts/desplegar.sh prod                     # muestra la cuenta y pide escribir "prod"
scripts/desplegar.sh prod --solo-backend      # sin republicar la página
scripts/desplegar.sh prod --solo-front        # solo la página
```

El script no despliega si fallan los tests, y comprueba la API antes de publicar la página.

**Volver a la versión anterior:**

```bash
git checkout <etiqueta o commit de la versión buena>
scripts/desplegar.sh prod
```

- Si un despliegue falla a medias, CloudFormation revierte solo: el sistema queda como estaba.
- Con urgencia y sin el dataset de pruebas a mano: `--sin-tests`, solo hacia una versión que ya estuvo en `prod`.
- Volver atrás el código **no deshace datos**: los registros solo se agregan. Para datos, sección 2.
- Etiquete cada versión que llegue a `prod` (`git tag prod-AAAA-MM-DD && git push --tags`): es a lo que se vuelve.

## 2. Restaurar datos

### 2.1 Tabla (DynamoDB): volver a un punto en el tiempo

La tabla guarda respaldo continuo de los últimos **35 días**, al segundo. La restauración **crea una tabla nueva**; la
original no se toca.

```bash
TABLA=$(salida TableName)
NUEVA="$TABLA-rest-$(date +%Y%m%d-%H%M)"

# ¿desde y hasta cuándo se puede restaurar?
aws dynamodb describe-continuous-backups --table-name "$TABLA" \
  --query "ContinuousBackupsDescription.PointInTimeRecoveryDescription"

# 1. Restaurar al instante anterior al daño (hora de Chile con su desfase, o --use-latest-restorable-time)
aws dynamodb restore-table-to-point-in-time --source-table-name "$TABLA" --target-table-name "$NUEVA" \
  --restore-date-time 2026-11-20T14:30:00-03:00
aws dynamodb wait table-exists --table-name "$NUEVA"      # puede tardar varios minutos

# 2. La restauración NO copia estas protecciones: activarlas en la tabla nueva
aws dynamodb update-continuous-backups --table-name "$NUEVA" --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true
aws dynamodb update-time-to-live --table-name "$NUEVA" --time-to-live-specification "Enabled=true,AttributeName=expira"
aws dynamodb update-table --table-name "$NUEVA" --deletion-protection-enabled

# 3. Revisar antes de cambiar nada: por ejemplo, los registros de un paciente conocido
aws dynamodb query --table-name "$NUEVA" --key-condition-expression "id_paciente = :p" \
  --expression-attribute-values '{":p":{"S":"<id del paciente>"}}' --select COUNT
```

**4. Hacer que el sistema use la tabla restaurada.** Agregue `TablaRestaurada="<nombre de la tabla nueva>"` a
`parameter_overrides` de `prod` en `samconfig.toml`, confirme el cambio en git y despliegue:

```bash
scripts/desplegar.sh prod --solo-backend
```

Tiene que quedar en `samconfig.toml`: si solo se pasa por la línea de comandos, el próximo despliegue vuelve a la tabla
dañada. No cambie la variable `TABLE` de las funciones a mano por la misma razón.

A tener en cuenta:

- Lo registrado **después** del instante elegido no está en la tabla restaurada. La tabla original sigue existiendo
  (para comparar y como evidencia); lo que falte se vuelve a ingresar por los canales normales (reenviar no duplica).
- Más de 35 días hacia atrás no es posible con este mecanismo. Si el hospital necesita respaldos más antiguos, hay que
  agregar respaldos periódicos (AWS Backup): está pendiente.
- **Ensaye la restauración en `prueba` cada seis meses.** Un respaldo que nunca se ha restaurado no es un respaldo.

### 2.2 Archivos (bucket S3): recuperar una versión anterior

El bucket guarda todas las versiones: sobrescribir o borrar un archivo no destruye el anterior.

```bash
BUCKET=$(salida BucketName)
aws s3api list-object-versions --bucket "$BUCKET" --prefix "procesados/<archivo>" \
  --query "[Versions[].[VersionId,LastModified,IsLatest],DeleteMarkers[].[VersionId,LastModified]]"
# dejar una versión anterior como la vigente (copiarla encima)
aws s3api copy-object --bucket "$BUCKET" --key "procesados/<archivo>" \
  --copy-source "$BUCKET/procesados/<archivo>?versionId=<VersionId>"
```

En `prod` nadie puede eliminar versiones (lo impide la política del bucket): la recuperación siempre es copiando.

## 3. Usuarios y roles

Solo con login activo (`prod`). Nadie se registra solo: TI da de alta. El usuario es el correo institucional.

| Rol (grupo) | Puede |
|---|---|
| `gestion` | Contacto, gestión del caso, ingreso de pacientes, eventos manuales, informes, importar |
| `especialista` | Revisión (veredicto), decisión clínica, orden manual, enmienda de eventos |
| `jefatura` | Aprobar, rechazar o retirar criterios locales |

Una persona puede estar en más de un grupo. Sin grupo, solo puede leer.

```bash
POOL=$(salida UsuariosId)
CORREO=persona@hospital.cl

# Alta: Cognito le envía una clave temporal (vale 3 días); en el primer ingreso define su clave y su segundo factor
aws cognito-idp admin-create-user --user-pool-id "$POOL" --username "$CORREO" \
  --user-attributes Name=email,Value="$CORREO" Name=email_verified,Value=true Name=name,Value="Nombre Apellido"
aws cognito-idp admin-add-user-to-group --user-pool-id "$POOL" --username "$CORREO" --group-name gestion

# Cambio de rol
aws cognito-idp admin-remove-user-from-group --user-pool-id "$POOL" --username "$CORREO" --group-name gestion
aws cognito-idp admin-add-user-to-group      --user-pool-id "$POOL" --username "$CORREO" --group-name especialista

# Baja: deshabilitar (no borrar: se conserva quién era en los registros) y cerrar sus sesiones
aws cognito-idp admin-disable-user          --user-pool-id "$POOL" --username "$CORREO"
aws cognito-idp admin-user-global-sign-out  --user-pool-id "$POOL" --username "$CORREO"

# Olvidó la clave / perdió el teléfono del segundo factor
aws cognito-idp admin-reset-user-password       --user-pool-id "$POOL" --username "$CORREO"
aws cognito-idp admin-set-user-mfa-preference   --user-pool-id "$POOL" --username "$CORREO" \
  --software-token-mfa-settings Enabled=false,PreferredMfa=false      # lo vuelve a configurar al entrar

# Quién tiene acceso (revisión trimestral)
aws cognito-idp list-users --user-pool-id "$POOL" --query "Users[].[Attributes[?Name=='email']|[0].Value,Enabled,UserStatus]" --output table
for g in gestion especialista jefatura; do echo "== $g"; aws cognito-idp list-users-in-group --user-pool-id "$POOL" --group-name $g \
  --query "Users[].Attributes[?Name=='email']|[].Value" --output text; done
```

**Importante:** una baja o un cambio de rol no es instantáneo. El token que la persona ya tiene sigue sirviendo hasta que
vence (**máximo 60 minutos**). Si no se puede esperar, vea "cortar el acceso" en la sección 6.

**Sistemas del hospital** (envían eventos a `POST /ingesta/eventos`): usan un cliente con secreto.

```bash
CLIENTE=$(salida ClienteIntegracionId)
aws cognito-idp describe-user-pool-client --user-pool-id "$POOL" --client-id "$CLIENTE" \
  --query "UserPoolClient.ClientSecret" --output text
```

Entregue el secreto por un canal seguro (nunca por correo ni chat) y no lo guarde en documentos. Rótelo al menos una
vez al año y siempre que cambie el personal que lo conoce. Cognito permite dos secretos vigentes a la vez, así que se
rota sin cortar el servicio: agregar un segundo secreto (operación `AddUserPoolClientSecret`; en la CLI,
`aws cognito-idp add-user-pool-client-secret help`), entregarlo al sistema del hospital y, cuando ya lo esté usando,
borrar el anterior (`DeleteUserPoolClientSecret`). Si el secreto se filtró, borre el anterior de inmediato.

## 4. Cargas de datos que fallan

Los archivos del hospital llegan a `s3://<bucket>/entrada/`. Cada uno termina en uno de tres destinos:

| Destino | Qué pasó | Qué hacer |
|---|---|---|
| `procesados/` | Se cargó | Nada |
| `errores/` | El archivo (o parte de sus filas) no pasó la validación | 4.1 |
| Cola de fallidos | La ingesta falló de forma inesperada (3 intentos), o una evaluación falló 5 veces | 4.2 |

### 4.1 Un archivo trae errores

```bash
BUCKET=$(salida BucketName)
aws s3 ls "s3://$BUCKET/errores/" --recursive --human-readable | tail
aws s3 cp "s3://$BUCKET/errores/<archivo>" -        # ver el detalle (qué fila, qué columna, por qué)
```

El mismo detalle aparece en la aplicación (carga de datos). Corrija el archivo **en el sistema de origen** y vuelva a
subirlo completo a `entrada/`: las filas que ya entraron no se duplican. No edite datos directamente en la tabla.

### 4.2 Hay mensajes en la cola de fallidos (alarma `AlarmaMensajesFallidos`)

```bash
FALLIDOS=$(salida ColaFallidosUrl)
aws sqs get-queue-attributes --queue-url "$FALLIDOS" --attribute-names ApproximateNumberOfMessages
aws sqs receive-message --queue-url "$FALLIDOS" --max-number-of-messages 10 --visibility-timeout 60 \
  --query "Messages[].[ReceiptHandle,Body]"
```

Hay dos clases de mensaje. Atienda **primero** los de archivo:

**a) Archivo que no se pudo procesar.** El cuerpo trae `requestContext` y, dentro de `requestPayload`, la ruta del
archivo (`Records[0].s3.object.key`) y el error (`responsePayload`). Revise los logs
(`aws logs tail "$(recurso IngestaArchivoLogGroup)" --since 6h`), corrija la causa y vuelva a subir el archivo a
`entrada/`. Luego borre el mensaje:

```bash
aws sqs delete-message --queue-url "$FALLIDOS" --receipt-handle "<ReceiptHandle>"
```

**b) Evaluación que falló cinco veces.** El cuerpo trae `id_paciente` e `id_lote`. Casi siempre la causa es Bedrock
(saturación, sin acceso al modelo) o un error del código: mire `aws logs tail "$(recurso TrabajadorLogGroup)" --since 6h`.
El paciente **no quedó sin prioridad**: rigen las reglas; lo que falta es la lectura de la IA. Resuelta la causa,
devuelva los mensajes a la cola de evaluación:

```bash
arn() { aws sqs get-queue-attributes --queue-url "$1" --attribute-names QueueArn --query Attributes.QueueArn --output text; }
aws sqs start-message-move-task --source-arn "$(arn "$FALLIDOS")" --destination-arn "$(arn "$(salida ColaEvaluacionUrl)")"
```

Ese comando mueve **todo** lo que haya en la cola de fallidos: por eso los mensajes de archivo se borran antes. Los
mensajes se conservan 14 días.

## 5. Qué significa cada alarma

Llegan por correo a la dirección configurada (`CorreoAlertas`), al dispararse y al volver a la normalidad. El nombre de
cada alarma contiene el identificador de la primera columna.

| Alarma | Qué significa | Primer paso |
|---|---|---|
| `AlarmaApiErrores` | La API terminó con un error no controlado o se le acabó el tiempo (30 s). Alguien vio un error | `aws logs tail "$(recurso ApiLogGroup)" --since 30m --filter-pattern "?ERROR ?Traceback ?\"Task timed out\""`. Si empezó tras un despliegue: volver atrás (sección 1) |
| `AlarmaApi5xx` | 5 o más respuestas de error del servidor en 5 minutos | Registro de accesos: qué ruta y qué usuario (campo `estado` 5xx); luego los logs de la API |
| `AlarmaApiLenta` | 1 de cada 20 solicitudes tarda más de 24 s (el tope es 30 s) | Ver en el registro de accesos qué rutas tardan (`ms`). Causas habituales: Bedrock o Textract lentos, o la lista creció mucho |
| `AlarmaApiSaturada` · `AlarmaTrabajadorSaturado` · `AlarmaIngestaSaturada` · `AlarmaBarridoSaturado` | Lambda rechazó ejecuciones: la cuenta llegó a su límite de ejecuciones simultáneas | Service Quotas → Lambda → *Concurrent executions*: pedir aumento. Revisar si otra carga de la cuenta lo está consumiendo |
| `AlarmaTrabajadorErrores` | El trabajador de la cola terminó con un error no controlado o se le acabó el tiempo (300 s). Los mensajes vuelven a la cola y se reintentan cada 30 minutos; al quinto intento van a fallidos. Una evaluación que falla de forma controlada no dispara esta alarma: se nota por `AlarmaColaAtrasada` y `AlarmaMensajesFallidos` | Logs del trabajador. Si es saturación de Bedrock, bajar `ConcurrenciaTrabajador` o pedir más cuota |
| `AlarmaIngestaErrores` | Falló de forma inesperada la ingesta de un archivo de `entrada/` | Logs de la ingesta; después de los reintentos queda en fallidos (4.2 a) |
| `AlarmaBarridoErrores` | Falló la reevaluación nocturna. No se repite sola | Logs del barrido. Para relanzarla: `aws lambda invoke --function-name "$(recurso BarridoFunction)" --invocation-type Event --cli-binary-format raw-in-base64-out --payload '{"limite": 400, "en_paralelo": 6}' /dev/null` |
| `AlarmaMensajesFallidos` | Hay mensajes en la cola de fallidos | Sección 4.2 |
| `AlarmaColaAtrasada` | Una evaluación lleva más de 1 hora esperando en la cola | ¿El trabajador está fallando? ¿Bedrock saturado? Si es solo volumen (una carga grande), subir `ConcurrenciaTrabajador` |

Una alarma **no** significa que un paciente quedó sin prioridad: si la IA o la cola fallan, la lista sigue calculándose
con las reglas. Lo que se pierde es la reevaluación con IA hasta que se resuelva.

Quién vio la ficha de un paciente (CloudWatch → Logs Insights, grupo `/aws/vendedlogs/apigateway/<stack>`):

```
fields hora, usuario, metodo, ruta, estado | filter ruta like "<id del paciente>" | sort @timestamp desc
```

## 6. Incidente de seguridad

Incidente es, por ejemplo: acceso de alguien no autorizado, una credencial o secreto expuesto, datos alterados o
borrados, la página o la API respondiendo algo que no corresponde, o un aviso de AWS sobre la cuenta.

**El plazo corre desde que se toma conocimiento.** La Ley 21.663 (Marco de Ciberseguridad), artículo 9, obliga a
reportar al CSIRT Nacional los incidentes que puedan tener efectos significativos:

| Qué | Plazo máximo |
|---|---|
| **Alerta temprana**, con lo que se sepa hasta ese momento | **3 horas** desde que se toma conocimiento |
| Actualización (evaluación inicial, gravedad, impacto) | 72 horas; **24 horas** si el hospital es operador de importancia vital y el incidente afecta sus servicios esenciales |
| Informe final | 15 días corridos desde la alerta temprana |
| Plan de acción (operadores de importancia vital) | 7 días corridos |

**No espere a entender todo para avisar.** El reporte lo hace el encargado de ciberseguridad del hospital por el canal
del CSIRT Nacional (a noviembre de 2026, `https://csirt.gob.cl/reportar/` y teléfono 1510; él confirma el canal
vigente con la Agencia Nacional de Ciberseguridad). Si hay datos personales comprometidos, avise además al delegado de
protección de datos (Ley 21.719).

**Orden de trabajo:**

1. **Anotar la hora** en que se supo y **avisar** al encargado de ciberseguridad del hospital (él reporta al CSIRT).
2. **Contener**, sin destruir evidencia:

   ```bash
   # Una persona comprometida
   aws cognito-idp admin-disable-user         --user-pool-id "$POOL" --username "$CORREO"
   aws cognito-idp admin-user-global-sign-out --user-pool-id "$POOL" --username "$CORREO"

   # Cortar el acceso a TODA la API de inmediato (los tokens ya emitidos valen hasta 60 minutos)
   aws lambda put-function-concurrency --function-name "$(recurso ApiFunction)" --reserved-concurrent-executions 0
   # ...y restablecerlo cuando corresponda
   aws lambda delete-function-concurrency --function-name "$(recurso ApiFunction)"
   ```

   - Secreto del cliente de sistemas expuesto: rotarlo (sección 3) y avisar al equipo del sistema que lo usa.
   - Credenciales de AWS expuestas: en IAM, revocar las sesiones activas del rol y cambiar las llaves; revisar en
     CloudTrail qué se hizo con ellas.
   - Deshabilitar la llave KMS deja **todos** los datos ilegibles y detiene el sistema: solo por decisión de quien
     dirige el incidente.
3. **Conservar la evidencia.** No borrar logs, usuarios ni tablas. Guardar el registro de accesos y los logs de las
   funciones del período (consola de CloudWatch → exportar), los eventos de CloudTrail y las horas en UTC y hora de
   Chile.
4. **Evaluar el daño.** ¿Qué pacientes, qué datos, desde cuándo? El registro de accesos dice quién pidió qué ruta; si se
   alteraron datos, la tabla se restaura al instante anterior (sección 2).
5. **Recuperar** y dejar por escrito qué pasó, qué se hizo y qué se cambia para que no se repita.

Datos que pedirá el reporte: fecha y hora de detección, sistema afectado (Ambulatorio Dinámico, cuenta y región de AWS),
tipo de incidente, datos y personas afectadas, medidas tomadas, contacto técnico.

## 7. Costos y alerta de gasto

El sistema no tiene servidores encendidos: se paga por uso. Qué mueve la cuenta:

| Concepto | Cuándo crece |
|---|---|
| **Bedrock (IA)** | Con cada evaluación con IA y cada informe leído. Es el gasto variable principal. Referencia del equipo, medida con datos sintéticos: del orden de USD 0,03 por evaluación (3 lecturas) y USD 0,013 por informe; depende del modelo |
| Barrido nocturno | Si se enciende, reevalúa con IA cada noche aunque nadie use la aplicación. Apagado por defecto |
| Textract | Por cada foto de informe leída |
| DynamoDB, Lambda, API Gateway, SQS, S3 | Por solicitud y por dato guardado; a escala de un hospital es bajo |
| Costos fijos chicos | Llave KMS propia, alarmas de CloudWatch, cliente de sistemas de Cognito, logs guardados |

Estos valores son órdenes de magnitud: los precios vigentes están en la calculadora de AWS.

- **Alerta de gasto:** el parámetro `PresupuestoMensualUSD` (junto con `CorreoAlertas`) crea un presupuesto que avisa al
  llegar al 80 % y si la proyección del mes supera el 100 %. Mira **toda la cuenta**: por eso conviene una cuenta por
  ambiente.
- **Ver en qué se gasta:** Billing → Cost Explorer, agrupando por servicio. Todos los recursos llevan las etiquetas
  `proyecto` y `ambiente` (para filtrar por ellas hay que activarlas una vez en Billing → *Cost allocation tags*).
- **Si el gasto de IA se dispara:** revisar si el barrido está encendido, bajar `LecturasIA` o `ConcurrenciaTrabajador`,
  o pasar `Algoritmo` a `reglas` mientras se investiga. Todo se cambia en `samconfig.toml` y se despliega.

## 8. Mantención

| Cada cuánto | Qué |
|---|---|
| Cada mes | Revisar alarmas disparadas, la cola de fallidos y el gasto |
| Cada 3 meses | Revisar quién tiene acceso y con qué rol (sección 3); dar de baja a quien ya no corresponde |
| Cada 6 meses | Ensayar una restauración en `prueba` (sección 2); actualizar dependencias (`pydantic` en `lambda/requirements.txt`, las de `front/package.json`) corriendo los tests y desplegando primero en `prueba` |
| Cada año | Rotar el secreto del cliente de sistemas; revisar la retención de logs y los límites de la API |
| Antes de octubre de 2028 | **Runtime de Lambda.** Las funciones usan Python 3.12. AWS tiene previsto dejar de darle soporte el 31 de octubre de 2028 (fecha de la documentación de Lambda a noviembre de 2026; puede cambiar, y AWS avisa por correo 180 días antes). Para cambiar de versión: `Runtime` en `template.yaml`, `--python-version` en `scripts/desplegar.py` y la versión de Python de los workflows; probar en `prueba`. Los parches de seguridad del runtime los aplica AWS solo |
| Cuando AWS lo anuncie | **Modelo de IA.** Los modelos de Bedrock también se retiran. Cambiar `ModelId` en `samconfig.toml` y volver a medir la concordancia con los especialistas antes de `prod` |

Pendientes de operación (no están hechos): respaldos de más de 35 días (AWS Backup), registro de CloudTrail con eventos
de datos para la tabla y el bucket de `prod`, política acotada para el rol del pipeline y cabeceras de seguridad de la
página.
