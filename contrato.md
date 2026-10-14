# Contrato — Ambulatorio Dinámico HLF

Fuente de datos: `perfiles.json` (500 pacientes, ya consolidado) en S3. **Nunca en el repo.**
Fecha de referencia del dataset: 2026-10-13. Todo cálculo usa una `fecha_corte`: solo registros con fecha ≤ corte.

## Reglas de negocio (todas con fuente; detalle en `docs/criterios_oficiales.md`)
- **Categoría** `alta | media | baja`: parte de `prioridad_inicial` (la que asignó el especialista a la SIC). Si después de la SIC
  hay un evento de descompensación o severidad grave, sube a la fila "descompensada / no controlada" de la
  **Tabla SSMSO 2025 del HLF** (págs. 84–111). El sistema **nunca baja** una categoría: eso lo hace el equipo clínico con motivo.
- **Orden** (MINSAL Ord. 536/2025): categoría → (grupos de especial protección: sin datos) → antigüedad > 1 año → orden de llegada.
- **Banderas** (no cambian el orden): `ges.vencida` (garantía GES, auge.minsal.cl) · `riesgo_inasistencia` = 2 inasistencias
  consecutivas, posible causal 8 · `medicion_alerta` = última medición fuera de rango.
- `estado = atendido` → no aparece. Fallecido con `fecha_defuncion <= corte` → `excluidos` (causal 9).
- No hay puntaje numérico ni pesos: el LLM (Bedrock) **solo** explica, transcribe fotos y extrae eventos de informes.

## Objeto Paciente (respuesta de la API)
```json
{
  "id_paciente": "PAC-HLF-00002", "nombre_fantasia": "Paciente Violeta 002", "edad": 49, "sexo": "M", "comuna": "Puente Alto",
  "especialidad": "Cardiología", "diagnostico_cie10": "I20", "diagnostico_texto": "Angina de pecho",
  "prioridad_inicial": "baja", "fecha_ingreso_lista": "2025-11-08", "dias_espera": 275,
  "categoria": "alta",
  "categoria_sistema": "alta",
  "estado_clinico": "descompensado",
  "antiguedad_mayor_1_anio": false,
  "ges": null,
  "medicion_alerta": true,
  "posicion": 41, "posicion_anterior": 313,
  "riesgo_inasistencia": false, "no_shows": 0,
  "razones": [
    {"factor": "prioridad_inicial", "valor": "baja (asignada por el especialista al priorizar la SIC)", "fuente": "Priorización de la SIC (CUD / Thalamus)"},
    {"factor": "evento", "valor": "hospitalizacion: ingreso hospitalario (grave, 2026-08-06)", "fuente": "Registro clínico posterior a la SIC"},
    {"factor": "tabla_oficial", "valor": "\"Angina inestable\" → prioridad alta", "fuente": "Tabla SSMSO 2025, HLF, pág. 85"},
    {"factor": "dias_espera", "valor": "275 días en lista", "fuente": "MINSAL Ord. 536/2025: antigüedad > 1 año"}
  ],
  "explicacion_ia": null,
  "estado_revision": "pendiente"
}
```
- `categoria` = la vigente (si el equipo ajustó, la ajustada). `categoria_sistema` = la que proponen las reglas.
- `estado_clinico`: `sin_cambios | descompensado | estabilizado` (eventos posteriores al ingreso a la lista).
- `ges`: `null` o `{"problema": 34, "nombre": "Depresión", "plazo_dias": 30, "vencida": true}`.
- `razones[].factor`: `prioridad_inicial | evento | tabla_oficial | dias_espera | ges | medicion`. Cada razón trae su `fuente`.
- `estado_revision`: `pendiente | confirmado | ajustado`.
- Campos de la capa dinámica (no cambian el orden; ver `docs/criterios_oficiales.md` §8–9):
  `criticidad` (0–100), `senal_temprana` (bool, agrega "mediciones empeorando" a `revision_sugerida`),
  `criticidad_detalle` (`eventos`, `mediciones`, `mejora`, `tendencia`, `fuera_de_rango_90d`),
  `autoreporte` (último reporte del chat por validar o `null`) y `alerta_chat` (bandera roja del chat → `contactar_hoy`).
  `razones[].factor` suma `criticidad` y `autoreporte`.

## Endpoints
| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/pacientes?especialidad=X&fecha_corte=AAAA-MM-DD` | Lista priorizada + `excluidos` |
| GET | `/pacientes/{id}` | Perfil completo con línea de tiempo (eventos, mediciones, citas) |
| POST | `/pacientes/{id}/informe` | Lee un informe (`texto` o `imagen_base64` + `media_type`) y **propone** un evento. No guarda nada |
| POST | `/eventos` | Agrega un evento confirmado → recalcula → devuelve la lista nueva |
| POST | `/pacientes` | Ingresa una interconsulta nueva (`nombre, edad, sexo, diagnostico_cie10, prioridad_inicial`, opcionales comuna, previsión, origen) |
| POST | `/pacientes/{id}/novedad` | `tipo`: `comorbilidad` (`condicion` de Charlson o `cie10`), `diagnostico` (`cie10`), `fallecimiento` o `atendido` (`fecha`). Queda registro `novedad#` |
| GET | `/pacientes/{id}/historia?fecha_corte=` | Posición y categoría cada 14 días (gráfico de evolución) |
| POST | `/pacientes/{id}/contacto` | `resultado`: citado · derivado_urgencia · se_mantiene · no_contesta (+ `nota`). Apaga "contactar hoy" salvo no_contesta |
| GET | `/kpis?fecha_corte=` | Cobertura, reevaluación, kappa (desde revisiones), alertas y egresos |
| GET | `/catalogo` | Diagnósticos, comunas, previsiones, orígenes y condiciones de Charlson con su peso |
| POST | `/importar` | `{archivos:[{nombre, contenido_base64}], confirmar}`: lee Excel/CSV, detecta la tabla, normaliza y valida. Sin `confirmar` solo revisa |
| GET | `/plantillas/{tabla}` | CSV de ejemplo: pacientes, lista_espera, eventos_clinicos, mediciones, citaciones, agenda_box |
| POST | `/pacientes/{id}/revision` | `{"accion":"confirmar"}` o `{"accion":"ajustar","categoria_ajustada":"alta|media|baja","motivo":"..."}` |
| POST | `/pacientes/{id}/explicar` | Bedrock redacta `explicacion_ia` desde `razones` |
| GET | `/boxes?fecha_corte=AAAA-MM-DD` | Ocupación de box por especialidad + pacientes sugeridos para cupos libres |
| POST | `/pacientes/{id}/autoreporte` | Chat del paciente: `eventos[]`, `mediciones[]`, `bandera_roja` (`ideacion_suicida` · `dolor_pecho` · `disnea_reposo`), `texto_libre`, `tendencia_autoreporte`, `limitacion_funcional`, `egreso_propuesto`, `confirma_asistencia`, `preferencia_horario`, `resumen[]`. Queda **por validar**; no cambia la prioridad |
| POST | `/pacientes/{id}/autoreporte/validar` | `{"accion":"validar"\|"descartar"}`: al validar, sus eventos y mediciones entran al cálculo con `fuente: "autoreporte"`. Responde como `POST /eventos` (`posicion_antes`, `posicion_despues`, `paciente`) |
| GET | `/health` | `{ok, pacientes}` para verificar el deploy |

## Respuesta POST /pacientes/{id}/informe
```json
{ "id_paciente": "PAC-HLF-00020", "fuente": "bedrock | reglas", "transcripcion": "texto leído de la foto o null",
  "evento": {"tipo_evento": "hospitalizacion", "subtipo": "ingreso hospitalario", "severidad": "grave",
             "fecha_evento": "2026-10-12", "evidencia": "Se hospitaliza en cardiología"},
  "categoria_actual": "media", "categoria_propuesta": "alta",
  "razones_propuestas": [{"factor": "tabla_oficial", "valor": "\"Angina inestable\" → prioridad alta", "fuente": "Tabla SSMSO 2025, HLF, pág. 85"}] }
```
Si no se detecta evento: `"evento": null` y `"mensaje"`. Leer fotos requiere `MODEL_ID` (Bedrock con visión).
Para confirmar, el front envía ese `evento` a `POST /eventos`.

## Respuesta POST /eventos
```json
{ "evento": {...}, "paciente": { ...objeto Paciente... }, "posicion_antes": 231, "posicion_despues": 49,
  "reevaluado_en_ms": 11, "lista": { ...misma forma que GET /pacientes, sin filtro de especialidad... } }
```
Body: `id_paciente`, `tipo_evento`, `subtipo`, `severidad`, `detalle` y opcionales `fecha_corte` (default 2026-10-13), `fecha_evento` (default = fecha_corte).
`tipo_evento`: cambio_farmaco · control_aps · examen_alterado · hospitalizacion · visita_urgencia

## Pacientes de demo (del dataset)
| ID | Historia | Qué muestra |
|---|---|---|
| PAC-HLF-00002 | Angina, baja → urgencia ESI 2 (20-jul) + hospitalización | Puesto 313 → 45: pasa a Alta por "Angina inestable" (pág. 85) y se mantiene |
| PAC-HLF-00001 | Depresión, PHQ-9 de 4 a 19 | Alta desde el inicio; GES N°34 vencida; medición fuera de rango |
| PAC-HLF-00028 | Buena respuesta + reducción de dosis | Estabilizado al fondo; el sistema no la baja solo |
| PAC-HLF-00020 | 2 inasistencias consecutivas | Bandera causal 8 sin bajar su prioridad |
| PAC-HLF-00009 | Fallece 2026-09-08 | Sale de la lista (causal 9) |
