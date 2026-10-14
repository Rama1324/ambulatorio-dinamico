"""API Ambulatorio Dinámico HLF — una sola Lambda detrás de API Gateway HTTP API.

Rutas (ver contrato.md):
  GET  /pacientes?fecha_corte=AAAA-MM-DD&especialidad=X
  GET  /pacientes/{id}?fecha_corte=...
  POST /eventos
  POST /pacientes/{id}/revision
  POST /pacientes/{id}/informe   (lee texto libre y propone un evento; no guarda)
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
import informe

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
    """perfiles.json + pacientes ingresados + eventos nuevos + última revisión por paciente."""
    base = perfiles()
    regs = registros()
    eventos = [r for r in regs if r["sk"].startswith("evento#")]
    revisiones = sorted([r for r in regs if r["sk"].startswith("revision#")], key=lambda r: r["sk"])
    out = dict(base)
    for r in regs:
        if r["sk"] == "paciente#":
            out[r["id_paciente"]] = json.loads(r["perfil"])
    for ev in eventos:
        pid = ev["id_paciente"]
        if pid not in out:
            continue
        if pid in base and out[pid] is base[pid]:
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
        "categoria": r["categoria"],
        "categoria_sistema": r["categoria"],
        "estado_clinico": r["estado_clinico"],
        "riesgo_vital": r["riesgo_vital"],
        "lace": r["lace"],
        "antiguedad_mayor_1_anio": r["antiguedad_mayor_1_anio"],
        "ges": r["ges"],
        "medicion_alerta": r["medicion_alerta"],
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
        if revision.get("categoria_ajustada"):
            out["categoria"] = revision["categoria_ajustada"]  # el equipo clínico decide
    return out


def lista(corte, especialidad=None, perfs=None, revs=None):
    if perfs is None:
        perfs, revs = perfiles_combinados()
    vals = list(perfs.values())
    activos, excluidos = puntaje.priorizar(vals, corte, especialidad)
    ant, _ = puntaje.priorizar(vals, corte - timedelta(days=14), especialidad)
    pos_ant = {r["id_paciente"]: r["posicion"] for r in ant}
    pacientes = [_enriquecer(r, perfs[r["id_paciente"]], revs.get(r["id_paciente"]), pos_ant.get(r["id_paciente"])) for r in activos]
    # el equipo clínico decide: si ajustó la categoría, esa manda en el orden (mismos criterios MINSAL)
    pacientes.sort(key=puntaje.clave_orden)
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


def historia(pid, corte):
    """Posición y categoría del paciente cada 14 días hasta la fecha de corte (mismas reglas que la lista)."""
    perfs, _ = perfiles_combinados()
    if pid not in perfs:
        return None
    fechas, f = [], date(2026, 4, 1)
    while f < corte:
        fechas.append(f); f += timedelta(days=14)
    fechas.append(corte)
    vals, puntos = list(perfs.values()), []
    for fc in fechas:
        activos, excluidos = puntaje.priorizar(vals, fc)
        r = next((x for x in activos if x["id_paciente"] == pid), None)
        if r:
            puntos.append({"fecha": fc.isoformat(), "posicion": r["posicion"], "total": len(activos),
                           "categoria": r["categoria"], "riesgo_vital": r["riesgo_vital"]})
        elif any(x["id_paciente"] == pid for x in excluidos):
            puntos.append({"fecha": fc.isoformat(), "excluido": True})
    eventos = [e for e in perfs[pid].get("eventos_clinicos", []) if e["fecha_evento"] <= corte.isoformat()
               and puntaje.descompensa(e) or (puntaje.estabiliza(e) and e["fecha_evento"] <= corte.isoformat())]
    return {"id_paciente": pid, "puntos": puntos, "eventos": eventos}


def post_evento(body):
    t0 = time.perf_counter()
    pid = body.get("id_paciente")
    perfs, _ = perfiles_combinados()
    if pid not in perfs:
        return 404, {"error": "paciente no existe"}
    if body.get("tipo_evento") not in TIPOS_EVENTO:
        return 400, {"error": f"tipo_evento debe ser uno de {sorted(TIPOS_EVENTO)}"}
    corte = date.fromisoformat(body.get("fecha_corte") or FECHA_REFERENCIA.isoformat())
    especialidad = perfs[pid]["lista_espera"]["especialidad"]
    antes = lista(corte)
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
    despues = lista(corte)
    fila = next((p for p in despues["pacientes"] if p["id_paciente"] == pid), None)
    ms = round((time.perf_counter() - t0) * 1000)
    return 200, {"evento": ev, "paciente": fila, "posicion_antes": pos_antes,
                 "posicion_despues": fila and fila["posicion"], "reevaluado_en_ms": ms, "lista": despues}


def catalogo():
    """Diagnósticos de la lista (especialidad, sub-especialidad, CIE-10, texto), tal como vienen en el registro."""
    vistos = {}
    for p in perfiles_combinados()[0].values():
        le = p["lista_espera"]
        vistos[le["diagnostico_cie10"]] = {"especialidad": le["especialidad"], "sub_especialidad": le["sub_especialidad"],
                                          "diagnostico_cie10": le["diagnostico_cie10"], "diagnostico_texto": le["diagnostico_texto"]}
    return {"diagnosticos": sorted(vistos.values(), key=lambda d: (d["especialidad"], d["diagnostico_cie10"])),
            "comunas": sorted({p["paciente"]["comuna"] for p in perfiles().values()}),
            "previsiones": sorted({p["paciente"]["prevision"] for p in perfiles().values()}),
            "origenes": sorted({p["lista_espera"]["origen_derivacion"] for p in perfiles().values()})}


def post_paciente(body):
    """Ingresa una nueva interconsulta a la lista (la prioridad inicial la define quien prioriza la SIC)."""
    cat = {d["diagnostico_cie10"]: d for d in catalogo()["diagnosticos"]}
    dx = cat.get(body.get("diagnostico_cie10"))
    nombre = (body.get("nombre") or "").strip()
    try:
        edad = int(body.get("edad"))
    except (TypeError, ValueError):
        edad = -1
    if not nombre or not dx or body.get("prioridad_inicial") not in puntaje.ORDEN_CAT or not 0 <= edad <= 120 \
            or body.get("sexo") not in ("F", "M"):
        return 400, {"error": "requiere nombre, edad (0-120), sexo (F/M), diagnostico_cie10 del catálogo y prioridad_inicial (alta|media|baja)"}
    corte = date.fromisoformat(body.get("fecha_corte") or FECHA_REFERENCIA.isoformat())
    ingreso = body.get("fecha_ingreso_lista") or corte.isoformat()
    pid = "PAC-NUEVO-" + uuid.uuid4().hex[:5].upper()
    perfil = {
        "id_paciente": pid,
        "paciente": {"nombre_fantasia": nombre, "edad": edad, "sexo": body["sexo"], "comuna": body.get("comuna") or "La Florida",
                     "prevision": body.get("prevision") or "FONASA B", "nivel_socioeconomico": "", "fallecido": False,
                     "fecha_defuncion": None},
        "lista_espera": {"id_solicitud": "IC-" + pid, "especialidad": dx["especialidad"], "sub_especialidad": dx["sub_especialidad"],
                         "diagnostico_cie10": dx["diagnostico_cie10"], "diagnostico_texto": dx["diagnostico_texto"],
                         "prioridad_inicial": body["prioridad_inicial"], "fecha_ingreso_lista": ingreso,
                         "origen_derivacion": body.get("origen_derivacion") or "CESFAM/APS", "estado": "en_espera"},
        "eventos_clinicos": [], "mediciones": [], "citaciones": [],
    }
    guardar({"id_paciente": pid, "sk": "paciente#", "perfil": json.dumps(perfil, ensure_ascii=False)})
    data = lista(corte)
    fila = next((p for p in data["pacientes"] if p["id_paciente"] == pid), None)
    return 200, {"id_paciente": pid, "paciente": fila}


def post_revision(pid, body):
    if pid not in perfiles_combinados()[0]:
        return 404, {"error": "paciente no existe"}
    accion = body.get("accion")
    if accion not in ("confirmar", "ajustar"):
        return 400, {"error": "accion debe ser 'confirmar' o 'ajustar'"}
    if accion == "ajustar" and (body.get("categoria_ajustada") not in puntaje.ORDEN_CAT or not body.get("motivo")):
        return 400, {"error": "ajustar requiere categoria_ajustada (alta|media|baja) y motivo"}
    rev = {"accion": accion, "categoria_ajustada": body.get("categoria_ajustada") if accion == "ajustar" else None,
           "motivo": body.get("motivo"),
           "usuario": body.get("usuario", "equipo clínico"), "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    guardar({"id_paciente": pid, "sk": f"revision#{rev['fecha']}", "revision": json.dumps(rev, ensure_ascii=False)})
    return 200, {"id_paciente": pid, "revision": rev}


def post_informe(pid, body):
    """Lee un informe en texto libre y PROPONE un evento. No guarda nada: el equipo clínico confirma con POST /eventos."""
    perfs, _ = perfiles_combinados()
    if pid not in perfs:
        return 404, {"error": "paciente no existe"}
    texto = (body.get("texto") or "").strip()
    transcripcion = None
    if not texto and body.get("imagen_base64"):  # foto de un informe en papel
        texto, motivo = informe.transcribir_foto(body["imagen_base64"], body.get("media_type", "image/jpeg"))
        if not texto:
            return 200, {"id_paciente": pid, "evento": None, "fuente": None, "mensaje": motivo}
        transcripcion = texto
    if not texto:
        return 400, {"error": "falta 'texto' o 'imagen_base64' del informe"}
    corte = date.fromisoformat(body.get("fecha_corte") or FECHA_REFERENCIA.isoformat())
    ev, fuente = informe.extraer(texto)
    if not ev:
        return 200, {"id_paciente": pid, "evento": None, "fuente": fuente, "transcripcion": transcripcion,
                     "mensaje": "No encontré en el informe un evento del registro (urgencia, hospitalización, examen alterado, "
                                "cambio de fármaco o control APS). Puedes registrarlo manualmente."}
    if not ev.get("fecha_evento") or ev["fecha_evento"] > corte.isoformat():
        ev["fecha_evento"] = corte.isoformat()
    antes = puntaje.puntuar(perfs[pid], corte)
    sim = copy.deepcopy(perfs[pid])
    sim.setdefault("eventos_clinicos", []).append({**ev, "id_evento": "EV-PREVIEW", "detalle": ev["evidencia"]})
    despues = puntaje.puntuar(sim, corte)
    return 200, {"id_paciente": pid, "evento": ev, "fuente": fuente, "transcripcion": transcripcion,
                 "categoria_actual": antes and antes.get("categoria"),
                 "categoria_propuesta": despues and despues.get("categoria"),
                 "razones_propuestas": despues and [r for r in despues["razones"] if r["factor"] == "tabla_oficial"]}


def post_explicar(pid, corte):
    d = detalle(pid, corte)
    if not d or not d["paciente"]:
        return 404, {"error": "paciente no está en la lista a esa fecha"}
    texto, fuente = explicar.explicar(d["paciente"])
    return 200, {"id_paciente": pid, "explicacion_ia": texto, "fuente": fuente}


def _motivo(p):
    """Por qué este paciente va primero, en una frase y con su fuente."""
    rz = {r["factor"]: r for r in p["razones"]}
    if p["categoria"] != p["categoria_sistema"]:
        return f'prioridad {p["categoria"]} ajustada por el equipo clínico: {p["revision"].get("motivo")}'
    if p["riesgo_vital"]:
        return f'RIESGO VITAL — {rz["riesgo_vital"]["valor"]}'
    tabla = rz.get("tabla_oficial", {}).get("valor", "")
    if p["estado_clinico"] == "descompensado" and tabla.startswith('"') and "no supera" not in tabla:
        return f'{rz["evento"]["valor"]} → {tabla} ({rz["tabla_oficial"]["fuente"]})'
    extra = " y lleva más de 1 año en lista" if p["antiguedad_mayor_1_anio"] else ""
    if p["estado_clinico"] == "descompensado":
        extra += f'; evento reciente para revisión clínica ({rz["evento"]["valor"]})'
    return f'prioridad {p["categoria"]}{extra}'


def _diferencia(a, b):
    """Por qué b va después de a, usando los mismos criterios de orden (MINSAL Ord. 536/2025)."""
    if a["categoria"] != b["categoria"]:
        return f'{b["nombre_fantasia"]} está en prioridad {b["categoria"]}; {a["nombre_fantasia"]} en {a["categoria"]}'
    if a["riesgo_vital"] != b["riesgo_vital"]:
        return f'misma prioridad, pero {a["nombre_fantasia"]} tiene alerta de riesgo vital'
    la, lb = a["lace"]["total"], b["lace"]["total"]
    if la != lb:
        return f'misma prioridad; {b["nombre_fantasia"]} tiene {la - lb} punto{"s" if la - lb != 1 else ""} LACE menos ({lb} vs {la})'
    if a["antiguedad_mayor_1_anio"] != b["antiguedad_mayor_1_anio"]:
        return f'misma prioridad, pero {a["nombre_fantasia"]} lleva más de 1 año en lista (criterio MINSAL)'
    dif = a["dias_espera"] - b["dias_espera"]
    return (f'misma prioridad {a["categoria"]}; {b["nombre_fantasia"]} lleva {dif} día{"s" if dif != 1 else ""} menos '
            f'en lista (orden de llegada)' if dif else "misma prioridad y misma fecha de ingreso")


def _fila_box(p):
    return {"id_paciente": p["id_paciente"], "nombre_fantasia": p["nombre_fantasia"], "posicion": p["posicion"],
            "categoria": p["categoria"], "diagnostico_texto": p["diagnostico_texto"], "dias_espera": p["dias_espera"],
            "riesgo_inasistencia": p["riesgo_inasistencia"], "riesgo_vital": p["riesgo_vital"], "motivo": _motivo(p),
            "accion": "contactar hoy y evaluar derivación a urgencia" if p["riesgo_vital"]
            else "confirmar asistencia por teléfono (2 inasistencias seguidas)" if p["riesgo_inasistencia"] else "citar"}


def boxes(corte, especialidad=None):
    b = box_data()
    data = lista(corte)
    cola = {}
    for p in data["pacientes"]:
        cola.setdefault(p["especialidad"], []).append(p)
    agenda = b.get("agenda", {})
    dia = max((f for f in agenda if f <= corte.isoformat()), default=None)  # último día hábil con agenda ≤ corte
    out = []
    for esp, info in sorted(b.get("especialidades", {}).items()):
        if especialidad and esp != especialidad:
            continue
        pendientes = list(cola.get(esp, []))
        asignaciones = []
        for bx in sorted((x for x in agenda.get(dia, []) if x["especialidad"] == esp), key=lambda x: x["id_box"]):
            libres = bx["capacidad"] - bx["usados"]
            pacientes = [pendientes.pop(0) for _ in range(min(libres, len(pendientes)))]
            asignaciones.append({**bx, "libres": libres, "pacientes": [_fila_box(p) for p in pacientes]})
        # alternativa: el siguiente de la lista, por si alguien no confirma; y por qué va después del último citado
        ultimo = next((a["pacientes"][-1] for a in reversed(asignaciones) if a["pacientes"]), None)
        alt = pendientes[0] if pendientes else None
        alternativa = None
        if alt:
            ref = next(p for p in cola[esp] if p["id_paciente"] == ultimo["id_paciente"]) if ultimo else None
            alternativa = {**_fila_box(alt), "por_que_despues": _diferencia(ref, alt) if ref else None}
        out.append({**info, "especialidad": esp, "dia_agenda": dia, "asignaciones": asignaciones, "alternativa": alternativa,
                    "sugeridos": [p for a in asignaciones for p in a["pacientes"]][:5]})
    return {"fecha_corte": corte.isoformat(), "dia_agenda": dia, "resumen": b.get("resumen", {}), "especialidades": out}


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
        if method == "GET" and len(partes) == 3 and partes[0] == "pacientes" and partes[2] == "historia":
            h = historia(partes[1], _fecha(qs))
            return _resp(200, h) if h else _resp(404, {"error": "paciente no existe"})
        if method == "GET" and len(partes) == 2 and partes[0] == "pacientes":
            d = detalle(partes[1], _fecha(qs))
            return _resp(200, d) if d else _resp(404, {"error": "paciente no existe"})
        if method == "POST" and partes == ["pacientes"]:
            return _resp(*post_paciente(body))
        if method == "GET" and partes == ["catalogo"]:
            return _resp(200, catalogo())
        if method == "POST" and partes == ["eventos"]:
            return _resp(*post_evento(body))
        if method == "POST" and len(partes) == 3 and partes[0] == "pacientes" and partes[2] == "revision":
            return _resp(*post_revision(partes[1], body))
        if method == "POST" and len(partes) == 3 and partes[0] == "pacientes" and partes[2] == "informe":
            return _resp(*post_informe(partes[1], body))
        if method == "POST" and len(partes) == 3 and partes[0] == "pacientes" and partes[2] == "explicar":
            return _resp(*post_explicar(partes[1], _fecha({**qs, **body})))
        if method == "GET" and partes == ["boxes"]:
            return _resp(200, boxes(_fecha(qs), qs.get("especialidad") or None))
        if method == "GET" and partes in ([], ["health"]):
            return _resp(200, {"ok": True, "pacientes": len(perfiles())})
        return _resp(404, {"error": f"ruta no encontrada: {method} {path}"})
    except Exception as e:  # nunca devolver 502 sin CORS: el front no podría leer el error
        return _resp(500, {"error": str(e)})
