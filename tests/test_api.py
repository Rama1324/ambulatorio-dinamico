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

def fila(d, pid):
    return next(p for p in d["pacientes"] if p["id_paciente"] == pid)

def test_lista_y_exclusion():
    s, d = call("GET", "/pacientes", {"fecha_corte": "2026-10-13"})
    assert s == 200 and sum(p["id_paciente"].startswith("PAC-HLF") for p in d["pacientes"]) == 409
    assert "PAC-HLF-00009" in [e["id_paciente"] for e in d["excluidos"]]
    assert all(k in d["pacientes"][0] for k in ("categoria", "estado_clinico", "posicion", "razones", "estado_revision"))
    assert {p["categoria"] for p in d["pacientes"]} <= {"alta", "media", "baja"}

def test_orden_minsal():
    """Categoría primero; dentro de la categoría, > 1 año en lista primero y luego orden de llegada."""
    _, d = call("GET", "/pacientes", {"fecha_corte": "2026-10-13"})
    orden = {"alta": 3, "media": 2, "baja": 1}
    claves = [(-orden[p["categoria"]], not p["riesgo_vital"], not p["antiguedad_mayor_1_anio"], -p["dias_espera"])
              for p in d["pacientes"]]
    assert claves == sorted(claves)

def test_riesgo_vital_00002():
    _, d = call("GET", "/pacientes", {"fecha_corte": "2026-08-10"})
    p = fila(d, "PAC-HLF-00002")
    assert p["riesgo_vital"] and p["razones"][0]["factor"] == "riesgo_vital"
    assert all(q["riesgo_vital"] for q in d["pacientes"][:p["posicion"]] if q["categoria"] == "alta")

def test_box_asigna_con_motivo_y_alternativa():
    _, d = call("GET", "/boxes", {"fecha_corte": "2026-10-13", "especialidad": "Cardiología"})
    e = d["especialidades"][0]
    asignados = [p for a in e["asignaciones"] for p in a["pacientes"]]
    assert asignados and all(p["motivo"] for p in asignados)
    assert e["alternativa"]["por_que_despues"]

def test_deterioro_agudo_sube_por_tabla_oficial():
    _, antes = call("GET", "/pacientes", {"fecha_corte": "2026-07-01"})
    _, despues = call("GET", "/pacientes", {"fecha_corte": "2026-08-10"})
    a, b = fila(antes, "PAC-HLF-00002"), fila(despues, "PAC-HLF-00002")
    assert a["categoria"] == "baja" and b["categoria"] == "alta" and b["posicion"] < a["posicion"]
    assert any(r["factor"] == "tabla_oficial" and "Angina inestable" in r["valor"] and "pág. 85" in r["fuente"] for r in b["razones"])

def test_no_baja_solo():
    """00028 se estabiliza: el sistema no le baja la categoría por su cuenta."""
    _, d = call("GET", "/pacientes", {"fecha_corte": "2026-10-13"})
    p = fila(d, "PAC-HLF-00028")
    assert p["estado_clinico"] == "estabilizado" and p["categoria"] == p["prioridad_inicial"]
    assert p["posicion"] > 350

def test_inasistencia_causal_8():
    _, d = call("GET", "/pacientes", {"fecha_corte": "2026-10-13"})
    p = fila(d, "PAC-HLF-00020")
    orden = {"alta": 3, "media": 2, "baja": 1}
    assert p["riesgo_inasistencia"] and orden[p["categoria"]] >= orden[p["prioridad_inicial"]]  # nunca la baja

def test_filtro_especialidad():
    _, d = call("GET", "/pacientes", {"especialidad": "Cardiología"})
    assert d["total"] > 0 and all(p["especialidad"] == "Cardiología" for p in d["pacientes"])

def test_evento_sube_paciente():
    s, d = call("POST", "/eventos", body={"id_paciente": "PAC-HLF-00020", "tipo_evento": "hospitalizacion",
                                          "subtipo": "ingreso UCI", "severidad": "grave"})
    assert s == 200 and d["posicion_despues"] < d["posicion_antes"] and d["paciente"]["categoria"] == "alta"
    assert d["reevaluado_en_ms"] < 72 * 3600 * 1000

def test_informe_texto_propone_sin_guardar():
    pid = "PAC-HLF-00003"
    _, antes = call("GET", f"/pacientes/{pid}")
    s, d = call("POST", f"/pacientes/{pid}/informe",
                body={"texto": "Paciente consulta en urgencia y se hospitaliza por descompensación de su cuadro."})
    assert s == 200 and d["evento"]["tipo_evento"] == "hospitalizacion" and d["fuente"] == "reglas"
    assert "hospitaliza" in d["evento"]["evidencia"]
    _, despues = call("GET", f"/pacientes/{pid}")
    assert len(despues["eventos_clinicos"]) == len(antes["eventos_clinicos"])  # solo propone

def test_informe_sin_evento():
    s, d = call("POST", "/pacientes/PAC-HLF-00003/informe", body={"texto": "Paciente refiere cefalea leve."})
    assert s == 200 and d["evento"] is None and d["mensaje"]

def test_foto_sin_bedrock_avisa():
    s, d = call("POST", "/pacientes/PAC-HLF-00003/informe", body={"imagen_base64": "aGVsbG8=", "media_type": "image/png"})
    assert s == 200 and d["evento"] is None and "Bedrock" in d["mensaje"]

def test_revision():
    s, _ = call("POST", "/pacientes/PAC-HLF-00001/revision", body={"accion": "confirmar"})
    assert s == 200
    _, d = call("GET", "/pacientes")
    assert fila(d, "PAC-HLF-00001")["estado_revision"] == "confirmado"
    s, _ = call("POST", "/pacientes/PAC-HLF-00001/revision", body={"accion": "ajustar"})
    assert s == 400

def test_ajuste_clinico_reordena():
    _, d = call("GET", "/pacientes")
    p = next(p for p in reversed(d["pacientes"]) if p["categoria"] == "baja" and p["id_paciente"] not in
             ("PAC-HLF-00028", "PAC-HLF-00002", "PAC-HLF-00020"))
    s, _ = call("POST", f"/pacientes/{p['id_paciente']}/revision",
                body={"accion": "ajustar", "categoria_ajustada": "alta", "motivo": "criterio clínico"})
    assert s == 200
    _, d2 = call("GET", "/pacientes")
    q = fila(d2, p["id_paciente"])
    assert q["categoria"] == "alta" and q["categoria_sistema"] == "baja" and q["posicion"] < p["posicion"]

def test_ges():
    _, d = call("GET", "/pacientes")
    p = next(p for p in d["pacientes"] if p["diagnostico_cie10"] == "F32" and p["edad"] >= 15)
    assert p["ges"]["problema"] == 34 and p["ges"]["plazo_dias"] == 30
    assert any(r["factor"] == "ges" and "auge.minsal.cl" in r["fuente"] for r in p["razones"])

def test_explicar_plantilla():
    s, d = call("POST", "/pacientes/PAC-HLF-00002/explicar", body={"fecha_corte": "2026-08-10"})
    assert s == 200 and "validación clínica" in d["explicacion_ia"] and "Angina inestable" in d["explicacion_ia"]

def test_detalle_y_boxes():
    s, d = call("GET", "/pacientes/PAC-HLF-00001")
    assert s == 200 and d["mediciones"]
    s, d = call("GET", "/boxes")
    assert s == 200 and d["especialidades"] and d["especialidades"][0]["sugeridos"]

def test_ingresar_paciente_nuevo():
    s, cat = call("GET", "/catalogo")
    assert s == 200 and any(d["diagnostico_cie10"] == "I50" for d in cat["diagnosticos"])
    s, d = call("POST", "/pacientes", body={"nombre": "Juan Pérez", "edad": 70, "sexo": "M", "diagnostico_cie10": "I50",
                                             "prioridad_inicial": "media", "fecha_corte": "2026-10-13"})
    assert s == 200 and d["paciente"]["categoria"] == "media" and d["paciente"]["especialidad"] == "Cardiología"
    pid = d["id_paciente"]
    s, r = call("POST", "/eventos", body={"id_paciente": pid, "tipo_evento": "hospitalizacion", "subtipo": "ingreso hospitalario",
                                          "severidad": "grave", "fecha_corte": "2026-10-13"})
    assert s == 200 and r["paciente"]["categoria"] == "alta" and r["paciente"]["riesgo_vital"]
    assert call("POST", "/pacientes", body={"nombre": "", "edad": 70})[0] == 400

def test_404():
    assert call("GET", "/nada")[0] == 404
