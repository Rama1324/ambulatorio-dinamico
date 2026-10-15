# Arquitectura — Ambulatorio Dinámico HLF

> "La lista de espera es una foto; la salud de las personas, una película."
> La lista se recalcula cada vez que llega un dato nuevo del paciente, con reglas oficiales y explicables, y los cupos
> reales de los box se asignan en ese orden. El equipo clínico decide y todo queda trazado.

## 1. Flujo de los datos

```mermaid
flowchart LR
  subgraph Fuentes["Registro del HLF (6 fuentes)"]
    P[pacientes.csv]
    L[lista_espera.csv]
    E[eventos_clinicos.csv]
    M[mediciones.csv]
    C[citaciones.csv]
    A[agenda_box.csv]
  end
  P & L & E & M & C --> PF[(perfiles.json<br/>un perfil por paciente)]
  A --> BX[(box.json<br/>agenda por día y box)]

  PF --> R["Reglas oficiales · puntaje.py<br/>1 Categoría: prioridad SIC → fila 'descompensada' Tabla SSMSO 2025<br/>2 Orden MINSAL 536: riesgo vital → LACE → protección → > 1 año → llegada<br/>3 Banderas: GES vencida · causal 8 · revisión sugerida<br/>4 Egresos: fallecido (causal 9) · atendido"]
  PF --> K["Señal temprana · criticidad.py<br/>tendencia de mediciones (no cambia el orden)"]
  R & K --> LI[Lista priorizada<br/>a la fecha de operación]
  LI --> BD["Box del día<br/>cupos libres = capacidad − agenda − citas activas"]
  BX --> BD

  subgraph Equipo["Equipo clínico (decide)"]
    EV[Registra evento / informe]
    RV[Confirma o ajusta prioridad]
    CT[Contacta 'riesgo vital']
    CI[Asigna cupo · asistió · no asistió · canceló]
  end
  LI --> RV & CT
  BD --> CI
  EV & RV & CT & CI --> DB[(DynamoDB<br/>registros con fecha)]
  DB -->|se recalcula al instante| R
```

**Principio de la fecha de corte:** todo se calcula con los registros con fecha ≤ al día de operación elegido (días hábiles
con agenda, del 14-04 al 13-10-2026). Al retroceder un día se ve la lista y los box tal como estaban ese día.

## 2. Servicios AWS (despliegue simple, AWS Academy)

```mermaid
flowchart LR
  U[Gestor / médico contralor<br/>navegador o celular] -->|HTTP| W[S3 sitio web estático<br/>React compilado]
  U -->|HTTPS fetch| G[API Gateway HTTP API]
  G --> L[AWS Lambda · Python 3.12<br/>rol LabRole]
  L -->|lee al iniciar| S[(S3 privado<br/>perfiles.json · box.json)]
  L -->|eventos · revisiones · contactos · citas| D[(DynamoDB on-demand)]
  L -.->|opcional: redactar y leer informes| B[Amazon Bedrock]
```

| Pieza | Servicio | Por qué |
|---|---|---|
| Front | S3 (website) | Sin servidor ni build en la nube: `npm run build` + `aws s3 sync` |
| API | API Gateway HTTP + Lambda | Paga por uso; escala sola; una sola función con todas las rutas |
| Datos base | S3 privado y cifrado | El dataset del hospital nunca está en el repo ni es público |
| Registros del equipo | DynamoDB | Trazabilidad de cada decisión (quién, cuándo, a qué fecha) |
| IA | Bedrock (opcional) | Solo redacta y lee informes; si no está, plantillas y palabras clave |

Plantilla: `template-lab.yaml` (sin crear roles IAM, usa `LabRole`). Script: `scripts/desplegar_lab.sh`.
Para una cuenta propia con permisos IAM y Amplify, ver `template.yaml` y DEPLOY.md.

## 3. Cómo resuelve el desafío
1. **La prioridad deja de estar congelada.** Cada evento (urgencia, hospitalización, examen alterado) recalcula la lista
   en milisegundos con la tabla oficial del HLF y el orden MINSAL: reevaluación < 72 h → inmediata.
2. **Criterio común para el 100 % de la lista,** explicable: cada posición trae sus razones con la fuente oficial.
3. **Uso real de los box.** Los cupos libres de la agenda se asignan en el orden de la lista; si alguien no asiste o
   cancela, el cupo se libera y pasa al siguiente. Las inasistencias no bajan la prioridad (causal 8 solo como bandera).
4. **El equipo decide.** Confirmar / ajustar con motivo (kappa de concordancia), contacto del riesgo vital, resultado de
   cada cita: todo queda en DynamoDB.
5. **Validado con el registro** (`scripts/validar_priorizacion.py`): los 15 pacientes que fallecieron estaban, 7 días antes,
   en el 5 % superior de la lista con estas reglas (mediana) vs el 47 % en la lista estática.
