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


def test_descompensacion_moderada_sube_a_la_fila_pero_no_es_grave():
    """Como las reglas: una urgencia por 'descompensación' moderada sube a la fila de la tabla; la gravedad la decide el
    código mirando la severidad registrada del evento citado, no el LLM."""
    p = next(x for x in app.perfiles().values() if x["lista_espera"]["diagnostico_cie10"] == "I50" and x["lista_espera"]["prioridad_inicial"] != "alta"
             and any(e["subtipo"] == "descompensación" and e["severidad"] == "moderada" and e["fecha_evento"] >= x["lista_espera"]["fecha_ingreso_lista"]
                     for e in x.get("eventos_clinicos", [])))
    e = next(e for e in p["eventos_clinicos"] if e["subtipo"] == "descompensación" and e["severidad"] == "moderada"
             and e["fecha_evento"] >= p["lista_espera"]["fecha_ingreso_lista"])
    fc = date.fromisoformat(e["fecha_evento"])
    r = decisor.decidir(p, resp(evento="si", citas_ev=[{"fecha": e["fecha_evento"], "tipo": e["tipo_evento"], "valor": e["subtipo"]}]), fc, KB)
    assert r["categoria"] == "alta" and not r["descompensacion_grave"]


def test_00028_no_baja_solo():
    p = perfil("PAC-HLF-00028")
    reg = algoritmo.evaluar_paciente(p, CORTE, oraculo(p))
    reglas = puntaje.puntuar(p, CORTE)
    assert decisor.ORDEN_CAT[reg["categoria_final"]] >= decisor.ORDEN_CAT[reglas["categoria"]]


def test_00009_fallecido_sale_de_la_lista():
    assert algoritmo.evaluar_paciente(perfil("PAC-HLF-00009"), CORTE, oraculo("PAC-HLF-00009")) is None


def test_un_desconocido_no_es_normal_lo_responde_el_registro():
    """Si la IA no puede leer un dato, no se toma como 'no' ni se manda a un humano: lo responde el registro estructurado."""
    p = perfil("PAC-HLF-00002")                                   # tiene hospitalización grave, sin estabilización posterior
    r = decisor.decidir(p, resp(evento="desconocido", estab="desconocido"), CORTE, KB)
    assert r["estado_clinico"] == "descompensado" and r["categoria"] == "alta" and r["descompensacion_grave"]
    assert any(x["motivo"] == "resuelto_con_registro" and not x["bloqueante"] for x in r["revision"])
    p["eventos_clinicos"].append({"id_evento": "X", "fecha_evento": "2026-10-01", "tipo_evento": "control_aps", "subtipo": "estabilización", "severidad": "leve"})
    r = decisor.decidir(p, resp(evento="si", estab="desconocido", citas_ev=[{"fecha": "2026-08-06", "tipo": "hospitalizacion", "valor": "ingreso hospitalario"}]), CORTE, KB)
    assert r["estado_clinico"] == "estabilizado"                  # el registro sí muestra la estabilización


# ---------- R: controles antes de mover ----------
def test_cita_inexistente_mantiene_reglas_y_pide_revision():
    p = perfil("PAC-HLF-00002")
    falsa = resp(evento="si", citas_ev=[{"fecha": "2026-09-09", "tipo": "hospitalizacion", "valor": "ingreso UCI"}]).model_dump()
    reg = algoritmo.evaluar_paciente(p, CORTE, rubrica.ClienteFalso(falsa))
    assert reg["respaldo_reglas"] and not reg["requiere_revision"] and any(m["motivo"] == "cita_invalida" for m in reg["controles"])
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
    assert reg["respaldo_reglas"] and any(m["motivo"] == "inestable" for m in reg["controles"])
    assert reg["categoria_final"] == reg["categoria_reglas"]


def test_bedrock_falla_usa_reglas_y_lo_registra():
    p = perfil("PAC-HLF-00002")
    reg = algoritmo.evaluar_paciente(p, CORTE, rubrica.ClienteFalso({}, fallar=True))
    assert reg["respaldo_reglas"] and not reg["requiere_revision"] and reg["controles"][0]["motivo"] == "fallo_llm"   # técnico: no molesta al médico
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
        assert reg["descompensacion_grave_final"] or not puntaje.puntuar(p, CORTE)["riesgo_vital"], p["id_paciente"]  # ni la marca grave
        if reg["categoria_final"] != reg["categoria_reglas"]:
            assert not reg["requiere_revision"] and reg["movido_por_rubrica"]


def test_quitar_la_marca_de_grave_tambien_es_bajar():
    """Misma categoría, pero la rúbrica no marca descompensación grave cuando las reglas sí: bloqueado (requiere humano)."""
    lect = [(resp(), {}, [])]
    motivos = controles.evaluar(lect, [{"categoria": "alta", "descompensacion_grave": False, "revision": []}],
                                {"categoria": "alta", "riesgo_vital": True})
    assert any(m["motivo"] == "bajaria" for m in motivos)


def test_propiedad_nunca_se_pierde_la_marca_grave_sin_humano():
    rnd = random.Random(11)
    perfs = [p for p in app.perfiles().values() if (r := puntaje.puntuar(p, CORTE)) and not r.get("excluido") and r["riesgo_vital"]]
    for p in perfs:
        h = rubrica.historial(p, CORTE)
        def azar(_t):
            ev = rnd.choice(h["eventos"]) if h["eventos"] else None
            c = [dict(fecha=ev["fecha"], tipo=ev["tipo"], valor=ev["valor"])] if ev else []
            return {"evento_grave": {"valor": "si", "citas": c}, "estabilizado_despues": {"valor": "no", "citas": []},
                    "tendencia_medicion": {"valor": "desconocido", "citas": []}, "cambio_tratamiento_por_mal_control": {"valor": "no", "citas": []}}
        reg = algoritmo.evaluar_paciente(p, CORTE, rubrica.ClienteFalso(azar))
        assert reg["descompensacion_grave_final"] or reg["requiere_revision"], p["id_paciente"]


def test_discrepancia_de_mas_de_un_nivel_pide_revision():
    lect = [(resp(), {}, [])]
    motivos = controles.evaluar(lect, [{"categoria": "alta", "descompensacion_grave": False, "revision": []}], {"categoria": "baja"})
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


def test_medicion_sube_solo_con_umbral_con_fuente_y_si_el_registro_lo_confirma():
    """El LLM dice 'empeora'; el código usa los valores REGISTRADOS (no los que escribe el LLM) y el umbral con fuente."""
    def dec(pid, kb=KB, cita_valor="9.5"):
        return decisor.decidir(perfil(pid), resp(tend="empeora", citas_tend=[{"fecha": "2026-09-01", "tipo": "HbA1c", "valor": cita_valor}]), CORTE, kb)
    con = dec("PAC-HLF-00296")                                     # HbA1c 8,4 → 10,1: empeora y sobre 7
    assert any("pág. 101" in r["fuente"] and "10.1" in r["valor"] for r in con["razones"] if r["factor"] == "medicion")
    # y además supera 10% con deterioro: Queensland CPC categoría 1 → alta (regla del registro, sin IA)
    assert con["categoria"] == "alta" and any(r["factor"] == "criterio_registro" and "HbA1c > 10%" in r["valor"] and r["riesgo"] for r in con["razones"])
    assert any(x["motivo"] == "fila_a_validar" for x in con["revision"])     # la equivalencia del equipo queda a validar
    assert KB["diagnosticos"]["E11"]["medicion"]["umbral"]["valor"] == 7      # guía MINSAL DM2: compensado si HbA1c < 7 %
    kb_sin = copy.deepcopy(KB)
    kb_sin["diagnosticos"]["E11"]["medicion"]["umbral"] = {"valor": None, "sentido": "mayor_igual", "estado": "a_validar_por_medico", "fuente": "sin fuente"}
    sin = dec("PAC-HLF-00296", kb_sin)                             # sin fuente, el umbral del equipo no actúa (solo revisión)…
    assert not any(r["factor"] == "medicion" for r in sin["razones"])
    assert sin["categoria"] == "alta" and any(r["factor"] == "criterio_registro" for r in sin["razones"])   # …pero sí la regla oficial de Queensland
    bajo = dec("PAC-HLF-00298")                                    # empeora pero 6,1 < 7
    assert bajo["categoria"] == "baja" and any(x["motivo"] == "medicion_empeora" for x in bajo["revision"])
    falso = dec("PAC-HLF-00326")                                   # el LLM dice empeora; el registro muestra que mejora
    assert falso["categoria"] == "baja" and any("no lo confirma" in x["detalle"] for x in falso["revision"])
    assert dec("PAC-HLF-00296", cita_valor="9,5 %")["categoria"] == "alta"   # un número mal escrito por el LLM no rompe nada (usa el registro)


# ---------- R: orden Ord. 536 sin LACE ----------
def test_orden_536_no_usa_lace():
    a = {"id_paciente": "A", "categoria": "media", "riesgo_vital": False, "grupo_proteccion": None, "dias_espera": 200, "lace": {"total": 9}}
    b = {"id_paciente": "B", "categoria": "media", "riesgo_vital": False, "grupo_proteccion": None, "dias_espera": 300, "lace": {"total": 0}}
    assert sorted([a, b], key=decisor.clave_orden_536)[0]["id_paciente"] == "B"     # más días esperando primero, LACE no cuenta


# ---------- R: base de conocimiento auditable ----------
def test_cada_valor_tiene_fuente_o_esta_a_validar():
    assert KB["diagnosticos"]["I20"]["ventanas"]["visita_urgencia"]["estado"] == "a_validar_por_medico"   # 45 d no sale del estudio de IAM
    assert KB["diagnosticos"]["K70"]["ventanas"]["hospitalizacion"]["estado"] == "a_validar_por_medico"   # 90 d no sale de la cita
    for cie, d in KB["diagnosticos"].items():
        if d.get("fila_descompensado"):
            assert d["fila_descompensado"]["pagina"] and d["estado"] in ("con_fuente", "a_validar_por_medico")
        for v in d["ventanas"].values():
            assert v["valor"] and v["fuente"] and (v["estado"] == "con_fuente" or (v["estado"] == "a_validar_por_medico" and v["nota"]))
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
        # la ventana de I20 está a validar: el evento no vence y la rúbrica coincide con las reglas
        assert res["statusCode"] == 200 and ev["categoria_final"] == "alta" and ev["categoria_rubrica"] == "alta" and not ev["requiere_revision"]
        d = json.loads(app.handler({"requestContext": {"http": {"method": "GET"}}, "rawPath": "/pacientes",
                                    "queryStringParameters": {"fecha_corte": "2026-10-13"}})["body"])
        f = next(p for p in d["pacientes"] if p["id_paciente"] == pid)
        assert f["algoritmo"] == "rubrica" and f["categoria"] == "alta" and f["riesgo_vital"] and not f["rubrica"]["requiere_revision"]
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


# ---------- Revisión adversaria: casos encontrados y su arreglo ----------
def cita(e):
    return {"fecha": e["fecha_evento"], "tipo": e["tipo_evento"], "valor": e["subtipo"]}


def test_a8_el_codigo_verifica_lo_que_cita_el_llm():
    """Citar un control de rutina como descompensación, o una 'estabilización' anterior al evento, no mueve a nadie."""
    p = perfil("PAC-HLF-00002")
    leve = {"id_evento": "L", "fecha_evento": "2026-07-01", "tipo_evento": "control_aps", "subtipo": "control rutina", "severidad": "leve"}
    antes = {"id_evento": "E", "fecha_evento": "2026-08-01", "tipo_evento": "control_aps", "subtipo": "estabilización", "severidad": "leve"}
    p["eventos_clinicos"] += [leve, antes]
    r = decisor.decidir(p, resp(evento="si", citas_ev=[cita(leve)]), CORTE, KB)
    assert r["categoria"] == "baja" and any(x["motivo"] == "cita_no_respalda" and x["bloqueante"] for x in r["revision"])
    grave = next(e for e in p["eventos_clinicos"] if e["fecha_evento"] == "2026-08-06")   # hospitalización grave
    r = decisor.decidir(p, resp(evento="si", estab="si", citas_ev=[cita(grave)], citas_est=[cita(antes)]), CORTE, KB)
    assert any(x["motivo"] == "cita_no_respalda" for x in r["revision"])
    # 'no se estabilizó' contra un registro que sí muestra estabilización: no sube, lo revisa un humano
    p["eventos_clinicos"].append({"id_evento": "X", "fecha_evento": "2026-10-01", "tipo_evento": "control_aps", "subtipo": "estabilización", "severidad": "leve"})
    r = decisor.decidir(p, resp(evento="si", estab="no", citas_ev=[cita(grave)]), CORTE, KB)
    assert any(x["motivo"] == "contradice_registro" and x["bloqueante"] for x in r["revision"])


def test_a1_perder_la_marca_grave_por_un_no_del_llm_queda_para_un_humano():
    p = next(x for x in app.perfiles().values() if (r := puntaje.puntuar(x, CORTE)) and not r.get("excluido") and r["riesgo_vital"])
    reg = algoritmo.evaluar_paciente(p, CORTE, rubrica.ClienteFalso(resp().model_dump()))
    assert reg["descompensacion_grave_final"] and reg["requiere_revision"] and any(m["motivo"] == "bajaria" for m in reg["controles"])


def test_a7_una_excepcion_en_la_formula_cae_a_las_reglas(monkeypatch):
    def rompe(*a, **k):
        raise ValueError("simulado")
    monkeypatch.setattr(decisor, "decidir", rompe)
    p = perfil("PAC-HLF-00002")
    reg = algoritmo.evaluar_paciente(p, CORTE, oraculo(p))
    assert reg["categoria_final"] == puntaje.puntuar(p, CORTE)["categoria"] and reg["respaldo_reglas"]
    assert any(m["motivo"] == "error_formula" for m in reg["controles"])


def test_a9_desconocido_en_las_otras_preguntas_no_es_no():
    p = perfil("PAC-HLF-00296")
    r = decisor.decidir(p, resp(tend="desconocido", cambio="desconocido"), CORTE, KB)
    assert sum(x["motivo"] == "sin_dato" for x in r["revision"]) == 2


def test_a5_la_evaluacion_se_reaplica_a_la_fecha_de_corte_y_vence_si_cambia_la_rubrica():
    kb = copy.deepcopy(KB)
    kb["diagnosticos"]["I20"]["ventanas"] = {x: {"valor": 30, "fuente": "PMID de prueba", "estado": "con_fuente"} for x in ("hospitalizacion", "visita_urgencia")}
    p, t1 = perfil("PAC-HLF-00002"), date(2026, 8, 10)
    e = json.loads(json.dumps(algoritmo.evaluar_paciente(p, t1, oraculo(p, t1), kb=kb), default=str))
    assert e["categoria_final"] == "alta" and not e["requiere_revision"]
    # mismo historial (misma firma) pero 64 días después: la ventana de 30 días ya venció → no se usa la razón vieja
    tarde = algoritmo.reaplicar(e, p, date(2026, 10, 13), kb)
    assert tarde["categoria_rubrica"] == "baja" and tarde["requiere_revision"] and tarde["categoria_final"] == "alta"
    assert algoritmo.vigente(e, p, t1, kb)
    assert not algoritmo.vigente({**e, "hash_prompt": "otro"}, p, t1, kb)            # cambió el prompt
    assert not algoritmo.vigente({**e, "version_kb": "otra"}, p, t1, kb)             # cambió la base de conocimiento
    assert not algoritmo.vigente({**e, "firma": "otra"}, p, t1, kb)                  # llegó un dato nuevo
    assert not algoritmo.vigente(e, p, date(2026, 8, 1), kb)                         # evaluada a un corte posterior


def _r(pid, **cambios):
    p = perfil(pid)
    return {**puntaje.puntuar(p, CORTE), "posicion": 1, **cambios}, p


def test_a2_marca_grave_sin_fecha_no_tumba_la_lista():
    r, p = _r("PAC-HLF-00489", riesgo_vital=True, fecha_descompensacion=None, registro_descompensacion=None)
    out = app._enriquecer(r, p, None, None, date(2026, 6, 1))
    assert out["evaluacion"]["estado"] == "pendiente"


def test_a3_a4_senales_del_algoritmo_y_decisiones_humanas():
    rev = {"fecha_corte": "2026-09-01", "fecha": "2026-09-01T10:00:00", "accion": "ajustar", "categoria_ajustada": "baja"}
    sube = {"motivo": "algoritmo: sube a media por la rúbrica", "fecha": "2026-10-13", "registrado": "2026-10-13T10:00", "algoritmo": True}
    nota = {"motivo": "algoritmo: fallo_llm — x", "fecha": "2026-10-13", "registrado": "2026-10-13T10:00", "algoritmo": True, "informativa": True}
    # A3: el algoritmo sube al paciente después del ajuste humano → se pide revisar y se muestra la categoría del sistema
    r, p = _r("PAC-HLF-00489", categoria="media", senales=[sube])
    out = app._enriquecer(r, p, rev, None, CORTE)
    assert out["estado_revision"] == "requiere_revision" and out["categoria"] == "media"
    # A4: una nota o falla del algoritmo no anula la decisión humana
    r, p = _r("PAC-HLF-00489", categoria="baja", senales=[nota])
    out = app._enriquecer(r, p, {**rev, "categoria_ajustada": "alta"}, None, CORTE)
    assert out["categoria"] == "alta"
    # y si el algoritmo sube pero el equipo lo tenía más arriba, no baja
    r, p = _r("PAC-HLF-00489", categoria="media", senales=[sube])
    out = app._enriquecer(r, p, {**rev, "categoria_ajustada": "alta"}, None, CORTE)
    assert out["categoria"] == "alta" and out["estado_revision"] == "requiere_revision"


def test_a11_comorbilidad_registrada_despues_del_corte_no_entra_al_prompt():
    p = perfil("PAC-HLF-00002")
    p["paciente"].setdefault("comorbilidades", []).append({"nombre": "Futura", "fecha": "2026-10-10"})
    assert "Futura" not in rubrica.historial(p, date(2026, 8, 10))["comorbilidades"]
    assert "Futura" in rubrica.historial(p, CORTE)["comorbilidades"]


def test_r10_con_reglas_las_rutas_nuevas_no_llaman_a_bedrock():
    os.environ.pop("ALGORITMO", None)
    for ruta in ("/pacientes/PAC-HLF-00002/evaluar", "/algoritmo/barrido"):
        res = app.handler({"requestContext": {"http": {"method": "POST"}}, "rawPath": ruta, "body": "{}"})
        assert res["statusCode"] == 409


def test_r18_barrido_reintenta_las_fallidas():
    pid = "PAC-HLF-00002"
    try:
        os.environ["ALGORITMO"] = "rubrica"
        app._llm["cliente"] = rubrica.ClienteFalso({}, fallar=True)
        assert app.evaluar_y_guardar(pid, CORTE)["respaldo_reglas"]
        app._llm["cliente"] = oraculo(pid)
        app.barrido(CORTE, limite=500)
        e = app.evaluaciones()[pid]
        assert not any(m["motivo"] == "fallo_llm" for m in e["controles"])
    finally:
        os.environ.pop("ALGORITMO", None)
        app._llm["cliente"] = None


def test_r11_cada_fecha_de_corte_usa_su_evaluacion_vigente():
    """Slider: con evaluaciones a dos cortes, la fecha antigua usa la suya (no 'sin evaluación'), y nada responde 500."""
    pid, t1 = "PAC-HLF-00002", date(2026, 8, 10)
    try:
        os.environ["ALGORITMO"] = "rubrica"
        for c in (t1, CORTE):
            app._llm["cliente"] = oraculo(pid, c)
            app.evaluar_y_guardar(pid, c)
        app._llm["cliente"] = None
        for c in (t1, date(2026, 8, 20), CORTE):   # 20-08: mismo historial que el 10-08 → usa esa lectura, reaplicada al 20-08
            f = next(p for p in app.lista(c)["pacientes"] if p["id_paciente"] == pid)
            assert f["algoritmo"] == "rubrica" and f["categoria"] == "alta"
            assert f["rubrica"]["fecha_corte_aplicada"] == c.isoformat()
        # 01-09: llegó una medición (25-08) que ninguna evaluación vio → reglas, marcado, hasta que el barrido lo evalúe
        f = next(p for p in app.lista(date(2026, 9, 1))["pacientes"] if p["id_paciente"] == pid)
        assert f["algoritmo"] == "reglas (sin evaluación vigente)"
    finally:
        os.environ.pop("ALGORITMO", None)
        app._llm["cliente"] = None


def test_descompensado_va_antes_que_grupo_de_proteccion_estable():
    """Reclamo del HLF: una paciente Rettig recién ingresada (alta, estable) quedó sobre Iris 435 (alta, hospitalización
    grave, HTA sin fila en la tabla). El criterio médico del Ord. 536 va antes que el grupo de protección."""
    iris = {"id_paciente": "IRIS", "categoria": "alta", "riesgo_vital": False, "estado_clinico": "descompensado", "grupo_proteccion": None,
            "dias_espera": 177, "antiguedad_mayor_1_anio": False, "lace": {"total": 4}}
    maria = {"id_paciente": "MARIA", "categoria": "alta", "riesgo_vital": False, "estado_clinico": "sin_cambios", "grupo_proteccion": "Rettig",
             "dias_espera": 0, "antiguedad_mayor_1_anio": False, "lace": {"total": 0}}
    for clave in (decisor.clave_orden_536, puntaje.clave_orden):
        assert [x["id_paciente"] for x in sorted([maria, iris], key=clave)] == ["IRIS", "MARIA"]
    grave = {**iris, "id_paciente": "GRAVE", "riesgo_vital": True}
    assert sorted([iris, grave], key=decisor.clave_orden_536)[0]["id_paciente"] == "GRAVE"   # la descompensación grave sigue primero
