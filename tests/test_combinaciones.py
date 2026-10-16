"""Combinaciones de riesgo: base del paciente + gatillo en el texto. La IA marca y cita; el código verifica contra el
registro y aplica (solo sube; urgencia primero). Sin Bedrock (ClienteFalso)."""
import copy
import json
import os
import sys
from datetime import date

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["LOCAL"] = "1"; os.environ.setdefault("DATA_DIR", os.path.join(RAIZ, "data")); os.environ.pop("MODEL_ID", None)
sys.path.insert(0, os.path.join(RAIZ, "lambda"))
import app  # noqa: E402
import combinaciones  # noqa: E402
import decisor  # noqa: E402
import puntaje  # noqa: E402
import rubrica  # noqa: E402

CORTE = date(2026, 10, 13)


def marca(*m, otras=()):
    """ClienteFalso: responde las combinaciones solo a la pregunta de combinaciones; lo demás, vacío."""
    def r(texto):
        if "COMBINACIONES (lista cerrada)" in texto:
            return {"combinaciones": [dict(zip(("id", "cita_gatillo", "cita_base"), x)) for x in m],
                    "otras": [{"descripcion": d, "cita": c} for d, c in otras]}
        if "DOCUMENTO" in texto:
            return {"hallazgos": []}
        return {"criterio": "no_determinable", "cita": "", "urgencia": "ninguna", "cita_urgencia": ""}
    return rubrica.ClienteFalso(r)


def paciente(cond):
    return next(p for p in app.lista(CORTE)["pacientes"] if cond(p))


def sin_diabetes(p):
    return not any("diab" in (c.get("nombre") or c.get("condicion") or "").lower() for c in p.get("comorbilidades", []))


def informe(pid, texto, cli):
    try:
        os.environ["ALGORITMO"] = "rubrica"
        app._llm["cliente"] = cli
        res = app.handler({"requestContext": {"http": {"method": "POST"}}, "rawPath": f"/pacientes/{pid}/informe",
                           "body": json.dumps({"texto": texto, "fecha_corte": CORTE.isoformat()})})
        r = json.loads(res["body"])
        if r.get("paciente") is None:  # si nada cambió, la respuesta no trae la fila: se lee de la lista
            r["paciente"] = next(p for p in app.lista(CORTE)["pacientes"] if p["id_paciente"] == pid)
        return r
    finally:
        os.environ.pop("ALGORITMO", None)
        app._llm["cliente"] = None


def test_base_completa_y_con_fuente():
    kb = combinaciones.cargar()["kb"]
    assert len(kb["combinaciones"]) >= 30
    for c in kb["combinaciones"]:
        assert c["efecto"] in ("urgencia", "alta", "alerta") and c["fuente"]["documento"] and c["estado"] in ("verificado", "guia_citada")
        b = c["base"]
        assert b.get("cualquiera") or b.get("cie10") or b.get("terminos") or b.get("edad_min")


def test_diabetes_con_una_encarnada_sube_a_alta():
    p = paciente(lambda x: x["diagnostico_cie10"] == "E11" and x["categoria"] == "baja")
    r = informe(p["id_paciente"], "Control 12/10/2026. Presenta uña encarnada del ortejo mayor derecho con enrojecimiento local.",
                marca(("pie_diabetico_lesion", "uña encarnada del ortejo mayor derecho con enrojecimiento local", "")))
    q = r["paciente"]
    assert q["categoria"] == "alta"
    assert any(x["factor"] == "combinacion" and "amputación" in x["valor"] for x in q["razones"])


def test_pie_diabetico_infectado_es_urgencia_y_va_primero():
    p = paciente(lambda x: x["diagnostico_cie10"] == "E11" and x["categoria"] == "baja")
    r = informe(p["id_paciente"], "Úlcera plantar con pus y mal olor, fiebre de 38,5.",
                marca(("pie_diabetico_infeccion", "Úlcera plantar con pus y mal olor", "")))
    q = r["paciente"]
    assert q["urgencia_hoy"] and q["razones"][0]["factor"] == "urgencia"
    assert all(x["urgencia_hoy"] for x in app.lista(CORTE)["pacientes"][:q["posicion"] - 1])   # en el carril de urgencia


def test_sin_diabetes_la_una_encarnada_no_sube():
    p = paciente(lambda x: x["diagnostico_cie10"] == "M17" and x["categoria"] == "baja" and sin_diabetes(x))
    r = informe(p["id_paciente"], "Uña encarnada del ortejo mayor con enrojecimiento local.",
                marca(("pie_diabetico_lesion", "Uña encarnada del ortejo mayor con enrojecimiento local", "")))
    assert r["paciente"]["categoria"] == "baja"


def test_la_base_puede_venir_del_texto_si_se_verifica():
    p = paciente(lambda x: x["diagnostico_cie10"] == "M17" and x["categoria"] == "baja" and sin_diabetes(x))
    r = informe(p["id_paciente"], "Paciente diabético tipo 2 en tratamiento. Uña encarnada con enrojecimiento.",
                marca(("pie_diabetico_lesion", "Uña encarnada con enrojecimiento", "Paciente diabético tipo 2")))
    assert r["paciente"]["categoria"] == "alta"


def test_anticoagulado_con_golpe_en_la_cabeza_es_urgencia():
    p = paciente(lambda x: x["diagnostico_cie10"] == "I10" and x["categoria"] != "alta")
    r = informe(p["id_paciente"], "Usuaria de acenocumarol por fibrilación auricular. Ayer sufrió caída con golpe en la cabeza, sin síntomas.",
                marca(("anticoagulado_tec", "caída con golpe en la cabeza", "Usuaria de acenocumarol")))
    q = r["paciente"]
    assert q["urgencia_hoy"] and q["categoria"] == "alta" and "NG232" in q["razones"][0]["fuente"]


def test_gatillo_negado_no_cuenta():
    p = paciente(lambda x: x["diagnostico_cie10"] == "I10" and x["categoria"] == "baja")
    r = informe(p["id_paciente"], "Usuario de warfarina. Niega caída con golpe en la cabeza.",
                marca(("anticoagulado_tec", "caída con golpe en la cabeza", "Usuario de warfarina")))
    assert not r["paciente"]["urgencia_hoy"] and r["paciente"]["categoria"] == "baja"


def test_adulto_mayor_por_edad_del_registro():
    p = paciente(lambda x: x["edad"] >= 65 and x["categoria"] == "baja")
    r = informe(p["id_paciente"], "Sufrió caída en su casa, con dolor de cadera derecha y no puede apoyar la pierna.",
                marca(("adulto_mayor_caida_cadera", "dolor de cadera derecha y no puede apoyar la pierna", "")))
    assert r["paciente"]["urgencia_hoy"]


def test_combinacion_no_listada_queda_como_alerta_sin_cambiar_prioridad():
    p = paciente(lambda x: x["diagnostico_cie10"] == "M75" and x["categoria"] == "baja")
    r = informe(p["id_paciente"], "Paciente con lupus en tratamiento con hidroxicloroquina refiere visión borrosa progresiva.",
                marca(otras=[("lupus + hidroxicloroquina + visión borrosa: posible toxicidad retiniana", "visión borrosa progresiva")]))
    q = r["paciente"]
    assert q["categoria"] == "baja" and any(x["factor"] == "alerta_combinacion" for x in q["razones"])
    assert any("combinación de riesgo no listada" in s["motivo"] for s in q["revision_sugerida"])


def test_con_reglas_no_se_llama_a_la_ia():
    p = paciente(lambda x: x["diagnostico_cie10"] == "E11" and x["categoria"] == "baja")
    r = json.loads(app.handler({"requestContext": {"http": {"method": "POST"}}, "rawPath": f'/pacientes/{p["id_paciente"]}/informe',
                                "body": json.dumps({"texto": "uña encarnada", "fecha_corte": CORTE.isoformat()})})["body"])
    assert "combinaciones" not in r


def test_entre_descompensados_va_primero_el_mas_grave():
    base = {"categoria": "alta", "riesgo_vital": True, "estado_clinico": "descompensado", "grupo_proteccion": None, "dias_espera": 500,
            "antiguedad_mayor_1_anio": True, "lace": {"total": 0}}
    uci = {**base, "id_paciente": "UCI", "agudeza": 3, "dias_espera": 10}
    esi2 = {**base, "id_paciente": "ESI2", "agudeza": 2}
    for clave in (decisor.clave_orden_536, puntaje.clave_orden):
        assert sorted([esi2, uci], key=clave)[0]["id_paciente"] == "UCI"
    assert puntaje.agudeza({"subtipo": "ingreso UCI", "severidad": "grave"}) == 3


def test_signos_vitales_no_son_razon_de_prioridad():
    p = copy.deepcopy(app.perfiles()[paciente(lambda x: x["diagnostico_cie10"] == "I10")["id_paciente"]])
    p["mediciones"] = [{"fecha_medicion": "2026-10-01", "tipo_medicion": "presion_sistolica", "valor": 190, "unidad": "mmHg", "fuera_de_rango": True}]
    assert not any(x["factor"] == "medicion" for x in puntaje.puntuar(p, CORTE)["razones"])
    p["mediciones"] = [{"fecha_medicion": f, "tipo_medicion": "HbA1c", "valor": v, "unidad": "%", "fuera_de_rango": True}
                       for f, v in (("2026-06-01", 8.1), ("2026-09-01", 8.6))]
    assert any(x["factor"] == "medicion" and "dos mediciones" in x["valor"] for x in puntaje.puntuar(p, CORTE)["razones"])


def test_la_urgencia_sale_del_carril_cuando_el_especialista_la_revisa():
    p = paciente(lambda x: x["diagnostico_cie10"] == "E11" and x["categoria"] == "baja")
    r = informe(p["id_paciente"], "Úlcera en el pie con pus y fiebre.", marca(("pie_diabetico_infeccion", "Úlcera en el pie con pus y fiebre", "")))
    assert r["paciente"]["urgencia_hoy"] and r["paciente"]["contactar_hoy"]
    s, _ = app.post_revision(p["id_paciente"], {"accion": "confirmar", "fecha_corte": CORTE.isoformat(), "usuario": "Dra. Prueba"})
    assert s == 200
    q = next(x for x in app.lista(CORTE)["pacientes"] if x["id_paciente"] == p["id_paciente"])
    assert not q["urgencia_hoy"] and q["urgencia_cerrada"] and q["categoria"] == "alta"   # sale del carril, no baja


def test_si_la_ia_falla_queda_una_alerta_visible():
    p = paciente(lambda x: x["diagnostico_cie10"] == "M54" and x["categoria"] == "baja")
    r = informe(p["id_paciente"], "Lumbago con pérdida del control de la orina.", rubrica.ClienteFalso({}, fallar=True))
    q = next(x for x in app.lista(CORTE)["pacientes"] if x["id_paciente"] == p["id_paciente"])
    assert any(x["factor"] == "alerta_combinacion" and "no pudo revisar" in x["valor"] for x in q["razones"])
    assert r is not None
