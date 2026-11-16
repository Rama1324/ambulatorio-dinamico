"""Seguridad de la API (ESPECIFICACION_MVP §8): identidad, permisos por rol, CORS, errores, registro de accesos, gzip y
paginación de GET /pacientes. Sin Cognito real: los eventos de API Gateway se arman a mano con
requestContext.authorizer.jwt.claims (lo que entrega el autorizador JWT después de validar la firma)."""
import base64
import gzip
import json

import pytest

import app
import ingesta
import seguridad

PID = "PAC-HLF-00002"


# ---------- utilidades ----------
def persona(*grupos, nombre="Dra. Ana Rojas", grupos_como_texto=False):
    claims = {"sub": "a1b2", "name": nombre, "email": "ana@hlf.cl", "cognito:username": "arojas", "token_use": "id",
              "cognito:groups": f"[{' '.join(grupos)}]" if grupos_como_texto else list(grupos)}
    return {"jwt": {"claims": claims, "scopes": None}}


def maquina(scope="ambulatorio/ingesta", client_id="sistema-urgencias"):
    return {"jwt": {"claims": {"sub": client_id, "client_id": client_id, "token_use": "access", "scope": scope}, "scopes": None}}


def evento(method, path, qs=None, body=None, autorizador=None, cabeceras=None):
    ev = {"requestContext": {"http": {"method": method}, "requestId": "req-test"}, "rawPath": path,
          "queryStringParameters": qs, "headers": cabeceras or {}, "body": json.dumps(body) if body is not None else None}
    if autorizador:
        ev["requestContext"]["authorizer"] = autorizador
    return ev


def llamar(*a, **kw):
    r = app.handler(evento(*a, **kw))
    cuerpo = r["body"]
    if r.get("isBase64Encoded"):
        cuerpo = gzip.decompress(base64.b64decode(cuerpo)).decode("utf-8")
    return r["statusCode"], (json.loads(cuerpo) if r["headers"].get("Content-Type", "").startswith("application/json") else cuerpo), r


@pytest.fixture
def cognito(monkeypatch):
    monkeypatch.setenv("AUTH", "cognito")


@pytest.fixture
def capturar_accion(monkeypatch):
    """Reemplaza las acciones de paciente por una que solo guarda el cuerpo que le llegó (no ensucia el almacén)."""
    recibidos = []
    for nombre in list(app.ACCIONES_PACIENTE):
        monkeypatch.setitem(app.ACCIONES_PACIENTE, nombre, lambda pid, body: (recibidos.append(body) or (200, {"ok": True})))
    return recibidos


# ---------- identidad ----------
def test_identidad_de_persona_con_grupos_como_lista_y_como_texto(cognito):
    for aut in (persona("especialista", "gestion"), persona("especialista", "gestion", grupos_como_texto=True)):
        ident = seguridad.identidad({"requestContext": {"authorizer": aut}})
        assert ident["usuario"] == "Dra. Ana Rojas" and ident["origen"] == "token"
        assert ident["roles"] == ["gestion", "especialista"]
    # Sin `name`: el correo; sin correo: la cuenta de Cognito
    sin_nombre = persona("gestion"); del sin_nombre["jwt"]["claims"]["name"]
    assert seguridad.identidad({"requestContext": {"authorizer": sin_nombre}})["usuario"] == "ana@hlf.cl"
    del sin_nombre["jwt"]["claims"]["email"]
    assert seguridad.identidad({"requestContext": {"authorizer": sin_nombre}})["usuario"] == "arojas"
    # Grupos con formato JSON y grupos que no son roles del sistema
    json_txt = persona(); json_txt["jwt"]["claims"]["cognito:groups"] = '["jefatura", "otro_grupo"]'
    assert seguridad.identidad({"requestContext": {"authorizer": json_txt}})["roles"] == ["jefatura"]


def test_identidad_de_maquina(cognito):
    ident = seguridad.identidad({"requestContext": {"authorizer": maquina()}})
    assert ident == {**ident, "usuario": "sistema:sistema-urgencias", "roles": ["integracion"], "origen": "token_maquina",
                     "cliente": "sistema-urgencias"}
    sin_scope = seguridad.identidad({"requestContext": {"authorizer": maquina(scope="otro/permiso")}})
    assert sin_scope["roles"] == [] and sin_scope["origen"] == "token_maquina"
    # scopes también pueden venir en jwt.scopes (lista)
    m = maquina(scope=""); m["jwt"]["scopes"] = ["ambulatorio/ingesta"]
    assert seguridad.identidad({"requestContext": {"authorizer": m}})["roles"] == ["integracion"]


def test_sin_token_con_cognito_es_anonimo_y_cualquier_valor_raro_de_auth_exige_token(monkeypatch):
    monkeypatch.setenv("AUTH", "Cognito ")
    assert seguridad.modo() == "cognito" and seguridad.identidad(evento("GET", "/pacientes"))["origen"] == "anonimo"
    monkeypatch.setenv("AUTH", "ningna")   # error de tipeo: cierra, no abre
    assert seguridad.modo() == "cognito"


def test_identidad_declarada_en_la_demo(monkeypatch):
    monkeypatch.delenv("AUTH", raising=False)
    ident = seguridad.identidad(evento("POST", "/eventos", body={"usuario": "Enf. Pérez"}, cabeceras={"X-Rol": "Especialista"}))
    assert ident == {"usuario": "Enf. Pérez", "roles": ["especialista"], "origen": "declarado", "cliente": None}
    # Un claims falso en la demo tampoco vale sin `sub`: no hay token
    assert seguridad.identidad({"requestContext": {"authorizer": {"jwt": {"claims": {"name": "x"}}}}})["origen"] == "anonimo"


# ---------- tabla de permisos ----------
# Todas las rutas que existen (app.py y los rutear de los módulos, §5–§8) con su rol mínimo. Escrita aquí a mano a
# propósito: si alguien cambia la tabla de seguridad.py sin querer, este test lo nota.
ESPERADO = {
    ("GET", "/"): None, ("GET", "/health"): None,
    ("GET", "/yo"): "autenticado",
    ("GET", "/pacientes"): "lectura", ("GET", f"/pacientes/{PID}"): "lectura", ("GET", f"/pacientes/{PID}/historia"): "lectura",
    ("GET", f"/pacientes/{PID}/evaluaciones"): "lectura", ("GET", f"/pacientes/{PID}/decisiones"): "lectura",
    ("GET", "/catalogo"): "lectura", ("GET", "/estadisticas"): "lectura", ("GET", "/kpis"): "lectura",
    ("GET", "/plantillas/lista_espera"): "lectura", ("GET", "/decisiones"): "lectura", ("GET", "/decisiones/DIC-1"): "lectura",
    ("GET", "/aprendizaje"): "lectura", ("GET", "/criterios-locales"): "lectura", ("GET", "/conocimiento"): "lectura",
    ("GET", "/conocimiento/diagnostico/I20"): "lectura", ("POST", f"/pacientes/{PID}/explicar"): "lectura",
    ("POST", "/pacientes"): "gestion", ("POST", "/importar"): "gestion", ("POST", "/eventos"): "gestion",
    ("POST", f"/pacientes/{PID}/contacto"): "gestion", ("POST", f"/pacientes/{PID}/gestion"): "gestion",
    ("POST", f"/pacientes/{PID}/informe"): "gestion", ("POST", f"/pacientes/{PID}/novedad"): "gestion",
    ("POST", f"/pacientes/{PID}/evaluar"): "gestion",
    ("POST", f"/pacientes/{PID}/revision"): "especialista", ("POST", f"/pacientes/{PID}/decision"): "especialista",
    ("POST", f"/pacientes/{PID}/orden"): "especialista", ("POST", f"/pacientes/{PID}/eventos/EV-1/enmienda"): "especialista",
    ("POST", "/criterios-locales/CL-0001/resolver"): "jefatura", ("POST", "/algoritmo/barrido"): "jefatura",
    ("POST", "/ingesta/eventos"): "integracion", ("GET", "/ingesta/lotes"): "integracion", ("GET", "/ingesta/lotes/L-1"): "integracion",
}
IDENTIDADES = {
    "sin_grupo": persona(), "gestion": persona("gestion"), "especialista": persona("especialista"),
    "jefatura": persona("jefatura"), "integracion": maquina(), "maquina_sin_scope": maquina(scope="otro"),
}
# Quién alcanza cada exigencia (jerarquía jefatura ⊇ especialista ⊇ gestion; integracion solo ingesta y sus lotes)
ALCANZA = {
    "autenticado": set(IDENTIDADES), "lectura": {"sin_grupo", "gestion", "especialista", "jefatura"},
    "gestion": {"gestion", "especialista", "jefatura"}, "especialista": {"especialista", "jefatura"}, "jefatura": {"jefatura"},
    "integracion": {"integracion", "gestion", "especialista", "jefatura"},
}


def _partes(path):
    return [p for p in path.split("/") if p]


def test_la_tabla_cubre_todas_las_rutas_y_nada_mas():
    for (m, path), exigencia in ESPERADO.items():
        assert seguridad.permiso(m, _partes(path)) == exigencia, (m, path)
    assert len(seguridad.REGLAS) == len(ESPERADO)


@pytest.mark.parametrize("ruta", sorted(ESPERADO, key=str))
def test_matriz_de_permisos(cognito, ruta):
    m, path = ruta
    exigencia = ESPERADO[ruta]
    for nombre, aut in IDENTIDADES.items():
        ident = seguridad.identidad({"requestContext": {"authorizer": aut}})
        r = seguridad.autorizar(ident, m, _partes(path))
        puede = exigencia is None or nombre in ALCANZA[exigencia]
        assert (r is None) == puede, (m, path, nombre, r)
        if r:
            assert r[0] == 403 and r[1]["error"].startswith("Acceso denegado")
    # sin token: 401 salvo las libres
    r = seguridad.autorizar(seguridad.identidad({}), m, _partes(path))
    assert (r is None) if exigencia is None else (r[0] == 401)


def test_ruta_sin_regla_denegada_con_cognito(cognito):
    assert seguridad.permiso("POST", ["pacientes", PID, "borrar"]) == seguridad.SIN_REGLA
    s, d, _ = llamar("POST", f"/pacientes/{PID}/borrar", body={}, autorizador=persona("jefatura"))
    assert s == 403 and d["codigo"] == "ruta_sin_regla"
    assert llamar("GET", "/nada", autorizador=None)[0] == 401
    assert llamar("DELETE", "/pacientes", autorizador=persona("jefatura"))[0] == 403


def test_handler_con_cognito_401_403_y_rutas_libres(cognito):
    assert llamar("GET", "/pacientes")[0] == 401
    assert llamar("POST", "/eventos", body={"x": 1})[0] == 401
    assert llamar("POST", "/eventos", autorizador=None)[0] == 401
    r = app.handler({**evento("POST", "/eventos", autorizador=None), "body": "{roto"})
    assert r["statusCode"] == 401          # sin token ni siquiera se lee el cuerpo
    s, d, _ = llamar("GET", "/health")
    assert s == 200 and d["auth"] == "cognito" and d["almacen"] == "memoria" and d["algoritmo"] in ("reglas", "rubrica")
    assert "etiqueta" in d["conocimiento"] or "error" in d["conocimiento"]
    assert llamar("OPTIONS", "/pacientes/PAC-HLF-00002/revision")[0] == 200
    s, d, _ = llamar("POST", f"/pacientes/{PID}/revision", body={"accion": "confirmar"}, autorizador=persona("gestion"))
    assert s == 403 and d["requiere"] == "especialista" and "especialista o jefatura" in d["error"]
    s, d, _ = llamar("GET", "/catalogo", autorizador=maquina())
    assert s == 403 and "solo puede enviar datos a la ingesta" in d["error"]
    assert llamar("GET", "/catalogo", autorizador=persona())[0] == 200


def test_yo(cognito):
    s, d, _ = llamar("GET", "/yo", autorizador=persona("especialista"))
    assert s == 200 and d["usuario"] == "Dra. Ana Rojas" and d["roles"] == ["especialista"] and d["auth"] == "cognito"
    assert d["se_exige"] and d["permisos"]["especialista"] and not d["permisos"]["jefatura"] and d["permisos"]["gestion"]
    s, d, _ = llamar("GET", "/yo", autorizador=maquina())
    assert s == 200 and d["permisos"]["integracion"] and not d["permisos"]["lectura"]
    assert llamar("GET", "/yo")[0] == 401


def test_yo_en_la_demo(monkeypatch):
    monkeypatch.delenv("AUTH", raising=False)
    s, d, _ = llamar("GET", "/yo", cabeceras={"x-rol": "gestion"})
    assert s == 200 and d["auth"] == "ninguna" and not d["se_exige"] and "No es un control de seguridad" in d["aviso"]
    assert d["roles"] == ["gestion"] and not d["permisos"]["especialista"]


# ---------- el usuario sale del token ----------
def test_con_token_se_ignora_el_usuario_del_navegador(cognito, capturar_accion):
    s, _, _ = llamar("POST", f"/pacientes/{PID}/contacto", body={"usuario": "Otro Nombre", "resultado": "contestó"},
                     autorizador=persona("gestion"))
    assert s == 200 and capturar_accion[-1]["usuario"] == "Dra. Ana Rojas"
    s, _, _ = llamar("POST", f"/pacientes/{PID}/gestion", body={"usuario": "x", "responsable": ""}, autorizador=persona("gestion"))
    assert capturar_accion[-1]["usuario"] == capturar_accion[-1]["responsable"] == "Dra. Ana Rojas"
    s, _, _ = llamar("POST", f"/pacientes/{PID}/gestion", body={"responsable": "Secretaria Box 3"}, autorizador=persona("gestion"))
    assert capturar_accion[-1]["responsable"] == "Secretaria Box 3"


def test_auth_ninguna_no_cambia_el_comportamiento(monkeypatch, capturar_accion):
    monkeypatch.delenv("AUTH", raising=False)
    s, _, _ = llamar("POST", f"/pacientes/{PID}/revision", body={"usuario": "Dr. Demo", "accion": "confirmar"})
    assert s == 200 and capturar_accion[-1] == {"usuario": "Dr. Demo", "accion": "confirmar"}
    # sin rol declarado y con un rol "bajo" declarado: todo permitido igual (el rol es solo informativo)
    assert llamar("POST", "/algoritmo/barrido", body={}, cabeceras={"x-rol": "gestion"})[0] in (200, 409)
    s, d, _ = llamar("GET", "/pacientes", {"fecha_corte": "2026-10-13"})
    assert s == 200 and d["total"] == len(d["pacientes"]) > 400


def test_idempotency_key_llega_a_la_ingesta(monkeypatch):
    monkeypatch.delenv("AUTH", raising=False)
    vistos = []
    monkeypatch.setattr(ingesta, "rutear", lambda m, p, qs, body, cab=None: vistos.append(cab) or (200, {"ok": True}))
    assert llamar("POST", "/ingesta/eventos", body={"eventos": []}, cabeceras={"Idempotency-Key": "abc-1"})[0] == 200
    assert vistos[-1]["idempotency-key"] == "abc-1"


# ---------- CORS y cabeceras ----------
def test_cors_por_defecto_abierto_en_la_demo(monkeypatch):
    monkeypatch.delenv("ORIGEN_PERMITIDO", raising=False)
    _, _, r = llamar("OPTIONS", "/pacientes", cabeceras={"Origin": "https://cualquiera.cl"})
    h = r["headers"]
    assert h["Access-Control-Allow-Origin"] == "*"
    assert set(h["Access-Control-Allow-Headers"].split(",")) == {"content-type", "authorization", "idempotency-key", "x-rol"}
    assert h["Access-Control-Allow-Methods"] == "GET,POST,OPTIONS"
    assert h["X-Content-Type-Options"] == "nosniff" and h["Cache-Control"] == "no-store"


def test_cors_con_origen_permitido_y_no_permitido(monkeypatch):
    monkeypatch.setenv("ORIGEN_PERMITIDO", "https://main.app.cl, https://otra.cl/")
    _, _, r = llamar("GET", "/health", cabeceras={"origin": "https://main.app.cl"})
    assert r["headers"]["Access-Control-Allow-Origin"] == "https://main.app.cl" and "Origin" in r["headers"]["Vary"]
    _, _, r = llamar("GET", "/health", cabeceras={"origin": "https://otra.cl"})
    assert r["headers"]["Access-Control-Allow-Origin"] == "https://otra.cl"
    _, _, r = llamar("GET", "/health", cabeceras={"origin": "https://malicioso.cl"})
    assert "Access-Control-Allow-Origin" not in r["headers"]
    _, _, r = llamar("GET", "/health")
    assert "Access-Control-Allow-Origin" not in r["headers"]


# ---------- errores ----------
def test_500_no_filtra_el_detalle(monkeypatch, capsys):
    monkeypatch.delenv("AUTH", raising=False)
    monkeypatch.setenv("LOCAL", "0")   # el almacén sigue en memoria (se decidió al importar datos); solo cambia el mensaje
    monkeypatch.setattr(app, "catalogo", lambda: (_ for _ in ()).throw(RuntimeError("tabla secreta arn:aws:dynamodb:xyz")))
    capsys.readouterr()
    s, d, r = llamar("GET", "/catalogo")
    assert s == 500 and "secreta" not in r["body"] and "RuntimeError" not in r["body"] and "detalle" not in d
    assert d["id_solicitud"] == "req-test" and r["headers"]["Access-Control-Allow-Origin"] == "*"
    log = capsys.readouterr().out
    error = next(json.loads(l) for l in log.splitlines() if '"tipo": "error"' in l)
    assert error["id_solicitud"] == "req-test" and "secreta" in error["mensaje"] and "Traceback" in error["traza"]
    monkeypatch.setenv("LOCAL", "1")
    s, d, _ = llamar("GET", "/catalogo")
    assert s == 500 and "secreta" in d["detalle"]


def test_400_y_409_se_mantienen(monkeypatch):
    monkeypatch.delenv("AUTH", raising=False)
    import datos
    assert llamar("GET", "/pacientes", {"fecha_corte": "hola"})[0] == 400
    r = app.handler({**evento("POST", "/eventos"), "body": "[1, 2]"})
    assert r["statusCode"] == 400
    monkeypatch.setitem(app.ACCIONES_PACIENTE, "contacto", lambda pid, body: (_ for _ in ()).throw(datos.Conflicto(pid, 3, 5)))
    s, d, _ = llamar("POST", f"/pacientes/{PID}/contacto", body={"rev_vista": 3})
    assert s == 409 and d["codigo"] == "conflicto_edicion" and d["rev_actual"] == 5 and d["rev_vista"] == 3


# ---------- registro de accesos ----------
def test_registro_de_accesos_sin_cuerpo(cognito, capturar_accion, capsys):
    capsys.readouterr()
    llamar("POST", f"/pacientes/{PID}/contacto", body={"nota": "SECRETO-CLINICO dolor torácico", "usuario": "x"},
           autorizador=persona("gestion"))
    lineas = [json.loads(l) for l in capsys.readouterr().out.splitlines() if l.startswith("{")]
    acceso = next(l for l in lineas if l["tipo"] == "acceso")
    assert set(acceso) == {"tipo", "id_solicitud", "metodo", "ruta", "estado", "ms", "usuario", "roles", "origen", "id_paciente"}
    assert acceso["usuario"] == "Dra. Ana Rojas" and acceso["roles"] == ["gestion"] and acceso["origen"] == "token"
    assert acceso["id_paciente"] == PID and acceso["estado"] == 200 and acceso["metodo"] == "POST"
    assert "SECRETO" not in json.dumps(lineas) and "torácico" not in json.dumps(lineas)
    # también queda el acceso denegado, y el paciente de POST /eventos sale del cuerpo
    llamar("POST", "/eventos", body={"id_paciente": PID, "descripcion": "SECRETO"}, autorizador=persona())
    acceso = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert acceso["estado"] == 403 and acceso["id_paciente"] is None    # denegado antes de leer el cuerpo


# ---------- compresión ----------
def test_gzip_ida_y_vuelta(monkeypatch):
    monkeypatch.delenv("AUTH", raising=False)
    plano = app.handler(evento("GET", "/pacientes", {"fecha_corte": "2026-10-13"}))
    comp = app.handler(evento("GET", "/pacientes", {"fecha_corte": "2026-10-13"}, cabeceras={"Accept-Encoding": "gzip, deflate, br"}))
    assert not plano.get("isBase64Encoded") and comp["isBase64Encoded"]
    assert comp["headers"]["Content-Encoding"] == "gzip" and "Accept-Encoding" in comp["headers"]["Vary"]
    assert json.loads(gzip.decompress(base64.b64decode(comp["body"]))) == json.loads(plano["body"])
    assert len(comp["body"]) < len(plano["body"]) / 5


def test_no_comprime_respuestas_chicas_ni_sin_accept_encoding(monkeypatch):
    monkeypatch.delenv("AUTH", raising=False)
    r = app.handler(evento("GET", "/health", cabeceras={"accept-encoding": "gzip"}))
    assert not r.get("isBase64Encoded") and "Content-Encoding" not in r["headers"] and json.loads(r["body"])["ok"]
    r = app.handler(evento("GET", "/catalogo", cabeceras={"accept-encoding": "br"}))
    assert not r.get("isBase64Encoded")


# ---------- paginación y fila resumen ----------
def test_sin_parametros_la_lista_es_identica(monkeypatch):
    monkeypatch.delenv("AUTH", raising=False)
    from datetime import date
    _, d, _ = llamar("GET", "/pacientes", {"fecha_corte": "2026-10-13"})
    assert d == json.loads(json.dumps(app.lista(date(2026, 10, 13)), ensure_ascii=False, default=str))
    assert set(d) == {"fecha_corte", "total", "pacientes", "excluidos"}


def test_paginacion_y_resumen(monkeypatch):
    monkeypatch.delenv("AUTH", raising=False)
    _, todo, _ = llamar("GET", "/pacientes", {"fecha_corte": "2026-10-13", "especialidad": "Cardiología"})
    _, d, _ = llamar("GET", "/pacientes", {"fecha_corte": "2026-10-13", "especialidad": "Cardiología", "desde": "3", "limite": "5"})
    assert d["total"] == todo["total"] and [p["posicion"] for p in d["pacientes"]] == [3, 4, 5, 6, 7]
    assert d["pacientes"] == todo["pacientes"][2:7] and d["siguiente"] == 8 and d["campos"] == "completo"
    _, d, _ = llamar("GET", "/pacientes", {"fecha_corte": "2026-10-13", "especialidad": "Cardiología",
                                           "desde": str(todo["total"] - 1), "limite": "10", "campos": "resumen"})
    assert len(d["pacientes"]) == 2 and d["siguiente"] is None and d["total"] == todo["total"]
    fila = d["pacientes"][0]
    assert set(fila) <= set(app.CAMPOS_RESUMEN) and "razones" not in fila and "lace" not in fila
    assert {"id_paciente", "especialidad", "diagnostico_cie10", "categoria", "posicion", "dias_espera", "riesgo_vital"} <= set(fila)
    _, d, _ = llamar("GET", "/pacientes", {"fecha_corte": "2026-10-13", "desde": "100000"})
    assert d["pacientes"] == [] and d["siguiente"] is None and d["total"] > 400   # total de la lista, no de la página
    for malo in ({"limite": "0"}, {"limite": "diez"}, {"desde": "-1"}, {"campos": "todo"}):
        assert llamar("GET", "/pacientes", {"fecha_corte": "2026-10-13", **malo})[0] == 400, malo
