"""Criterios clínicos por enfermedad (criterios_especialidad.json): la IA elige el criterio citando el texto, el código
verifica y aplica (solo sube; la urgencia prevalece). Sin Bedrock (ClienteFalso)."""
import json
import os
import sys
from datetime import date

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["LOCAL"] = "1"; os.environ.setdefault("DATA_DIR", os.path.join(RAIZ, "data")); os.environ.pop("MODEL_ID", None)
sys.path.insert(0, os.path.join(RAIZ, "lambda"))
import app  # noqa: E402
import criterios  # noqa: E402
import rubrica  # noqa: E402

CORTE = date(2026, 10, 13)


def responde(criterio, cita, urgencia="ninguna", cita_u=""):
    return rubrica.ClienteFalso({"criterio": criterio, "cita": cita, "urgencia": urgencia, "cita_urgencia": cita_u})


def ingresar(cie, prioridad, motivo, cli, nombre="Prueba criterios"):
    try:
        os.environ["ALGORITMO"] = "rubrica"
        app._llm["cliente"] = cli
        s, r = app.post_paciente({"nombre": nombre, "edad": 70, "sexo": "M", "diagnostico_cie10": cie, "prioridad_inicial": prioridad,
                                  "motivo_interconsulta": motivo, "fecha_corte": CORTE.isoformat()})
        return s, r
    finally:
        os.environ.pop("ALGORITMO", None)
        app._llm["cliente"] = None


def en_carril_de_urgencia(p):
    """Todos los que van antes también son urgencia (los tests comparten la memoria: puede haber otras urgencias)."""
    lista = app.lista(CORTE)["pacientes"]
    return all(q["urgencia_hoy"] for q in lista[:p["posicion"] - 1])


def test_json_completo_y_mapeado():
    kb = criterios.cargar()
    assert len(kb["kb"]["especialidades"]) == 5 and set(criterios.CIE10) <= set(kb["por_id"]) and len(criterios.CIE10) == 46
    registro = {"I50", "I20", "I10", "J44", "J45", "K70", "K21", "E11", "E03", "E66", "G40", "G43", "F32", "F41", "M17", "M54", "M75"}
    assert registro <= set(kb["por_cie"])                                 # los 17 diagnósticos del registro tienen criterios
    cat = app.catalogo()["diagnosticos"]
    assert {d["diagnostico_cie10"] for d in cat} == registro                # solo se ingresan diagnósticos del registro del hospital
    assert {d["especialidad"] for d in cat} == {"Cardiología", "Traumatología", "Endocrinología", "Salud Mental", "Broncopulmonar",
                                                "Neurología", "Gastroenterología"}
    assert criterios.enfermedad_de("F32")["id"] == "psiquiatria_07"        # la depresión del registro usa sus criterios


def test_criterio_alta_sube_y_explica():
    s, r = ingresar("M17", "media", "Gonartrosis derecha con masa de crecimiento rápido, sospecha de tumor.",
                    responde("alta.0", "sospecha de tumor"))
    p = r["paciente"]
    assert s == 200 and p["categoria"] == "alta" and r["criterio"]["criterio_id"] == "alta.0"
    assert any(x["factor"] == "criterio_clinico" and "sospecha de tumor" in x["valor"] for x in p["razones"])


def test_urgencia_prevalece_y_va_primero():
    s, r = ingresar("M54", "baja", "Lumbago con pérdida de control de esfínteres desde ayer.",
                    responde("alta.0", "pérdida de control de esfínteres", "urgencia.0", "pérdida de control de esfínteres desde ayer"))
    p = r["paciente"]
    assert p["categoria"] == "alta" and p["urgencia_hoy"] and p["contactar_hoy"] and en_carril_de_urgencia(p)
    assert p["razones"][0]["factor"] == "urgencia"


def test_criterio_baja_no_baja_a_nadie():
    s, r = ingresar("M17", "media", "Dolor leve que responde a analgesia, en manejo médico inicial.", responde("baja.0", "Dolor leve que responde a analgesia"))
    assert r["paciente"]["categoria"] == "media"
    assert any("se mantiene media" in x["valor"] for x in r["paciente"]["razones"] if x["factor"] == "criterio_clinico")


def test_cita_inventada_o_criterio_inexistente_no_cuenta():
    s, r = ingresar("M17", "baja", "Control de rodilla.", responde("alta.0", "sospecha de tumor"))
    assert r["paciente"]["categoria"] == "baja" and r["criterio"]["nivel"] is None
    s, r = ingresar("M17", "baja", "Control de rodilla.", responde("alta.9", "Control de rodilla"))
    assert r["paciente"]["categoria"] == "baja"


def test_informacion_insuficiente_no_asigna_baja():
    s, r = ingresar("M17", "media", "Derivado a traumatología.", responde("no_determinable", ""))
    assert r["paciente"]["categoria"] == "media" and r["criterio"]["nivel"] is None


def test_negacion_no_cumple_el_criterio():
    s, r = ingresar("M17", "media", "Sin sospecha de tumor. Dolor moderado.", responde("alta.0", "sospecha de tumor"))
    assert r["paciente"]["categoria"] == "media"


def test_urgencia_transversal_de_psiquiatria_en_un_paciente_del_registro():
    pid = next(p["id_paciente"] for p in app.lista(CORTE)["pacientes"] if p["diagnostico_cie10"] == "F32" and p["categoria"] != "alta")
    texto = "Control salud mental 12/10/2026. Refiere ideación suicida activa con plan e intencionalidad."
    try:
        os.environ["ALGORITMO"] = "rubrica"
        app._llm["cliente"] = rubrica.ClienteFalso(lambda t: {"hallazgos": []} if "DOCUMENTO" in t else
                                                   {"criterio": "alta.0", "cita": "ideación suicida activa con plan", "urgencia": "urgencia.0",
                                                    "cita_urgencia": "ideación suicida activa con plan e intencionalidad"})
        res = app.handler({"requestContext": {"http": {"method": "POST"}}, "rawPath": f"/pacientes/{pid}/informe",
                           "body": json.dumps({"texto": texto, "fecha_corte": CORTE.isoformat()})})
        r = json.loads(res["body"])
    finally:
        os.environ.pop("ALGORITMO", None)
        app._llm["cliente"] = None
    assert r["criterio"]["urgencia"] and r["paciente"]["urgencia_hoy"] and en_carril_de_urgencia(r["paciente"])


def test_con_reglas_no_se_llama_a_la_ia():
    s, r = app.post_paciente({"nombre": "Sin IA", "edad": 60, "sexo": "F", "diagnostico_cie10": "M17", "prioridad_inicial": "baja",
                              "motivo_interconsulta": "sospecha de tumor", "fecha_corte": CORTE.isoformat()})
    assert s == 200 and r["criterio"] is None and r["paciente"]["categoria"] == "baja"
