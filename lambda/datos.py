"""Datos: fecha de trabajo, lectura del registro (S3 o data/ local) y de lo que registra el equipo (DynamoDB o memoria).
Cada registro del equipo es un ítem pk=id_paciente, sk="<tipo>#<fecha>" (evento, revision, contacto, decision, gestion,
orden, evaluacion, novedad) o sk="paciente#" (perfil ingresado o modificado)."""
import copy
import json
import os
from datetime import date, datetime, timedelta, timezone

LOCAL = os.environ.get("LOCAL") == "1"
# Fecha de trabajo. FECHA_REFERENCIA=hoy → fecha real de Chile (versión publicada); AAAA-MM-DD → simulación
# (el dataset sintético llega al 2026-10-13).
_FR = os.environ.get("FECHA_REFERENCIA", "2026-10-13")
TIEMPO_REAL = _FR == "hoy"


def hoy():
    if not TIEMPO_REAL:
        return date.fromisoformat(_FR)
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Santiago")).date()
    except Exception:  # sin base de zonas horarias: Chile continental en horario de verano (UTC-3)
        return (datetime.now(timezone.utc) - timedelta(hours=3)).date()


_cache = {"perfiles": None}
_mem = []  # almacenamiento en memoria para modo local
_req = {"registros": None}  # registros leídos una sola vez por solicitud


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


def _ultimo_por_paciente(prefijo, campo):
    out = {}
    for r in sorted((r for r in registros() if r["sk"].startswith(prefijo)), key=lambda r: r["sk"]):
        out[r["id_paciente"]] = json.loads(r[campo])
    return out


def decisiones():
    """Última decisión clínica por paciente."""
    return _ultimo_por_paciente("decision#", "decision")


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


def nueva_solicitud():
    """Cada solicitud HTTP vuelve a leer los registros (una sola vez)."""
    _req["registros"] = None


def ahora():
    """Marca de tiempo UTC con microsegundos: ordena los registros y dice qué se registró después de qué."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def guardar_evento(pid, ev):
    guardar({"id_paciente": pid, "sk": f"evento#{ev['fecha_evento']}#{ev['id_evento']}", "evento": json.dumps(ev, ensure_ascii=False)})


def fecha_de(qs):
    """Fecha de corte de la consulta o del cuerpo de la solicitud; si no viene, hoy."""
    f = (qs or {}).get("fecha_corte")
    return date.fromisoformat(f) if f else hoy()


def fecha_valida(valor, corte, campo="fecha"):
    """Fecha ISO real, no posterior a la fecha de corte ni anterior al año 2000. Devuelve (fecha_iso, error)."""
    try:
        f = date.fromisoformat(str(valor))
    except (TypeError, ValueError):
        return None, f"{campo} inválida: '{valor}' (formato AAAA-MM-DD)"
    if f > corte:
        return None, f"{campo} {f} es posterior a la fecha de hoy ({corte})"
    if f.year < 2000:
        return None, f"{campo} {f} no es plausible"
    return f.isoformat(), None


def posterior(s, desde_corte, desde_ts):
    """¿La señal ocurrió o se registró después de la revisión? (fecha clínica > corte revisado, o registro posterior)."""
    return s["fecha"] > desde_corte or bool(s.get("registrado") and s["registrado"] > desde_ts)


# Fecha en que se extrajo el registro del hospital que se cargó (el dataset sintético es al 2026-10-13)
REGISTRO_AL = os.environ.get("REGISTRO_AL", "2026-10-13")


def datos_hasta():
    """Fecha del último dato del registro cargado (eventos, mediciones o citas): hasta dónde llega la información."""
    if "datos_hasta" not in _cache:
        fechas = [x.get(k) for p in perfiles().values() for lista_, k in (("eventos_clinicos", "fecha_evento"),
                  ("mediciones", "fecha_medicion"), ("citaciones", "fecha_cita")) for x in p.get(lista_, [])]
        fechas = [f for f in fechas if f]
        _cache["datos_hasta"] = max(fechas) if fechas else hoy().isoformat()
    return _cache["datos_hasta"]


def gestiones():
    return _ultimo_por_paciente("gestion#", "gestion")


def ajustes_orden():
    """Último ajuste manual de posición por paciente (un registro con 'quitar' lo deshace)."""
    out = {}
    for pid, a in _ultimo_por_paciente("orden#", "orden").items():
        if not a.get("quitar"):
            out[pid] = a
    return out


def evaluaciones():
    return _ultimo_por_paciente("evaluacion#", "evaluacion")


def evaluaciones_por_paciente():
    """Todas las evaluaciones de cada paciente, la más reciente primero (cada fecha de corte usa la vigente)."""
    out = {}
    for r in sorted((r for r in registros() if r["sk"].startswith("evaluacion#")), key=lambda r: r["sk"], reverse=True):
        out.setdefault(r["id_paciente"], []).append(json.loads(r["evaluacion"]))
    return out
