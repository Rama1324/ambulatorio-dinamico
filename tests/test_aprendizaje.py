"""Retroalimentación del especialista y aprendizaje (ESPECIFICACION_MVP §6): el recorrido que se demuestra, en orden.

Hipertensión (I10) no tiene fila de descompensación en la tabla del HLF: una urgencia grave no la sube. Un especialista dice
que debió subir (criterio_faltante) → criterio local PROPUESTO (no cambia a nadie) → jefatura lo aprueba → los que calzan
suben citándolo → retirarlo no baja a nadie. Los tests de este archivo comparten el almacén y van en orden."""
import json
import os
import random
import sys
from datetime import date

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["LOCAL"] = "1"; os.environ.setdefault("DATA_DIR", os.path.join(RAIZ, "data")); os.environ.pop("MODEL_ID", None)
sys.path.insert(0, os.path.join(RAIZ, "lambda"))
import app  # noqa: E402
import datos  # noqa: E402
import decisor  # noqa: E402
import puntaje  # noqa: E402
import rubrica  # noqa: E402

C = "2026-10-13"
FECHA_EV = "2026-10-01"
A, B, D, E = "PAC-HLF-00027", "PAC-HLF-00302", "PAC-HLF-00292", "PAC-HLF-00039"   # hipertensión (I10), prioridad baja
ESP = "Dr. Soto (cardiólogo)"
JEFA = "Dra. Rojas (jefatura Cardiología)"
ORDEN = puntaje.ORDEN_CAT


def call(method, path, qs=None, body=None):
    r = app.handler({"requestContext": {"http": {"method": method}}, "rawPath": path,
                     "queryStringParameters": qs, "body": json.dumps(body) if body else None})
    return r["statusCode"], json.loads(r["body"])


def filas(corte=C):
    return {p["id_paciente"]: p for p in call("GET", "/pacientes", {"fecha_corte": corte})[1]["pacientes"]}


def urgencia(pid, fecha=FECHA_EV):
    return call("POST", "/eventos", body={"id_paciente": pid, "tipo_evento": "visita_urgencia", "subtipo": "triage ESI 2",
                                          "fecha_evento": fecha, "fecha_corte": C, "especialidad": "Cardiología"})


def foto(f):
    return {pid: (p["categoria"], p["riesgo_vital"]) for pid, p in f.items()}


def test_00_parten_en_baja_y_sin_evento():
    datos.restablecer()
    f = filas()
    for pid in (A, B, D, E):
        assert f[pid]["diagnostico_cie10"] == "I10" and f[pid]["categoria"] == "baja" and f[pid]["estado_clinico"] == "sin_cambios"


def test_01_urgencia_grave_en_hipertension_no_sube_y_queda_dictamen():
    s, b = urgencia(A)
    assert s == 200 and b["paciente"]["categoria"] == "baja"
    d = b["dictamen"]
    assert d["id_paciente"] == A and d["disparador"]["tipo"] == "evento" and d["disparador"]["id_evento"] == b["evento"]["id_evento"]
    assert d["motor"] == "reglas" and d["resultado"]["cambio"] == "igual" and d["resultado"]["requiere_revision"]
    assert d["patron"] == "I10|visita_urgencia|grave"
    assert any(r.get("sin_regla") for r in d["fundamento"]) and "no tiene fila" in d["explicacion"]
    info = d["informacion_utilizada"]
    assert info["conocimiento"]["paquete"]["huella"] and info["conocimiento"]["paquete"]["etiqueta"].startswith("kb-")
    assert all({"id", "version", "sha256"} <= set(x) for x in info["conocimiento"]["fuentes"])
    assert {"diagnosticos_tabla_hlf", "registro_paciente"} <= {x["id"] for x in info["conocimiento"]["fuentes"]}
    assert any(c["id_evento"] == b["evento"]["id_evento"] for c in info["antecedentes"]["citados"])
    assert info["precedentes"]["total"] == 0 and info["ia"] is None
    # queda en la cola del especialista
    _, q = call("GET", "/decisiones", {"estado": "pendiente"})
    assert d["id_dictamen"] in [x["id_dictamen"] for x in q["decisiones"]]


def test_02_criterio_faltante_propone_criterio_y_nadie_mas_cambia():
    antes = foto(filas())
    rev = filas()[A]["rev"]
    s, b = call("POST", f"/pacientes/{A}/revision", body={
        "accion": "ajustar", "categoria_ajustada": "alta", "veredicto": "incorrecta", "motivo_codigo": "criterio_faltante",
        "motivo": "hipertensión con urgencia ESI 2: riesgo de daño de órgano blanco", "usuario": ESP, "fecha_corte": C, "rev_vista": rev})
    assert s == 200, b
    assert b["revision"]["patron"] == "I10|visita_urgencia|grave" and b["revision"]["id_dictamen"] == b["id_dictamen"]
    c = b["aprendizaje"]["criterio_local"]
    assert c["estado"] == "propuesto" and c["patron_texto"] == "I10|visita_urgencia|grave" and c["efecto"] == {"tipo": "subir_a", "categoria": "alta"}
    assert "jefatura" in b["aprendizaje"]["mensaje"] and b["aprendizaje"]["precedente"]["incorrectas"] == 1
    despues = foto(filas())
    assert {pid for pid in antes if antes[pid] != despues.get(pid)} == {A}     # solo el revisado (por su revisión)
    assert despues[A] == ("alta", False)
    # el dictamen juzgado trae su revisión unida
    _, h = call("GET", f"/pacientes/{A}/decisiones")
    assert h["decisiones"][0]["revision"]["veredicto"] == "incorrecta" and not h["decisiones"][0]["necesita_revision"]


def test_03_otro_paciente_igual_ve_la_sugerencia_sin_cambiar_de_prioridad():
    s, b = urgencia(B)
    assert s == 200 and b["paciente"]["categoria"] == "baja" and not b["paciente"]["riesgo_vital"]
    assert [x["id"] for x in b["paciente"]["criterios_propuestos"]] == ["CL-0001"]
    assert b["paciente"]["gestion"]["estado"] == "pendiente_revision"
    d = b["dictamen"]
    assert d["resultado"]["requiere_revision"] and d["informacion_utilizada"]["conocimiento"]["criterios_propuestos"][0]["id"] == "CL-0001"
    assert d["informacion_utilizada"]["precedentes"]["incorrectas"] == 1        # lo que ya dijo el especialista del mismo patrón
    assert filas()[A]["gestion"]["estado"] != "pendiente_revision"              # quien lo propuso ya lo revisó


def test_04_jefatura_aprueba_y_suben_los_que_calzan_citando_el_criterio():
    antes = foto(filas())
    malo = call("POST", "/criterios-locales/CL-0001/resolver", body={"accion": "aprobar", "motivo": "corto", "usuario": JEFA})
    assert malo[0] == 400
    s, b = call("POST", "/criterios-locales/CL-0001/resolver", body={
        "accion": "aprobar", "motivo": "revisado en reunión clínica de cardiología: se adopta", "usuario": JEFA, "fecha_corte": C})
    assert s == 200 and b["criterio"]["estado"] == "vigente" and b["criterio"]["vigente_desde"] == C
    assert call("POST", "/criterios-locales/CL-0001/resolver", body={"accion": "aprobar", "motivo": "x" * 25, "usuario": JEFA})[0] == 409
    despues = filas()
    cambiaron = {pid for pid in antes if foto(despues)[pid] != antes[pid]}
    assert B in cambiaron and all(despues[p]["diagnostico_cie10"] == "I10" for p in cambiaron)
    assert {d["id_paciente"] for d in b["dictamenes"]} == cambiaron
    f = despues[B]
    assert f["categoria"] == "alta" and f["riesgo_vital"] and f["razones"][0]["factor"] == "riesgo_vital"
    razon = next(r for r in f["razones"] if r["factor"] == "criterio_local")
    assert "CL-0001 v1" in razon["fuente"] and JEFA in razon["fuente"] and "basado en 1 revisión" in razon["fuente"]
    d = next(d for d in call("GET", f"/pacientes/{B}/decisiones")[1]["decisiones"] if d["disparador"]["tipo"] == "criterio_local")
    assert d["resultado"]["cambio"] == "sube" and d["resultado"]["alerta_nueva"] and "criterio local" in d["explicacion"].lower()
    assert "criterios_locales" in [x["id"] for x in d["informacion_utilizada"]["conocimiento"]["fuentes"]]
    # base de conocimiento: el criterio aparece para el diagnóstico y sube la versión de la capa local
    _, kb = call("GET", "/conocimiento/diagnostico/I10")
    assert [c["id"] for c in kb["criterios_locales"]] == ["CL-0001"]
    assert call("GET", "/conocimiento")[1]["capa_local"]["version"] == 1


def test_05_evento_nuevo_igual_sube_solo_citando_el_criterio():
    s, b = urgencia(D)
    assert s == 200 and b["paciente"]["categoria"] == "alta" and b["paciente"]["riesgo_vital"]
    d = b["dictamen"]
    assert d["resultado"]["cambio"] == "sube" and d["resultado"]["alerta_nueva"]
    assert d["informacion_utilizada"]["conocimiento"]["criterios_locales"] == [{"id": "CL-0001", "version": 1}]
    assert "CL-0001" in d["explicacion"]


def test_06_antes_de_la_aprobacion_el_criterio_no_rige():
    p = datos.perfil_de(D)
    assert puntaje.puntuar(p, date(2026, 10, 5))["categoria"] == "baja"      # el evento ya estaba, el criterio aún no
    assert puntaje.puntuar(p, date(2026, 10, 13))["categoria"] == "alta"
    assert filas("2026-10-05")[D]["categoria"] == "baja"


def test_11_reglas_e_ia_coinciden_cuando_rige_un_criterio_local():
    kb = decisor.cargar_kb()
    try:
        os.environ["ALGORITMO"] = "rubrica"
        app._llm["cliente"] = rubrica.ClienteFalso(lambda texto: rubrica.respuesta_determinista(
            rubrica.historial(datos.perfil_de(E), date(2026, 10, 13)), decisor.kb_diagnostico(kb, "I10")))
        s, b = urgencia(E)
        assert s == 200, b
        ev = b["evaluacion"]
        assert ev["categoria_final"] == "alta" and ev["categoria_rubrica"] == "alta" and ev["descompensacion_grave_final"]
        assert not ev["respaldo_reglas"] and not any(m["motivo"] == "bajaria" for m in ev["controles"])
        assert b["paciente"]["algoritmo"] == "rubrica" and b["paciente"]["categoria"] == "alta"
        d = b["dictamen"]
        assert d["motor"] == "ia_rubrica" and d["informacion_utilizada"]["ia"]["modelo"] == "falso"
        assert d["informacion_utilizada"]["ia"]["huella_kb"] and d["informacion_utilizada"]["ia"]["lecturas"] == 3
    finally:
        os.environ.pop("ALGORITMO", None)
        app._llm["cliente"] = None


def test_07_criterio_no_aplica_no_baja_a_nadie_y_queda_en_reglas_a_validar():
    antes = foto(filas())
    pid = "PAC-HLF-00002"   # sube a alta por "Angina inestable" (tabla del HLF)
    s, b = call("POST", f"/pacientes/{pid}/revision", body={
        "accion": "confirmar", "veredicto": "incorrecta", "motivo_codigo": "criterio_no_aplica",
        "motivo": "la angina es estable, no corresponde la fila de angina inestable", "usuario": ESP, "fecha_corte": C})
    assert s == 200 and "reglas a validar" in b["aprendizaje"]["mensaje"] and b["aprendizaje"]["criterio_local"] is None
    assert foto(filas()) == antes
    _, a = call("GET", "/aprendizaje")
    r = a["reglas_a_validar"][0]
    assert r["factor"] == "tabla_oficial" and "Angina inestable" in r["valor"] and r["especialistas"] == 1 and pid in r["pacientes"]
    g = a["concordancia"]["global"]
    assert g["n"] == 2 and g["incorrectas"] == 2 and g["n_kappa"] == 2
    assert {x["patron"] for x in a["concordancia"]["por_patron"]} == {"I10|visita_urgencia|grave", "I20|hospitalizacion|grave"}
    assert all("n" in x for x in a["concordancia"]["por_diagnostico"] + a["concordancia"]["por_regla"])


def test_08_retirar_el_criterio_no_baja_a_nadie_y_vuelven_a_la_cola():
    antes = filas()
    subidos = {pid for pid, f in antes.items() if any(c["id"] == "CL-0001" for c in f.get("criterios_locales") or [])}
    assert {B, D, E} <= subidos
    k0 = call("GET", "/kpis", {"fecha_corte": C})[1]["concordancia"]["revisiones"]
    s, b = call("POST", "/criterios-locales/CL-0001/resolver", body={
        "accion": "retirar", "motivo": "se reemplazará por el protocolo de HTA del servicio", "usuario": JEFA, "fecha_corte": C})
    assert s == 200 and b["criterio"]["estado"] == "retirado" and set(b["conservan_prioridad"]) == subidos
    despues = filas()
    for pid in subidos:
        assert despues[pid]["categoria"] == "alta" and despues[pid]["estado_revision"] == "ajustado"
        assert despues[pid]["revision"]["automatica"] and despues[pid]["revision"]["usuario"] == JEFA
        assert "criterios_locales" not in despues[pid]
    assert all(ORDEN[despues[p]["categoria"]] >= ORDEN[antes[p]["categoria"]] for p in antes if p in despues)
    _, q = call("GET", "/decisiones", {"estado": "pendiente", "limite": 200})
    pend = {d["id_paciente"] for d in q["decisiones"] if d["disparador"]["tipo"] == "criterio_local"}
    assert subidos <= pend
    assert call("GET", "/kpis", {"fecha_corte": C})[1]["concordancia"]["revisiones"] == k0   # la automática no cuenta
    _, a = call("GET", "/aprendizaje")
    assert a["concordancia"]["global"]["n"] == 2
    assert [h["evento"] for h in a["criterios_locales"][0]["historial"]] == ["proponer", "aprobar", "retirar"]   # solo se agrega


def _sube_por_hospitalizacion():
    """Un paciente de angina (I20) en prioridad baja al que una hospitalización sube a alta."""
    f = filas()
    pid = next(p for p, x in sorted(f.items()) if x["diagnostico_cie10"] == "I20" and x["categoria"] == "baja" and x["estado_clinico"] == "sin_cambios"
               and not x.get("revision"))
    s, b = call("POST", "/eventos", body={"id_paciente": pid, "tipo_evento": "hospitalizacion", "subtipo": "ingreso hospitalario",
                                          "fecha_evento": FECHA_EV, "fecha_corte": C})
    assert s == 200 and b["paciente"]["categoria"] == "alta"
    return pid, b["evento"]["id_evento"]


def test_09_enmiendas_cambian_la_prioridad_de_ese_paciente_y_dejan_dictamen():
    for accion in ("no_relacionado", "anular"):
        pid, ide = _sube_por_hospitalizacion()
        assert call("POST", f"/pacientes/{pid}/eventos/{ide}/enmienda", body={"accion": accion, "motivo": "corto", "usuario": ESP})[0] == 400
        assert call("POST", f"/pacientes/{pid}/eventos/EV-NO-EXISTE/enmienda",
                    body={"accion": accion, "motivo": "x" * 25, "usuario": ESP})[0] == 404
        assert call("POST", f"/pacientes/{A}/eventos/{ide}/enmienda", body={"accion": accion, "motivo": "x" * 25, "usuario": ESP})[0] == 404
        s, b = call("POST", f"/pacientes/{pid}/eventos/{ide}/enmienda", body={
            "accion": accion, "motivo": "la hospitalización fue por una fractura de cadera, no por angina", "usuario": ESP, "fecha_corte": C})
        assert s == 200, b
        assert b["paciente"]["categoria"] == "baja"
        d = b["dictamen"]
        assert d["disparador"]["tipo"] == "enmienda" and d["disparador"]["id_evento"] == ide and d["resultado"]["cambio"] == "baja"
        assert "persona" in d["explicacion"]
        perfil = datos.perfil_de(pid)
        if accion == "anular":
            assert [e["id_evento"] for e in perfil["eventos_anulados"]] == [ide]
            assert call("POST", f"/pacientes/{pid}/eventos/{ide}/enmienda",
                        body={"accion": "anular", "motivo": "x" * 25, "usuario": ESP})[0] == 409
        else:
            assert next(e for e in perfil["eventos_clinicos"] if e["id_evento"] == ide)["relacionado"] is False


def test_09b_evento_no_relacionado_sugiere_la_enmienda():
    pid, ide = _sube_por_hospitalizacion()
    s, b = call("POST", f"/pacientes/{pid}/revision", body={
        "accion": "confirmar", "veredicto": "incorrecta", "motivo_codigo": "evento_no_relacionado",
        "motivo": "la hospitalización fue por una apendicitis", "usuario": ESP, "fecha_corte": C})
    sug = b["aprendizaje"]["sugerencia"]
    assert s == 200 and sug["accion"] == "no_relacionado" and sug["id_evento"] == ide and sug["ruta"].endswith(f"/eventos/{ide}/enmienda")
    s, b = call("POST", sug["ruta"], body={**sug["cuerpo"], "fecha_corte": C})
    assert s == 200 and b["paciente"]["categoria"] == "baja"


def test_10_rev_vista_desactualizado_responde_409():
    rev = filas()[A]["rev"]
    urgencia(A, "2026-10-02")                                               # llega algo nuevo mientras lo tenía abierto
    n = len(datos.registros_tipo("revision#", A))
    s, b = call("POST", f"/pacientes/{A}/revision", body={"accion": "confirmar", "usuario": ESP, "fecha_corte": C, "rev_vista": rev})
    assert s == 409 and b["codigo"] == "conflicto_edicion"
    assert len(datos.registros_tipo("revision#", A)) == n                    # no quedó nada a medias
    s, _ = call("POST", f"/pacientes/{A}/revision", body={"accion": "confirmar", "usuario": ESP, "fecha_corte": C, "rev_vista": filas()[A]["rev"]})
    assert s == 200


def test_validaciones_del_veredicto():
    base = {"accion": "confirmar", "usuario": ESP, "fecha_corte": C}
    assert call("POST", f"/pacientes/{A}/revision", body={**base, "veredicto": "regular"})[0] == 400
    assert call("POST", f"/pacientes/{A}/revision", body={**base, "veredicto": "incorrecta"})[0] == 400          # sin motivo_codigo
    assert call("POST", f"/pacientes/{A}/revision", body={**base, "veredicto": "incorrecta", "motivo_codigo": "otro", "motivo": "x"})[0] == 400
    assert call("POST", f"/pacientes/{A}/revision", body={**base, "id_dictamen": "DIC-NO-EXISTE"})[0] == 404
    assert {m["valor"] for m in call("GET", "/catalogo")[1]["motivos_veredicto"]} == {
        "criterio_faltante", "criterio_no_aplica", "evento_no_relacionado", "lectura_incorrecta", "informacion_no_registrada", "otro"}
    assert call("POST", "/criterios-locales/CL-9999/resolver", body={"accion": "aprobar", "motivo": "x" * 25, "usuario": JEFA})[0] == 404


def test_criterio_faltante_hacia_abajo_o_sin_evento_no_propone():
    pid = "PAC-HLF-00181"   # I10 baja, sin evento determinante
    s, b = call("POST", f"/pacientes/{pid}/revision", body={
        "accion": "ajustar", "categoria_ajustada": "media", "veredicto": "incorrecta", "motivo_codigo": "criterio_faltante",
        "motivo": "control de presión muy alterado en consulta", "usuario": ESP, "fecha_corte": C})
    assert s == 200 and b["aprendizaje"]["criterio_local"] is None and "evento determinante" in b["aprendizaje"]["mensaje"]
    assert b["revision"]["patron"] == "I10|*|*" and b["id_dictamen"]                 # revisión directa: se documenta igual
    d = call("GET", f"/pacientes/{pid}/decisiones")[1]["decisiones"][0]
    assert d["disparador"]["tipo"] == "revision_directa" and d["revision"]["veredicto"] == "incorrecta" and not d["necesita_revision"]


def test_12_propiedad_criterios_locales_cualesquiera_nunca_bajan_a_nadie():
    datos.restablecer()
    perfs = list(datos.perfiles_combinados()[0].values())
    corte = date(2026, 10, 13)
    sin = {r["id_paciente"]: r for r in (puntaje.puntuar(p, corte) for p in perfs) if r and not r.get("excluido")}
    azar = random.Random(7)
    dxs = sorted({puntaje.cie_base(p["lista_espera"]["diagnostico_cie10"]) for p in perfs})
    for i in range(40):
        c = {"id": f"CL-{9000 + i}", "version": 1, "estado": azar.choice(["vigente", "propuesto", "retirado"]), "evento": "aprobar",
             "patron": {"diagnostico": azar.choice(dxs), "tipo_evento": azar.choice(["visita_urgencia", "hospitalizacion", "*"]),
                        "severidad": azar.choice(["grave", "moderada", "*"])},
             "efecto": {"tipo": "subir_a", "categoria": azar.choice(["alta", "media", "baja"])}, "texto": f"criterio de prueba {i}",
             "precedentes": [], "vigente_desde": azar.choice(["2026-01-01", "2026-09-01", "2026-12-01"]),
             "vigente_hasta": azar.choice([None, "2026-10-01"]), "fecha": datos.ahora(), "resuelto_por": "prueba"}
        datos.guardar({"id_paciente": "_kb", "sk": f'criterio_local#{c["id"]}#{c["fecha"]}', "criterio_local": json.dumps(c)})
    con = {r["id_paciente"]: r for r in (puntaje.puntuar(p, corte) for p in perfs) if r and not r.get("excluido")}
    assert set(con) == set(sin)
    subieron = 0
    for pid, r in sin.items():
        assert ORDEN[con[pid]["categoria"]] >= ORDEN[r["categoria"]], pid
        assert con[pid]["riesgo_vital"] or not r["riesgo_vital"], pid
        subieron += con[pid]["categoria"] != r["categoria"] or con[pid]["riesgo_vital"] != r["riesgo_vital"]
    assert subieron > 0                       # la prueba no es trivial: algún criterio sí aplicó
    datos.restablecer()
