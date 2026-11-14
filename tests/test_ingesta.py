"""Ingesta continua (lambda/ingesta.py): una sola tubería para la app, los archivos, la API para sistemas, la zona de carga
S3 y los informes. S3, SQS y SNS se prueban con moto (sin AWS ni credenciales reales)."""
import base64
import json
import os
import sys
import time
from datetime import date

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["LOCAL"] = "1"; os.environ.setdefault("DATA_DIR", os.path.join(RAIZ, "data")); os.environ.pop("MODEL_ID", None)
sys.path.insert(0, os.path.join(RAIZ, "lambda"))
import app  # noqa: E402
import bitacora  # noqa: E402
import datos  # noqa: E402
import ingesta  # noqa: E402

CORTE = date(2026, 10, 13)
Q = {"fecha_corte": CORTE.isoformat()}


def call(method, path, qs=None, body=None, cabeceras=None):
    r = app.handler({"requestContext": {"http": {"method": method}}, "rawPath": path, "queryStringParameters": qs,
                     "headers": cabeceras or {}, "body": json.dumps(body) if body is not None else None})
    return r["statusCode"], json.loads(r["body"])


def en_espera(especialidad, n=1, sin_eventos=True, excluir=()):
    """Pacientes en la lista de esa especialidad, elegidos por criterio (sin eventos previos: el cambio se ve limpio)."""
    perfs = datos.perfiles_combinados()[0]
    out = [pid for pid, p in sorted(perfs.items()) if p["lista_espera"]["especialidad"] == especialidad
           and p["lista_espera"]["estado"] == "en_espera" and not p["paciente"].get("fallecido") and pid not in excluir
           and (not sin_eventos or not p["eventos_clinicos"])]
    return out[:n] if n > 1 else out[0]


def atendido():
    return next(pid for pid, p in sorted(datos.perfiles_combinados()[0].items()) if p["lista_espera"]["estado"] == "atendido")


def eventos_de(pid):
    return [json.loads(i["evento"]) for i in datos.registros_tipo("evento#", pid)]


@pytest.fixture
def espia(monkeypatch):
    """Sustituye la bitácora (la implementa otro módulo): registra con qué se la llamó y devuelve un dictamen por paciente."""
    llamadas = {"fotos": [], "lote": []}

    def fotos(pids, corte):
        # la foto es de ANTES: los eventos del lote todavía no están guardados
        llamadas["fotos"].append({"pids": list(pids), "corte": corte, "eventos_ya_guardados": {
            pid: len([e for e in eventos_de(pid) if e.get("canal")]) for pid in pids}})
        return {pid: {"id_paciente": pid, "categoria": "baja", "posicion": 99, "razones": [{"x": 1}], "nombre_fantasia": "X"} for pid in pids}

    def registrar_lote(disparadores, corte, antes, **kw):
        llamadas["lote"].append({"disparadores": disparadores, "corte": corte, "antes": antes, **kw})
        return [{"id_dictamen": f"DIC-{pid}", "id_paciente": pid, "motor": "reglas",
                 "resultado": {"cambio": "sube", "categoria_antes": "baja", "categoria": "alta"}} for pid in disparadores]
    monkeypatch.setattr(bitacora, "fotos", fotos)
    monkeypatch.setattr(bitacora, "registrar_lote", registrar_lote)
    return llamadas


# ---------- la tubería ----------
def test_tuberia_registra_deduplica_rechaza_y_cuenta_fuera_de_lista(espia):
    datos.restablecer()
    card, endo, egresado = en_espera("Cardiología"), en_espera("Endocrinología"), atendido()
    carga = {"eventos": [
        {"id_paciente": card, "fecha_evento": "2026-10-10", "tipo_evento": "visita_urgencia", "subtipo": "triage ESI 2", "severidad": "leve"},
        {"id_paciente": card, "fecha_evento": "2026-10-10", "tipo_evento": "visita_urgencia", "subtipo": "triage ESI 2"},  # repetida
        {"id_paciente": endo, "id_evento": "URG-991", "fecha_evento": "2026-10-11", "tipo_evento": "hospitalizacion", "subtipo": "ingreso UCI"},
        {"id_paciente": card, "fecha_evento": "2026-10-12", "tipo_evento": "visita_urgencia", "subtipo": "teletransporte"},
        {"id_paciente": card, "fecha_evento": "2026-12-01", "tipo_evento": "visita_urgencia", "subtipo": "triage ESI 1"},
        {"id_paciente": "PAC-NO-ESTA", "fecha_evento": "2026-10-10", "tipo_evento": "visita_urgencia", "subtipo": "triage ESI 1"},
        {"id_paciente": egresado, "fecha_evento": "2026-10-10", "tipo_evento": "visita_urgencia", "subtipo": "triage ESI 1"}],
        "mediciones": [{"id_paciente": endo, "fecha_medicion": "2026-10-11", "tipo_medicion": "HbA1c", "valor": 11.2, "unidad": "%"}]}
    antes_egresado = len(datos.registros_de(egresado))
    r = ingesta.registrar(carga, canal="api", origen="urgencia-hlf", usuario="integracion", corte=CORTE)
    assert (r["recibidos"], r["registrados"], r["duplicados"], r["fuera_de_lista"]) == (8, 3, 1, 2), r
    assert [(x["tabla"], x["indice"]) for x in r["rechazados"]] == [("eventos", 3), ("eventos", 4)]
    assert "teletransporte" in r["rechazados"][0]["motivo"] and "posterior" in r["rechazados"][1]["motivo"]
    assert r["pacientes_afectados"] == 2 and r["evaluacion"] == "sincrona" and r["estado"] == "procesado"
    # cada evento nuevo lleva su traza; la severidad sale del subtipo, no del remitente (que dijo "leve")
    ev = next(e for e in eventos_de(card) if e.get("canal"))
    assert ev["severidad"] == "grave" and ev["canal"] == "api" and ev["origen"] == "urgencia-hlf" and ev["id_lote"] == r["id_lote"]
    assert ev["registrado"] > "2026-11" and ev["usuario"] == "integracion" and ev["id_evento"].startswith("EV-")
    assert any(e["id_evento"] == "URG-991" for e in eventos_de(endo))            # el id del sistema de origen se respeta
    # de quien no está en la lista no se guarda nada (minimización de datos)
    assert datos.registros_de("PAC-NO-ESTA") == [] and len(datos.registros_de(egresado)) == antes_egresado
    # un lote que toca dos especialidades: una sola foto y un solo registro de dictámenes, una vez por paciente
    assert espia["fotos"][0]["pids"] == sorted([card, endo]) and espia["fotos"][0]["eventos_ya_guardados"] == {card: 0, endo: 0}
    (lote,) = espia["lote"]
    assert sorted(lote["disparadores"]) == sorted([card, endo]) and lote["canal"] == "api" and lote["id_lote"] == r["id_lote"]
    assert lote["disparadores"][card]["tipo"] == "evento" and "triage ESI 2 (grave)" in lote["disparadores"][card]["descripcion"]
    assert "1 medición" in lote["disparadores"][endo]["descripcion"] and lote["antes"][card]["posicion"] == 99
    assert [d["id_dictamen"] for d in r["dictamenes"]] == [f"DIC-{card}", f"DIC-{endo}"] and r["dictamenes"][0]["cambio"] == "sube"
    # el registro del lote queda en _ingesta
    lt = ingesta.lote(r["id_lote"])
    assert lt["canal"] == "api" and lt["por_tabla"]["eventos"]["fuera_de_lista"] == 2 and lt["estado"] == "procesado"
    assert lt["pacientes_afectados"] == sorted([card, endo]) and "PAC-NO-ESTA" not in json.dumps(lt)
    # reenviar lo mismo no duplica: todo es duplicado, nada se evalúa
    n = len(datos.registros())
    r2 = ingesta.registrar(carga, canal="api", origen="urgencia-hlf", corte=CORTE)
    assert (r2["registrados"], r2["duplicados"], r2["dictamenes"]) == (0, 4, []) and len(datos.registros()) == n
    assert len(espia["lote"]) == 1


def test_por_rut_y_bitacora_vacia_no_rompe_nada():
    datos.restablecer()
    s, p = call("POST", "/pacientes", body={"nombre": "Rosa Rut", "edad": 66, "sexo": "F", "diagnostico_cie10": "I50", "rut": "12.345.678-5",
                                            "prioridad_inicial": "baja", "fecha_ingreso_lista": "2026-05-01", **Q})
    assert s == 200
    pid = p["id_paciente"]
    r = ingesta.registrar({"eventos": [{"rut": "12345678-5", "fecha_evento": "2026-10-12", "tipo_evento": "hospitalizacion",
                                        "subtipo": "ingreso hospitalario"}]}, canal="api", origen="hospitalizacion-hlf", corte=CORTE)
    assert r["registrados"] == 1 and r["dictamenes"] == [] and not r["errores"]       # la bitácora aún no devuelve dictámenes
    assert eventos_de(pid)[0]["canal"] == "api"
    from lista import fila_de
    assert fila_de(pid, CORTE)["riesgo_vital"]                                                     # las reglas rigen de inmediato


def test_un_paciente_que_falla_al_evaluar_no_bota_el_lote(espia, monkeypatch):
    datos.restablecer()
    a, b = en_espera("Salud Mental", n=2)
    llamados = []

    def evaluar(pid, corte):
        llamados.append(pid)
        if pid == a:
            raise TimeoutError("Bedrock no respondió")
        return {"id_paciente": pid, "categoria_final": "alta"}
    monkeypatch.setattr(ingesta, "algoritmo_activo", lambda: "rubrica")
    monkeypatch.setattr(ingesta, "evaluar_y_guardar", evaluar)
    ev = lambda pid, f, s: {"id_paciente": pid, "fecha_evento": f, "tipo_evento": "visita_urgencia", "subtipo": s}  # noqa: E731
    r = ingesta.registrar({"eventos": [ev(a, "2026-10-01", "triage ESI 2"), ev(b, "2026-10-01", "triage ESI 3"),
                                       ev(b, "2026-10-05", "triage ESI 2")]}, canal="api", origen="urgencia-hlf", corte=CORTE)
    assert sorted(llamados) == sorted([a, b])                                        # una vez por paciente aunque traiga dos eventos
    assert r["registrados"] == 3 and r["estado"] == "con_errores"
    assert r["errores"] == [{"etapa": "evaluacion", "id_paciente": a, "error": "TimeoutError: Bedrock no respondió"}]
    (lote,) = espia["lote"]
    assert lote["evaluaciones"] == {b: {"id_paciente": b, "categoria_final": "alta"}} and sorted(lote["disparadores"]) == sorted([a, b])
    assert "y 1 evento(s) más" in lote["disparadores"][b]["descripcion"] and "triage ESI 2" in lote["disparadores"][b]["descripcion"]
    assert ingesta.lote(r["id_lote"])["cierre"]["errores"][0]["id_paciente"] == a


def test_modo_cola_sin_cola_definida_procesa_en_linea(espia, monkeypatch):
    datos.restablecer()
    monkeypatch.delenv("COLA_EVALUACION_URL", raising=False)
    pid = en_espera("Neurología")
    r = ingesta.registrar({"eventos": [{"id_paciente": pid, "fecha_evento": "2026-10-02", "tipo_evento": "visita_urgencia",
                                        "subtipo": "triage ESI 1"}]}, canal="s3", origen="urgencia", corte=CORTE, evaluar="cola")
    assert r["evaluacion"] == "sincrona" and r["en_cola"] == 0 and len(espia["lote"]) == 1 and r["dictamenes"]


# ---------- canales de la app: el contrato no pierde campos ----------
def test_post_eventos_conserva_su_contrato_y_agrega_lote_y_dictamen(espia):
    datos.restablecer()
    pid = en_espera("Cardiología")
    s, r = call("POST", "/eventos", body={"id_paciente": pid, "tipo_evento": "hospitalizacion", "subtipo": "ingreso UCI", "usuario": "Enf. Rojas", **Q})
    assert s == 200
    assert {"evento", "paciente", "posicion_antes", "posicion_despues", "total", "reevaluado_en_ms", "id_lote", "dictamen"} <= set(r)
    assert r["evento"]["canal"] == "app" and r["evento"]["id_lote"] == r["id_lote"] and r["evento"]["id_evento"].startswith("EV-DEMO-")
    assert r["evento"]["usuario"] == "Enf. Rojas" and r["posicion_despues"] < r["posicion_antes"] and r["dictamen"]["id_dictamen"] == f"DIC-{pid}"
    assert espia["lote"][0]["canal"] == "app" and espia["lote"][0]["usuario"] == "Enf. Rojas"
    # simular dos veces el mismo evento en la app registra dos (cada uno con su id), como antes
    s, r2 = call("POST", "/eventos", body={"id_paciente": pid, "tipo_evento": "hospitalizacion", "subtipo": "ingreso UCI", **Q})
    assert s == 200 and r2["evento"]["id_evento"] != r["evento"]["id_evento"]
    assert call("POST", "/eventos", body={"id_paciente": "PAC-NO-ESTA", "tipo_evento": "hospitalizacion", "subtipo": "ingreso UCI"})[0] == 404


def test_post_importar_conserva_su_contrato_y_agrega_lote(espia):
    datos.restablecer()
    pid = en_espera("Broncopulmonar")
    csv = f"id_paciente;fecha_evento;tipo_evento;subtipo\n{pid};2026-10-03;hospitalizacion;ingreso hospitalario\nPAC-NO-ESTA;2026-10-03;hospitalizacion;\n"
    archivos = [{"nombre": "eventos.csv", "contenido_base64": base64.b64encode(csv.encode()).decode()}]
    s, rev = call("POST", "/importar", body={"archivos": archivos, **Q})
    assert s == 200 and set(rev) == {"informe", "resumen", "avisos", "cargado", "impacto"} and not rev["cargado"]
    s, r = call("POST", "/importar", body={"archivos": archivos, "confirmar": True, "usuario": "Estadística HLF", **Q})
    assert s == 200 and r["cargado"] and {"informe", "resumen", "avisos", "impacto", "id_lote", "dictamenes"} <= set(r)
    assert r["ingesta"]["registrados"] == 1 and r["ingesta"]["fuera_de_lista"] == 1 and r["dictamenes"][0]["id_paciente"] == pid
    ev = next(e for e in eventos_de(pid) if e.get("canal"))
    assert ev["canal"] == "archivo" and ev["id_lote"] == r["id_lote"] and ev["usuario"] == "Estadística HLF"
    assert espia["lote"][0]["disparadores"][pid]["tipo"] == "importacion"
    assert ingesta.lote(r["id_lote"])["archivo"] == "eventos.csv"


# ---------- API para sistemas ----------
def test_api_para_sistemas_con_idempotency_key(espia):
    datos.restablecer()
    a, b = en_espera("Traumatología", n=2)
    cuerpo = {"origen": "urgencia-hlf", "fecha_corte": "2026-10-13", "eventos": [
        {"rut_paciente": a, "fecha": "13-10-2026", "tipo": "urgencia", "triage": "Triage ESI 2", "motivo_consulta": "dolor torácico"},
        {"id_paciente": b, "fecha_evento": "xx", "tipo_evento": "visita_urgencia", "subtipo": "triage ESI 2"}],
        "mediciones": [{"id_paciente": a, "fecha_medicion": "2026-10-13", "tipo_medicion": "eva", "valor": "9"}]}
    s, r = call("POST", "/ingesta/eventos", body=cuerpo, cabeceras={"Idempotency-Key": "urg-0001"})
    assert s == 200 and (r["registrados"], r["duplicados"], len(r["rechazados"])) == (2, 0, 1), r
    assert r["rechazados"][0]["indice"] == 1 and r["rechazados"][0]["motivo"].startswith("fecha no reconocida: 'xx'")
    ev = next(e for e in eventos_de(a) if e.get("canal"))
    assert (ev["subtipo"], ev["motivo"], ev["origen"]) == ("triage ESI 2", "dolor torácico", "urgencia-hlf")   # sinónimos de los archivos
    # misma clave → misma respuesta, sin procesar de nuevo (no hay lote nuevo)
    n_lotes = len(ingesta.lotes(200))
    s2, r2 = call("POST", "/ingesta/eventos", body=cuerpo, cabeceras={"idempotency-key": "urg-0001"})
    assert (s2, r2) == (s, r) and len(ingesta.lotes(200)) == n_lotes
    assert call("POST", "/ingesta/eventos", body={**cuerpo, "origen": "otro"}, cabeceras={"Idempotency-Key": "urg-0001"})[0] == 409
    # sin clave: se procesa, pero la idempotencia por contenido evita duplicar
    s3, r3 = call("POST", "/ingesta/eventos", body=cuerpo)
    assert s3 == 200 and (r3["registrados"], r3["duplicados"]) == (0, 2) and r3["id_lote"] != r["id_lote"]
    # la clave vence a las 24 h (ítem con expira: pasado ese momento ya no cuenta)
    (idem,) = datos.globales("_idem", "ingesta#urg-0001")
    assert 23 * 3600 < idem["expira"] - time.time() <= 24 * 3600
    # lotes
    s, lst = call("GET", "/ingesta/lotes", {"limite": "2"})
    assert s == 200 and [x["id_lote"] for x in lst["lotes"]] == [r3["id_lote"], r["id_lote"]] and "rechazados" not in lst["lotes"][0]
    s, lt = call("GET", f"/ingesta/lotes/{r['id_lote']}")
    assert s == 200 and lt["rechazados"][0]["indice"] == 1 and lt["origen"] == "urgencia-hlf"
    assert call("GET", "/ingesta/lotes/LOT-NO-EXISTE")[0] == 404


def test_api_cuerpo_sin_la_forma_esperada_es_400():
    for cuerpo in ({"eventos": [{}]}, {"origen": "x", "eventos": {"a": 1}}, {"origen": "x"}, {"origen": "x", "eventos": [{}] * (ingesta.MAX_FILAS + 1)}):
        s, r = call("POST", "/ingesta/eventos", body=cuerpo)
        assert s == 400 and r["error"], cuerpo
    s, r = call("POST", "/ingesta/eventos", body={"origen": "x", "eventos": ["no es objeto", {"id_paciente": "PAC-HLF-00002"}]})
    assert s == 200 and [x["motivo"] for x in r["rechazados"]] == ["cada fila debe ser un objeto JSON", "falta fecha_evento, tipo_evento"]


def test_mil_eventos_en_tiempo_razonable(espia, capsys):
    datos.restablecer()
    pids = [pid for pid, p in sorted(datos.perfiles_combinados()[0].items()) if p["lista_espera"]["estado"] == "en_espera"
            and not p["paciente"].get("fallecido")][:250]
    eventos = [{"id_paciente": pids[i % len(pids)], "id_evento": f"URG-{i:05d}", "fecha_evento": f"2026-10-{1 + i % 12:02d}",
                "tipo_evento": "visita_urgencia", "subtipo": ["triage ESI 2", "triage ESI 3", "triage ESI 4-5"][i % 3]} for i in range(1000)]
    t0 = time.perf_counter()
    s, r = call("POST", "/ingesta/eventos", body={"origen": "urgencia-hlf", "eventos": eventos, **Q})
    seg = time.perf_counter() - t0
    with capsys.disabled():
        print(f"\n  1.000 eventos (250 pacientes) por POST /ingesta/eventos: {seg:.2f} s (tubería {r['procesado_en_ms']} ms)")
    assert s == 200 and r["registrados"] == 1000 and r["pacientes_afectados"] == 250 and seg < 20
    t0 = time.perf_counter()
    s, r = call("POST", "/ingesta/eventos", body={"origen": "urgencia-hlf", "eventos": eventos, **Q})
    with capsys.disabled():
        print(f"  reenvío de los mismos 1.000 (todos duplicados): {time.perf_counter() - t0:.2f} s")
    assert r["duplicados"] == 1000 and r["registrados"] == 0


# ---------- zona de carga S3 y cola (moto) ----------
@pytest.fixture
def aws(monkeypatch):
    boto3 = pytest.importorskip("boto3")
    from moto import mock_aws
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(k, "prueba")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    with mock_aws():
        s3, sqs, sns = (boto3.client(x, region_name="us-east-1") for x in ("s3", "sqs", "sns"))
        s3.create_bucket(Bucket="hlf-datos")
        cola = sqs.create_queue(QueueName="evaluacion")["QueueUrl"]
        avisos = sqs.create_queue(QueueName="avisos")["QueueUrl"]
        tema = sns.create_topic(Name="alertas")["TopicArn"]
        sns.subscribe(TopicArn=tema, Protocol="sqs", Endpoint=sqs.get_queue_attributes(QueueUrl=avisos, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"])
        monkeypatch.setenv("TEMA_ALERTAS_ARN", tema)
        yield type("AWS", (), {"s3": s3, "sqs": sqs, "cola": cola, "avisos": avisos})


def _evento_s3(key):
    return {"Records": [{"s3": {"bucket": {"name": "hlf-datos"}, "object": {"key": key.replace(" ", "+")}}}]}


def _mensajes(sqs, url):
    out = []
    while True:
        r = sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10).get("Messages", [])
        if not r:
            return out
        out += r


def test_zona_de_carga_s3_cola_y_avisos(aws, espia, monkeypatch):
    datos.restablecer()
    monkeypatch.setenv("COLA_EVALUACION_URL", aws.cola)
    a, b = en_espera("Gastroenterología", n=2)
    csv = ("RUN;Fecha;Categorización;Tipo;Motivo consulta\n"
           f"{a};12/10/2026;ESI 2;urgencia;hematemesis\n{b};12/10/2026;ESI 4-5;urgencia;resfrío\n"
           f"{b};32/10/2026;ESI 3;urgencia;dolor\nPAC-NO-ESTA;12/10/2026;ESI 1;urgencia;trauma\n")
    aws.s3.put_object(Bucket="hlf-datos", Key="entrada/urgencia/export 2026-10-12.csv", Body=csv.encode("latin-1"))
    r = ingesta.s3_handler(_evento_s3("entrada/urgencia/export 2026-10-12.csv"))
    assert r["procesados"][0]["estado"] == "procesado"
    res = json.loads(aws.s3.get_object(Bucket="hlf-datos", Key="procesados/urgencia/export 2026-10-12.csv.resultado.json")["Body"].read())
    assert (res["registrados"], res["fuera_de_lista"], len(res["rechazados"]), res["evaluacion"]) == (2, 1, 1, "en_cola"), res
    assert res["rechazados"][0]["indice"] == 4 and res["informe"][0]["tabla"] == "eventos_clinicos"
    ev = next(e for e in eventos_de(a) if e.get("canal"))
    assert (ev["canal"], ev["origen"], ev["subtipo"], ev["motivo"]) == ("s3", "urgencia", "triage ESI 2", "hematemesis")
    assert espia["lote"] == []                                                   # la evaluación quedó en la cola, no en línea
    # aviso sin datos de pacientes: solo archivo y conteos
    (aviso,) = _mensajes(aws.sqs, aws.avisos)
    texto = json.loads(aviso["Body"])["Message"]
    assert "export 2026-10-12.csv" in texto and a not in texto and "PAC-NO-ESTA" not in texto and json.loads(texto)["rechazados"] == 1
    # el trabajador consume la cola: la foto de antes viaja resumida y sin identificación; un mensaje roto falla solo
    msgs = _mensajes(aws.sqs, aws.cola)
    assert sorted(json.loads(m["Body"])["id_paciente"] for m in msgs) == sorted([a, b])
    cuerpo = json.loads(msgs[0]["Body"])
    assert cuerpo["antes"] == {"id_paciente": cuerpo["id_paciente"], "categoria": "baja", "posicion": 99} and len(msgs[0]["Body"]) < 2048
    registros = [{"messageId": m["MessageId"], "body": m["Body"]} for m in msgs] + [{"messageId": "roto", "body": "{no es json"}]
    assert ingesta.cola_handler({"Records": registros}) == {"batchItemFailures": [{"itemIdentifier": "roto"}]}
    assert sorted(p for l in espia["lote"] for p in l["disparadores"]) == sorted([a, b]) and espia["lote"][0]["canal"] == "s3"
    lt = ingesta.lote(res["id_lote"])
    assert lt["estado"] == "en_cola" and sorted(x["id_paciente"] for x in lt["evaluados_por_la_cola"]) == sorted([a, b])
    # reintento del mismo mensaje (SQS entrega al menos una vez): no repite el dictamen
    assert ingesta.cola_handler({"Records": registros[:1]}) == {"batchItemFailures": []} and len(espia["lote"]) == 2
    # reenviar el mismo archivo no duplica nada
    r = ingesta.s3_handler(_evento_s3("entrada/urgencia/export 2026-10-12.csv"))
    res = json.loads(aws.s3.get_object(Bucket="hlf-datos", Key="procesados/urgencia/export 2026-10-12.csv.resultado.json")["Body"].read())
    assert (res["registrados"], res["duplicados"]) == (0, 2)


def test_zona_de_carga_archivo_ilegible_va_a_errores(aws, monkeypatch):
    datos.restablecer()
    aws.s3.put_object(Bucket="hlf-datos", Key="entrada/basura.csv", Body=b"columna_rara;otra\n1;2\n")
    aws.s3.put_object(Bucket="hlf-datos", Key="procesados/no-se-toca.csv", Body=b"x")
    r = ingesta.s3_handler({"Records": _evento_s3("entrada/basura.csv")["Records"] + _evento_s3("procesados/no-se-toca.csv")["Records"]})
    assert [x["estado"] for x in r["procesados"]] == ["error"]                  # fuera de entrada/ no se procesa
    err = json.loads(aws.s3.get_object(Bucket="hlf-datos", Key="errores/basura.csv.error.json")["Body"].read())
    assert "No se reconoció qué tabla es" in err["error"]
    assert json.loads(json.loads(_mensajes(aws.sqs, aws.avisos)[0]["Body"])["Message"])["archivo"] == "entrada/basura.csv"


def test_api_booleanos_json_y_evento_sin_relacion_no_sube(espia):
    """JSON trae true/false de verdad (no "si"/"no" como un CSV): un evento grave sin relación con el diagnóstico queda
    registrado pero no sube la prioridad."""
    datos.restablecer()
    from lista import fila_de
    pid = en_espera("Cardiología")
    antes = fila_de(pid, CORTE)
    s, r = call("POST", "/ingesta/eventos", body={"origen": "his-hlf", **Q, "eventos": [
        {"id_paciente": pid, "fecha_evento": "2026-10-07", "tipo_evento": "hospitalizacion", "subtipo": "ingreso hospitalario",
         "motivo": "fractura de cadera por caída", "relacionado": False}]})
    assert s == 200 and r["registrados"] == 1
    ev = next(e for e in eventos_de(pid) if e.get("canal"))
    assert ev["relacionado"] is False
    despues = fila_de(pid, CORTE)
    assert despues["categoria"] == antes["categoria"] and not despues["riesgo_vital"]
