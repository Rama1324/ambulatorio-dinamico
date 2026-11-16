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
Modo AWS:   TABLE (DynamoDB pk=id_paciente, sk; índice PorDia). El registro se carga con scripts/cargar_registro.py.
"""
import base64
import gzip
import json
import os
import time
import traceback
import uuid

import aprendizaje
import base_conocimiento
import bitacora
import datos
import importar
import ingesta
import seguridad
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

JSON = {"Content-Type": "application/json"}
COMPRIMIR_DESDE = 10 * 1024   # bytes: bajo esto gzip no ahorra lo que cuesta (y la lista completa pasa de 6 MB sin él)

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
    return {"statusCode": status, "headers": dict(JSON), "body": json.dumps(body, ensure_ascii=False, default=str)}


# ---------- GET /pacientes: paginación y fila resumen (integraciones) ----------
CAMPOS_RESUMEN = ("id_paciente", "nombre_fantasia", "rut", "edad", "especialidad", "diagnostico_cie10", "diagnostico_texto",
                  "prioridad_inicial", "categoria", "posicion", "posicion_especialidad", "dias_espera", "estado_clinico",
                  "riesgo_vital", "urgencia_hoy", "plazo_vencido", "ges", "riesgo_inasistencia", "estado_revision", "rev",
                  "dictamen")


def _entero(qs, clave, minimo):
    crudo = qs.get(clave)
    try:
        n = int(str(crudo).strip())
    except ValueError:
        raise datos.EntradaInvalida(f"'{clave}' debe ser un número entero (llegó '{crudo}')")
    if n < minimo:
        raise datos.EntradaInvalida(f"'{clave}' debe ser {minimo} o más (llegó {n})")
    return n


def _recortar(resultado, qs):
    """`desde` (posición inicial: 1 = el primero, igual que `posicion`), `limite` (cuántos) y `campos=resumen` (fila corta
    para integraciones). Sin ninguno de los tres la respuesta queda idéntica. `total` es siempre el total de la lista."""
    dados = {k: str(qs.get(k)).strip() for k in ("desde", "limite", "campos") if str(qs.get(k) or "").strip()}
    if not dados:
        return resultado
    campos = dados.get("campos", "completo").lower()
    if campos not in ("resumen", "completo"):
        raise datos.EntradaInvalida(f"'campos' admite 'resumen' o 'completo' (llegó '{dados['campos']}')")
    desde = _entero(dados, "desde", 1) if "desde" in dados else 1
    limite = _entero(dados, "limite", 1) if "limite" in dados else None
    pagina = resultado["pacientes"][desde - 1:(desde - 1 + limite) if limite else None]
    if campos == "resumen":
        pagina = [{k: p[k] for k in CAMPOS_RESUMEN if k in p} for p in pagina]
    fin = desde - 1 + len(pagina)
    return {**resultado, "pacientes": pagina, "desde": desde, "limite": limite, "campos": campos,
            "siguiente": fin + 1 if fin < resultado["total"] else None}


def _rutear_modulos(method, partes, qs, body, cabeceras):
    """Rutas de los módulos por dominio: cada `rutear` devuelve (status, cuerpo) o None si la ruta no es suya."""
    for intento in (lambda: ingesta.rutear(method, partes, qs, body, cabeceras),          # /ingesta/…
                    lambda: bitacora.rutear(method, partes, qs, body),                    # /decisiones, /pacientes/{id}/decisiones
                    lambda: aprendizaje.rutear(method, partes, qs, body),                 # /aprendizaje, /criterios-locales, enmiendas
                    lambda: base_conocimiento.rutear(method, partes, qs, body)):          # /conocimiento
        r = intento()
        if r is not None:
            return r
    return None


def _rutear(method, partes, qs, body, cabeceras=None):
    if method == "OPTIONS":
        return 200, {}
    if method == "GET" and partes in ([], ["health"]):
        return 200, {"ok": True, "pacientes": len(perfiles()), "fecha_hoy": hoy().isoformat(),
                     "modo": "tiempo_real" if datos.TIEMPO_REAL else "simulacion", "datos": "sinteticos",
                     "datos_hasta": datos.datos_hasta(), "registro_al": datos.REGISTRO_AL,
                     "auth": seguridad.modo(), "algoritmo": algoritmo_activo(),
                     "modelo_ia": (os.environ.get("MODEL_ID") or None) if algoritmo_activo() == "rubrica" else None, "almacen": "memoria" if datos.LOCAL else "dynamodb",
                     "conocimiento": _paquete_conocimiento()}
    r = _rutear_modulos(method, partes, qs, body, cabeceras or {})
    if r is not None:
        return r
    if method == "GET" and partes == ["pacientes"]:
        return 200, _recortar(lista(fecha_de(qs), qs.get("especialidad") or None), qs)
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


def _paquete_conocimiento():
    """Versión de la base de conocimiento para /health. /health no debe caerse si falta un archivo: eso lo dice /conocimiento."""
    try:
        return base_conocimiento.paquete()
    except Exception as e:  # noqa: BLE001
        return {"error": type(e).__name__}


# ---------- handler: identidad → permiso → ruta → cabeceras, compresión y registro de accesos ----------
def _log(registro):
    """Una línea JSON en la salida estándar (CloudWatch Logs la guarda tal cual)."""
    print(json.dumps(registro, ensure_ascii=False, default=str), flush=True)


def _cuerpo(event):
    """El cuerpo como objeto JSON. API Gateway puede entregarlo en base64."""
    crudo = event.get("body")
    if not crudo:
        return {}
    try:
        if event.get("isBase64Encoded"):
            crudo = base64.b64decode(crudo).decode("utf-8")
        body = json.loads(crudo)
    except (ValueError, TypeError):
        raise datos.EntradaInvalida("el cuerpo de la solicitud no es JSON válido")
    if not isinstance(body, dict):
        raise datos.EntradaInvalida("el cuerpo de la solicitud debe ser un objeto JSON")
    return body


def _id_paciente(partes, body):
    """El paciente que toca la solicitud (para el registro de accesos): el de la ruta o, en POST /eventos, el del cuerpo."""
    if len(partes) >= 2 and partes[0] == "pacientes":
        return partes[1]
    pid = body.get("id_paciente") if isinstance(body, dict) else None
    return pid if isinstance(pid, str) else None


def _atender(event, method, path, partes, cabeceras, estado):
    """Identidad y permiso ANTES de leer el cuerpo y enrutar (sin token no se procesa nada, ni siquiera un JSON roto).
    `estado` recibe lo que el registro de accesos necesita saber."""
    estado["id_paciente"] = _id_paciente(partes, None)
    ident = estado["ident"] = seguridad.identidad(event)
    negado = seguridad.autorizar(ident, method, partes)
    if negado:
        return _resp(*negado)
    body = _cuerpo(event)
    estado["id_paciente"] = _id_paciente(partes, body)
    body = seguridad.aplicar_identidad(body, ident)   # con token, el nombre de quien registra sale del token
    qs = event.get("queryStringParameters") or {}
    if method == "GET" and partes == ["yo"]:
        return _resp(200, seguridad.yo(ident))
    if method == "GET" and len(partes) == 2 and partes[0] == "plantillas" and partes[1] in importar.PLANTILLAS:
        return {"statusCode": 200, "headers": {"Content-Type": "text/csv; charset=utf-8",
                                               "Content-Disposition": f'attachment; filename="plantilla_{partes[1]}.csv"'},
                "body": importar.plantilla_csv(partes[1])}
    r = _rutear(method, partes, qs, body, cabeceras)
    return _resp(*r) if r else _resp(404, {"error": f"ruta no encontrada: {method} {path}"})


def _comprimir(resp, cabeceras):
    """gzip si el cliente lo acepta y el cuerpo pasa de COMPRIMIR_DESDE. API Gateway HTTP API no comprime y una Lambda
    síncrona no puede responder más de 6 MB: la lista de una especialidad grande (18,7 MB) baja a ~0,3 MB."""
    aceptadas = {c.split(";")[0].strip().lower() for c in str(cabeceras.get("accept-encoding") or "").split(",")}
    cuerpo = resp.get("body") or ""
    crudo = cuerpo.encode("utf-8") if isinstance(cuerpo, str) else cuerpo
    if "gzip" not in aceptadas or resp.get("isBase64Encoded") or len(crudo) <= COMPRIMIR_DESDE:
        return resp
    return {**resp, "body": base64.b64encode(gzip.compress(crudo, compresslevel=6)).decode("ascii"), "isBase64Encoded": True,
            "headers": {**resp["headers"], "Content-Encoding": "gzip"}}


def _cerrar(resp, cabeceras, id_solicitud):
    """Cabeceras de seguridad y CORS en TODAS las respuestas (también 4xx/5xx: si no, el front no puede leer el error)."""
    cors = seguridad.cabeceras_cors(cabeceras.get("origin"))
    vary = [v for v in (cors.pop("Vary", None), "Accept-Encoding") if v]
    resp = {**resp, "headers": {**seguridad.CABECERAS_SEGURIDAD, **cors, **resp.get("headers", {}), "Vary": ", ".join(vary),
                                "X-Id-Solicitud": id_solicitud}}
    return _comprimir(resp, cabeceras)


def handler(event, context=None):
    t0 = time.perf_counter()
    datos.nueva_solicitud()  # leer DynamoDB una vez por solicitud
    event = event if isinstance(event, dict) else {}
    contexto = event.get("requestContext") or {}
    id_solicitud = getattr(context, "aws_request_id", None) or contexto.get("requestId") or uuid.uuid4().hex
    method = (contexto.get("http", {}).get("method") or event.get("httpMethod") or "GET").upper()
    path = (event.get("rawPath") or event.get("path") or "/").rstrip("/") or "/"
    partes = [p for p in path.split("/") if p]
    cabeceras = {str(k).lower(): v for k, v in (event.get("headers") or {}).items()}
    estado = {"ident": None, "id_paciente": None}
    try:
        resp = _atender(event, method, path, partes, cabeceras, estado)
    except datos.EntradaInvalida as e:
        resp = _resp(400, {"error": str(e)})
    except datos.Conflicto as e:  # el paciente cambió desde que se abrió su ficha (rev_vista): recargar
        resp = _resp(409, {"error": str(e), "codigo": "conflicto_edicion", "id_paciente": e.id_paciente,
                           "rev_vista": e.rev_vista, "rev_actual": e.rev_actual})
    except Exception as e:  # el detalle va solo al log: puede traer datos clínicos o pistas del sistema
        _log({"tipo": "error", "id_solicitud": id_solicitud, "metodo": method, "ruta": path, "error": type(e).__name__,
              "mensaje": str(e), "traza": traceback.format_exc()})
        cuerpo = {"error": "Error interno. Si persiste, informe este código al equipo de soporte.", "id_solicitud": id_solicitud}
        if os.environ.get("LOCAL") == "1":   # en local, para depurar
            cuerpo["detalle"] = f"{type(e).__name__}: {e}"
        resp = _resp(500, cuerpo)
    resp = _cerrar(resp, cabeceras, id_solicitud)
    ident = estado["ident"] or seguridad.ANONIMO
    # Registro de accesos: quién vio o cambió qué ficha. Sin cuerpo ni datos clínicos.
    _log({"tipo": "acceso", "id_solicitud": id_solicitud, "metodo": method, "ruta": path, "estado": resp["statusCode"],
          "ms": round((time.perf_counter() - t0) * 1000, 1), "usuario": ident.get("usuario"), "roles": ident.get("roles") or [],
          "origen": ident.get("origen"), "id_paciente": estado["id_paciente"]})
    return resp
