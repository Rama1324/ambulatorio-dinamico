# Contrato — Ambulatorio Dinámico HLF

Fuente de datos: `perfiles.json` (500 pacientes, ya consolidado) en S3. **Nunca en el repo.**
Fecha de referencia del dataset: 2026-10-13. Todo cálculo usa una `fecha_corte`: solo registros con fecha ≤ corte.

## Reglas de negocio
- `estado = atendido` → no aparece en la lista.
- Fallecido con `fecha_defuncion <= corte` → sale de la lista y va a `excluidos` (control de exclusión).
- El puntaje lo calculan **reglas** (`lambda/puntaje.py`). Bedrock **solo explica**: nunca decide la prioridad.
- El médico confirma o ajusta. Toda confirmación queda registrada (trazabilidad).
- Las inasistencias **no bajan la prioridad clínica**: generan la bandera `riesgo_inasistencia` para la gestión de box.

## Objeto Paciente (respuesta de la API)
```json
{
  "id_paciente": "PAC-HLF-00002",
  "nombre_fantasia": "Paciente Violeta 002",
  "edad": 49,
  "sexo": "M",
  "comuna": "Puente Alto",
  "especialidad": "Cardiología",
  "diagnostico_cie10": "I20",
  "diagnostico_texto": "Angina de pecho",
  "prioridad_inicial": "baja",
  "fecha_ingreso_lista": "2025-11-08",
  "dias_espera": 275,
  "puntaje": 59.6,
  "categoria": "alta",
  "posicion": 18,
  "posicion_anterior": 312,
  "riesgo_inasistencia": false,
  "razones": [
    {"factor": "prioridad_inicial", "valor": "baja", "puntos": 5},
    {"factor": "dias_espera", "valor": 275, "puntos": 11.3},
    {"factor": "evento", "valor": "hospitalizacion: ingreso hospitalario (2026-08-06)", "puntos": 22},
    {"factor": "evento", "valor": "visita_urgencia: triage ESI 2 (2026-07-20)", "puntos": 18},
    {"factor": "mediciones_fuera_rango", "valor": "1/3 últimas", "puntos": 3.3}
  ],
  "explicacion_ia": "Texto generado por Bedrock a partir de 'razones' (null hasta que se pida)",
  "estado_revision": "pendiente"
}
```
`categoria`: critica ≥70 · alta 50–69 · media 30–49 · baja <30
`estado_revision`: pendiente | confirmado | ajustado

## Endpoints
| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/pacientes?especialidad=X&fecha_corte=AAAA-MM-DD` | Lista priorizada + `excluidos` |
| GET | `/pacientes/{id}` | Perfil completo con línea de tiempo (eventos, mediciones, citas) |
| POST | `/pacientes/{id}/explicar` | Bedrock genera `explicacion_ia` desde `razones` |
| POST | `/eventos` | Agrega un evento (body = objeto evento) → recalcula → devuelve la lista nueva |
| POST | `/pacientes/{id}/revision` | Médico confirma o ajusta. Body: `{"accion":"confirmar"|"ajustar","puntaje_ajustado":n,"motivo":"..."}` |
| GET | `/boxes?fecha_corte=AAAA-MM-DD` | Ocupación de box por especialidad + pacientes sugeridos para cupos libres |
| GET | `/health` | `{ok, pacientes}` para verificar el deploy |

Respuesta de GET `/pacientes`:
```json
{ "fecha_corte": "2026-10-13", "total": 409, "pacientes": [ ... ], "excluidos": [ {"id_paciente": "PAC-HLF-00009", "motivo": "fallecido"} ] }
```

## Respuesta POST /eventos
```json
{ "evento": {...}, "paciente": { ...objeto Paciente... }, "posicion_antes": 26, "posicion_despues": 4,
  "reevaluado_en_ms": 6, "lista": { ...misma forma que GET /pacientes... } }
```
Body opcional extra: `fecha_corte` (default 2026-10-13); `fecha_evento` default = fecha_corte.

## Respuesta POST /pacientes/{id}/explicar
```json
{ "id_paciente": "PAC-HLF-00002", "explicacion_ia": "texto", "fuente": "bedrock" }
```
`fuente` = `plantilla` si Bedrock no está configurado o falla.

## Objeto Evento (POST /eventos)
```json
{ "id_paciente": "PAC-HLF-00020", "fecha_evento": "2026-10-14", "tipo_evento": "visita_urgencia",
  "subtipo": "triage ESI 2", "severidad": "grave", "detalle": "triage ESI 2 (Cardiología)" }
```
`tipo_evento`: cambio_farmaco · control_aps · examen_alterado · hospitalizacion · visita_urgencia

## Pacientes de demo (del dataset)
| ID | Historia | Qué muestra |
|---|---|---|
| PAC-HLF-00002 | baja → urgencia ESI 2 + hospitalización | Salta del puesto 312 al 18 |
| PAC-HLF-00001 | PHQ-9 sube de 4 a 19 | Deterioro progresivo |
| PAC-HLF-00028 | buena respuesta + reducción de dosis | Baja al final |
| PAC-HLF-00020 | 2 inasistencias | Bandera de riesgo de inasistencia |
| PAC-HLF-00009 | fallece 2026-09-08 | Sale de la lista |
