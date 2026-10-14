# Prompts de Amazon Bedrock

El LLM **nunca prioriza**: solo redacta, transcribe o extrae. La prioridad la calculan las reglas de `lambda/puntaje.py`.
Los textos vigentes viven en el código; aquí se resumen para revisión clínica y para el pitch.

| Uso | Archivo | Qué hace | Si Bedrock falla |
|---|---|---|---|
| Resumen para el equipo | `lambda/explicar.py` (`PROMPT_SISTEMA`) | Redacta en 3 frases las razones ya calculadas, con fuente | Plantilla fija |
| Lectura de informe escrito | `lambda/informe.py` (`PROMPT`) | Extrae **un** evento con el vocabulario del registro y cita la frase del informe; ignora hallazgos negados | Reglas de palabras clave con negación (estilo NegEx) |
| Foto de un informe | `lambda/informe.py` (`PROMPT_FOTO`) | Transcribe textual el documento; luego se aplica la lectura de informe | Aviso: "requiere Bedrock" |

Salvaguardas:
- La evidencia citada debe existir textualmente en el informe; si no, la extracción se descarta.
- Solo se aceptan `tipo_evento` / `subtipo` del vocabulario del dataset.
- Todo evento extraído lo confirma el equipo clínico antes de recalcular la lista.
