"""Reglas oficiales del registro (Queensland CPC / NICE), piso por diagnóstico, letalidad y plazo de referencia.
Cada razón trae su fuente y 'qué puede pasar' (riesgo). Sin IA."""
import copy
import os
import sys
from datetime import date

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["LOCAL"] = "1"; os.environ.setdefault("DATA_DIR", os.path.join(RAIZ, "data")); os.environ.pop("MODEL_ID", None)
sys.path.insert(0, os.path.join(RAIZ, "lambda"))
import app  # noqa: E402
import combinaciones  # noqa: E402
import puntaje  # noqa: E402

CORTE = date(2026, 10, 13)


def perfil(cie, cat="baja"):
    p = next(x for x in app.perfiles().values() if x["lista_espera"]["diagnostico_cie10"] == cie and x["lista_espera"]["prioridad_inicial"] == cat
             and (r := puntaje.puntuar(x, CORTE)) and not r.get("excluido"))
    p = copy.deepcopy(p)
    p["eventos_clinicos"] = []
    return p


def ev(fecha, tipo, subtipo, sev="grave"):
    return {"id_evento": fecha + subtipo, "fecha_evento": fecha, "tipo_evento": tipo, "subtipo": subtipo, "severidad": sev}


def test_asma_con_uci_en_12_meses_sube_a_alta_con_fuente_y_riesgo():
    p = perfil("J45")
    p["eventos_clinicos"] = [ev("2026-02-01", "hospitalizacion", "ingreso UCI"),            # UCI hace 8 meses…
                             ev("2026-03-01", "control_aps", "estabilización", "leve")]       # …ya estabilizada: igual cuenta (UCI en 12 meses)
    r = puntaje.puntuar(p, CORTE)
    x = next(z for z in r["razones"] if z["factor"] == "criterio_registro")
    assert r["categoria"] == "alta" and "UCI" in x["valor"] and "health.qld.gov.au" in x["fuente"] and "16,5%" in x["riesgo"]


def test_epoc_con_mas_de_3_urgencias_en_12_meses_sube_a_media():
    p = perfil("J44")
    p["eventos_clinicos"] = [ev(f, "visita_urgencia", "triage ESI 3", "moderada") for f in ("2026-01-10", "2026-03-10", "2026-05-10", "2026-07-10")]
    r = puntaje.puntuar(p, CORTE)
    assert r["categoria"] in ("media", "alta") and any(z["factor"] == "criterio_registro" and "4 en 12 meses" in z["valor"] for z in r["razones"])


def test_sin_piso_por_guia_extranjera():
    """Que Queensland no tenga categoría 3 para cirrosis no sube a nadie: sin evento, rige la prioridad inicial."""
    p = perfil("K70")
    r = puntaje.puntuar(p, CORTE)
    assert r["categoria"] == "baja" and not any(z["factor"] == "piso" for z in r["razones"])
    assert r["estado_evaluacion"] == "sin_evento_nuevo" and r["puntaje_inicial"] == 1 and r["puntaje_propuesto"] is None


def test_estado_de_evaluacion_y_puntajes():
    p = perfil("I50", "media")
    p["eventos_clinicos"] = [ev("2026-10-01", "hospitalizacion", "ingreso hospitalario")]
    r = puntaje.puntuar(p, CORTE)
    assert r["estado_evaluacion"] == "determinada" and r["prioridad_propuesta"] == "alta" and r["puntaje_propuesto"] == 3 and r["puntaje_inicial"] == 2
    q = perfil("M75", "media")                                   # evento que las reglas de su diagnóstico no cubren
    q["eventos_clinicos"] = [ev("2026-10-01", "visita_urgencia", "triage ESI 2")]
    r = puntaje.puntuar(q, CORTE)
    assert r["estado_evaluacion"] == "evaluada_sin_cambio" and r["puntaje_propuesto"] is None and r["categoria"] == "media"
    q["lista_espera"]["diagnostico_cie10"] = "Z99"               # diagnóstico sin ninguna regla
    assert puntaje.puntuar(q, CORTE)["estado_evaluacion"] == "sin_regla_aplicable"


def test_valores_imposibles_no_entran_a_las_reglas():
    p = perfil("E11")
    p["mediciones"] = [{"fecha_medicion": "2026-06-01", "tipo_medicion": "HbA1c", "valor": 8.0, "unidad": "%", "fuera_de_rango": True},
                       {"fecha_medicion": "2026-09-01", "tipo_medicion": "HbA1c", "valor": 85.0, "unidad": "%", "fuera_de_rango": True}]
    r = puntaje.puntuar(p, CORTE)
    assert not any(z["factor"] == "criterio_registro" for z in r["razones"])   # 85% es imposible: no sube a nadie


def test_plazo_de_referencia_vencido_se_explica_sin_mover_a_nadie():
    p = perfil("M17")
    p["lista_espera"]["fecha_ingreso_lista"] = "2025-01-01"
    r = puntaje.puntuar(p, CORTE)
    x = next(z for z in r["razones"] if z["factor"] == "plazo")
    assert r["plazo_vencido"] and r["plazo_dias"] == 365 and "Sobolev" in x["riesgo"] and r["categoria"] == "baja"


def test_entre_descompensados_va_primero_el_mas_letal():
    base = {"categoria": "alta", "urgencia_hoy": False, "riesgo_vital": True, "estado_clinico": "descompensado", "grupo_proteccion": None,
            "antiguedad_mayor_1_anio": True, "lace": {"total": 0}, "agudeza": 2}
    cirrosis = {**base, "id_paciente": "K70", "letalidad": 1, "dias_espera": 10}
    asma = {**base, "id_paciente": "J45", "letalidad": 3, "dias_espera": 900}
    assert sorted([asma, cirrosis], key=puntaje.clave_orden)[0]["id_paciente"] == "K70"


def test_la_descompensacion_explica_su_letalidad():
    p = perfil("I50", "media")
    p["eventos_clinicos"] = [ev("2026-10-01", "hospitalizacion", "ingreso hospitalario")]
    r = puntaje.puntuar(p, CORTE)
    assert r["letalidad"] == 2 and any(z["factor"] in ("tabla_oficial", "riesgo_vital") and "24,5–29,6%" in (z.get("riesgo") or "") for z in r["razones"])


def test_combinacion_no_verificada_solo_alerta():
    d = {"aplicadas": [{"id": "asplenia_fiebre", "nombre": "Asplenia o esplenectomía + fiebre", "efecto": "alerta", "desenlace": "sepsis fulminante",
                        "cita_gatillo": "fiebre de 39", "cita_base": None, "fuente": {}, "estado": "sin_verificar", "letalidad": 2, "riesgo": "x"}],
         "alertas": [], "lecturas": 3, "errores": []}
    e = combinaciones.evento(d, "2026-10-13")
    assert not e["urgencia"] and e["nivel_criterio"] is None and e["alertas"] and "sin fuente verificada" in e["alertas"][0]["descripcion"]


def test_todos_los_criterios_del_registro_tienen_fuente_y_riesgo():
    for cie, enf in puntaje.criterios_registro().items():
        assert enf["fuente_url"].startswith("https://") and enf["riesgo"]
        for n in ("alta", "media", "baja"):
            assert enf["niveles"][n]["justificacion"]
