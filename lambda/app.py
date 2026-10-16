"""API Ambulatorio Dinámico HLF — una sola Lambda detrás de API Gateway HTTP API. Este archivo solo enruta (ver contrato.md):

  datos.py            fecha de trabajo, registro del hospital (S3) y registros del equipo (DynamoDB)
  catalogo.py         vocabularios cerrados y catálogo del front
  lista.py            lista priorizada, ficha, historia y estadísticas
  acciones.py         lo que registra el equipo clínico (eventos, revisiones, contactos, decisiones, gestión, ajustes)
  ingreso.py          ingreso de pacientes y carga de archivos
  lectura_informe.py  lectura de informes (texto o foto) con IA
  indicadores.py      KPIs
  evaluacion_ia.py    algoritmo con rúbrica (ALGORITMO=rubrica) y barrido nocturno

Modo local: LOCAL=1 y DATA_DIR=ruta a data/ (lee perfiles.json, guarda en memoria).
Modo AWS:   BUCKET, PERFILES_KEY, TABLE (DynamoDB pk=id_paciente, sk=texto).
"""
import json

import datos
import importar
import informe  # noqa: F401  (los tests lo usan como app.informe)
import puntaje  # noqa: F401  (los tests lo usan como app.puntaje)
from acciones import post_decision, post_evento, post_contacto, post_gestion, post_novedad, post_orden, post_revision
from catalogo import catalogo
from datos import evaluaciones, fecha_de, hoy, perfiles, perfiles_combinados, registros  # noqa: F401
from evaluacion_ia import _llm, algoritmo_activo, barrido, evaluar_y_guardar  # noqa: F401  (_llm: los tests inyectan un ClienteFalso)
from indicadores import _kappa, kpis  # noqa: F401
from ingreso import normalizar_rut, post_importar, post_paciente  # noqa: F401
from lectura_informe import post_informe
from lista import _enriquecer, detalle, estadisticas, historia, lista, post_explicar  # noqa: F401

CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "content-type",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS", "Content-Type": "application/json"}

# POST /pacientes/{id}/<accion>: función que recibe (id, body)
ACCIONES_PACIENTE = {"revision": post_revision, "contacto": post_contacto, "decision": post_decision, "gestion": post_gestion,
                     "orden": post_orden, "novedad": post_novedad, "informe": post_informe}


def _evaluaciones_de(pid):
    return sorted((json.loads(r["evaluacion"]) for r in registros() if r["id_paciente"] == pid and r["sk"].startswith("evaluacion#")),
                  key=lambda e: e["fecha"], reverse=True)


def barrido_handler(event, context=None):
    """Punto de entrada de la función de barrido (EventBridge Scheduler)."""
    datos.nueva_solicitud()
    return barrido(limite=int((event or {}).get("limite", 400)), en_paralelo=int((event or {}).get("en_paralelo", 3)))


def _resp(status, body):
    return {"statusCode": status, "headers": CORS, "body": json.dumps(body, ensure_ascii=False, default=str)}


def _rutear(method, partes, qs, body):
    if method == "OPTIONS":
        return 200, {}
    if method == "GET" and partes in ([], ["health"]):
        return 200, {"ok": True, "pacientes": len(perfiles()), "fecha_hoy": hoy().isoformat(),
                     "modo": "tiempo_real" if datos.TIEMPO_REAL else "simulacion", "datos": "sinteticos",
                     "datos_hasta": datos.datos_hasta(), "registro_al": datos.REGISTRO_AL}
    if method == "GET" and partes == ["pacientes"]:
        return 200, lista(fecha_de(qs), qs.get("especialidad") or None)
    if method == "GET" and partes == ["catalogo"]:
        return 200, catalogo()
    if method == "GET" and partes == ["estadisticas"]:
        return 200, estadisticas(fecha_de(qs), qs.get("especialidad") or None)
    if method == "GET" and partes == ["kpis"]:
        return 200, kpis(fecha_de(qs), qs.get("especialidad") or None)
    if method == "POST" and partes == ["pacientes"]:
        return post_paciente(body)
    if method == "POST" and partes == ["importar"]:
        return post_importar(body)
    if method == "POST" and partes == ["eventos"]:
        return post_evento(body)

    if len(partes) == 2 and partes[0] == "pacientes" and method == "GET":
        d = detalle(partes[1], fecha_de(qs))
        return (200, d) if d else (404, {"error": "paciente no existe"})
    if len(partes) == 3 and partes[0] == "pacientes":
        pid, sub = partes[1], partes[2]
        if method == "GET" and sub == "historia":
            h = historia(pid, fecha_de(qs), qs.get("especialidad") or None)
            return (200, h) if h else (404, {"error": "paciente no existe"})
        if method == "GET" and sub == "evaluaciones":
            return 200, {"id_paciente": pid, "evaluaciones": _evaluaciones_de(pid), "algoritmo_activo": algoritmo_activo()}
        if method == "POST" and sub in ACCIONES_PACIENTE:
            return ACCIONES_PACIENTE[sub](pid, body)
        if method == "POST" and sub == "explicar":
            return post_explicar(pid, fecha_de({**qs, **body}))
        if method == "POST" and sub == "evaluar":
            if algoritmo_activo() != "rubrica":
                return 409, {"error": "el algoritmo con rúbrica no está activo (ALGORITMO=reglas)", "algoritmo_activo": algoritmo_activo()}
            if pid not in perfiles_combinados()[0]:
                return 404, {"error": "paciente no existe"}
            return 200, {"evaluacion": evaluar_y_guardar(pid, fecha_de({**qs, **body})), "algoritmo_activo": algoritmo_activo()}

    if method == "POST" and partes == ["algoritmo", "barrido"]:
        if algoritmo_activo() != "rubrica":
            return 409, {"error": "el algoritmo con rúbrica no está activo (ALGORITMO=reglas)", "algoritmo_activo": algoritmo_activo()}
        return 200, barrido(fecha_de({**qs, **body}), limite=int(body.get("limite", 20)))
    return None


def handler(event, context=None):
    datos.nueva_solicitud()  # leer DynamoDB una vez por solicitud
    try:
        method = event.get("requestContext", {}).get("http", {}).get("method") or event.get("httpMethod", "GET")
        path = (event.get("rawPath") or event.get("path") or "/").rstrip("/") or "/"
        qs = event.get("queryStringParameters") or {}
        try:
            body = json.loads(event.get("body") or "{}") if event.get("body") else {}
        except ValueError:
            return _resp(400, {"error": "el cuerpo de la solicitud no es JSON válido"})
        partes = [p for p in path.split("/") if p]
        if method == "GET" and len(partes) == 2 and partes[0] == "plantillas" and partes[1] in importar.PLANTILLAS:
            return {"statusCode": 200, "headers": {**CORS, "Content-Type": "text/csv; charset=utf-8",
                                                   "Content-Disposition": f'attachment; filename="plantilla_{partes[1]}.csv"'},
                    "body": importar.plantilla_csv(partes[1])}
        r = _rutear(method, partes, qs, body)
        return _resp(*r) if r else _resp(404, {"error": f"ruta no encontrada: {method} {path}"})
    except datos.EntradaInvalida as e:
        return _resp(400, {"error": str(e)})
    except Exception as e:  # nunca devolver 502 sin CORS: el front no podría leer el error
        return _resp(500, {"error": str(e)})
