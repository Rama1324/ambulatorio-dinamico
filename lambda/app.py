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
import re
import time
import uuid
from datetime import date, datetime, timedelta, timezone

import puntaje
import explicar
import importar
import informe
from modelos import Lectura, normalizar

LOCAL = os.environ.get("LOCAL") == "1"
# Fecha de referencia del dataset (2026-10-13). En la clínica: FECHA_REFERENCIA=hoy → se usa la fecha del día.
_fr = os.environ.get("FECHA_REFERENCIA", "2026-10-13")
FECHA_REFERENCIA = date.today() if _fr == "hoy" else date.fromisoformat(_fr)
TIPOS_EVENTO = {"cambio_farmaco", "control_aps", "examen_alterado", "hospitalizacion", "visita_urgencia"}
RESULTADOS_CONTACTO = {
    "citado": "Contactado: citado (sobrecupo o cupo liberado)",
    "derivado_urgencia": "Contactado: derivado a urgencia",
    "se_mantiene": "Contactado: se mantiene en lista según criterio médico",
    "no_contesta": "No contesta: reintentar",
}

_cache = {"perfiles": None, "box": None}
_mem = []  # almacenamiento en memoria para modo local
_req = {"registros": None}  # registros leídos una sola vez por solicitud


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
    _req["registros"] = None
    if LOCAL:
        _mem.append(item)
    else:
        _tabla().put_item(Item=item)


def registros():
    """Eventos, revisiones, contactos, novedades, pacientes e importaciones registrados por el equipo."""
    if _req["registros"] is not None:
        return _req["registros"]
    if LOCAL:
        items = list(_mem)
    else:
        tabla, items, kw = _tabla(), [], {}
        while True:
            r = tabla.scan(**kw)
            items += r["Items"]
            if "LastEvaluatedKey" not in r:
                break
            kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]
    _req["registros"] = items
    return items


def contactos():
    """Último contacto por paciente, con el número de intentos sin respuesta desde el último contacto efectivo."""
    out, intentos = {}, {}
    for r in sorted((r for r in registros() if r["sk"].startswith("contacto#")), key=lambda r: r["sk"]):
        c = json.loads(r["contacto"])
        pid = r["id_paciente"]
        intentos[pid] = intentos.get(pid, 0) + 1 if c["resultado"] == "no_contesta" else 0
        out[pid] = {**c, "intentos_sin_respuesta": intentos[pid]}
    return out


def citados_hoy(corte):
    """Pacientes citados con hora reservada en un box para la fecha de corte: {id_paciente: contacto}."""
    return {pid: c for pid, c in contactos().items()
            if c["resultado"] == "citado" and c.get("fecha_corte") == corte.isoformat() and c.get("hora")}


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
        e = json.loads(ev["evento"])
        if not any(x.get("id_evento") == e["id_evento"] for x in out[pid].setdefault("eventos_clinicos", [])):
            out[pid]["eventos_clinicos"].append(e)
    ult_rev = {r["id_paciente"]: json.loads(r["revision"]) for r in revisiones}
    return out, ult_rev


# ---------- lógica ----------
def _fecha(qs):
    f = (qs or {}).get("fecha_corte")
    return date.fromisoformat(f) if f else FECHA_REFERENCIA


def _posterior(s, desde_corte, desde_ts):
    """¿La señal ocurrió o se registró después de la revisión? (fecha clínica > corte revisado, o registro posterior)."""
    return s["fecha"] > desde_corte or bool(s.get("registrado") and s["registrado"] > desde_ts)


def _enriquecer(r, perfil, revision, pos_ant, corte=None, contacto=None):
    pac, le = perfil["paciente"], perfil["lista_espera"]
    corte_iso = (corte or FECHA_REFERENCIA).isoformat()
    out = {
        "id_paciente": r["id_paciente"],
        "nombre_fantasia": pac["nombre_fantasia"],
        "edad": pac["edad"],
        "sexo": pac["sexo"],
        "comuna": pac["comuna"],
        "comorbilidades": pac.get("comorbilidades", []),
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
        "grupo_proteccion": r.get("grupo_proteccion"),
        "acg": r.get("acg"),
        "razones": r["razones"],
        "explicacion_ia": None,
        "estado_revision": "pendiente",
        "revision_sugerida": [],
        "contactar_hoy": r["riesgo_vital"],
        "contacto": None,
    }
    senales = r.get("senales", [])
    # Una revisión vale solo para lo que el equipo vio: desde la fecha de corte en que revisó y hasta que llegue
    # un evento nuevo. Un evento posterior invalida la confirmación o el ajuste y vuelve a pedir revisión.
    if revision and revision.get("fecha_corte", "0000") <= corte_iso:
        nuevas = [s for s in senales if _posterior(s, revision.get("fecha_corte", ""), revision.get("fecha", ""))]
        out["revision"] = revision
        if nuevas:
            out["estado_revision"] = "requiere_revision"
            out["revision_sugerida"] = nuevas
            out["revision_vencida_por"] = nuevas[-1]["motivo"]
        else:
            out["estado_revision"] = "ajustado" if revision["accion"] == "ajustar" else "confirmado"
            if revision.get("categoria_ajustada"):
                out["categoria"] = revision["categoria_ajustada"]  # el equipo clínico decide
    else:
        out["revision_sugerida"] = senales
    # 'Contactar hoy' se reconoce con un contacto registrado después de la última descompensación (salvo 'no contesta').
    if contacto and contacto.get("fecha_corte", "0000") <= corte_iso:
        out["contacto"] = contacto
        if r["riesgo_vital"] and contacto["resultado"] != "no_contesta" and (
                contacto["fecha_corte"] >= (r.get("fecha_descompensacion") or "") and
                contacto["fecha"] >= (r.get("registro_descompensacion") or "")):
            out["contactar_hoy"] = False
    return out


def lista(corte, especialidad=None, perfs=None, revs=None):
    if perfs is None:
        perfs, revs = perfiles_combinados()
    vals = list(perfs.values())
    activos, excluidos = puntaje.priorizar(vals, corte, especialidad)
    ant, _ = puntaje.priorizar(vals, corte - timedelta(days=14), especialidad)
    pos_ant = {r["id_paciente"]: r["posicion"] for r in ant}
    cont = contactos()
    pacientes = [_enriquecer(r, perfs[r["id_paciente"]], revs.get(r["id_paciente"]), pos_ant.get(r["id_paciente"]), corte,
                             cont.get(r["id_paciente"])) for r in activos]
    # el equipo clínico decide: si ajustó la categoría, esa manda en el orden (mismos criterios MINSAL)
    pacientes.sort(key=puntaje.clave_orden)
    for i, p in enumerate(pacientes, 1):
        p["posicion"] = i
    exc = [{"id_paciente": r["id_paciente"], "motivo": r["motivo"], "fecha": r.get("fecha"),
            "nombre_fantasia": perfs[r["id_paciente"]]["paciente"].get("nombre_fantasia"),
            "especialidad": perfs[r["id_paciente"]]["lista_espera"].get("especialidad"),
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
    fechas, f = [], corte - timedelta(days=14 * 14)  # últimas 28 semanas
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
        "registrado": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "usuario": body.get("usuario", "equipo clínico"),
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
            "origenes": sorted({p["lista_espera"]["origen_derivacion"] for p in perfiles().values()}),
            "charlson": [{"condicion": n, "peso": p} for n, p in puntaje.CONDICIONES_CHARLSON],
            "grupos_proteccion": sorted(puntaje.GRUPOS_PROTECCION),
            "acg": [{"nivel": k, "texto": v} for k, v in puntaje.ACG_NIVELES.items()],
            "resultados_contacto": [{"valor": k, "texto": v} for k, v in RESULTADOS_CONTACTO.items()]}


def post_novedad(pid, body):
    """Novedad registrada por el equipo: comorbilidad, cambio de diagnóstico o egreso (fallecimiento / atención)."""
    perfs, _ = perfiles_combinados()
    if pid not in perfs:
        return 404, {"error": "paciente no existe"}
    tipo = body.get("tipo")
    corte = date.fromisoformat(body.get("fecha_corte") or FECHA_REFERENCIA.isoformat())
    fecha = body.get("fecha") or corte.isoformat()
    p = copy.deepcopy(perfs[pid])
    cat = {d["diagnostico_cie10"]: d for d in catalogo()["diagnosticos"]}
    if tipo == "comorbilidad":
        cond, cie = body.get("condicion"), body.get("cie10")
        if cond in puntaje.PESO_CHARLSON:
            nueva = {"condicion": cond, "nombre": cond, "fecha": fecha}
        elif cie in cat:
            nueva = {"cie10": cie, "nombre": f'{cie} {cat[cie]["diagnostico_texto"]}', "fecha": fecha}
        else:
            return 400, {"error": "indique 'condicion' (lista de Charlson) o 'cie10' del catálogo"}
        p["paciente"].setdefault("comorbilidades", []).append(nueva)
        texto = f'comorbilidad registrada: {nueva["nombre"]}'
    elif tipo == "diagnostico":
        dx = cat.get(body.get("cie10"))
        if not dx:
            return 400, {"error": "cie10 debe estar en el catálogo"}
        p["lista_espera"].update({k: dx[k] for k in ("especialidad", "sub_especialidad", "diagnostico_cie10", "diagnostico_texto")})
        texto = f'diagnóstico cambiado a {dx["diagnostico_cie10"]} {dx["diagnostico_texto"]}'
    elif tipo == "riesgo":
        grupo, acg = body.get("grupo_proteccion") or None, body.get("acg") or None
        if grupo and grupo not in puntaje.GRUPOS_PROTECCION or acg and acg not in puntaje.ACG_NIVELES:
            return 400, {"error": "grupo_proteccion o acg no válido"}
        p["paciente"]["grupo_proteccion"], p["paciente"]["acg"] = grupo, acg
        texto = "datos de riesgo: " + ", ".join(x for x in [grupo and f"grupo {grupo}", acg and f"ACG {acg}"] if x) if grupo or acg else "datos de riesgo borrados"
    elif tipo == "fallecimiento":
        p["paciente"].update({"fallecido": True, "fecha_defuncion": fecha})
        p["lista_espera"]["estado"] = "fallecido"
        texto = f"fallecimiento el {fecha} (causal de egreso 9)"
    elif tipo == "atendido":
        p["lista_espera"].update({"estado": "atendido", "fecha_atencion": fecha})
        texto = f"atendido en consulta nueva de especialidad el {fecha}: sale de la lista"
    else:
        return 400, {"error": "tipo debe ser comorbilidad, diagnostico, riesgo, fallecimiento o atendido"}
    p["eventos_clinicos"] = [e for e in p.get("eventos_clinicos", []) if not e.get("id_evento", "").startswith("EV-DEMO")]
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    guardar({"id_paciente": pid, "sk": "paciente#", "perfil": json.dumps(p, ensure_ascii=False, default=str)})
    guardar({"id_paciente": pid, "sk": f"novedad#{ahora}", "novedad": json.dumps(
        {"tipo": tipo, "detalle": texto, "usuario": body.get("usuario", "equipo clínico"), "fecha": ahora}, ensure_ascii=False)})
    fila = next((x for x in lista(corte)["pacientes"] if x["id_paciente"] == pid), None)
    return 200, {"id_paciente": pid, "mensaje": texto, "paciente": fila, "en_lista": fila is not None}


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
                     "fecha_defuncion": None,
                     "grupo_proteccion": body.get("grupo_proteccion") if body.get("grupo_proteccion") in puntaje.GRUPOS_PROTECCION else None,
                     "acg": body.get("acg") if body.get("acg") in puntaje.ACG_NIVELES else None},
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


def post_importar(body):
    """Revisa (confirmar=false) o carga (confirmar=true) archivos Excel/CSV con datos del hospital."""
    archivos = body.get("archivos") or []
    if not archivos:
        return 400, {"error": "envíe 'archivos': [{nombre, contenido_base64}]"}
    informe, datos = importar.procesar(archivos)
    existentes, _ = perfiles_combinados()
    cat = {d["diagnostico_cie10"]: d for d in catalogo()["diagnosticos"]}
    perfs, agenda, resumen, avisos = importar.combinar(datos, existentes, cat)
    out = {"informe": informe, "resumen": resumen, "avisos": avisos, "cargado": False}
    if body.get("confirmar"):
        for pid, p in perfs.items():
            guardar({"id_paciente": pid, "sk": "paciente#", "perfil": json.dumps(p, ensure_ascii=False, default=str)})
        for a in agenda:
            guardar({"id_paciente": "_agenda", "sk": f'agenda#{a["fecha"]}#{a["id_box"]}', "fila": json.dumps(a, ensure_ascii=False)})
        out["cargado"] = True
    return 200, out


def agenda_combinada():
    """Agenda de box.json + bloques importados (un bloque importado reemplaza al mismo box ese día)."""
    agenda = {f: list(filas) for f, filas in box_data().get("agenda", {}).items()}
    for r in registros():
        if r["sk"].startswith("agenda#"):
            a = json.loads(r["fila"])
            dia = [x for x in agenda.get(a["fecha"], []) if x["id_box"] != a["id_box"]]
            agenda[a["fecha"]] = dia + [{k: v for k, v in a.items() if k != "fecha"}]
    return agenda


def post_revision(pid, body):
    if pid not in perfiles_combinados()[0]:
        return 404, {"error": "paciente no existe"}
    accion = body.get("accion")
    if accion not in ("confirmar", "ajustar"):
        return 400, {"error": "accion debe ser 'confirmar' o 'ajustar'"}
    if accion == "ajustar" and (body.get("categoria_ajustada") not in puntaje.ORDEN_CAT or not body.get("motivo")):
        return 400, {"error": "ajustar requiere categoria_ajustada (alta|media|baja) y motivo"}
    corte = date.fromisoformat(body.get("fecha_corte") or FECHA_REFERENCIA.isoformat())
    previa = next((p for p in lista(corte)["pacientes"] if p["id_paciente"] == pid), None)
    rev = {"accion": accion, "categoria_ajustada": body.get("categoria_ajustada") if accion == "ajustar" else None,
           "categoria_sistema": previa and previa["categoria_sistema"],  # para medir concordancia (kappa)
           "motivo": body.get("motivo"), "fecha_corte": corte.isoformat(),
           "usuario": body.get("usuario", "equipo clínico"), "fecha": datetime.now(timezone.utc).isoformat(timespec="microseconds")}
    guardar({"id_paciente": pid, "sk": f"revision#{rev['fecha']}", "revision": json.dumps(rev, ensure_ascii=False)})
    return 200, {"id_paciente": pid, "revision": rev}


def post_contacto(pid, body):
    """Registra el contacto con un paciente 'contactar hoy' (reconoce la alerta, con motivo y trazabilidad)."""
    if pid not in perfiles_combinados()[0]:
        return 404, {"error": "paciente no existe"}
    if body.get("resultado") not in RESULTADOS_CONTACTO:
        return 400, {"error": f"resultado debe ser uno de {sorted(RESULTADOS_CONTACTO)}"}
    corte = date.fromisoformat(body.get("fecha_corte") or FECHA_REFERENCIA.isoformat())
    c = {"resultado": body["resultado"], "texto": RESULTADOS_CONTACTO[body["resultado"]], "nota": body.get("nota", ""),
         "fecha_corte": corte.isoformat(), "usuario": body.get("usuario", "equipo clínico"),
         "fecha": datetime.now(timezone.utc).isoformat(timespec="microseconds")}
    if body["resultado"] == "citado" and body.get("hora"):
        # reserva la hora: ningún otro paciente puede recibir la misma hora en el mismo box ese día
        ocupada = next((pid2 for pid2, x in citados_hoy(corte).items() if pid2 != pid and x.get("id_box") == body.get("id_box")
                        and x.get("hora") == body["hora"]), None)
        if ocupada:
            return 409, {"error": f"La hora {body['hora']} del {body.get('id_box')} ya fue reservada para otro paciente"}
        c.update({"hora": body["hora"], "hora_fin": body.get("hora_fin"), "id_box": body.get("id_box"),
                  "texto": f"Citado hoy {body['hora']}" + (f" – {body['hora_fin']} h" if body.get("hora_fin") else " h") +
                           (f" · {body['id_box'].replace('BOX-', 'Box ')}" if body.get("id_box") else "")})
    guardar({"id_paciente": pid, "sk": f"contacto#{c['fecha']}", "contacto": json.dumps(c, ensure_ascii=False)})
    fila = next((p for p in lista(corte)["pacientes"] if p["id_paciente"] == pid), None)
    return 200, {"id_paciente": pid, "contacto": c, "paciente": fila}


def _kappa(pares, cats=("alta", "media", "baja")):
    """Kappa de Cohen entre la categoría propuesta por el sistema y la decisión del equipo clínico."""
    n = len(pares)
    if not n:
        return None
    po = sum(a == b for a, b in pares) / n
    pe = sum((sum(a == c for a, _ in pares) / n) * (sum(b == c for _, b in pares) / n) for c in cats)
    return round((po - pe) / (1 - pe), 2) if pe < 1 else 1.0


def kpis(corte):
    """KPIs del hospital: cobertura con criterio común, reevaluación < 72 h tras un evento, concordancia (kappa ≥ 0,70)."""
    data = lista(corte)
    regs = registros()
    revs = [json.loads(r["revision"]) for r in regs if r["sk"].startswith("revision#")]
    pares = [(r["categoria_sistema"], r.get("categoria_ajustada") or r["categoria_sistema"]) for r in revs if r.get("categoria_sistema")]
    eventos = [json.loads(r["evento"]) for r in regs if r["sk"].startswith("evento#")]
    vitales = [p for p in data["pacientes"] if p["riesgo_vital"]]
    return {
        "fecha_corte": corte.isoformat(),
        "cobertura": {"evaluados": data["total"], "en_espera": data["total"], "pct": 100.0 if data["total"] else 0,
                      "criterio": "Tabla SSMSO 2025 (HLF) + orden MINSAL Ord. 536/2025, el mismo para toda la lista"},
        "reevaluacion": {"eventos_registrados": len(eventos), "reevaluados_menos_72h": len(eventos),
                         "detalle": "Cada evento recalcula la lista en el mismo momento en que se registra (milisegundos)."},
        "concordancia": {"revisiones": len(pares), "acuerdos": sum(a == b for a, b in pares), "kappa": _kappa(pares),
                         "meta": 0.70, "suficiente": len(pares) >= 10},
        "alertas": {"riesgo_vital": len(vitales), "contactados": sum(not p["contactar_hoy"] for p in vitales),
                    "pendientes": sum(p["contactar_hoy"] for p in vitales),
                    "revision_sugerida": sum(bool(p["revision_sugerida"]) for p in data["pacientes"])},
        "egresos": {"fallecidos": sum(e["motivo"] == "fallecido" for e in data["excluidos"]),
                    "atendidos": sum(e["motivo"] == "atendido" for e in data["excluidos"])},
    }


def post_informe(pid, body):
    """Lee un informe (texto o foto con Amazon Textract), PROPONE eventos validados con Pydantic y no guarda nada:
    el equipo clínico elige y confirma con POST /eventos."""
    perfs, _ = perfiles_combinados()
    if pid not in perfs:
        return 404, {"error": "paciente no existe"}
    corte = date.fromisoformat(body.get("fecha_corte") or FECHA_REFERENCIA.isoformat())
    texto = (body.get("texto") or "").strip()
    try:
        if texto:
            lectura = Lectura(origen="texto", texto=texto)
        elif body.get("imagen_base64"):
            lectura = informe.leer_foto(body["imagen_base64"])
        else:
            return 400, {"error": "falta 'texto' o 'imagen_base64' del informe"}
    except Exception as e:
        print(f"Textract no pudo leer la foto: {e}")
        return 200, {"id_paciente": pid, "eventos": [], "evento": None,
                     "mensaje": "No se pudo leer la foto con Amazon Textract (OCR). Verifique la conexión a AWS o "
                                "escriba el texto del informe."}
    eventos, descartados, avisos = informe.analizar(lectura, corte)

    # Identidad: el error más grave sería registrar el evento en otro paciente
    pac = perfs[pid]["paciente"]
    doc = normalizar(lectura.texto)
    menciona = normalizar(pac["nombre_fantasia"]) in doc or normalizar(pid) in doc
    otros = sorted({o for o in re.findall(r"pac-[a-z]+-\d{3,}", doc) if o != normalizar(pid)})
    if otros:
        avisos.insert(0, f"¡Atención! El documento menciona a otro paciente ({', '.join(o.upper() for o in otros)}). No lo registre aquí.")
    elif lectura.origen == "foto" and not menciona:
        avisos.insert(0, f"El documento no menciona a {pac['nombre_fantasia']} ni su ID: confirme que corresponde a este paciente.")

    antes = puntaje.puntuar(perfs[pid], corte)
    propuestas = []
    for ev in eventos:
        e = ev.model_dump(mode="json")
        e["fecha_evento"] = e["fecha_evento"] or corte.isoformat()
        sim = copy.deepcopy(perfs[pid])
        sim.setdefault("eventos_clinicos", []).append({**e, "id_evento": "EV-PREVIEW", "detalle": e["evidencia"]})
        despues = puntaje.puntuar(sim, corte)
        propuestas.append({**e, "categoria_propuesta": despues and despues.get("categoria"),
                           "razones_propuestas": despues and [r for r in despues["razones"] if r["factor"] == "tabla_oficial"]})
    out = {"id_paciente": pid, "lectura": lectura.resumen(), "transcripcion": lectura.texto if lectura.origen == "foto" else None,
           "eventos": propuestas, "evento": propuestas[0] if propuestas else None, "descartados": descartados,
           "advertencias": avisos, "identidad_en_documento": menciona, "otro_paciente": bool(otros),
           "categoria_actual": antes and antes.get("categoria"),
           "fuente": propuestas[0]["detectado_por"] if propuestas else "reglas"}
    if propuestas:
        out["categoria_propuesta"] = propuestas[0]["categoria_propuesta"]
        out["razones_propuestas"] = propuestas[0]["razones_propuestas"]
    else:
        out["mensaje"] = ("No encontré en el informe un evento del registro (urgencia, hospitalización, examen alterado, "
                          "cambio de fármaco o control APS). Puede registrarlo manualmente.")
    return 200, out


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
            "contactar_hoy": p["contactar_hoy"], "contacto": p["contacto"],
            "accion": "contactar hoy y evaluar derivación a urgencia" if p["contactar_hoy"]
            else (p["contacto"]["texto"] if p["riesgo_vital"] and p["contacto"] else None)
            or ("confirmar asistencia por teléfono (2 inasistencias seguidas)" if p["riesgo_inasistencia"] else "citar")}


def _horas_libres(bx, n):
    """Horas sugeridas para n pacientes en un bloque: el bloque se divide por su capacidad (ej. 08:30–13:30 con 10 cupos
    = una hora cada 30 min). El registro informa cuántas horas quedan libres, no cuáles: se sugieren las últimas del bloque."""
    try:
        ini, fin = (datetime.strptime(x.strip(), "%H:%M") for x in bx.get("bloque", "").split("-"))
        minutos = max(1, int((fin - ini).total_seconds() // 60) // max(1, bx["capacidad"]))
        desde = [ini + timedelta(minutes=minutos * (bx["usados"] + i)) for i in range(n)]
        return {"minutos": minutos, "horas": [d.strftime("%H:%M") for d in desde],
                "hasta": [(d + timedelta(minutes=minutos)).strftime("%H:%M") for d in desde]}
    except (ValueError, KeyError):
        return {"minutos": None, "horas": [None] * n, "hasta": [None] * n}


def boxes(corte, especialidad=None):
    b = box_data()
    data = lista(corte)
    cola = {}
    for p in data["pacientes"]:
        cola.setdefault(p["especialidad"], []).append(p)
    agenda = agenda_combinada()
    dia = max((f for f in agenda if f <= corte.isoformat()), default=None)  # último día hábil con agenda ≤ corte
    citados = citados_hoy(corte)
    out = []
    for esp, info in sorted(b.get("especialidades", {}).items()):
        if especialidad and esp != especialidad:
            continue
        por_id = {p["id_paciente"]: p for p in cola.get(esp, [])}
        pendientes = [p for p in cola.get(esp, []) if p["id_paciente"] not in citados]  # los citados ya tienen su hora
        asignaciones = []
        for bx in sorted((x for x in agenda.get(dia, []) if x["especialidad"] == esp), key=lambda x: x["id_box"]):
            libres = bx["capacidad"] - bx["usados"]
            todas = _horas_libres(bx, libres)
            # 1) horas ya reservadas (citados) quedan fijas; 2) el resto se propone en el orden de la lista
            fijas = [(pid, c) for pid, c in citados.items() if c.get("id_box") == bx["id_box"] and pid in por_id]
            tomadas = {c["hora"] for _, c in fijas}
            filas = [{**_fila_box(por_id[pid]), "hora": c["hora"], "hora_fin": c.get("hora_fin"), "citado": True} for pid, c in fijas]
            libres_h = [(h, f) for h, f in zip(todas["horas"], todas["hasta"]) if h not in tomadas]
            for h, f in libres_h:
                if not pendientes:
                    break
                filas.append({**_fila_box(pendientes.pop(0)), "hora": h, "hora_fin": f, "citado": False})
            filas.sort(key=lambda x: x["hora"] or "")
            asignaciones.append({**bx, "libres": libres, "libres_sin_citar": libres - len(fijas),
                                 "minutos_por_hora": todas["minutos"], "pacientes": filas})
        # alternativa: el siguiente de la lista, por si alguien no confirma; y por qué va después del último citado
        ultimo = next((a["pacientes"][-1] for a in reversed(asignaciones) if a["pacientes"]), None)
        alt = pendientes[0] if pendientes else None
        alternativa = None
        if alt:
            ref = next(p for p in cola[esp] if p["id_paciente"] == ultimo["id_paciente"]) if ultimo else None
            alternativa = {**_fila_box(alt), "por_que_despues": _diferencia(ref, alt) if ref else None}
        # pacientes con riesgo vital que no alcanzan cupo hoy: hay que gestionarlos igual (no esperar)
        sin_cupo = [_fila_box(p) for p in pendientes if p["riesgo_vital"]]
        out.append({**info, "especialidad": esp, "dia_agenda": dia, "asignaciones": asignaciones, "alternativa": alternativa,
                    "cupos_libres_hoy": sum(a["libres"] for a in asignaciones), "vitales_sin_cupo": sin_cupo,
                    "sugeridos": [p for a in asignaciones for p in a["pacientes"]][:5]})
    cupo = {p["id_paciente"]: {"id_box": a["id_box"], "hora": p["hora"], "hora_fin": p["hora_fin"], "citado": p["citado"]}
            for e in out for a in e["asignaciones"] for p in a["pacientes"]}
    # mapa de todos los box del hospital ese día (los que no aparecen en la agenda no tienen bloque asignado)
    del_dia = {x["id_box"]: x for x in agenda.get(dia, [])}
    asignados = {a["id_box"]: len(a["pacientes"]) for e in out for a in e["asignaciones"]}
    todos = sorted({x["id_box"] for filas in agenda.values() for x in filas})
    mapa = [{"id_box": i, **({**del_dia[i], "libres": del_dia[i]["capacidad"] - del_dia[i]["usados"],
                              "pacientes_asignados": asignados.get(i, 0)} if i in del_dia else {"especialidad": None})}
            for i in todos]
    return {"fecha_corte": corte.isoformat(), "dia_agenda": dia, "resumen": b.get("resumen", {}), "especialidades": out,
            "cupo_por_paciente": cupo, "mapa": mapa}


def duracion_consulta(especialidad):
    """Minutos promedio de atención real por especialidad (citaciones del registro con estado 'asistió')."""
    mins = [c["minutos_atencion_real"] for p in perfiles().values() for c in p.get("citaciones", [])
            if c.get("estado_cita") == "asistio" and c.get("minutos_atencion_real") and c.get("especialidad") == especialidad]
    if not mins:
        mins = [c["minutos_atencion_real"] for p in perfiles().values() for c in p.get("citaciones", [])
                if c.get("estado_cita") == "asistio" and c.get("minutos_atencion_real")]
    return (round(sum(mins) / len(mins)) if mins else 30), len(mins)


def disponible(corte, especialidad, cupos=None, desde=None, hasta=None):
    """Médico con tiempo libre: a quiénes atender, en el orden de la lista, sin repetir a quienes ya tienen hora hoy."""
    if not especialidad:
        return 400, {"error": "indique la especialidad"}
    dur, n_citas = duracion_consulta(especialidad)
    inicio = None
    if desde and hasta:
        h1, h2 = datetime.strptime(desde, "%H:%M"), datetime.strptime(hasta, "%H:%M")
        minutos = int((h2 - h1).total_seconds() // 60)
        if minutos <= 0:
            return 400, {"error": "la hora de término debe ser posterior a la de inicio"}
        cupos, inicio = max(1, minutos // dur), h1
    cupos = max(1, min(int(cupos or 5), 40))
    ya_con_hora = {**boxes(corte, especialidad)["cupo_por_paciente"], **citados_hoy(corte)}
    data = lista(corte, especialidad)
    candidatos = [p for p in data["pacientes"] if p["id_paciente"] not in ya_con_hora]
    elegidos, reservas = candidatos[:cupos], candidatos[cupos:cupos + 3]
    filas = []
    for i, p in enumerate(elegidos):
        f = _fila_box(p)
        if inicio:
            f["hora"] = (inicio + timedelta(minutes=dur * i)).strftime("%H:%M")
            f["hora_fin"] = (inicio + timedelta(minutes=dur * (i + 1))).strftime("%H:%M")
        filas.append(f)
    ref = elegidos[-1] if elegidos else None
    return 200, {"fecha_corte": corte.isoformat(), "especialidad": especialidad, "cupos": cupos,
                 "duracion_min": dur, "duracion_fuente": f"promedio de {n_citas} consultas reales del registro",
                 "excluidos_con_hora_hoy": len(ya_con_hora), "en_espera": data["total"],
                 "pacientes": filas,
                 "reservas": [{**_fila_box(p), "por_que_despues": _diferencia(ref, p) if ref else None} for p in reservas]}


# ---------- HTTP ----------
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "content-type",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS", "Content-Type": "application/json"}


def _resp(status, body):
    return {"statusCode": status, "headers": CORS, "body": json.dumps(body, ensure_ascii=False, default=str)}


def handler(event, context=None):
    _req["registros"] = None  # leer DynamoDB una vez por solicitud
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
        if method == "POST" and partes == ["importar"]:
            return _resp(*post_importar(body))
        if method == "GET" and len(partes) == 2 and partes[0] == "plantillas" and partes[1] in importar.TABLAS:
            return {"statusCode": 200, "headers": {**CORS, "Content-Type": "text/csv; charset=utf-8",
                                                   "Content-Disposition": f'attachment; filename="plantilla_{partes[1]}.csv"'},
                    "body": importar.plantilla_csv(partes[1])}
        if method == "POST" and partes == ["eventos"]:
            return _resp(*post_evento(body))
        if method == "POST" and len(partes) == 3 and partes[0] == "pacientes" and partes[2] == "revision":
            return _resp(*post_revision(partes[1], body))
        if method == "POST" and len(partes) == 3 and partes[0] == "pacientes" and partes[2] == "contacto":
            return _resp(*post_contacto(partes[1], body))
        if method == "GET" and partes == ["disponible"]:
            return _resp(*disponible(_fecha(qs), qs.get("especialidad"), qs.get("cupos"), qs.get("desde"), qs.get("hasta")))
        if method == "GET" and partes == ["kpis"]:
            return _resp(200, kpis(_fecha(qs)))
        if method == "POST" and len(partes) == 3 and partes[0] == "pacientes" and partes[2] == "novedad":
            return _resp(*post_novedad(partes[1], body))
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
