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
    assert r["categoria"] == "alta" and "a validar" in onc["valor"] and "88, 94, 95, 111" in onc["fuente"]
    assert r["estado_clinico"] == sin["estado_clinico"] and r["riesgo_vital"] == sin["riesgo_vital"]   # no es una descompensación


def test_con_reglas_el_informe_funciona_como_antes():
    pid = paciente()
    res = app.handler({"requestContext": {"http": {"method": "POST"}}, "rawPath": f"/pacientes/{pid}/informe",
                       "body": json.dumps({"texto": "Se hospitaliza en medicina por neumonía.", "fecha_corte": CORTE.isoformat()})})
    r = json.loads(res["body"])
    assert "registrados" not in r and r["eventos"][0]["tipo_evento"] == "hospitalizacion"   # propone; no registra
