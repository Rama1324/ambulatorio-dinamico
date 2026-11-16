"""Bitácora de decisiones (ESPECIFICACION_MVP §5): un dictamen por disparador, con qué se usó, de qué fuentes y versiones,
el resultado antes/después y una explicación por plantilla; la cola de revisión del especialista; los campos nuevos de la
lista y de los KPI. Más los dos arreglos del motor: alerta PHQ-9 y vigencia de las lecturas de la IA por huella."""
import copy
import json
import os
import sys
from datetime import date

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["LOCAL"] = "1"; os.environ.setdefault("DATA_DIR", os.path.join(RAIZ, "data")); os.environ.pop("MODEL_ID", None)
sys.path.insert(0, os.path.join(RAIZ, "lambda"))
import algoritmo  # noqa: E402
import app  # noqa: E402
import bitacora  # noqa: E402
import datos  # noqa: E402
import decisor  # noqa: E402
import lista as modulo_lista  # noqa: E402
import puntaje  # noqa: E402
import rubrica  # noqa: E402

C = "2026-10-13"
CORTE = date(2026, 10, 13)


def call(method, path, qs=None, body=None):
    r = app.handler({"requestContext": {"http": {"method": method}}, "rawPath": path,
                     "queryStringParameters": qs, "body": json.dumps(body) if body else None})
    return r["statusCode"], json.loads(r["body"])


def filas(corte=C):
    return {p["id_paciente"]: p for p in call("GET", "/pacientes", {"fecha_corte": corte})[1]["pacientes"]}


def baja_sin_evento(cie, excluir=()):
    return next(p for p, x in sorted(filas().items()) if x["diagnostico_cie10"] == cie and x["categoria"] == "baja"
                and x["estado_clinico"] == "sin_cambios" and p not in excluir)


# ---------- explicación por plantilla: sirve para los cinco cambios y dice la fuente que más pesó ----------
def _res(antes, despues, **kw):
    return {"categoria_antes": antes, "categoria": despues, "cambio": bitacora._cambio(antes and {"categoria": antes}, despues and {"categoria": despues}),
            "riesgo_vital": False, "urgencia_hoy": False, "posicion_antes": None, "posicion": None, "total": 10, "alerta_nueva": False,
            "requiere_revision": False, **kw}


def test_explicacion_para_los_cinco_cambios():
    tabla = {"factor": "tabla_oficial", "valor": '"Angina inestable" → prioridad alta', "fuente": "Tabla SSMSO 2025, HLF, pág. 85"}
    inicial = {"factor": "prioridad_inicial", "valor": "baja (asignada…)", "fuente": "SIC"}
    sube = bitacora.explicacion(_res("baja", "alta", riesgo_vital=True, alerta_nueva=True), [inicial, tabla], {"tipo": "evento"})
    assert sube.startswith("Subió de prioridad baja a alta") and "Tabla SSMSO 2025, HLF, pág. 85" in sube and "72 horas" in sube
    baja = bitacora.explicacion(_res("alta", "baja"), [inicial], {"tipo": "enmienda", "descripcion": "enmienda «anular»"})
    assert baja.startswith("Bajó de prioridad alta a baja") and "persona" in baja and "enmienda" in baja
    igual = bitacora.explicacion(_res("baja", "baja", requiere_revision=True), [inicial, {
        "factor": "tabla_oficial", "valor": "la tabla del HLF no tiene fila para este diagnóstico descompensado", "fuente": "Tabla", "sin_regla": True}], {})
    assert igual.startswith("Se mantiene en prioridad baja") and "no tiene fila" in igual and "revisión del especialista" in igual
    ingresa = bitacora.explicacion(_res(None, "media"), [inicial], {"tipo": "ingreso"})
    assert ingresa.startswith("Ingresa a la lista con prioridad media")
    sale = bitacora.explicacion(_res("alta", None), bitacora._fundamento(None, {"motivo": "fallecido", "fecha": "2026-10-10"}), {})
    assert sale.startswith("Sale de la lista: fallecimiento") and "2026-10-10" in sale
    assert {bitacora._cambio(a and {"categoria": a}, b and {"categoria": b}) for a, b in
            (("baja", "alta"), ("alta", "baja"), ("media", "media"), (None, "baja"), ("alta", None))} == set(bitacora.CAMBIOS)


# ---------- dictámenes de cada disparador ----------
def test_evento_que_sube_documenta_antes_despues_fuentes_y_explicacion():
    pid = baja_sin_evento("I20")
    rev0 = filas()[pid]["rev"]
    s, b = call("POST", "/eventos", body={"id_paciente": pid, "tipo_evento": "hospitalizacion", "subtipo": "ingreso hospitalario",
                                          "fecha_evento": "2026-10-05", "fecha_corte": C, "especialidad": "Cardiología"})
    d = b["dictamen"]
    r = d["resultado"]
    assert s == 200 and r["categoria_antes"] == "baja" and r["categoria"] == "alta" and r["cambio"] == "sube"
    assert r["riesgo_vital"] and r["alerta_nueva"] and r["posicion"] < r["posicion_antes"] and r["total"] == b["total"]
    assert r["posicion"] == b["posicion_despues"] and r["estado_clinico"] == "descompensado"
    assert d["explicacion"].startswith("Subió de prioridad baja a alta") and "pág. 85" in d["explicacion"]
    assert d["patron"] == "I20|hospitalizacion|grave" and d["evento_determinante"]["id_evento"] == b["evento"]["id_evento"]
    ids = {x["id"] for x in d["informacion_utilizada"]["conocimiento"]["fuentes"]}
    assert {"diagnosticos_tabla_hlf", "ssmso_hlf_2025", "registro_paciente"} <= ids
    a = d["informacion_utilizada"]["antecedentes"]
    assert a["firma"] == rubrica.firma(datos.perfil_de(pid), CORTE) and a["eventos"] >= 1 and a["hasta"] == C
    # la fila de la lista: rev subió y trae el resumen del último dictamen
    f = filas()[pid]
    assert f["rev"] > rev0 and f["dictamen"] == {"id_dictamen": d["id_dictamen"], "fecha": d["fecha"], "cambio": "sube", "motor": "reglas",
                                                 "necesita_revision": True}
    assert all("rev" in x and "dictamen" in x for x in filas().values())


def test_ingreso_y_novedad_registran_su_dictamen():
    s, b = call("POST", "/pacientes", body={"nombre": "Paciente Bitácora", "edad": 60, "sexo": "F", "diagnostico_cie10": "I10",
                                            "prioridad_inicial": "media", "fecha_corte": C, "usuario": "Admisión"})
    assert s == 200 and b["dictamen"]["disparador"]["tipo"] == "ingreso" and b["dictamen"]["resultado"]["cambio"] == "ingresa"
    assert b["dictamen"]["resultado"]["posicion_antes"] is None and b["dictamen"]["explicacion"].startswith("Ingresa a la lista con prioridad media")
    pid = b["id_paciente"]
    s, n = call("POST", f"/pacientes/{pid}/novedad", body={"tipo": "fallecimiento", "fecha": C, "fecha_corte": C, "usuario": "Admisión"})
    d = n["dictamen"]
    assert s == 200 and d["disparador"]["tipo"] == "novedad" and d["resultado"]["cambio"] == "sale" and not n["en_lista"]
    assert d["explicacion"].startswith("Sale de la lista: fallecimiento") and d["fundamento"][0]["factor"] == "evento"
    assert [x["disparador"]["tipo"] for x in call("GET", f"/pacientes/{pid}/decisiones")[1]["decisiones"]] == ["novedad", "ingreso"]


def test_fotos_calcula_una_lista_por_especialidad(monkeypatch):
    llamadas = []
    original = modulo_lista.lista
    monkeypatch.setattr(modulo_lista, "lista", lambda corte, esp=None, *a, **k: llamadas.append(esp) or original(corte, esp, *a, **k))
    perfs = datos.perfiles_combinados()[0]
    pids = [p for p in sorted(perfs) if perfs[p]["lista_espera"]["especialidad"] in ("Cardiología", "Endocrinología")][:120]
    f = bitacora.fotos(pids, CORTE)
    assert sorted(llamadas) == ["Cardiología", "Endocrinología"] and set(f) == set(pids)
    assert all(x is None or x["id_paciente"] == p for p, x in f.items())


# ---------- cola de revisión ----------
def _dic(pid, fecha, patron, alerta=False, requiere=True):
    return bitacora.guardar_dictamen({"id_dictamen": f"DIC-T-{pid[-5:]}", "id_paciente": pid, "fecha": fecha, "fecha_corte": C,
                                      "especialidad": "Cardiología", "disparador": {"tipo": "evento"}, "motor": "reglas", "patron": patron,
                                      "resultado": {"cambio": "igual", "alerta_nueva": alerta, "requiere_revision": requiere},
                                      "fundamento": [], "explicacion": "", "informacion_utilizada": {}})


def _veredicto(pid, patron, veredicto):
    r = {"accion": "confirmar", "veredicto": veredicto, "motivo_codigo": None if veredicto == "adecuada" else "otro", "patron": patron,
         "usuario": "Dr. Cola", "fecha": "2020-01-01T00:00:00+00:00", "fecha_corte": "2020-01-01", "categoria_sistema": "baja"}
    datos.guardar({"id_paciente": pid, "sk": f"revision#{r['fecha']}", "revision": json.dumps(r)})


def test_cola_ordena_alertas_nuevas_y_luego_patrones_con_mas_desacuerdo():
    datos.restablecer()
    _veredicto("PAC-HLF-00400", "X|b|grave", "incorrecta")          # el patrón X|b ya tuvo desacuerdo
    _veredicto("PAC-HLF-00401", "X|a|grave", "adecuada")
    _dic("PAC-HLF-00010", "2026-11-01T10:00:00+00:00", "X|a|grave")
    _dic("PAC-HLF-00011", "2026-11-01T09:00:00+00:00", "X|b|grave")
    _dic("PAC-HLF-00012", "2026-11-01T08:00:00+00:00", "X|a|grave", alerta=True)
    _dic("PAC-HLF-00013", "2026-11-01T11:00:00+00:00", "X|a|grave", requiere=False)   # no necesita revisión
    _, q = call("GET", "/decisiones", {"estado": "pendiente"})
    assert [d["id_paciente"] for d in q["decisiones"]] == ["PAC-HLF-00012", "PAC-HLF-00011", "PAC-HLF-00010"]
    assert call("GET", "/decisiones", {"estado": "pendiente", "especialidad": "Neurología"})[1]["total"] == 0
    assert call("GET", "/decisiones", {"estado": "todas"})[1]["total"] == 4
    # el especialista revisa a uno: sale de pendientes y pasa a revisadas, con su veredicto unido
    s, b = call("POST", "/pacientes/PAC-HLF-00011/revision", body={"accion": "confirmar", "usuario": "Dr. Cola", "fecha_corte": C})
    assert s == 200 and b["id_dictamen"] == "DIC-T-00011" and b["revision"]["veredicto"] == "adecuada"
    assert "PAC-HLF-00011" not in [d["id_paciente"] for d in call("GET", "/decisiones")[1]["decisiones"]]
    rev = call("GET", "/decisiones", {"estado": "revisada"})[1]["decisiones"]
    assert [d["id_dictamen"] for d in rev] == ["DIC-T-00011"] and rev[0]["revision"]["veredicto"] == "adecuada"
    assert call("GET", "/decisiones/DIC-T-00011")[1]["revision"]["usuario"] == "Dr. Cola"
    assert call("GET", "/decisiones/DIC-NO")[0] == 404 and call("GET", "/decisiones", {"estado": "otra"})[0] == 400
    assert call("GET", "/pacientes/PAC-NO-EXISTE/decisiones")[0] == 404
    datos.restablecer()


def test_kpis_agregan_decisiones_y_segundos_del_evento_al_dictamen():
    pid = baja_sin_evento("I10")
    call("POST", "/eventos", body={"id_paciente": pid, "tipo_evento": "visita_urgencia", "subtipo": "triage ESI 2", "fecha_corte": C})
    _, k = call("GET", "/kpis", {"fecha_corte": C})
    assert k["decisiones"]["total"] >= 1 and k["decisiones"]["pendientes"] >= 1 and {"adecuadas", "incorrectas"} <= set(k["decisiones"])
    assert k["reevaluacion"]["mediana_segundos_evento_a_dictamen"] is not None and k["reevaluacion"]["mediana_segundos_evento_a_dictamen"] < 60
    assert "mediana_horas" in k["reevaluacion"] and "kappa" in k["concordancia"]       # los campos de antes siguen


def test_la_carga_inicial_no_crea_dictamenes():
    datos.restablecer()
    assert datos.registros_tipo("dictamen#") == [] and all(f["dictamen"] is None for f in filas().values())


# ---------- arreglos del motor ----------
def test_alerta_phq9_se_emite_sin_cambiar_la_prioridad_ni_el_orden():
    perfs = datos.perfiles_combinados()[0]
    con = []
    for p in perfs.values():
        if puntaje.cie_base(p["lista_espera"]["diagnostico_cie10"]) not in ("F32", "F33"):
            continue
        r = puntaje.puntuar(p, CORTE)
        if not r or r.get("excluido"):
            continue
        sin_phq = copy.deepcopy(p)
        sin_phq["mediciones"] = [m for m in sin_phq["mediciones"] if m["tipo_medicion"] != "PHQ9"]
        r0 = puntaje.puntuar(sin_phq, CORTE)
        assert (r["categoria"], r["riesgo_vital"], r["estado_evaluacion"]) == (r0["categoria"], r0["riesgo_vital"], r0["estado_evaluacion"])
        assert puntaje.clave_orden(r) == puntaje.clave_orden(r0)
        if any(x["factor"] == "alerta_clinica" for x in r["razones"]):
            con.append(p["id_paciente"])
    assert len(con) == 14 and "PAC-HLF-00001" in con              # antes se emitían 0
    r = puntaje.puntuar(perfs["PAC-HLF-00001"], CORTE)
    a = next(x for x in r["razones"] if x["factor"] == "alerta_clinica")
    assert "PHQ-9 = 19" in a["valor"] and "NICE NG222" in a["fuente"] and "alerta_clinica" not in puntaje.FACTORES_REGLA


def test_evaluacion_de_la_ia_sin_huella_o_con_otra_huella_no_es_vigente():
    kb = decisor.cargar_kb()
    p = copy.deepcopy(datos.perfil_de("PAC-HLF-00002"))
    cli = rubrica.ClienteFalso(rubrica.respuesta_determinista(rubrica.historial(p, CORTE), decisor.kb_diagnostico(kb, "I20")))
    e = json.loads(json.dumps(algoritmo.evaluar_paciente(p, CORTE, cli), default=str))
    import base_conocimiento
    huella_manifiesto = next(f["sha256"] for f in base_conocimiento.fuentes() if f["id"] == "rubrica_v1")
    assert e["huella_kb"] == huella_manifiesto                              # la huella es la del manifiesto
    assert algoritmo.vigente(e, p, CORTE, kb)
    assert not algoritmo.vigente({k: v for k, v in e.items() if k != "huella_kb"}, p, CORTE, kb)   # guardada sin huella
    assert not algoritmo.vigente({**e, "huella_kb": "0" * 64}, p, CORTE, kb)                        # la fuente cambió sin subir versión
    otra = copy.deepcopy(kb)
    otra["diagnosticos"]["I20"]["texto"] += " (editado)"
    assert not algoritmo.vigente(e, p, CORTE, otra)
