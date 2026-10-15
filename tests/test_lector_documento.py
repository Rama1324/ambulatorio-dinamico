"""Lector de documentos con IA: el LLM lee, el código verifica y la tabla del HLF decide. Sin Bedrock (ClienteFalso)."""
import copy
import json
import os
import sys
from datetime import date

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["LOCAL"] = "1"; os.environ.setdefault("DATA_DIR", os.path.join(RAIZ, "data")); os.environ.pop("MODEL_ID", None)
sys.path.insert(0, os.path.join(RAIZ, "lambda"))
import app  # noqa: E402
import lector_documento as ld  # noqa: E402
import puntaje  # noqa: E402
import rubrica  # noqa: E402

CORTE = date(2026, 10, 13)
BIOPSIA = ("Informe de anatomía patológica. Fecha: 2026-10-10.\nPaciente con nódulo pulmonar en estudio.\n"
           "Biopsia transbronquial: adenocarcinoma pulmonar moderadamente diferenciado.")


def cliente(*hallazgos):
    return rubrica.ClienteFalso({"hallazgos": [{"tipo": t, "cita": c} for t, c in hallazgos]})


def paciente(esp="Broncopulmonar", cat="baja"):
    return next(p["id_paciente"] for p in app.lista(CORTE)["pacientes"] if p["especialidad"] == esp and p["categoria"] == cat)


def informe(pid, texto, cli):
    try:
        os.environ["ALGORITMO"] = "rubrica"
        app._llm["cliente"] = cli
        res = app.handler({"requestContext": {"http": {"method": "POST"}}, "rawPath": f"/pacientes/{pid}/informe",
                           "body": json.dumps({"texto": texto, "fecha_corte": CORTE.isoformat()})})
        return res["statusCode"], json.loads(res["body"])
    finally:
        os.environ.pop("ALGORITMO", None)
        app._llm["cliente"] = None


def test_biopsia_con_cancer_sube_sola_a_alta_con_su_fuente():
    pid = paciente()
    s, r = informe(pid, BIOPSIA, cliente(("cancer_confirmado", "adenocarcinoma pulmonar moderadamente diferenciado")))
    assert s == 200 and r["registrados"] and r["registrados"][0]["tipo_evento"] == "hallazgo_oncologico"
    assert r["registrados"][0]["fecha_evento"] == "2026-10-10"                       # fecha tomada del documento
    assert r["paciente"]["categoria"] == "alta" and r["posicion_despues"] < r["posicion_antes"]
    onc = [x for x in r["paciente"]["razones"] if x["factor"] == "oncologico"]
    assert onc and "pág. 95" in onc[0]["fuente"] and "adenocarcinoma" in onc[0]["valor"]
    assert not r["paciente"]["riesgo_vital"]                                         # cáncer no es "descompensación grave"


def test_cita_inventada_o_sin_cancer_no_registra_nada():
    pid = paciente()
    s, r = informe(pid, BIOPSIA, cliente(("cancer_confirmado", "carcinoma de células pequeñas"),       # no está en el texto
                                         ("sospecha_cancer", "Paciente con nódulo pulmonar en estudio")))  # no menciona cáncer
    assert not r["registrados"] and len(r["descartados"]) >= 2


def test_negacion_no_se_registra_sola():
    pid = paciente()
    texto = "Control broncopulmonar. TAC sin cambios, se descarta neoplasia pulmonar."
    s, r = informe(pid, texto, cliente(("sospecha_cancer", "neoplasia pulmonar")))
    assert not r["registrados"] and r["eventos"] and "negación" in r["eventos"][0]["motivo"]


def test_antecedente_en_remision_no_sube():
    pid = paciente()
    texto = "Antecedente de cáncer de mama tratado en 2015, en remisión completa."
    s, r = informe(pid, texto, cliente(("antecedente_cancer", "cáncer de mama tratado en 2015, en remisión completa")))
    assert not r["registrados"] and r["informativos"] and "pág. 102" in r["informativos"][0]["nota"]


def test_estabilizacion_nunca_se_registra_sola():
    pid = paciente()
    s, r = informe(pid, "Control: paciente estable, buena respuesta al tratamiento.", cliente(("estabilizacion", "paciente estable")))
    assert not r["registrados"] and r["eventos"][0]["subtipo"] == "estabilización"


def test_lecturas_que_no_coinciden_quedan_como_propuesta():
    pid = paciente()
    n = {"k": 0}
    def alterna(_t):
        n["k"] += 1
        return {"hallazgos": [{"tipo": "cancer_confirmado", "cita": "adenocarcinoma pulmonar"}] if n["k"] % 3 else []}
    s, r = informe(pid, BIOPSIA, rubrica.ClienteFalso(alterna))
    assert not r["registrados"] and "no es estable" in r["eventos"][0]["motivo"]


def test_documento_de_otro_paciente_no_registra():
    pid = paciente()
    otro = "PAC-HLF-00001" if pid != "PAC-HLF-00001" else "PAC-HLF-00002"
    s, r = informe(pid, BIOPSIA + f"\nPaciente {otro}.", cliente(("cancer_confirmado", "adenocarcinoma pulmonar")))
    assert not r["registrados"] and r["otro_paciente"]


def test_bedrock_falla_no_registra_y_lo_dice():
    pid = paciente()
    s, r = informe(pid, BIOPSIA, rubrica.ClienteFalso({}, fallar=True))
    assert s == 200 and not r["registrados"] and "error" in r["mensaje"]


def test_cancer_en_especialidad_sin_fila_propia_sube_y_queda_a_validar():
    p = copy.deepcopy(app.perfiles()[paciente("Cardiología", "baja")])
    sin = puntaje.puntuar(p, CORTE)
    p["eventos_clinicos"].append({"id_evento": "X", "fecha_evento": "2026-10-01", "tipo_evento": "hallazgo_oncologico",
                                  "subtipo": "sospecha de cáncer", "severidad": "grave", "detalle": "lesión sospechosa de malignidad"})
    r = puntaje.puntuar(p, CORTE)
    onc = next(x for x in r["razones"] if x["factor"] == "oncologico")
    assert r["categoria"] == "alta" and "todo cáncer" in onc["valor"] and "88, 94, 95, 111" in onc["fuente"]
    assert r["estado_clinico"] == sin["estado_clinico"] and r["riesgo_vital"] == sin["riesgo_vital"]   # no es una descompensación


def test_con_reglas_el_informe_funciona_como_antes():
    pid = paciente()
    res = app.handler({"requestContext": {"http": {"method": "POST"}}, "rawPath": f"/pacientes/{pid}/informe",
                       "body": json.dumps({"texto": "Se hospitaliza en medicina por neumonía.", "fecha_corte": CORTE.isoformat()})})
    r = json.loads(res["body"])
    assert "registrados" not in r and r["eventos"][0]["tipo_evento"] == "hospitalizacion"   # propone; no registra


def test_revisar_archivo_dice_si_el_paciente_sube_baja_o_queda_igual_y_por_que():
    import base64
    pid = paciente()
    csv = (f"id_paciente,fecha_evento,tipo_evento,subtipo,detalle\n{pid},2026-10-12,hospitalizacion,ingreso UCI,Ingreso a UCI\n"
           f"PAC-HLF-00009,2026-10-12,control_aps,control,Control\n")
    s, r = app.post_importar({"archivos": [{"nombre": "eventos.csv", "contenido_base64": base64.b64encode(csv.encode()).decode()}],
                              "fecha_corte": CORTE.isoformat()})
    x = next(i for i in r["impacto"] if i["id_paciente"] == pid)
    assert x["cambio"] == "sube" and x["posicion_despues"] < x["posicion_antes"]
    assert any("ingreso UCI" in m["valor"] for m in x["por_que"]) and any(m["factor"] == "prioridad" for m in x["por_que"])
    assert not r["cargado"] and not any(e["subtipo"] == "ingreso UCI" and e["fecha_evento"] == "2026-10-12"
                                        for e in app.perfiles_combinados()[0][pid]["eventos_clinicos"])   # nada se guardó


# ---------- motivo del evento: amputación ≠ dolor de dedo; relacionado o no con la enfermedad por la que espera ----------
def test_evento_grave_no_relacionado_no_sube_la_prioridad_de_su_especialidad():
    p = copy.deepcopy(app.perfiles()[paciente("Cardiología", "baja")])
    antes = puntaje.puntuar(p, CORTE)
    p["eventos_clinicos"].append({"id_evento": "A", "fecha_evento": "2026-10-10", "tipo_evento": "hospitalizacion", "subtipo": "ingreso hospitalario",
                                  "severidad": "grave", "motivo": "amputación traumática de pierna", "relacionado": False})
    r = puntaje.puntuar(p, CORTE)
    assert r["categoria"] == antes["categoria"] and r["estado_clinico"] == antes["estado_clinico"] and not r["riesgo_vital"]
    assert any("sin relación" in s["motivo"] and "amputación" in s["motivo"] for s in r["senales"])   # queda visible para revisar
    p["eventos_clinicos"][-1]["relacionado"] = True                                                  # la misma hospitalización, por su cardiopatía
    assert puntaje.puntuar(p, CORTE)["estado_clinico"] == "descompensado"


def test_urgencia_leve_no_es_descompensacion():
    p = copy.deepcopy(app.perfiles()[paciente("Cardiología", "baja")])
    antes = puntaje.puntuar(p, CORTE)
    p["eventos_clinicos"].append({"id_evento": "D", "fecha_evento": "2026-10-10", "tipo_evento": "visita_urgencia", "subtipo": "triage ESI 4-5",
                                  "severidad": "leve", "motivo": "dolor de dedo"})
    r = puntaje.puntuar(p, CORTE)
    assert r["categoria"] == antes["categoria"] and r["estado_clinico"] == antes["estado_clinico"]


def test_ia_amputacion_en_paciente_cardiologico_no_lo_sube():
    pid = paciente("Cardiología", "baja")
    texto = "DAU urgencia 12/10/2026. Ingresa por accidente de tránsito con amputación traumática de pierna derecha. Se hospitaliza en traumatología."
    cli = rubrica.ClienteFalso({"hallazgos": [{"tipo": "hospitalizacion", "cita": "Se hospitaliza en traumatología", "motivo": "amputación traumática",
                                               "relacionado": "no"}]})
    s, r = informe(pid, texto, cli)
    assert r["registrados"] and r["registrados"][0]["relacionado"] is False
    assert r["paciente"]["categoria"] == "baja" and r["posicion_despues"] == r["posicion_antes"]
    assert any("sin relación" in x["motivo"] for x in r["paciente"]["revision_sugerida"])


def test_ia_descompensacion_relacionada_si_sube():
    pid = next(p["id_paciente"] for p in app.lista(CORTE)["pacientes"] if p["diagnostico_cie10"] == "I50" and p["categoria"] != "alta")
    texto = "Epicrisis 12/10/2026. Hospitalización por insuficiencia cardíaca descompensada con edema pulmonar."
    cli = rubrica.ClienteFalso({"hallazgos": [{"tipo": "hospitalizacion", "cita": "Hospitalización por insuficiencia cardíaca descompensada",
                                               "motivo": "insuficiencia cardíaca descompensada", "relacionado": "si"}]})
    s, r = informe(pid, texto, cli)
    assert r["registrados"] and r["registrados"][0].get("relacionado") is not False
    assert r["posicion_despues"] < r["posicion_antes"]
