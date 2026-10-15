"""Tests del algoritmo decisor 'rúbrica + fórmula fija'. Ninguno llama a Bedrock: usan ClienteFalso."""
import copy
import itertools
import json
import os
import random
import sys
from datetime import date

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["LOCAL"] = "1"; os.environ.setdefault("DATA_DIR", os.path.join(RAIZ, "data")); os.environ.pop("MODEL_ID", None)
sys.path.insert(0, os.path.join(RAIZ, "lambda"))
import algoritmo  # noqa: E402
import app  # noqa: E402
import controles  # noqa: E402
import decisor  # noqa: E402
import puntaje  # noqa: E402
import rubrica  # noqa: E402

KB = decisor.cargar_kb()
CORTE = date(2026, 10, 13)


def perfil(pid):
    return copy.deepcopy(app.perfiles()[pid])


def oraculo(pid_o_perfil, corte=CORTE):
    """ClienteFalso que responde como el lector determinista (respuesta 'perfecta' grabada)."""
    p = perfil(pid_o_perfil) if isinstance(pid_o_perfil, str) else pid_o_perfil
    dx = decisor.kb_diagnostico(KB, p["lista_espera"]["diagnostico_cie10"])
    return rubrica.ClienteFalso(rubrica.respuesta_determinista(rubrica.historial(p, corte), dx))


def resp(evento="no", estab="no", tend="desconocido", cambio="no", citas_ev=None, citas_est=None, citas_tend=None, senal=""):
    return rubrica.RespuestaRubrica.model_validate({
        "evento_grave": {"valor": evento, "citas": citas_ev or []}, "estabilizado_despues": {"valor": estab, "citas": citas_est or []},
        "tendencia_medicion": {"valor": tend, "citas": citas_tend or []}, "cambio_tratamiento_por_mal_control": {"valor": cambio, "citas": []},
        "senal_no_cubierta": senal})


# ---------- R: el LLM nunca decide; la fórmula sube según la tabla con fuente ----------
def test_00002_sube_a_alta_por_angina_inestable():
    reg = algoritmo.evaluar_paciente(perfil("PAC-HLF-00002"), date(2026, 8, 10), oraculo("PAC-HLF-00002", date(2026, 8, 10)))
    assert reg["categoria_final"] == "alta" and reg["descompensacion_grave_final"] and not reg["requiere_revision"]
    assert any(r["factor"] == "tabla_oficial" and "pág. 85" in r["fuente"] for r in reg["razones"])   # cada razón con su fuente
    assert all(r.get("fuente") for r in reg["razones"])


def test_00028_no_baja_solo():
    p = perfil("PAC-HLF-00028")
    reg = algoritmo.evaluar_paciente(p, CORTE, oraculo(p))
    reglas = puntaje.puntuar(p, CORTE)
    assert decisor.ORDEN_CAT[reg["categoria_final"]] >= decisor.ORDEN_CAT[reglas["categoria"]]


def test_00009_fallecido_sale_de_la_lista():
    assert algoritmo.evaluar_paciente(perfil("PAC-HLF-00009"), CORTE, oraculo("PAC-HLF-00009")) is None


def test_un_desconocido_no_es_normal():
    p = perfil("PAC-HLF-00002")
    r = decisor.decidir(p, resp(evento="desconocido"), CORTE, KB)
    assert any(x["motivo"] == "dato_desconocido" and x["bloqueante"] for x in r["revision"])
    reg = algoritmo.evaluar_paciente(p, CORTE, rubrica.ClienteFalso(resp(evento="desconocido").model_dump()))
    assert reg["requiere_revision"] and any(m["motivo"] == "dato_desconocido" for m in reg["controles"])
    assert reg["categoria_final"] == puntaje.puntuar(p, CORTE)["categoria"]


# ---------- R: controles antes de mover ----------
def test_cita_inexistente_mantiene_reglas_y_pide_revision():
    p = perfil("PAC-HLF-00002")
    falsa = resp(evento="si", citas_ev=[{"fecha": "2026-09-09", "tipo": "hospitalizacion", "valor": "ingreso UCI"}]).model_dump()
    reg = algoritmo.evaluar_paciente(p, CORTE, rubrica.ClienteFalso(falsa))
    assert reg["requiere_revision"] and any(m["motivo"] == "cita_invalida" for m in reg["controles"])
    assert reg["categoria_final"] == reg["categoria_reglas"]


def test_si_sin_cita_es_cita_invalida():
    p = perfil("PAC-HLF-00002")
    reg = algoritmo.evaluar_paciente(p, CORTE, rubrica.ClienteFalso(resp(evento="si").model_dump()))
    assert any(m["motivo"] == "cita_invalida" for m in reg["controles"])


def test_tres_corridas_distintas_es_inestable():
    p, fc = perfil("PAC-HLF-00002"), date(2026, 8, 10)
    buena = rubrica.respuesta_determinista(rubrica.historial(p, fc), decisor.kb_diagnostico(KB, "I20"))
    vacia = resp().model_dump()
    ciclo = itertools.cycle([buena, vacia, buena])
    reg = algoritmo.evaluar_paciente(p, fc, rubrica.ClienteFalso(lambda _t: next(ciclo)))
    assert reg["requiere_revision"] and any(m["motivo"] == "inestable" for m in reg["controles"])
    assert reg["categoria_final"] == reg["categoria_reglas"]


def test_bedrock_falla_usa_reglas_y_lo_registra():
    p = perfil("PAC-HLF-00002")
    reg = algoritmo.evaluar_paciente(p, CORTE, rubrica.ClienteFalso({}, fallar=True))
    assert reg["requiere_revision"] and reg["controles"][0]["motivo"] == "fallo_llm"
    assert reg["categoria_final"] == reg["categoria_reglas"] and all(l["meta"].get("error") for l in reg["lecturas"])


def test_json_invalido_es_fallo():
    p = perfil("PAC-HLF-00002")
    reg = algoritmo.evaluar_paciente(p, CORTE, rubrica.ClienteFalso({"evento_grave": "tal vez"}))
    assert any(m["motivo"] == "fallo_llm" for m in reg["controles"]) and "json_invalido" in reg["lecturas"][0]["meta"]["error"]


def test_bajar_siempre_requiere_humano():
    """Reglas: descompensado (alta). La rúbrica dice 'estabilizado' → daría la prioridad inicial (más baja) → bloqueado."""
    p = perfil("PAC-HLF-00002")
    reglas = puntaje.puntuar(p, CORTE)
    assert reglas["categoria"] == "alta"
    h = rubrica.historial(p, CORTE)
    grave = [e for e in h["eventos"] if e["severidad"] == "grave"][-1]
    p["eventos_clinicos"].append({"id_evento": "X", "fecha_evento": "2026-10-01", "tipo_evento": "control_aps", "subtipo": "estabilización", "severidad": "leve"})
    r = resp(evento="si", estab="si", citas_ev=[{"fecha": grave["fecha"], "tipo": grave["tipo"], "valor": grave["valor"]}],
             citas_est=[{"fecha": "2026-10-01", "tipo": "control_aps", "valor": "estabilización"}]).model_dump()
    reg = algoritmo.evaluar_paciente(p, CORTE, rubrica.ClienteFalso(r))
    # las reglas tampoco bajan solas: con estabilización, ambas dan la prioridad vigente o el control bloquea
    assert decisor.ORDEN_CAT[reg["categoria_final"]] >= decisor.ORDEN_CAT[puntaje.puntuar(p, CORTE)["categoria"]]


def test_propiedad_ninguna_respuesta_baja_a_alguien_sin_humano():
    """Para 150 pacientes y respuestas aleatorias (válidas o no), la categoría final nunca es menor que la de las reglas."""
    rnd = random.Random(7)
    perfs = [p for p in app.perfiles().values() if puntaje.puntuar(p, CORTE) and not puntaje.puntuar(p, CORTE).get("excluido")]
    for p in rnd.sample(perfs, 150):
        h = rubrica.historial(p, CORTE)
        regs = h["eventos"] + h["mediciones"]
        def azar(_t):
            c = lambda: [dict(fecha=x["fecha"], tipo=x["tipo"], valor=x["valor"]) for x in rnd.sample(regs, min(len(regs), rnd.randint(0, 2)))]
            return {"evento_grave": {"valor": rnd.choice(["si", "no", "desconocido"]), "citas": c()},
                    "estabilizado_despues": {"valor": rnd.choice(["si", "no", "desconocido"]), "citas": c()},
                    "tendencia_medicion": {"valor": rnd.choice(["empeora", "estable", "mejora", "desconocido"]), "citas": c()},
                    "cambio_tratamiento_por_mal_control": {"valor": rnd.choice(["si", "no"]), "citas": c()}, "senal_no_cubierta": ""}
        reg = algoritmo.evaluar_paciente(p, CORTE, rubrica.ClienteFalso(azar))
        assert decisor.ORDEN_CAT[reg["categoria_final"]] >= decisor.ORDEN_CAT[reg["categoria_reglas"]], p["id_paciente"]
        if reg["categoria_final"] != reg["categoria_reglas"]:
            assert not reg["requiere_revision"] and reg["movido_por_rubrica"]


def test_discrepancia_de_mas_de_un_nivel_pide_revision():
    lect = [(resp(), {}, [])]
    motivos = controles.evaluar(lect, [{"categoria": "alta", "revision": []}], {"categoria": "baja"})
    assert any(m["motivo"] == "discrepancia" for m in motivos)


# ---------- R: ventana del evento y medición clave (solo con fuente) ----------
def test_evento_fuera_de_ventana_no_mantiene_descompensado():
    kb = copy.deepcopy(KB)
    kb["diagnosticos"]["I20"]["ventanas"] = {x: {"valor": 30, "fuente": "PMID de prueba", "estado": "con_fuente"} for x in ("hospitalizacion", "visita_urgencia")}
    p = perfil("PAC-HLF-00002")
    h = rubrica.historial(p, CORTE)
    g = [e for e in h["eventos"] if e["severidad"] == "grave"][-1]
    r = decisor.decidir(p, resp(evento="si", citas_ev=[{"fecha": g["fecha"], "tipo": g["tipo"], "valor": g["valor"]}]), CORTE, kb)
    assert r["estado_clinico"] == "evento_fuera_de_ventana" and r["categoria"] == "baja"
    # y el control impide que eso baje al paciente sin un humano
    motivos = controles.evaluar([(resp(), {}, [])], [r], puntaje.puntuar(p, CORTE))
    assert any(m["motivo"] == "bajaria" for m in motivos)


def test_medicion_sube_solo_con_umbral_con_fuente():
    p = next(x for x in app.perfiles().values() if x["lista_espera"]["diagnostico_cie10"] == "E11" and x["lista_espera"]["prioridad_inicial"] == "baja")
    cita = [{"fecha": "2026-09-01", "tipo": "HbA1c", "valor": "9.5"}]
    kb_sin = copy.deepcopy(KB)
    kb_sin["diagnosticos"]["E11"]["medicion"]["umbral"] = {"valor": None, "sentido": "mayor_igual", "estado": "a_validar_por_medico", "fuente": "sin fuente"}
    sin = decisor.decidir(p, resp(tend="empeora", citas_tend=cita), CORTE, kb_sin)
    assert sin["categoria"] == "baja" and any(x["motivo"] == "medicion_empeora" for x in sin["revision"])   # sin fuente: solo revisión
    u = KB["diagnosticos"]["E11"]["medicion"]["umbral"]
    assert u["estado"] == "con_fuente" and u["valor"] == 7          # guía MINSAL DM2: compensado si HbA1c < 7 %
    con = decisor.decidir(p, resp(tend="empeora", citas_tend=cita), CORTE, KB)
    assert con["categoria"] == "media" and any("pág. 101" in r["fuente"] for r in con["razones"] if r["factor"] == "medicion")
    estable = decisor.decidir(p, resp(tend="estable", citas_tend=cita), CORTE, KB)
    assert estable["categoria"] == "baja"                           # supera el umbral pero no empeora: no sube


# ---------- R: orden Ord. 536 sin LACE ----------
def test_orden_536_no_usa_lace():
    a = {"id_paciente": "A", "categoria": "media", "riesgo_vital": False, "grupo_proteccion": None, "dias_espera": 200, "lace": {"total": 9}}
    b = {"id_paciente": "B", "categoria": "media", "riesgo_vital": False, "grupo_proteccion": None, "dias_espera": 300, "lace": {"total": 0}}
    assert sorted([a, b], key=decisor.clave_orden_536)[0]["id_paciente"] == "B"     # más días esperando primero, LACE no cuenta


# ---------- R: base de conocimiento auditable ----------
def test_cada_valor_tiene_fuente_o_esta_a_validar():
    for cie, d in KB["diagnosticos"].items():
        if d.get("fila_descompensado"):
            assert d["fila_descompensado"]["pagina"] and d["estado"] in ("con_fuente", "a_validar_por_medico")
        for v in d["ventanas"].values():
            assert v["estado"] == "con_fuente" and v["valor"] and v["fuente"]
        if d.get("medicion"):
            u = d["medicion"]["umbral"]
            assert u["estado"] in ("con_fuente", "a_validar_por_medico") and (u["valor"] is None) == (u["estado"] != "con_fuente")
    assert KB["pendientes_medicos"]


def test_esquema_sin_referencias_y_envoltorio_corregido():
    assert "$ref" not in json.dumps(rubrica.HERRAMIENTA) and "$defs" not in json.dumps(rubrica.HERRAMIENTA)
    p = perfil("PAC-HLF-00002")
    buena = rubrica.respuesta_determinista(rubrica.historial(p, CORTE), decisor.kb_diagnostico(KB, "I20"))
    r, meta = rubrica.leer_rubrica(p, CORTE, decisor.kb_diagnostico(KB, "I20"), rubrica.ClienteFalso({"valor": buena}))
    assert r is not None and meta["envoltorio_corregido"]
    r, meta = rubrica.leer_rubrica(p, CORTE, decisor.kb_diagnostico(KB, "I20"), rubrica.ClienteFalso({"otra": {"x": 1}}))
    assert r is None and "json_invalido" in meta["error"]          # solo se desenvuelve si adentro están las preguntas


def test_prompt_no_ve_etiquetas_medicas():
    sistema, texto, _ = rubrica.armar_prompt(perfil("PAC-HLF-00002"), CORTE, decisor.kb_diagnostico(KB, "I20"))
    for prohibido in ("prioridad_medico", "comentario", "clave_motor"):
        assert prohibido not in (sistema + texto)


# ---------- R: integración detrás de ALGORITMO ----------
def test_api_con_rubrica_aplica_evaluacion_vigente_y_reglas_sin_cambios():
    pid = "PAC-HLF-00002"
    try:
        os.environ["ALGORITMO"] = "rubrica"
        app._llm["cliente"] = oraculo(pid)
        res = app.handler({"requestContext": {"http": {"method": "POST"}}, "rawPath": f"/pacientes/{pid}/evaluar",
                           "body": json.dumps({"fecha_corte": "2026-10-13"})})
        ev = json.loads(res["body"])["evaluacion"]
        assert res["statusCode"] == 200 and ev["categoria_final"] == "alta" and ev["categoria_rubrica"] == "baja"
        assert ev["requiere_revision"] and any(m["motivo"] == "bajaria" for m in ev["controles"])   # fuera de ventana: decide un humano
        d = json.loads(app.handler({"requestContext": {"http": {"method": "GET"}}, "rawPath": "/pacientes",
                                    "queryStringParameters": {"fecha_corte": "2026-10-13"}})["body"])
        f = next(p for p in d["pacientes"] if p["id_paciente"] == pid)
        assert f["algoritmo"] == "rubrica" and f["categoria"] == "alta" and f["rubrica"]["requiere_revision"]
        assert any("bajaria" in s["motivo"] for s in f["revision_sugerida"])
        otro = next(p for p in d["pacientes"] if p["id_paciente"] != pid)
        assert otro["algoritmo"].startswith("reglas")
    finally:
        os.environ.pop("ALGORITMO", None)
        app._llm["cliente"] = None
    d = json.loads(app.handler({"requestContext": {"http": {"method": "GET"}}, "rawPath": "/pacientes",
                                "queryStringParameters": {"fecha_corte": "2026-10-13"}})["body"])
    assert "algoritmo" not in d["pacientes"][0]     # con reglas no aparecen campos nuevos


def test_evento_nuevo_dispara_la_reevaluacion():
    pid = next(p["id_paciente"] for p in app.lista(CORTE)["pacientes"] if p["diagnostico_cie10"] == "J44" and not p["riesgo_vital"])
    try:
        os.environ["ALGORITMO"] = "rubrica"
        app._llm["cliente"] = rubrica.ClienteFalso(lambda texto: rubrica.respuesta_determinista(
            rubrica.historial(app.perfiles_combinados()[0][pid], CORTE), decisor.kb_diagnostico(KB, "J44")))
        res = app.handler({"requestContext": {"http": {"method": "POST"}}, "rawPath": "/eventos", "body": json.dumps(
            {"id_paciente": pid, "tipo_evento": "hospitalizacion", "subtipo": "ingreso hospitalario", "fecha_corte": "2026-10-13"})})
        b = json.loads(res["body"])
        assert res["statusCode"] == 200 and b["evaluacion"]["id_paciente"] == pid
        assert b["evaluacion"]["categoria_final"] == "alta" and b["paciente"]["algoritmo"] == "rubrica"
    finally:
        os.environ.pop("ALGORITMO", None)
        app._llm["cliente"] = None
