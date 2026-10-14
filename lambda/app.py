"""API Ambulatorio Dinámico HLF — una sola Lambda detrás de API Gateway HTTP API.

Rutas (ver contrato.md):
  GET  /pacientes?fecha_corte=AAAA-MM-DD&especialidad=X
  GET  /pacientes/{id}?fecha_corte=...
  POST /eventos
  POST /pacientes/{id}/revision
  POST /pacientes/{id}/explicar
  GET  /boxes?especialidad=X&fecha_corte=...

Modo local: LOCAL=1 y DATA_DIR=ruta a data/ (lee perfiles.json y box.json, guarda en memoria).
Modo AWS:   BUCKET, PERFILES_KEY, BOX_KEY, TABLE (DynamoDB pk=id_paciente, sk=texto).
"""
import copy
import json
import os
import time
import uuid
from datetime import date, datetime, timedelta, timezone

import puntaje
import explicar

LOCAL = os.environ.get("LOCAL") == "1"
FECHA_REFERENCIA = date(2026, 10, 13)
TIPOS_EVENTO = {"cambio_farmaco", "control_aps", "examen_alterado", "hospitalizacion", "visita_urgencia"}

_cache = {"perfiles": None, "box": None}
_mem = []  # almacenamiento en memoria para modo local


# ---------- datos ----------
def _leer_json(nombre_env, archivo):
    if LOCAL:
        with open(os.path.join(os.environ.get("DATA_DIR", "data"), archivo), encoding="utf-8") as f:
            return json.load(f)
    import boto3
    obj = boto3.client("s3").get_object(Bucket=os.environ["BUCKET"], Key=os.environ.get(nombre_env, archivo))
    return json.loads(obj["Body"].read())


def perfiles():
    if _cache["perfiles"] is None:
        _cache["perfiles"] = {p["id_paciente"]: p for p in _leer_json("PERFILES_KEY", "perfiles.json")}
    return _cache["perfiles"]


def box_data():
    if _cache["box"] is None:
        try:
            _cache["box"] = _leer_json("BOX_KEY", "box.json")
        except Exception:
            _cache["box"] = {}
    return _cache["box"]


def _tabla():
    import boto3
    return boto3.resource("dynamodb").Table(os.environ["TABLE"])


def guardar(item):
    if LOCAL:
        _mem.append(item)
    else:
        _tabla().put_item(Item=item)


def registros():
    """Todos los eventos y revisiones agregados durante la demo."""
    if LOCAL:
        return list(_mem)
    tabla, items, kw = _tabla(), [], {}
    while True:
        r = tabla.scan(**kw)
        items += r["Items"]
        if "LastEvaluatedKey" not in r:
            return items
        kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]


def perfiles_combinados():
    """perfiles.json + eventos nuevos + última revisión por paciente."""
    base = perfiles()
    regs = registros()
    eventos = [r for r in regs if r["sk"].startswith("evento#")]
    revisiones = sorted([r for r in regs if r["sk"].startswith("revision#")], key=lambda r: r["sk"])
    out = dict(base)
    for ev in eventos:
        pid = ev["id_paciente"]
        if pid not in out:
            continue
        if out[pid] is base[pid]:
            out[pid] = copy.deepcopy(base[pid])
        out[pid].setdefault("eventos_clinicos", []).append(json.loads(ev["evento"]))
    ult_rev = {r["id_paciente"]: json.loads(r["revision"]) for r in revisiones}
    return out, ult_rev


# ---------- lógica ----------
def _fecha(qs):
    f = (qs or {}).get("fecha_corte")
    return date.fromisoformat(f) if f else FECHA_REFERENCIA


def _enriquecer(r, perfil, revision, pos_ant):
    pac, le = perfil["paciente"], perfil["lista_espera"]
    out = {
        "id_paciente": r["id_paciente"],
        "nombre_fantasia": pac["nombre_fantasia"],
        "edad": pac["edad"],
        "sexo": pac["sexo"],
        "comuna": pac["comuna"],
        "especialidad": le["especialidad"],
        "diagnostico_cie10": le["diagnostico_cie10"],
        "diagnostico_texto": le["diagnostico_texto"],
        "prioridad_inicial": le["prioridad_inicial"],
        "fecha_ingreso_lista": le["fecha_ingreso_lista"],
        "dias_espera": r["dias_espera"],
        "puntaje": r["puntaje"],
        "categoria": r["categoria"],
        "posicion": r.get("posicion"),
        "posicion_anterior": pos_ant,
        "riesgo_inasistencia": r["riesgo_inasistencia"],
        "no_shows": r["no_shows"],
        "razones": r["razones"],
        "explicacion_ia": None,
        "estado_revision": "pendiente",
    }
    if revision:
        out["estado_revision"] = revision["accion"] == "ajustar" and "ajustado" or "confirmado"
        out["revision"] = revision
        if revision.get("puntaje_ajustado") is not None:
            out["puntaje_ajustado"] = revision["puntaje_ajustado"]
    return out


def lista(corte, especialidad=None, perfs=None, revs=None):
    if perfs is None:
        perfs, revs = perfiles_combinados()
    vals = list(perfs.values())
    activos, excluidos = puntaje.priorizar(vals, corte, especialidad)
    ant, _ = puntaje.priorizar(vals, corte - timedelta(days=14), especialidad)
    pos_ant = {r["id_paciente"]: r["posicion"] for r in ant}
    pacientes = [_enriquecer(r, perfs[r["id_paciente"]], revs.get(r["id_paciente"]), pos_ant.get(r["id_paciente"])) for r in activos]
    # el equipo clínico decide: si ajustó el puntaje, ese valor manda en el orden
    pacientes.sort(key=lambda p: -(p["puntaje_ajustado"] if p.get("puntaje_ajustado") is not None else p["puntaje"]))
    for i, p in enumerate(pacientes, 1):
        p["posicion"] = i
    exc = [{"id_paciente": r["id_paciente"], "motivo": r["motivo"],
            "fecha_defuncion": perfs[r["id_paciente"]]["paciente"].get("fecha_defuncion")} for r in excluidos]
    return {"fecha_corte": corte.isoformat(), "total": len(pacientes), "pacientes": pacientes, "excluidos": exc}


def detalle(pid, corte):
    perfs, revs = perfiles_combinados()
    if pid not in perfs:
        return None
    data = lista(corte, perfs[pid]["lista_espera"]["especialidad"], perfs, revs)
    fila = next((p for p in data["pacientes"] if p["id_paciente"] == pid), None)
    p = perfs[pid]
    return {
        "paciente": fila,
        "excluido": next((e for e in data["excluidos"] if e["id_paciente"] == pid), None),
        "eventos_clinicos": [e for e in p.get("eventos_clinicos", []) if e["fecha_evento"] <= corte.isoformat()],
        "mediciones": [m for m in p.get("mediciones", []) if m["fecha_medicion"] <= corte.isoformat()],
        "citaciones": [c for c in p.get("citaciones", []) if c["fecha_cita"] <= corte.isoformat()],
        "lista_espera": p["lista_espera"],
        "datos_paciente": p["paciente"],
    }


def post_evento(body):
    t0 = time.perf_counter()
    pid = body.get("id_paciente")
    if pid not in perfiles():
        return 404, {"error": "paciente no existe"}
    if body.get("tipo_evento") not in TIPOS_EVENTO:
        return 400, {"error": f"tipo_evento debe ser uno de {sorted(TIPOS_EVENTO)}"}
    corte = date.fromisoformat(body.get("fecha_corte") or FECHA_REFERENCIA.isoformat())
    especialidad = perfiles()[pid]["lista_espera"]["especialidad"]
    antes = lista(corte, especialidad)
    pos_antes = next((p["posicion"] for p in antes["pacientes"] if p["id_paciente"] == pid), None)
    ev = {
        "id_evento": "EV-DEMO-" + uuid.uuid4().hex[:6].upper(),
        "fecha_evento": body.get("fecha_evento") or corte.isoformat(),
        "tipo_evento": body["tipo_evento"],
        "subtipo": body.get("subtipo", ""),
        "severidad": body.get("severidad", "moderada"),
        "detalle": body.get("detalle") or f'{body.get("subtipo", body["tipo_evento"])} ({especialidad})',
    }
    guardar({"id_paciente": pid, "sk": f"evento#{ev['fecha_evento']}#{ev['id_evento']}", "evento": json.dumps(ev, ensure_ascii=False)})
    despues = lista(corte, especialidad)
    fila = next((p for p in despues["pacientes"] if p["id_paciente"] == pid), None)
    ms = round((time.perf_counter() - t0) * 1000)
    return 200, {"evento": ev, "paciente": fila, "posicion_antes": pos_antes,
                 "posicion_despues": fila and fila["posicion"], "reevaluado_en_ms": ms, "lista": despues}


def post_revision(pid, body):
    if pid not in perfiles():
        return 404, {"error": "paciente no existe"}
    accion = body.get("accion")
    if accion not in ("confirmar", "ajustar"):
        return 400, {"error": "accion debe ser 'confirmar' o 'ajustar'"}
    if accion == "ajustar" and (body.get("puntaje_ajustado") is None or not body.get("motivo")):
        return 400, {"error": "ajustar requiere puntaje_ajustado y motivo"}
    rev = {"accion": accion, "puntaje_ajustado": body.get("puntaje_ajustado"), "motivo": body.get("motivo"),
           "usuario": body.get("usuario", "equipo clínico"), "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    guardar({"id_paciente": pid, "sk": f"revision#{rev['fecha']}", "revision": json.dumps(rev, ensure_ascii=False)})
    return 200, {"id_paciente": pid, "revision": rev}


def post_explicar(pid, corte):
    d = detalle(pid, corte)
    if not d or not d["paciente"]:
        return 404, {"error": "paciente no está en la lista a esa fecha"}
    texto, fuente = explicar.explicar(d["paciente"])
    return 200, {"id_paciente": pid, "explicacion_ia": texto, "fuente": fuente}


def boxes(corte, especialidad=None):
    b = box_data()
    data = lista(corte)
    sugerencias = {}
    for p in data["pacientes"]:
        sugerencias.setdefault(p["especialidad"], []).append(p)
    out = []
    for esp, info in sorted(b.get("especialidades", {}).items()):
        if especialidad and esp != especialidad:
            continue
        libres_dia = info.get("cupos_libres_promedio_dia", 0)
        top = sugerencias.get(esp, [])[: max(1, round(libres_dia))]
        out.append({**info, "especialidad": esp,
                    "sugeridos": [{"id_paciente": p["id_paciente"], "nombre_fantasia": p["nombre_fantasia"],
                                   "puntaje": p["puntaje"], "categoria": p["categoria"],
                                   "accion": "confirmar por teléfono" if p["riesgo_inasistencia"] else "citar"} for p in top]})
    return {"fecha_corte": corte.isoformat(), "resumen": b.get("resumen", {}), "especialidades": out}


# ---------- HTTP ----------
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "content-type",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS", "Content-Type": "application/json"}


def _resp(status, body):
    return {"statusCode": status, "headers": CORS, "body": json.dumps(body, ensure_ascii=False, default=str)}


def handler(event, context=None):
    try:
        method = event.get("requestContext", {}).get("http", {}).get("method") or event.get("httpMethod", "GET")
        path = (event.get("rawPath") or event.get("path") or "/").rstrip("/") or "/"
        qs = event.get("queryStringParameters") or {}
        body = json.loads(event.get("body") or "{}") if event.get("body") else {}
        partes = [p for p in path.split("/") if p]

        if method == "OPTIONS":
            return _resp(200, {})
        if method == "GET" and partes == ["pacientes"]:
            return _resp(200, lista(_fecha(qs), qs.get("especialidad") or None))
        if method == "GET" and len(partes) == 2 and partes[0] == "pacientes":
            d = detalle(partes[1], _fecha(qs))
            return _resp(200, d) if d else _resp(404, {"error": "paciente no existe"})
        if method == "POST" and partes == ["eventos"]:
            return _resp(*post_evento(body))
        if method == "POST" and len(partes) == 3 and partes[0] == "pacientes" and partes[2] == "revision":
            return _resp(*post_revision(partes[1], body))
        if method == "POST" and len(partes) == 3 and partes[0] == "pacientes" and partes[2] == "explicar":
            return _resp(*post_explicar(partes[1], _fecha({**qs, **body})))
        if method == "GET" and partes == ["boxes"]:
            return _resp(200, boxes(_fecha(qs), qs.get("especialidad") or None))
        if method == "GET" and partes in ([], ["health"]):
            return _resp(200, {"ok": True, "pacientes": len(perfiles())})
        return _resp(404, {"error": f"ruta no encontrada: {method} {path}"})
    except Exception as e:  # nunca devolver 502 sin CORS: el front no podría leer el error
        return _resp(500, {"error": str(e)})
