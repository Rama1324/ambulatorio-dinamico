"""Clientes de IA: modo simulado (MODEL_ID=simulado) de punta a punta, robustez con Bedrock (toolChoice, thinking),
LECTURAS_IA, guardrail, caché de prompts y métricas de costo. Ninguno llama a AWS: Bedrock se simula con un objeto que
tiene `converse` y devuelve o lanza lo que el test necesita."""
import copy
import json
import os
import sys
import types
from datetime import date

import pytest
from botocore.exceptions import ClientError

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["LOCAL"] = "1"; os.environ.setdefault("DATA_DIR", os.path.join(RAIZ, "data")); os.environ.pop("MODEL_ID", None)
sys.path.insert(0, os.path.join(RAIZ, "lambda"))
import app  # noqa: E402
import cliente_ia  # noqa: E402
import combinaciones  # noqa: E402
import criterios  # noqa: E402
import datos  # noqa: E402
import decisor  # noqa: E402
import evaluacion_ia  # noqa: E402
import explicar  # noqa: E402
import lector_documento  # noqa: E402
import puntaje  # noqa: E402
import rubrica  # noqa: E402

CORTE = date(2026, 10, 13)
KB = decisor.cargar_kb()
VARIABLES = ("MODEL_ID", "MODEL_ID_REDACCION", "ALGORITMO", "LECTURAS_IA", "GUARDRAIL_ID", "GUARDRAIL_VERSION", "BEDROCK_CACHE")


@pytest.fixture(autouse=True)
def entorno_limpio(monkeypatch):
    for v in VARIABLES:
        monkeypatch.delenv(v, raising=False)
    evaluacion_ia._llm["cliente"] = None
    explicar._sin_thinking.clear()
    yield
    evaluacion_ia._llm["cliente"] = None


def call(method, path, body=None):
    r = app.handler({"requestContext": {"http": {"method": method}}, "rawPath": path, "body": json.dumps(body or {})})
    return r["statusCode"], json.loads(r["body"])


def perfil(pid):
    return copy.deepcopy(app.perfiles_combinados()[0][pid])


def error_validacion(mensaje):
    return ClientError({"Error": {"Code": "ValidationException", "Message": mensaje}}, "Converse")


class Bedrock:
    """boto3 bedrock-runtime simulado: guarda cada petición; `rechazar(kwargs)` devuelve la excepción a lanzar (o None);
    `responder(kwargs)` devuelve la respuesta de Converse."""

    def __init__(self, entrada=None, rechazar=None, responder=None):
        self.peticiones, self.rechazar = [], rechazar or (lambda kw: None)
        self.responder = responder or (lambda kw: {"stopReason": "tool_use", "usage": {"inputTokens": 1000, "outputTokens": 200,
                                                                                         "cacheReadInputTokens": 700},
                                                   "output": {"message": {"content": [
                                                       {"toolUse": {"toolUseId": "t1", "name": kw["toolConfig"]["tools"][0]["toolSpec"]["name"],
                                                                    "input": entrada}}]}}})

    def converse(self, **kw):
        self.peticiones.append(copy.deepcopy(kw))
        e = self.rechazar(kw)
        if e:
            raise e
        return self.responder(kw)


def rechaza_forzado(kw):
    if "tool" in kw["toolConfig"]["toolChoice"]:
        return error_validacion("The model returned the following errors: tool_choice type 'tool' is not supported by this model")


def lectura_real(pid="PAC-HLF-00002", corte=CORTE):
    """(perfil, dx, respuesta correcta) para leer la rúbrica con el Bedrock simulado."""
    p = perfil(pid)
    dx = decisor.kb_diagnostico(KB, p["lista_espera"]["diagnostico_cie10"])
    return p, dx, rubrica.respuesta_determinista(rubrica.historial(p, corte), dx)


def metricas(capsys):
    return [json.loads(l) for l in capsys.readouterr().out.splitlines() if l.startswith('{"metrica"')]


# ---------- 1. Modo simulado de punta a punta (sin AWS) ----------
def test_simulado_un_evento_se_evalua_y_queda_rotulado(monkeypatch, capsys):
    monkeypatch.setenv("ALGORITMO", "rubrica")
    monkeypatch.setenv("MODEL_ID", "simulado")
    pid = next(p["id_paciente"] for p in app.lista(CORTE)["pacientes"] if p["diagnostico_cie10"] == "J44" and not p["riesgo_vital"])
    s, b = call("POST", "/eventos", {"id_paciente": pid, "tipo_evento": "hospitalizacion", "subtipo": "ingreso hospitalario",
                                     "fecha_corte": CORTE.isoformat()})
    ev = b["evaluacion"]
    assert s == 200 and ev["modelo"] == "simulado" and all(x["meta"]["modelo"] == "simulado" for x in ev["lecturas"])
    assert ev["corridas"] == 3 and not any(m["motivo"] == "fallo_llm" for m in ev["controles"])
    reglas = puntaje.puntuar(perfil(pid), CORTE)          # el lector simulado responde con el mismo criterio que las reglas
    assert ev["categoria_final"] == reglas["categoria"] == "alta" and ev["descompensacion_grave_final"] == reglas["riesgo_vital"]
    guardada = datos.evaluaciones_por_paciente()[pid][0]
    assert guardada["modelo"] == "simulado" and guardada["estabilidad"]["control"]
    assert b["paciente"]["algoritmo"] == "rubrica" and b["paciente"]["rubrica"]["modelo"] == "simulado"
    ms = metricas(capsys)
    assert ms and all(m["modelo"] == "simulado" and m["tarea"] == "rubrica" and m["resultado"] == "ok" for m in ms)


def test_simulado_un_informe_en_texto_registra_el_hallazgo_verificado(monkeypatch):
    monkeypatch.setenv("ALGORITMO", "rubrica")
    monkeypatch.setenv("MODEL_ID", "simulado")
    pid = next(p["id_paciente"] for p in app.lista(CORTE)["pacientes"] if p["categoria"] == "baja" and p["diagnostico_cie10"] == "E11")
    texto = "Epicrisis. Fecha: 2026-10-10.\nSe hospitaliza en sala de medicina por mal control metabólico.\nSin otras novedades."
    s, r = call("POST", f"/pacientes/{pid}/informe", {"texto": texto, "fecha_corte": CORTE.isoformat()})
    assert s == 200 and r["modo"] == "ia" and r["ia"]["lecturas"] == 3 and not r["ia"]["errores"]
    reg = r["registrados"]
    assert [(e["tipo_evento"], e["subtipo"]) for e in reg] == [("hospitalizacion", "ingreso hospitalario")]
    assert reg[0]["cita"] in texto and reg[0]["fecha_evento"] == "2026-10-10" and reg[0]["origen"] == "documento_ia"
    assert datos.evaluaciones_por_paciente()[pid][0]["modelo"] == "simulado"   # el evento registrado se reevaluó


def test_simulado_no_inventa_hallazgos_criterios_ni_combinaciones():
    sim = rubrica.ClienteSimulado()
    r = lector_documento.leer_documento("Control en policlínico. Paciente refiere sentirse bien. Se descarta hospitalización.", sim)
    assert r["aceptados"] == [] and r["propuestos"] == [] and r["lecturas"] == 3
    enf = criterios.enfermedad_de("M17")
    c = criterios.clasificar("Gonartrosis con masa de crecimiento rápido, sospecha de tumor.", enf, sim)
    assert c["nivel"] is None and c["urgencia"] is None and c["lecturas"] == 3 and not c["errores"]
    d = combinaciones.detectar("Diabético con uña encarnada infectada.", perfil("PAC-HLF-00001"), sim)
    assert d["aplicadas"] == [] and d["alertas"] == [] and combinaciones.evento(d, CORTE.isoformat()) is None
    # la rúbrica por texto no se interpreta: solo por leer_rubrica (historial estructurado)
    with pytest.raises(rubrica.ErrorLectura):
        sim.leer("s", "t", rubrica.HERRAMIENTA)


def test_cliente_llm_entrega_el_simulado_y_los_tests_pueden_inyectar(monkeypatch):
    monkeypatch.setenv("MODEL_ID", "simulado")
    assert isinstance(evaluacion_ia.cliente_llm(), rubrica.ClienteSimulado) and evaluacion_ia.cliente_llm(barrido=True).model_id == "simulado"
    falso = rubrica.ClienteFalso({})
    evaluacion_ia._llm["cliente"] = falso
    assert evaluacion_ia.cliente_llm() is falso


def test_simulado_el_resumen_usa_la_plantilla_y_lo_dice(monkeypatch):
    monkeypatch.setenv("MODEL_ID", "simulado")
    monkeypatch.setenv("MODEL_ID_REDACCION", "otro-modelo")
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=lambda *a, **k: pytest.fail("no debe llamar a Bedrock")))
    s, r = call("POST", "/pacientes/PAC-HLF-00002/explicar", {"fecha_corte": CORTE.isoformat()})
    assert s == 200 and r["fuente"] == "plantilla" and r["resumen"]["en_pocas_palabras"]
    fila = next(p for p in app.lista(CORTE)["pacientes"] if p["id_paciente"] == "PAC-HLF-00002")
    assert explicar.explicar(fila)[1] == "plantilla"


# ---------- 2. Robustez con Bedrock ----------
def test_si_el_modelo_rechaza_el_tool_choice_forzado_reintenta_con_auto_y_lo_recuerda():
    p, dx, correcta = lectura_real()
    br = Bedrock(correcta, rechazar=rechaza_forzado)
    cli = rubrica.ClienteBedrock(model_id="modelo-nuevo", cliente=br)
    r, meta = rubrica.leer_rubrica(p, CORTE, dx, cli)
    assert r is not None and "error" not in meta and meta["tool_choice"] == "auto" and meta["modelo"] == "modelo-nuevo"
    assert [list(x["toolConfig"]["toolChoice"]) for x in br.peticiones] == [["tool"], ["auto"]]
    instruccion = br.peticiones[1]["messages"][0]["content"][-1]["text"]
    assert "responder_rubrica" in instruccion and "SOLO" in instruccion
    assert br.peticiones[0]["messages"][0]["content"] == br.peticiones[1]["messages"][0]["content"][:-1]  # mismo contenido + instrucción
    rubrica.leer_rubrica(p, CORTE, dx, cli)                       # recuerda: la siguiente va directo con auto
    assert [list(x["toolConfig"]["toolChoice"]) for x in br.peticiones[2:]] == [["auto"]]


def test_otros_errores_no_se_reintentan_con_auto():
    p, dx, correcta = lectura_real()
    for e in (error_validacion("Malformed input request: messages.0.content is too long"),
              ClientError({"Error": {"Code": "ThrottlingException", "Message": "tool_choice rate exceeded"}}, "Converse")):
        br = Bedrock(correcta, rechazar=lambda kw, e=e: e)
        cli = rubrica.ClienteBedrock(model_id="m", cliente=br)
        r, meta = rubrica.leer_rubrica(p, CORTE, dx, cli)
        assert r is None and "fallo_llm" in meta["error"] and len(br.peticiones) == 1 and cli.forzar


def test_con_auto_una_respuesta_sin_la_herramienta_sigue_siendo_error():
    p, dx, correcta = lectura_real()
    texto_libre = lambda kw: {"stopReason": "end_turn", "usage": {"inputTokens": 10, "outputTokens": 5},
                              "output": {"message": {"content": [{"text": json.dumps(correcta)}]}}}
    br = Bedrock(correcta, rechazar=rechaza_forzado, responder=texto_libre)
    r, meta = rubrica.leer_rubrica(p, CORTE, dx, rubrica.ClienteBedrock(model_id="m", cliente=br))
    assert r is None and "no usó la herramienta" in meta["error"]   # nunca se interpreta texto libre


def _resumen_bedrock(monkeypatch, rechazar):
    salida = json.dumps({"en_pocas_palabras": "Paciente de 70 años.", "mientras_esperaba": ["Se hospitalizó."],
                         "por_que_importa": "Riesgo.", "que_hacer": ["Llamar hoy."], "que_falta": []})
    br = Bedrock(rechazar=rechazar, responder=lambda kw: {"stopReason": "end_turn", "usage": {"inputTokens": 1, "outputTokens": 1},
                                                           "output": {"message": {"content": [{"text": salida}]}}})
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=lambda *a, **k: br))
    return br


def test_resumen_reintenta_sin_thinking_y_usa_el_modelo_de_redaccion(monkeypatch):
    monkeypatch.setenv("MODEL_ID", "modelo-lectura")
    monkeypatch.setenv("MODEL_ID_REDACCION", "modelo-redaccion")
    br = _resumen_bedrock(monkeypatch, lambda kw: error_validacion("additionalModelRequestFields: thinking.type: Input should be 'adaptive'")
                          if "additionalModelRequestFields" in kw else None)
    s, r = call("POST", "/pacientes/PAC-HLF-00002/explicar", {"fecha_corte": CORTE.isoformat()})
    assert s == 200 and r["fuente"] == "bedrock" and r["resumen"]["que_hacer"] == ["Llamar hoy."]
    assert [("additionalModelRequestFields" in x, x["modelId"]) for x in br.peticiones] == [(True, "modelo-redaccion"), (False, "modelo-redaccion")]
    call("POST", "/pacientes/PAC-HLF-00002/explicar", {"fecha_corte": CORTE.isoformat()})
    assert "additionalModelRequestFields" not in br.peticiones[-1] and len(br.peticiones) == 3   # lo recuerda


def test_resumen_sin_modelo_de_redaccion_usa_model_id_y_otro_error_va_a_la_plantilla(monkeypatch):
    monkeypatch.setenv("MODEL_ID", "modelo-lectura")
    br = _resumen_bedrock(monkeypatch, lambda kw: error_validacion("Malformed input request"))
    s, r = call("POST", "/pacientes/PAC-HLF-00002/explicar", {"fecha_corte": CORTE.isoformat()})
    assert s == 200 and r["fuente"] == "plantilla" and len(br.peticiones) == 1 and br.peticiones[0]["modelId"] == "modelo-lectura"


# ---------- LECTURAS_IA ----------
def test_lecturas_ia_1_sin_control_de_estabilidad_y_queda_escrito(monkeypatch):
    monkeypatch.setenv("LECTURAS_IA", "1")
    p, dx, correcta = lectura_real()
    falso = rubrica.ClienteFalso(correcta)
    evaluacion_ia._llm["cliente"] = falso
    reg = evaluacion_ia.evaluar_y_guardar("PAC-HLF-00002", CORTE)
    assert falso.llamadas == 1 and reg["corridas"] == 1 and len(reg["lecturas"]) == 1
    assert reg["estabilidad"] == {"lecturas": 1, "control": False, "nota": evaluacion_ia.estabilidad(1)["nota"]}
    assert "sin control de estabilidad" in reg["estabilidad"]["nota"]
    assert reg["categoria_final"] == "alta" and not reg["respaldo_reglas"]   # se decide con la lectura verificada
    # criterios por enfermedad: con 1 lectura basta 1 de 1 verificada (la cita igual se verifica)
    texto = "Gonartrosis derecha con masa de crecimiento rápido, sospecha de tumor."
    cli = rubrica.ClienteFalso({"criterio": "alta.0", "cita": "sospecha de tumor", "urgencia": "ninguna", "cita_urgencia": ""})
    c = criterios.clasificar(texto, criterios.enfermedad_de("M17"), cli)
    assert cli.llamadas == 1 and c["criterio_id"] == "alta.0" and c["control_estabilidad"] is False
    inventada = rubrica.ClienteFalso({"criterio": "alta.0", "cita": "tumor maligno confirmado", "urgencia": "ninguna", "cita_urgencia": ""})
    assert criterios.clasificar(texto, criterios.enfermedad_de("M17"), inventada)["criterio_id"] is None


def test_lecturas_ia_2_si_no_coinciden_rigen_las_reglas(monkeypatch):
    monkeypatch.setenv("LECTURAS_IA", "2")
    p, dx, correcta = lectura_real()
    distinta = {**correcta, "evento_grave": {"valor": "no", "citas": []}, "estabilizado_despues": {"valor": "no", "citas": []}}
    n = {"i": 0}

    def alterna(_):
        n["i"] += 1
        return correcta if n["i"] % 2 else distinta
    evaluacion_ia._llm["cliente"] = rubrica.ClienteFalso(alterna)
    reg = evaluacion_ia.evaluar_y_guardar("PAC-HLF-00002", CORTE)
    assert reg["corridas"] == 2 and reg["estabilidad"]["control"] and reg["respaldo_reglas"]
    assert reg["categoria_final"] == puntaje.puntuar(perfil("PAC-HLF-00002"), CORTE)["categoria"]
    # documento: con 2 lecturas, lo que aparece en 1 de 2 queda como propuesta
    doc = "Epicrisis.\nSe hospitaliza en sala de medicina."
    m = {"i": 0}

    def a_veces(_):
        m["i"] += 1
        return {"hallazgos": [{"tipo": "hospitalizacion", "cita": "Se hospitaliza en sala de medicina"}] if m["i"] == 1 else []}
    r = lector_documento.leer_documento(doc, rubrica.ClienteFalso(a_veces))
    assert r["lecturas"] == 2 and not r["aceptados"] and r["propuestos"][0]["lecturas"] == "1/2"


def test_lecturas_ia_invalido_usa_3(monkeypatch):
    for v, n in (("0", 1), ("7", 3), ("dos", 3), ("2", 2)):
        monkeypatch.setenv("LECTURAS_IA", v)
        assert cliente_ia.lecturas_ia() == n


# ---------- Guardrail y caché ----------
def test_guardrail_solo_si_esta_configurado(monkeypatch):
    p, dx, correcta = lectura_real()
    br = Bedrock(correcta)
    cli = rubrica.ClienteBedrock(model_id="m", cliente=br)
    rubrica.leer_rubrica(p, CORTE, dx, cli)
    monkeypatch.setenv("GUARDRAIL_ID", "gr-123")
    rubrica.leer_rubrica(p, CORTE, dx, cli)                        # falta la versión: sin guardrail
    monkeypatch.setenv("GUARDRAIL_VERSION", "2")
    rubrica.leer_rubrica(p, CORTE, dx, cli)
    lector_documento.leer_documento("Se hospitaliza en sala.", cli, lecturas=1)
    assert ["guardrailConfig" in x for x in br.peticiones] == [False, False, True, True]
    assert br.peticiones[2]["guardrailConfig"] == {"guardrailIdentifier": "gr-123", "guardrailVersion": "2", "trace": "disabled"}


def test_cache_mismo_contenido_con_un_cache_point(monkeypatch):
    p, dx, correcta = lectura_real()
    br = Bedrock(correcta)
    cli = rubrica.ClienteBedrock(model_id="m", cliente=br)
    r1, m1 = rubrica.leer_rubrica(p, CORTE, dx, cli)
    monkeypatch.setenv("BEDROCK_CACHE", "1")
    r2, m2 = rubrica.leer_rubrica(p, CORTE, dx, cli)
    sin, con = br.peticiones[0]["messages"][0]["content"], br.peticiones[1]["messages"][0]["content"]
    assert len(sin) == 1 and con[1] == {"cachePoint": {"type": "default"}} and len(con) == 3
    estable, variable, _ = rubrica.partes_prompt(p, CORTE, dx)
    assert con[0]["text"] == estable and con[2]["text"] == variable            # lo estable primero, el paciente al final
    assert sin[0]["text"] == variable + rubrica.SEPARADOR + estable           # sin caché, el texto de siempre: mismo contenido
    assert br.peticiones[0]["system"] == br.peticiones[1]["system"] and br.peticiones[0]["toolConfig"] == br.peticiones[1]["toolConfig"]
    assert r1 == r2 and m2["tokens_cache_lectura"] == 700
    # el hash del prompt (vigencia de las evaluaciones guardadas) no cambia con la caché
    assert m1["hash_prompt"] == m2["hash_prompt"] == rubrica.hash_prompt()
    # otras tareas: el cachePoint va después del sistema
    lector_documento.leer_documento("Se hospitaliza en sala.", cli, lecturas=1)
    assert br.peticiones[-1]["system"][-1] == {"cachePoint": {"type": "default"}}
    assert sum("cachePoint" in b for x in br.peticiones for b in x["messages"][0]["content"] + x["system"]) <= 4


# ---------- 3. Métricas de costo ----------
CLAVES = {"metrica", "tarea", "modelo", "tokens_entrada", "tokens_salida", "tokens_cache_lectura", "tokens_cache_escritura",
          "latencia_s", "resultado", "error"}


def test_metricas_una_linea_por_llamada_sin_texto_del_paciente(capsys):
    p, dx, correcta = lectura_real()
    capsys.readouterr()
    cli = rubrica.ClienteBedrock(model_id="m", cliente=Bedrock(correcta))
    rubrica.leer_rubrica(p, CORTE, dx, cli)
    secreto = "MARCADOR-CLINICO-XYZ"
    malo = rubrica.ClienteBedrock(model_id="m", cliente=Bedrock(rechazar=lambda kw: error_validacion(f"input invalid near '{secreto}'")))
    lector_documento.leer_documento(f"{secreto}. Se hospitaliza en sala.", malo, lecturas=1)
    ms = metricas(capsys)
    assert [m["tarea"] for m in ms] == ["rubrica", "documento"] and all(set(m) == CLAVES for m in ms)
    assert ms[0] == {**ms[0], "resultado": "ok", "tokens_entrada": 1000, "tokens_salida": 200, "tokens_cache_lectura": 700, "error": None}
    assert ms[1]["resultado"] == "error" and ms[1]["error"] == "ValidationException"
    linea = json.dumps(ms, ensure_ascii=False)
    hist = rubrica.historial(p, CORTE)
    assert secreto not in linea and hist["diagnostico_texto"] not in linea
    assert not any(e["fecha"] in linea for e in hist["eventos"])
