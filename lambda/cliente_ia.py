"""Piezas comunes de las llamadas a la IA (Amazon Bedrock, API Converse). Todo se configura por variables de entorno:

- MODEL_ID=simulado: lector determinista sin red (rubrica.ClienteSimulado) para demostrar el flujo sin AWS. Queda rotulado
  "simulado" en cada evaluación y métrica: no se puede confundir con una lectura de Bedrock.
- MODEL_ID_REDACCION (opcional): modelo del resumen para el equipo (explicar.py); si falta, MODEL_ID.
- LECTURAS_IA (1 a 3, por defecto 3): cuántas veces se lee cada texto. Con menos lecturas baja el costo, pero se pierde
  (o se debilita) el control de estabilidad: ver umbral_votos y evaluacion_ia.evaluar_y_guardar.
- GUARDRAIL_ID + GUARDRAIL_VERSION (opcionales): guardrailConfig en cada converse. Los guardrails no revisan argumentos ni
  resultados de herramientas: no reemplazan a privacidad.ocultar.
- BEDROCK_CACHE=1 (opcional, apagado): caché de prompts (bloques cachePoint). Bajo el mínimo de tokens del modelo la
  llamada funciona igual, solo que no se guarda.
- Cada llamada deja UNA línea JSON en la salida estándar ({"metrica": "ia", ...}) para sumar el costo por tarea en
  CloudWatch. Sin texto clínico: solo tarea, modelo, tokens, latencia y el código del error.
"""
import json
import os
import re

SIMULADO = "simulado"
TAREAS = ("rubrica", "documento", "criterios", "combinaciones", "resumen")
TAREA_DE_HERRAMIENTA = {"responder_rubrica": "rubrica", "listar_hallazgos": "documento",
                        "clasificar_criterio": "criterios", "marcar_combinaciones": "combinaciones"}
PUNTO_CACHE = {"cachePoint": {"type": "default"}}

# Errores de validación con los que un modelo rechaza una opción de la petición (se reintenta sin ella)
RECHAZA_TOOL_CHOICE = re.compile(r"tool.?choice|forced tool|tool use.{0,40}forc|forc\w*.{0,40}tool", re.IGNORECASE)
RECHAZA_THINKING = re.compile(r"thinking|additional.?model.?request", re.IGNORECASE)


def modelo(redaccion=False):
    """MODEL_ID (o MODEL_ID_REDACCION para el resumen). None si no hay IA configurada."""
    if redaccion and not simulado():
        return os.environ.get("MODEL_ID_REDACCION") or os.environ.get("MODEL_ID")
    return os.environ.get("MODEL_ID")


def simulado(model_id=None):
    return (model_id if model_id is not None else os.environ.get("MODEL_ID")) == SIMULADO


def lecturas_ia(defecto=3):
    """LECTURAS_IA acotado a 1..3. Un valor inválido no tumba la Lambda: usa el defecto y lo avisa."""
    v = os.environ.get("LECTURAS_IA")
    if not v:
        return defecto
    try:
        return min(3, max(1, int(v)))
    except ValueError:
        print(json.dumps({"aviso": "ia", "detalle": f"LECTURAS_IA inválido ({v[:10]!r}): se usan {defecto}"}))
        return defecto


def umbral_votos(lecturas):
    """Cuántas lecturas iguales y verificadas hacen falta: 2 de 3, 2 de 2 y, con 1 sola lectura, 1 de 1 (sin control de
    estabilidad; la cita igual se verifica contra el texto y el resultado solo puede subir la prioridad)."""
    return 2 if lecturas >= 2 else 1


def guardrail():
    """Argumentos extra para converse: {} si no hay guardrail configurado (los dos valores son necesarios)."""
    gid, ver = os.environ.get("GUARDRAIL_ID"), os.environ.get("GUARDRAIL_VERSION")
    if gid and ver:
        return {"guardrailConfig": {"guardrailIdentifier": gid, "guardrailVersion": ver, "trace": "disabled"}}
    if gid or ver:
        print(json.dumps({"aviso": "ia", "detalle": "falta GUARDRAIL_ID o GUARDRAIL_VERSION: se llama sin guardrail"}))
    return {}


def cache_activa():
    return os.environ.get("BEDROCK_CACHE") == "1"


def uso(r):
    u = (r or {}).get("usage") or {}
    return {"tokens_entrada": u.get("inputTokens") or 0, "tokens_salida": u.get("outputTokens") or 0,
            "tokens_cache_lectura": u.get("cacheReadInputTokens") or 0,
            "tokens_cache_escritura": u.get("cacheWriteInputTokens") or 0}


def codigo_error(e):
    """Código corto del error, sin el mensaje (un mensaje de error podría repetir texto de la petición)."""
    if isinstance(e, str):
        return e[:60]
    err = (getattr(e, "response", None) or {}).get("Error") or {}
    return err.get("Code") or type(e).__name__


def rechaza(e, patron):
    """¿Es un error de validación de Bedrock que rechaza la opción descrita por el patrón?"""
    err = (getattr(e, "response", None) or {}).get("Error") or {}
    return err.get("Code") == "ValidationException" and bool(patron.search(err.get("Message") or str(e)))


def metrica(tarea, modelo_id, latencia_s=0.0, tokens=None, error=None):
    """Una línea JSON por llamada al modelo (CloudWatch Logs Insights: filter metrica = "ia" | stats sum(...) by tarea)."""
    t = tokens or {}
    linea = {"metrica": "ia", "tarea": tarea, "modelo": modelo_id,
             "tokens_entrada": t.get("tokens_entrada", 0), "tokens_salida": t.get("tokens_salida", 0),
             "tokens_cache_lectura": t.get("tokens_cache_lectura", 0), "tokens_cache_escritura": t.get("tokens_cache_escritura", 0),
             "latencia_s": round(latencia_s or 0.0, 3), "resultado": "error" if error else "ok",
             "error": codigo_error(error) if error else None}
    print(json.dumps(linea, ensure_ascii=False))
    return linea
