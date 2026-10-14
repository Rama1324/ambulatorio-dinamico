"""Explicación de la prioridad con Amazon Bedrock (Converse API).

El LLM NO decide la prioridad: solo redacta, en lenguaje clínico claro, las 'razones'
que ya calculó puntaje.py. Si Bedrock falla, devuelve una explicación por plantilla
para que el demo nunca se caiga.
Variables de entorno: MODEL_ID (obligatoria para usar Bedrock), BEDROCK_REGION (opcional).
"""
import json
import os

PROMPT_SISTEMA = """Eres un asistente de gestión de listas de espera de un hospital público chileno.
Redactas para un gestor de salud y el equipo clínico.

Reglas estrictas:
- Usa SOLO los datos entregados. No inventes síntomas, exámenes, fechas ni diagnósticos.
- No decides la prioridad ni recomiendas tratamientos: explicas por qué el sistema propone ese puntaje.
- Máximo 3 frases cortas, en español de Chile, sin markdown ni viñetas.
- Menciona las 1–3 señales que más pesan (con su fecha si la hay) y si la tendencia es de deterioro, estabilidad o mejora.
- Termina siempre con: "Propuesta sujeta a validación clínica."
"""

NOMBRES = {
    "prioridad_inicial": "prioridad inicial",
    "dias_espera": "días en espera",
    "plazo_vencido": "plazo clínico vencido",
    "mediciones_fuera_rango": "mediciones fuera de rango",
    "edad": "edad",
}


def _datos(p):
    return {
        "edad": p.get("edad"),
        "especialidad": p.get("especialidad"),
        "diagnostico": f'{p.get("diagnostico_cie10")} {p.get("diagnostico_texto")}',
        "prioridad_inicial": p.get("prioridad_inicial"),
        "puntaje": p.get("puntaje"),
        "categoria": p.get("categoria"),
        "posicion_actual": p.get("posicion"),
        "posicion_hace_14_dias": p.get("posicion_anterior"),
        "riesgo_inasistencia": p.get("riesgo_inasistencia"),
        "razones": p.get("razones"),
    }


def plantilla(p):
    razones = sorted([r for r in p.get("razones", []) if r["factor"] != "prioridad_inicial"],
                     key=lambda r: -abs(r["puntos"]))[:3]
    partes = []
    for r in razones:
        nombre = r["valor"] if r["factor"] == "evento" else f'{NOMBRES.get(r["factor"], r["factor"])}: {r["valor"]}'
        partes.append(f'{nombre} ({"+" if r["puntos"] >= 0 else ""}{r["puntos"]} pts)')
    ant, act = p.get("posicion_anterior"), p.get("posicion")
    mov = ""
    if ant and act:
        mov = f" Subió {ant - act} puestos en 14 días." if ant > act else (f" Bajó {act - ant} puestos en 14 días." if act > ant else "")
    texto = (f'Prioridad {p.get("categoria")} ({p.get("puntaje")} pts) para {p.get("diagnostico_texto")}, '
             f'con prioridad inicial {p.get("prioridad_inicial")}. Principales factores: {"; ".join(partes) or "sin señales registradas"}.'
             f'{mov}')
    if p.get("riesgo_inasistencia"):
        texto += " Tiene inasistencias previas: confirmar asistencia por teléfono."
    return texto + " Propuesta sujeta a validación clínica."


def explicar(paciente):
    """Devuelve (texto, fuente) donde fuente es 'bedrock' o 'plantilla'."""
    model_id = os.environ.get("MODEL_ID")
    if not model_id:
        return plantilla(paciente), "plantilla"
    try:
        import boto3
        kw = {"region_name": os.environ["BEDROCK_REGION"]} if os.environ.get("BEDROCK_REGION") else {}
        client = boto3.client("bedrock-runtime", **kw)
        r = client.converse(
            modelId=model_id,
            system=[{"text": PROMPT_SISTEMA}],
            messages=[{"role": "user", "content": [{"text": "Datos del paciente:\n" + json.dumps(_datos(paciente), ensure_ascii=False)}]}],
            inferenceConfig={"maxTokens": 300, "temperature": 0.2},
        )
        texto = r["output"]["message"]["content"][0]["text"].strip()
        if "validación clínica" not in texto:
            texto += " Propuesta sujeta a validación clínica."
        return texto, "bedrock"
    except Exception as e:
        print(f"Bedrock falló, uso plantilla: {e}")
        return plantilla(paciente), "plantilla"
