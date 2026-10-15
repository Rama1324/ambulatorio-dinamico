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


def test_json_completo_y_mapeado():
    kb = criterios.cargar()
    assert len(kb["por_id"]) == 46 and set(criterios.CIE10) == set(kb["por_id"])
    cat = {d["diagnostico_cie10"] for d in app.catalogo()["diagnosticos"]}
    assert {"N40", "H33", "H91", "F31", "M32"} <= cat                      # se pueden ingresar pacientes de esas especialidades
    assert criterios.enfermedad_de("F32")["id"] == "psiquiatria_07"        # la depresión del registro usa sus criterios


def test_criterio_alta_sube_y_explica():
    s, r = ingresar("N40", "media", "Paciente con HPB, 2 episodios de retención urinaria aguda que requirieron sonda.",
                    responde("alta.0", "retención urinaria aguda"))
    p = r["paciente"]
    assert s == 200 and p["categoria"] == "alta" and r["criterio"]["criterio_id"] == "alta.0"
    assert any(x["factor"] == "criterio_clinico" and "retención urinaria aguda" in x["valor"] for x in p["razones"])


def test_urgencia_prevalece_y_va_primero():
    s, r = ingresar("H91", "baja", "Hipoacusia súbita de oído izquierdo de 24 horas de evolución.",
                    responde("alta.0", "Hipoacusia súbita", "urgencia.0", "Hipoacusia súbita de oído izquierdo de 24 horas"))
    p = r["paciente"]
    assert p["categoria"] == "alta" and p["urgencia_hoy"] and p["contactar_hoy"] and p["posicion"] == 1
    assert p["razones"][0]["factor"] == "urgencia"


def test_criterio_baja_no_baja_a_nadie():
    s, r = ingresar("N40", "media", "Síntomas leves, IPSS bajo, en manejo médico inicial.", responde("baja.0", "Síntomas leves, IPSS bajo"))
    assert r["paciente"]["categoria"] == "media"
    assert any("se mantiene media" in x["valor"] for x in r["paciente"]["razones"] if x["factor"] == "criterio_clinico")


def test_cita_inventada_o_criterio_inexistente_no_cuenta():
    s, r = ingresar("N40", "baja", "Control de próstata.", responde("alta.0", "retención urinaria aguda"))
    assert r["paciente"]["categoria"] == "baja" and r["criterio"]["nivel"] is None
    s, r = ingresar("N40", "baja", "Control de próstata.", responde("alta.9", "Control de próstata"))
    assert r["paciente"]["categoria"] == "baja"


def test_informacion_insuficiente_no_asigna_baja():
    s, r = ingresar("N40", "media", "Derivado a urología.", responde("no_determinable", ""))
    assert r["paciente"]["categoria"] == "media" and r["criterio"]["nivel"] is None


def test_negacion_no_cumple_el_criterio():
    s, r = ingresar("N40", "media", "Sin retención urinaria aguda. Síntomas moderados.", responde("alta.0", "retención urinaria aguda"))
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
    assert r["criterio"]["urgencia"] and r["paciente"]["urgencia_hoy"] and r["paciente"]["posicion"] == 1


def test_con_reglas_no_se_llama_a_la_ia():
    s, r = app.post_paciente({"nombre": "Sin IA", "edad": 60, "sexo": "F", "diagnostico_cie10": "N40", "prioridad_inicial": "baja",
                              "motivo_interconsulta": "retención urinaria aguda", "fecha_corte": CORTE.isoformat()})
    assert s == 200 and r["criterio"] is None and r["paciente"]["categoria"] == "baja"
