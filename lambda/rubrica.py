"""Lectura del historial con una rúbrica cerrada (Amazon Bedrock). El LLM LEE y responde preguntas fijas con citas;
no asigna puntajes, categorías ni posiciones (eso lo hace decisor.py, código determinista).

- Salida estructurada: Converse con una herramienta obligatoria (toolChoice) cuyo esquema es RespuestaRubrica.
- "desconocido" es una respuesta válida y NO equivale a "no".
- Cada "sí" debe citar fecha, tipo y valor EXACTOS de un registro del historial (validar_citas lo comprueba).
- Nunca se envía `temperature` (el modelo la rechaza). Timeouts y reintentos acotados.
"""
import hashlib
import json
import os
import time
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

VERSION_RUBRICA = "rubrica_v1.1"  # v1.1: evento = descompensación de cualquier severidad (como la tabla)

SND = Literal["si", "no", "desconocido"]


class Cita(BaseModel):
    fecha: str = Field(description="Fecha exacta del registro citado (AAAA-MM-DD)")
    tipo: str = Field(description="tipo_evento o tipo_medicion exacto del registro citado")
    valor: str = Field(description="subtipo del evento o valor numérico de la medición, tal como aparece")


class Respuesta(BaseModel):
    valor: SND
    citas: list[Cita] = Field(default_factory=list)


class Tendencia(BaseModel):
    valor: Literal["empeora", "estable", "mejora", "desconocido"]
    citas: list[Cita] = Field(default_factory=list)


class RespuestaRubrica(BaseModel):
    evento_grave: Respuesta
    estabilizado_despues: Respuesta
    tendencia_medicion: Tendencia
    cambio_tratamiento_por_mal_control: Respuesta
    senal_no_cubierta: str = ""


# ---------- historial que ve el modelo (solo datos con fecha ≤ corte; nunca etiquetas médicas) ----------
def historial(perfil, corte):
    le, pac = perfil["lista_espera"], perfil["paciente"]
    corte_iso = corte.isoformat()
    eventos = sorted(({"fecha": e["fecha_evento"], "tipo": e["tipo_evento"], "valor": e.get("subtipo") or "",
                       "severidad": e.get("severidad"), **({"motivo": e["motivo"]} if e.get("motivo") else {}),
                       **({"relacionado_con_su_diagnostico": e["relacionado"]} if e.get("relacionado") is not None else {})}
                      for e in perfil.get("eventos_clinicos", [])
                      if le["fecha_ingreso_lista"] <= e["fecha_evento"] <= corte_iso), key=lambda x: x["fecha"])
    mediciones = sorted(({"fecha": m["fecha_medicion"], "tipo": m["tipo_medicion"], "valor": _num(m["valor"]),
                          "unidad": m.get("unidad"), "fuera_de_rango": m.get("fuera_de_rango")}
                         for m in perfil.get("mediciones", []) if m["fecha_medicion"] <= corte_iso), key=lambda x: x["fecha"])
    return {"diagnostico": le["diagnostico_cie10"], "diagnostico_texto": le["diagnostico_texto"],
            "prioridad_inicial": le["prioridad_inicial"], "fecha_ingreso_lista": le["fecha_ingreso_lista"],
            "edad": pac.get("edad"), "sexo": pac.get("sexo"),
            "comorbilidades": [c.get("nombre") or c.get("condicion") for c in pac.get("comorbilidades", [])
                               if (c.get("fecha") or "") <= corte_iso],  # las registradas después del corte no existían
            "eventos": eventos, "mediciones": mediciones, "fecha_corte": corte_iso}


def firma(perfil, corte):
    """Huella del historial a la fecha de corte: si cambia, la evaluación anterior deja de estar vigente."""
    h = historial(perfil, corte)
    h.pop("fecha_corte")
    return hashlib.sha256(json.dumps(h, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def _num(v):
    try:
        f = float(v)
        return str(int(f)) if f == int(f) else str(f)
    except (TypeError, ValueError):
        return str(v)


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()
    return " ".join(s.split())


def validar_citas(respuestas: RespuestaRubrica, hist):
    """Devuelve la lista de citas que NO existen en el historial y las respuestas 'sí' sin cita."""
    registros = {(r["fecha"], _norm(r["tipo"]), _norm(r["valor"])) for r in hist["eventos"] + hist["mediciones"]}
    malas = []
    for nombre in ("evento_grave", "estabilizado_despues", "cambio_tratamiento_por_mal_control", "tendencia_medicion"):
        r = getattr(respuestas, nombre)
        for c in r.citas:
            if (c.fecha, _norm(c.tipo), _norm(_num(c.valor))) not in registros:
                malas.append({"pregunta": nombre, "cita": c.model_dump()})
        if nombre != "tendencia_medicion" and r.valor == "si" and not r.citas:
            malas.append({"pregunta": nombre, "cita": None, "detalle": "respuesta 'sí' sin cita"})
    return malas


# ---------- prompt ----------
SISTEMA = """Eres un asistente que LEE el historial de un paciente en lista de espera de especialidad y responde una
rúbrica cerrada. No asignas prioridades ni puntajes: solo respondes las preguntas con los datos del historial.
Reglas:
1. Usa solo los registros del historial entregado. No supongas nada que no esté escrito.
2. Si un dato no está en el historial o no permite responder, responde "desconocido". La falta de datos NO es "no".
3. Cada respuesta "si" debe traer al menos una cita con la fecha, el tipo y el valor EXACTOS del registro que la respalda.
4. Para tendencia_medicion compara las mediciones de la medición clave indicada, de la más antigua a la más reciente.
   Cita las mediciones que usaste. Si hay menos de dos mediciones de ese tipo, responde "desconocido".
5. senal_no_cubierta: una frase breve solo si ves algo clínicamente relevante que la rúbrica no pregunta; si no, "".
Responde SIEMPRE con la herramienta responder_rubrica."""


def preguntas(dx_kb):
    medicion = dx_kb.get("medicion_clave")
    return [
        ("evento_grave", "¿Hay, después del ingreso a la lista, un evento de DESCOMPENSACIÓN de "
                         f"{dx_kb['texto']}: una visita a urgencia u hospitalización (de cualquier severidad) o cualquier "
                         "evento registrado como 'descompensación'? Cita el más reciente. (si/no/desconocido; si no hay "
                         "ningún evento registrado desde el ingreso, responde 'no' y deja la observación en senal_no_cubierta)"),
        ("estabilizado_despues", "¿Hay un control posterior a esa descompensación que registre estabilización o buena "
                                 "respuesta? (si/no/desconocido; 'no' si no hubo descompensación)"),
        ("tendencia_medicion", f"La medición clave de este diagnóstico es '{medicion}'. ¿Empeora, se mantiene o mejora en "
                               "el tiempo? (empeora/estable/mejora/desconocido)" if medicion else
                               "Este diagnóstico no tiene medición clave definida: responde 'desconocido' sin citas."),
        ("cambio_tratamiento_por_mal_control", "¿Hay un aumento de dosis o cambio de fármaco que indique mal control? "
                                               "(si/no/desconocido)"),
        ("senal_no_cubierta", "¿Algo relevante que la rúbrica no pregunta? Frase breve o vacío."),
    ]


def armar_prompt(perfil, corte, dx_kb):
    hist = historial(perfil, corte)
    texto = (f"Diagnóstico en lista: {hist['diagnostico']} {hist['diagnostico_texto']}\n"
             f"Ingreso a la lista: {hist['fecha_ingreso_lista']} · Fecha de corte: {hist['fecha_corte']}\n"
             f"Edad: {hist['edad']} · Sexo: {hist['sexo']} · Comorbilidades: {', '.join(hist['comorbilidades']) or 'ninguna registrada'}\n\n"
             "EVENTOS (fecha | tipo | valor=subtipo | severidad):\n" +
             ("\n".join(f"{e['fecha']} | {e['tipo']} | {e['valor']} | {e['severidad']}" for e in hist["eventos"]) or "(ninguno)") +
             "\n\nMEDICIONES (fecha | tipo | valor | unidad | fuera_de_rango):\n" +
             ("\n".join(f"{m['fecha']} | {m['tipo']} | {m['valor']} | {m['unidad']} | {m['fuera_de_rango']}" for m in hist["mediciones"])
              or "(ninguna)") +
             "\n\nRÚBRICA (responde cada pregunta):\n" + "\n".join(f"- {k}: {q}" for k, q in preguntas(dx_kb)))
    return SISTEMA, texto, hist


def _esquema_plano(modelo):
    """Esquema JSON sin $defs/$ref: el modelo a veces envolvía la respuesta en 'valor' al leer referencias anidadas."""
    s = modelo.model_json_schema()
    defs = s.pop("$defs", {})

    def resolver(x):
        if isinstance(x, dict):
            if "$ref" in x:
                return resolver(defs[x["$ref"].split("/")[-1]])
            return {k: resolver(v) for k, v in x.items() if k != "title"}
        if isinstance(x, list):
            return [resolver(v) for v in x]
        return x
    return resolver(s)


HERRAMIENTA = {"toolSpec": {"name": "responder_rubrica",
                            "description": "Respuestas de la rúbrica, con citas exactas del historial. Las claves de primer nivel "
                                           "son evento_grave, estabilizado_despues, tendencia_medicion, "
                                           "cambio_tratamiento_por_mal_control y senal_no_cubierta.",
                            "inputSchema": {"json": _esquema_plano(RespuestaRubrica)}}}
PREGUNTAS_CLAVE = {"evento_grave", "estabilizado_despues", "tendencia_medicion", "cambio_tratamiento_por_mal_control"}


def _desenvolver(crudo):
    """Si el modelo envolvió las respuestas en una sola clave (p. ej. {"valor": {...}}), las saca SOLO cuando adentro
    están exactamente las preguntas esperadas. No altera el contenido. Devuelve (dict, se_corrigio)."""
    if isinstance(crudo, dict) and not PREGUNTAS_CLAVE & set(crudo) and len(crudo) == 1:
        interior = next(iter(crudo.values()))
        if isinstance(interior, dict) and PREGUNTAS_CLAVE <= set(interior):
            return interior, True
    return crudo, False


def hash_prompt():
    plantilla = json.dumps(preguntas({"texto": "{dx}", "medicion_clave": "{medicion}"}), ensure_ascii=False)
    return hashlib.sha256((VERSION_RUBRICA + SISTEMA + plantilla + json.dumps(HERRAMIENTA, sort_keys=True)).encode()).hexdigest()[:12]


# ---------- clientes ----------
class ErrorLectura(Exception):
    pass


class ClienteBedrock:
    """Cliente real. El modelo y la región vienen de variables de entorno."""

    def __init__(self, model_id=None, region=None, timeout_s=20, reintentos=2):
        import boto3
        from botocore.config import Config
        self.model_id = model_id or os.environ.get("MODEL_ID", "us.anthropic.claude-sonnet-5")
        self.c = boto3.client("bedrock-runtime", region_name=region or os.environ.get("BEDROCK_REGION") or None,
                              config=Config(read_timeout=timeout_s, connect_timeout=5,
                                            retries={"max_attempts": reintentos, "mode": "standard"}))

    def leer(self, sistema, texto, herramienta, max_tokens=900):
        t0 = time.perf_counter()
        nombre = herramienta["toolSpec"]["name"]
        r = self.c.converse(modelId=self.model_id, system=[{"text": sistema}],
                            messages=[{"role": "user", "content": [{"text": texto}]}],
                            toolConfig={"tools": [herramienta], "toolChoice": {"tool": {"name": nombre}}},
                            inferenceConfig={"maxTokens": max_tokens})
        bloque = next((b["toolUse"] for b in r["output"]["message"]["content"] if "toolUse" in b), None)
        if not bloque:
            raise ErrorLectura(f"el modelo no usó la herramienta (stopReason={r.get('stopReason')})")
        return bloque["input"], {"modelo": self.model_id, "latencia_s": round(time.perf_counter() - t0, 2),
                                 "tokens_entrada": r["usage"]["inputTokens"], "tokens_salida": r["usage"]["outputTokens"]}


class ClienteFalso:
    """Para tests: devuelve respuestas grabadas (dict o función perfil→dict) sin llamar a Bedrock."""

    def __init__(self, respuestas, fallar=False):
        self.respuestas, self.fallar, self.llamadas = respuestas, fallar, 0
        self.model_id = "falso"

    def leer(self, sistema, texto, herramienta, max_tokens=900):
        self.llamadas += 1
        if self.fallar:
            raise ErrorLectura("falla simulada")
        r = self.respuestas(texto) if callable(self.respuestas) else self.respuestas
        return r, {"modelo": "falso", "latencia_s": 0.0, "tokens_entrada": 0, "tokens_salida": 0}


def respuesta_determinista(hist, dx_kb, tolerancia=0.05):
    """Responde la misma rúbrica con código (sin LLM). Se usa como respuesta grabada en tests y como brazo de control
    en la evaluación: si el LLM no supera a este lector, no aporta con datos estructurados."""
    def cita(r):
        return {"fecha": r["fecha"], "tipo": r["tipo"], "valor": r["valor"]}
    graves = [e for e in hist["eventos"] if e["tipo"] not in ("hallazgo_oncologico", "criterio_clinico", "combinacion_riesgo") and e.get("relacionado_con_su_diagnostico") is not False and
              (e["severidad"] == "grave" or "descompensaci" in _norm(e["valor"]))]  # = puntaje.descompensa
    ultimo = graves[-1] if graves else None
    estab = [e for e in hist["eventos"] if e["tipo"] == "control_aps" and _norm(e["valor"]) in ("estabilizacion", "buena respuesta")
             and ultimo and e["fecha"] > ultimo["fecha"]]
    med = dx_kb.get("medicion_clave")
    serie = [m for m in hist["mediciones"] if m["tipo"] == med] if med else []
    if len(serie) < 2:
        tend = {"valor": "desconocido", "citas": []}
    else:
        a, b = float(serie[0]["valor"]), float(serie[-1]["valor"])
        sube = (b - a) / abs(a) > tolerancia if a else b > a
        baja = (a - b) / abs(a) > tolerancia if a else b < a
        peor_si_baja = med in ("saturacion_o2", "peak_flow")
        tend = {"valor": ("empeora" if (baja if peor_si_baja else sube) else "mejora" if (sube if peor_si_baja else baja) else "estable"),
                "citas": [cita(serie[0]), cita(serie[-1])]}
    aumentos = [e for e in hist["eventos"] if e["tipo"] == "cambio_farmaco" and "aument" in _norm(e["valor"])]
    return {"evento_grave": {"valor": "si" if ultimo else "no", "citas": [cita(ultimo)] if ultimo else []},
            "estabilizado_despues": {"valor": "si" if estab else "no", "citas": [cita(estab[-1])] if estab else []},
            "tendencia_medicion": tend,
            "cambio_tratamiento_por_mal_control": {"valor": "si" if aumentos else "no", "citas": [cita(aumentos[-1])] if aumentos else []},
            "senal_no_cubierta": ""}


def leer_rubrica(perfil, corte, dx_kb, cliente):
    """Una lectura. Devuelve (RespuestaRubrica | None, meta). Nunca lanza: los errores quedan en meta['error']."""
    sistema, texto, hist = armar_prompt(perfil, corte, dx_kb)
    meta = {"version_rubrica": VERSION_RUBRICA, "hash_prompt": hash_prompt(), "modelo": getattr(cliente, "model_id", "?")}
    try:
        crudo, uso = cliente.leer(sistema, texto, HERRAMIENTA)
        meta.update(uso)
        crudo, corregido = _desenvolver(crudo)
        if corregido:
            meta["envoltorio_corregido"] = True
        return RespuestaRubrica.model_validate(crudo), meta
    except ValidationError as e:
        meta["error"] = f"json_invalido: {e.errors()[0]['msg']}"
    except Exception as e:  # timeout, permisos, throttling, herramienta no usada
        meta["error"] = f"fallo_llm: {type(e).__name__}: {str(e)[:160]}"
    return None, meta
