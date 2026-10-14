"""Lectura de un informe médico en texto libre (epicrisis, DAU de urgencia, nota clínica).

El LLM NO prioriza: solo convierte el texto en un evento estructurado con el mismo vocabulario del dataset
(tipo_evento / subtipo / severidad) y cita la frase que lo respalda. El equipo clínico confirma ese evento y
recién entonces las reglas oficiales (puntaje.py) recalculan la lista.
Sin Bedrock (o si falla) se usa una lectura por palabras clave, para que la demo nunca se caiga.
"""
import json
import os
import re

# Vocabulario permitido = valores reales del dataset (diccionario_datos.md)
SUBTIPOS = {
    "hospitalizacion": {"ingreso UCI": "grave", "ingreso hospitalario": "grave"},
    "visita_urgencia": {"descompensación grave": "grave", "triage ESI 2": "grave", "descompensación": "moderada"},
    "examen_alterado": {"resultado alterado": "moderada"},
    "cambio_farmaco": {"aumento dosis": "moderada", "reducción dosis": "leve"},
    "control_aps": {"estabilización": "leve", "buena respuesta": "leve", "control": "leve"},
}

# Palabras clave → evento del dataset, de lo más grave a lo menos grave (gana la primera que aparece)
PATRONES = [
    (r"\bUCI\b|cuidados intensivos|unidad de paciente cr[ií]tico|\bUPC\b", "hospitalizacion", "ingreso UCI"),
    (r"hospitaliz|se ingresa|ingres[oó] a (sala|servicio)|qued[oó] internad", "hospitalizacion", "ingreso hospitalario"),
    (r"descompensaci[oó]n grave|descompensad[oa] grave|grave descompensaci", "visita_urgencia", "descompensación grave"),
    (r"\bESI\s*2\b|\bC2\b|categorizaci[oó]n 2", "visita_urgencia", "triage ESI 2"),
    (r"descompensa", "visita_urgencia", "descompensación"),
    (r"examen alterado|resultado alterado|alterad[oa]s? (el|la|los|las)? ?(examen|ex[aá]menes|laboratorio)", "examen_alterado", "resultado alterado"),
    (r"aument[oóa]\w* (de )?(la )?dosis|sube (la )?dosis|se aumenta", "cambio_farmaco", "aumento dosis"),
    (r"reduc\w* (de )?(la )?dosis|baja (la )?dosis|se disminuye", "cambio_farmaco", "reducción dosis"),
    (r"estabiliz", "control_aps", "estabilización"),
    (r"buena respuesta|responde bien|mejor[ií]a", "control_aps", "buena respuesta"),
]

FECHA = re.compile(r"(\d{4})-(\d{2})-(\d{2})|(\d{1,2})[/-](\d{1,2})[/-](\d{4})")

PROMPT = """Eres un asistente que lee informes médicos de un hospital público chileno.
Tu única tarea es extraer UN evento clínico del texto, usando SOLO este vocabulario:
{vocab}
Responde SOLO un JSON: {{"tipo_evento": "...", "subtipo": "...", "fecha_evento": "AAAA-MM-DD o null",
"evidencia": "frase textual copiada del informe que respalda el evento"}}.
Si el texto no describe ninguno de esos eventos responde {{"tipo_evento": null}}.
Un hallazgo negado o descartado ("se descarta hospitalización", "no requiere ingreso", "niega consultas en urgencia") NO es un evento.
No inventes datos, no diagnostiques, no asignes prioridad."""


def _frase(texto, inicio, fin):
    a = max(texto.rfind(".", 0, inicio), texto.rfind("\n", 0, inicio)) + 1
    b = min([i for i in (texto.find(".", fin), texto.find("\n", fin)) if i != -1] or [len(texto)])
    return texto[a:b].strip()


def _fecha(texto):
    m = FECHA.search(texto)
    if not m:
        return None
    if m.group(1):
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return f"{m.group(6)}-{int(m.group(5)):02d}-{int(m.group(4)):02d}"


# Disparadores de negación en español (estilo NegEx, Chapman 2001; adaptaciones NegEx-MES / SpRadNeg): si aparecen en las
# palabras previas al término dentro de la misma frase, el hallazgo está negado ("se descarta hospitalización").
NEGACION = re.compile(r"\b(no|sin|niega|negativo|negativa|descarta|descartad[oa]|se\s+descarta|ausencia\s+de|no\s+presenta|"
                      r"no\s+requiere|no\s+amerita|no\s+se|tampoco|ni|evita|evitar|sin\s+necesidad\s+de)\b", re.IGNORECASE)
VENTANA_NEGACION = 6  # palabras previas


def _negado(texto, inicio):
    frase_ini = max(texto.rfind(".", 0, inicio), texto.rfind("\n", 0, inicio), texto.rfind(";", 0, inicio)) + 1
    previas = texto[frase_ini:inicio].split()[-VENTANA_NEGACION:]
    return bool(NEGACION.search(" ".join(previas)))


def por_reglas(texto):
    for patron, tipo, subtipo in PATRONES:
        for m in re.finditer(patron, texto, re.IGNORECASE):
            if _negado(texto, m.start()):
                continue
            return {"tipo_evento": tipo, "subtipo": subtipo, "severidad": SUBTIPOS[tipo][subtipo],
                    "fecha_evento": _fecha(texto), "evidencia": _frase(texto, m.start(), m.end())}
    return None


def validar(ev, texto):
    """Acepta solo valores del vocabulario del dataset y evidencia que esté en el texto."""
    if not ev or ev.get("tipo_evento") not in SUBTIPOS or ev.get("subtipo") not in SUBTIPOS[ev["tipo_evento"]]:
        return None
    ev["severidad"] = SUBTIPOS[ev["tipo_evento"]][ev["subtipo"]]
    if not ev.get("evidencia") or ev["evidencia"].lower() not in texto.lower():
        return None
    return ev


PROMPT_FOTO = """Transcribe textualmente el informe médico de la imagen (español). No resumas, no corrijas,
no agregues nada. Si una parte no se lee, escribe [ilegible]. Responde solo con el texto transcrito."""

FORMATOS = {"image/jpeg": "jpeg", "image/jpg": "jpeg", "image/png": "png", "image/webp": "webp"}


def transcribir_foto(imagen_b64, media_type="image/jpeg"):
    """Foto de un papel → texto, con la visión de Bedrock. Devuelve (texto | None, motivo)."""
    model_id = os.environ.get("MODEL_ID")
    if not model_id:
        return None, "Leer fotos requiere Amazon Bedrock (configurar MODEL_ID). Mientras tanto, pega el texto del informe."
    import base64
    import boto3
    kw = {"region_name": os.environ["BEDROCK_REGION"]} if os.environ.get("BEDROCK_REGION") else {}
    try:
        r = boto3.client("bedrock-runtime", **kw).converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [
                {"image": {"format": FORMATOS.get(media_type, "jpeg"), "source": {"bytes": base64.b64decode(imagen_b64)}}},
                {"text": PROMPT_FOTO}]}],
            inferenceConfig={"maxTokens": 1500, "temperature": 0},
        )
        return r["output"]["message"]["content"][0]["text"].strip(), "bedrock"
    except Exception as e:
        print(f"Bedrock falló al leer la foto: {e}")
        return None, f"No se pudo leer la foto: {e}"


def extraer(texto):
    """Devuelve (evento | None, fuente) con fuente 'bedrock' o 'reglas'."""
    texto = (texto or "").strip()
    model_id = os.environ.get("MODEL_ID")
    if model_id and texto:
        try:
            import boto3
            kw = {"region_name": os.environ["BEDROCK_REGION"]} if os.environ.get("BEDROCK_REGION") else {}
            vocab = json.dumps({t: list(s) for t, s in SUBTIPOS.items()}, ensure_ascii=False)
            r = boto3.client("bedrock-runtime", **kw).converse(
                modelId=model_id,
                system=[{"text": PROMPT.format(vocab=vocab)}],
                messages=[{"role": "user", "content": [{"text": texto}]}],
                inferenceConfig={"maxTokens": 300, "temperature": 0},
            )
            crudo = r["output"]["message"]["content"][0]["text"]
            ev = validar(json.loads(crudo[crudo.find("{"): crudo.rfind("}") + 1]), texto)
            if ev:
                return ev, "bedrock"
        except Exception as e:
            print(f"Bedrock falló al leer informe, uso reglas: {e}")
    return por_reglas(texto), "reglas"
