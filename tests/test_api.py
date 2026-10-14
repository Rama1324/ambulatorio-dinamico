import json, os, sys
from datetime import date
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["LOCAL"] = "1"; os.environ.setdefault("DATA_DIR", os.path.join(RAIZ, "data")); os.environ.pop("MODEL_ID", None)
sys.path.insert(0, os.path.join(RAIZ, "lambda"))
import app

def call(method, path, qs=None, body=None):
    r = app.handler({"requestContext": {"http": {"method": method}}, "rawPath": path,
                     "queryStringParameters": qs, "body": json.dumps(body) if body else None})
    return r["statusCode"], json.loads(r["body"])

def test_lista_y_exclusion():
    s, d = call("GET", "/pacientes", {"fecha_corte": "2026-10-13"})
    assert s == 200 and d["total"] == 409
    assert "PAC-HLF-00009" in [e["id_paciente"] for e in d["excluidos"]]
    assert all(k in d["pacientes"][0] for k in ("puntaje", "categoria", "posicion", "razones", "estado_revision"))

def test_deterioro_agudo_sube():
    _, d = call("GET", "/pacientes", {"fecha_corte": "2026-08-10"})
    pos = {p["id_paciente"]: p["posicion"] for p in d["pacientes"]}
    assert pos["PAC-HLF-00002"] < 30

def test_mejora_al_fondo():
    _, d = call("GET", "/pacientes", {"fecha_corte": "2026-10-13"})
    pos = {p["id_paciente"]: p["posicion"] for p in d["pacientes"]}
    assert pos["PAC-HLF-00028"] > 350

def test_filtro_especialidad():
    _, d = call("GET", "/pacientes", {"especialidad": "Cardiología"})
    assert d["total"] > 0 and all(p["especialidad"] == "Cardiología" for p in d["pacientes"])

def test_evento_sube_paciente():
    s, d = call("POST", "/eventos", body={"id_paciente": "PAC-HLF-00020", "tipo_evento": "hospitalizacion",
                                          "subtipo": "ingreso UCI", "severidad": "grave"})
    assert s == 200 and d["posicion_despues"] < d["posicion_antes"]
    assert d["reevaluado_en_ms"] < 72 * 3600 * 1000

def test_revision():
    s, _ = call("POST", "/pacientes/PAC-HLF-00001/revision", body={"accion": "confirmar"})
    assert s == 200
    _, d = call("GET", "/pacientes")
    p = next(p for p in d["pacientes"] if p["id_paciente"] == "PAC-HLF-00001")
    assert p["estado_revision"] == "confirmado"
    s, _ = call("POST", "/pacientes/PAC-HLF-00001/revision", body={"accion": "ajustar"})
    assert s == 400

def test_ajuste_reordena():
    _, d = call("GET", "/pacientes")
    pid = d["pacientes"][-2]["id_paciente"]  # no usar pacientes de demo: el estado queda en memoria
    s, _ = call("POST", f"/pacientes/{pid}/revision",
                body={"accion": "ajustar", "puntaje_ajustado": 99, "motivo": "criterio clínico"})
    assert s == 200
    _, d = call("GET", "/pacientes")
    assert d["pacientes"][0]["id_paciente"] == pid
    assert [p["posicion"] for p in d["pacientes"][:3]] == [1, 2, 3]

def test_plazo_ges():
    _, d = call("GET", "/pacientes")
    p = next(p for p in d["pacientes"] if p["diagnostico_cie10"] == "F32" and p["prioridad_inicial"] != "alta" and p["edad"] >= 15)
    assert any(r["factor"] == "dias_espera" and "GES N°34" in r["valor"] for r in p["razones"])

def test_explicar_plantilla():
    s, d = call("POST", "/pacientes/PAC-HLF-00002/explicar", body={"fecha_corte": "2026-08-10"})
    assert s == 200 and "validación clínica" in d["explicacion_ia"]

def test_detalle_y_boxes():
    s, d = call("GET", "/pacientes/PAC-HLF-00001")
    assert s == 200 and d["mediciones"]
    s, d = call("GET", "/boxes")
    assert s == 200 and d["especialidades"] and d["especialidades"][0]["sugeridos"]

def test_404():
    assert call("GET", "/nada")[0] == 404
