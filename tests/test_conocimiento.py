"""Base de conocimiento versionada y trazable (ESPECIFICACION_MVP §4): el manifiesto corresponde a los archivos, la huella
no depende del formato, qué sabe el sistema por diagnóstico, qué fuentes respaldan una decisión y las rutas. Sin AWS ni IA.

Si falla test_el_manifiesto_corresponde_a_los_archivos: alguien cambió una fuente o un archivo con reglas y no regeneró
el manifiesto. Se arregla con `python scripts/empaquetar_conocimiento.py` (docs/conocimiento/README.md §4)."""
import copy
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["LOCAL"] = "1"; os.environ.setdefault("DATA_DIR", os.path.join(RAIZ, "data")); os.environ.pop("MODEL_ID", None)
sys.path.insert(0, os.path.join(RAIZ, "lambda"))
import base_conocimiento as bc  # noqa: E402
import combinaciones  # noqa: E402
import criterios  # noqa: E402
import decisor  # noqa: E402
import puntaje  # noqa: E402
import rubrica  # noqa: E402

CORTE = date(2026, 10, 13)
KB = os.path.join(RAIZ, "lambda", "conocimiento")
SCRIPT = os.path.join(RAIZ, "scripts", "empaquetar_conocimiento.py")
BLOQUES = ("tabla", "si_se_descompensa", "regla_oncologica", "ges", "criterios_oficiales", "criterios_clinicos", "reglas_con_el_registro",
           "rubrica", "letalidad", "combinaciones", "orden", "plazo_referencia")


def _modulo(ruta):
    spec = importlib.util.spec_from_file_location(os.path.splitext(os.path.basename(ruta))[0], ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


emp = _modulo(SCRIPT)


def _json(ruta):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def _fuente(fid):
    return _json(os.path.join(KB, fid + ".json"))


@pytest.fixture(scope="module")
def perfs():
    """El registro tal como viene (sin lo que otros tests agregan en memoria)."""
    return {p["id_paciente"]: p for p in _json(os.path.join(os.environ["DATA_DIR"], "perfiles.json"))}


@pytest.fixture
def copia(tmp_path):
    """Copia de las fuentes, los módulos, los scripts y este README: para cambiar archivos sin tocar los reales."""
    for carpeta in ("lambda", "scripts", os.path.join("docs", "conocimiento")):
        shutil.copytree(os.path.join(RAIZ, carpeta), tmp_path / carpeta, ignore=shutil.ignore_patterns("__pycache__"))
    return tmp_path


def _razones_rubrica(p, kb):
    """Razones del modo con rúbrica, con el lector determinista (sin IA)."""
    dx = decisor.kb_diagnostico(kb, p["lista_espera"]["diagnostico_cie10"])
    resp = rubrica.RespuestaRubrica.model_validate(rubrica.respuesta_determinista(rubrica.historial(p, CORTE), dx))
    return decisor.decidir(p, resp, CORTE, kb)["razones"]


# ---------- manifiesto ----------
def test_el_manifiesto_corresponde_a_los_archivos():
    r = subprocess.run([sys.executable, "-X", "utf8", SCRIPT, "--verificar"], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
    assert bc.integridad() == {"integro": True, "diferencias": []}   # y el servicio ve lo mismo al leer los archivos
    m, paq = _json(os.path.join(KB, "manifiesto.json")), bc.paquete()
    assert (paq["etiqueta"], paq["huella"], paq["generado"]) == (m["paquete"]["etiqueta"], m["paquete"]["huella"], m["paquete"]["generado"])
    assert paq["integro"] and paq["motor"] == {"huella": m["motor"]["huella"], "archivos": len(m["motor"]["archivos"])}
    assert bc.fuentes() == m["fuentes"] and bc.motor() == m["motor"]


def test_el_manifiesto_trae_cada_fuente_con_version_huella_estado_y_quien_la_usa():
    m = _json(os.path.join(KB, "manifiesto.json"))
    assert sorted(f["id"] for f in m["fuentes"]) == sorted(n[:-5] for n in os.listdir(KB) if n.endswith(".json") and n != "manifiesto.json")
    tipos = {"tabla_oficial", "norma", "garantia_ges", "criterios_clinicos", "combinaciones", "evidencia", "rubrica"}
    for f in m["fuentes"]:
        assert {"id", "titulo", "tipo", "archivo", "version", "sha256", "fecha", "origen", "origen_url", "estado", "entradas", "usado_por"} <= set(f)
        j = _json(os.path.join(RAIZ, f["archivo"]))
        assert f["version"] == j["version"] and f["sha256"] == bc.huella_objeto(j) and f["tipo"] in tipos and f["entradas"] > 0
        assert f["usado_por"] and all(os.path.exists(os.path.join(RAIZ, u)) for u in f["usado_por"])
    estados = {f["id"]: f["estado"] for f in m["fuentes"]}   # salen de los JSON y de CRITERIO_PRIORIZACION §3
    assert estados["ord536"] == "fuente secundaria" and estados["criterios_especialidad"] == "origen no confirmado: solo sube"
    assert estados["diagnosticos_tabla_hlf"] == estados["ges_especialista"] == "verificado en la fuente"
    paq, motor = m["paquete"], m["motor"]
    assert re.fullmatch(r"kb-\d{4}\.\d{2}\.\d+", paq["etiqueta"]) and paq["generado"]
    assert len(paq["huella"]) == 12 and paq["huella"] == bc.huella_paquete(m["fuentes"], motor["archivos"])
    assert [a["archivo"] for a in motor["archivos"]] == ["lambda/" + n for n in emp.MOTOR] and motor["huella"] == motor["sha256"][:12]
    constantes = {c["nombre"]: c for c in motor["constantes"]}   # las constantes clínicas del código, con su fuente
    for nombre in ("puntaje.FILA_DESCOMPENSADO", "puntaje.EQUIVALENCIA_A_VALIDAR", "puntaje.FILA_ONCOLOGICA", "puntaje.LETALIDAD_DX", "puntaje.PLAZO_CATEGORIA"):
        assert constantes[nombre]["fuente"] and constantes[nombre]["sha256"]
    assert constantes["puntaje.FILA_DESCOMPENSADO"]["entradas"] == len(puntaje.FILA_DESCOMPENSADO)
    assert {r["efecto"] for r in motor["reglas_en_codigo"]} >= {"alta", "media"} and all(r["criterio"] and r["diagnosticos"] for r in motor["reglas_en_codigo"])


def test_cambiar_una_fuente_se_detecta_y_no_se_acepta_con_la_misma_version(copia, capsys):
    raiz, manifiesto = str(copia), copia / "lambda" / "conocimiento" / "manifiesto.json"
    assert emp.main(["--raiz", raiz, "--verificar"]) == 0
    ruta = copia / "lambda" / "conocimiento" / "ges_especialista.json"
    j = json.loads(ruta.read_text(encoding="utf-8"))
    version = j["version"]
    j["problemas"][0]["plazo_dias"] += 1                                   # alguien cambia una regla y no toca nada más
    ruta.write_text(json.dumps(j, ensure_ascii=False, indent=1), encoding="utf-8")
    capsys.readouterr()
    assert emp.main(["--raiz", raiz, "--verificar"]) == 1                   # el manifiesto lo delata…
    salida = capsys.readouterr().out
    assert "fuente ges_especialista: cambió el contenido" in salida and f"su versión sigue en '{version}'" in salida
    antes = manifiesto.read_bytes()
    assert emp.main(["--raiz", raiz]) == 2 and manifiesto.read_bytes() == antes   # …y no se regenera con la misma versión
    j["version"] = version + ".1"
    ruta.write_text(json.dumps(j, ensure_ascii=False, indent=1), encoding="utf-8")
    assert emp.main(["--raiz", raiz, "--etiqueta", "kb-2026.12.0"]) == 0
    m = json.loads(manifiesto.read_text(encoding="utf-8"))
    f = next(x for x in m["fuentes"] if x["id"] == "ges_especialista")
    assert f["version"] == version + ".1" and f["sha256"] == bc.huella_objeto(j)
    assert m["paquete"]["etiqueta"] == "kb-2026.12.0" and m["paquete"]["huella"] != json.loads(antes)["paquete"]["huella"]
    assert f"`{version}.1`" in (copia / "docs" / "conocimiento" / "README.md").read_text(encoding="utf-8")   # la tabla del README se actualiza sola
    assert emp.main(["--raiz", raiz, "--verificar"]) == 0
    despues = manifiesto.read_bytes()
    assert emp.main(["--raiz", raiz]) == 0 and manifiesto.read_bytes() == despues   # regenerar sin cambios no toca nada (ni `generado`)


def test_cambiar_una_regla_del_codigo_tambien_se_detecta(copia, capsys):
    ruta = copia / "lambda" / "puntaje.py"
    with open(ruta, "a", encoding="utf-8") as f:
        f.write("\nUMBRAL_NUEVO = 9  # sin fuente\n")
    assert emp.main(["--raiz", str(copia), "--verificar"]) == 1
    salida = capsys.readouterr().out
    assert "motor lambda/puntaje.py: cambió" in salida and "la constante puntaje.UMBRAL_NUEVO es nueva" in salida


def test_la_huella_no_depende_del_formato(tmp_path):
    with open(os.path.join(KB, "ord536.json"), "rb") as f:
        lf = f.read().replace(b"\r\n", b"\n")
    crlf, obj = lf.replace(b"\n", b"\r\n"), json.loads(lf.decode("utf-8"))
    otro = json.dumps(dict(reversed(list(obj.items()))), ensure_ascii=True, indent=4).encode()   # otro orden, otra sangría, \uXXXX
    assert bc.huella_json(lf) == bc.huella_json(crlf) == bc.huella_json(otro) == bc.huella_objeto(obj)
    for nombre, datos in (("lf.json", lf), ("crlf.json", crlf), ("bom.json", b"\xef\xbb\xbf" + crlf)):
        (tmp_path / nombre).write_bytes(datos)
    assert len({bc.huella_archivo(str(tmp_path / n)) for n in ("lf.json", "crlf.json", "bom.json")}) == 1
    obj["cascada"][0]["orden"] = 9
    assert bc.huella_objeto(obj) != bc.huella_json(lf)                      # el contenido sí importa
    with open(os.path.join(RAIZ, "lambda", "puntaje.py"), "rb") as f:
        py = f.read().replace(b"\r\n", b"\n")
    assert bc.huella_texto(py) == bc.huella_texto(py.replace(b"\n", b"\r\n")) != bc.huella_texto(py + b"# cambio\n")


def test_en_ejecucion_se_informa_lo_que_hay_en_disco(tmp_path, monkeypatch):
    """Un despliegue con una fuente cambiada y el manifiesto antiguo no certifica la versión declarada."""
    kb = tmp_path / "conocimiento"
    shutil.copytree(KB, kb)
    j = _fuente("ord536")
    j["cascada"][1]["detalle"] += " (cambiado)"
    (kb / "ord536.json").write_text(json.dumps(j, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(bc, "DIR_KB", str(kb))
    bc.reiniciar()
    try:
        i, paq = bc.integridad(), bc.paquete()
        assert not i["integro"] and len(i["diferencias"]) == 1 and i["diferencias"][0].startswith("ord536:")
        assert paq["integro"] is False and paq["huella"] != paq["huella_manifiesto"]
        razon = [{"factor": "dias_espera", "valor": "400 días en lista (más de 1 año)", "fuente": "MINSAL Ord. 536/2025: antigüedad > 1 año"}]
        assert bc.fuentes_de(razon)[0]["sha256"] == bc.huella_objeto(j)      # la huella real, no la del manifiesto
        for roto in ('{"fuentes": [{}], "motor": {"archivos": []}}', "no es json", None):   # manifiesto dañado o ausente: no se cae
            if roto is None:
                os.remove(kb / "manifiesto.json")
            else:
                (kb / "manifiesto.json").write_text(roto, encoding="utf-8")
            bc.reiniciar()
            assert not bc.integridad()["integro"] and bc.paquete()["etiqueta"] is None
            assert {f["id"]: f["version"] for f in bc.fuentes()}["ord536"] == j["version"]   # informa lo que encuentra en disco
            assert bc.fuentes_de(razon)[0]["sha256"] == bc.huella_objeto(j)
    finally:
        monkeypatch.undo()
        bc.reiniciar()
    assert bc.integridad()["integro"]


# ---------- coherencia entre las fuentes y el código ----------
def test_la_rubrica_consolidada_corresponde_a_sus_fuentes(copia):
    """rubrica_v1.json se genera desde otras 4 fuentes: si alguien cambia una y no la regenera, la fórmula leería lo antiguo."""
    consolidar = _modulo(os.path.join(RAIZ, "scripts", "consolidar_rubrica.py"))
    consolidar.KB = str(copia / "lambda" / "conocimiento")
    consolidar.main()
    assert bc.huella_archivo(os.path.join(consolidar.KB, "rubrica_v1.json")) == bc.huella_archivo(os.path.join(KB, "rubrica_v1.json"))
    fichas = {f["id"]: f for f in bc.fuentes()}
    assert all("scripts/consolidar_rubrica.py" in fichas[fid]["usado_por"] for fid in fichas["rubrica_v1"]["derivada_de"])


def test_las_constantes_del_codigo_coinciden_con_la_tabla():
    """La fila 'descompensado' está en puntaje.FILA_DESCOMPENSADO (reglas) y en ssmso_hlf_2025 → rubrica_v1 (fórmula)."""
    ssmso = _fuente("ssmso_hlf_2025")["diagnosticos"]
    con_fila = {c: d["fila_descompensado"] for c, d in ssmso.items() if d.get("fila_descompensado")}
    assert set(con_fila) == set(puntaje.FILA_DESCOMPENSADO)
    for cie, (texto, prioridad, pagina) in puntaje.FILA_DESCOMPENSADO.items():
        f = con_fila[cie]
        assert (prioridad, pagina) == (f["prioridad"], f["pagina"]) and texto.upper().startswith(f["texto_pdf"]), cie
    assert set(puntaje.EQUIVALENCIA_A_VALIDAR) == {c for c, d in ssmso.items() if d.get("equivalencia")}
    kb = decisor.cargar_kb()
    for cie in ssmso:                                                        # los dos modos usan la misma fila
        fila, dx = puntaje.fila_descompensado(cie)[0], decisor.kb_diagnostico(kb, cie)
        f = dx.get("fila_descompensado") if dx.get("estado") == "con_fuente" else None
        assert (fila and fila[1:]) == (f and (f["prioridad"], f["pagina"])), cie
    cascada = {c["criterio"] for c in _fuente("ord536")["cascada"]}         # claves con que fuentes_de cita el Ord. 536
    assert {"antiguedad_mayor_1_anio", "grupo_especial_proteccion"} <= cascada


# ---------- qué sabe y aplica el sistema para un diagnóstico ----------
def test_para_diagnostico_I20():
    d = bc.para_diagnostico("I20")
    assert (d["codigo"], d["cie10_base"], d["diagnostico"], d["especialidad"]) == ("I20", "I20", "Angina de pecho", "Cardiología")
    s = d["si_se_descompensa"]
    assert (s["fila"], s["prioridad"], s["pagina"], s["equivalencia_a_validar"]) == ("Angina inestable", "alta", 85, True)
    assert "angina inestable" in s["equivalencia"] and s["fuente"] == {"id": "ssmso_hlf_2025", "version": _fuente("ssmso_hlf_2025")["version"],
                                                                         "clave": "I20", "constante": "puntaje.FILA_DESCOMPENSADO"}
    assert d["tabla"]["fila"] is None and "HLF-CAR-01" in [x["codigo"] for x in d["tabla"]["misma_enfermedad"]]
    assert d["ges"] is None and d["criterios_clinicos"] is None and isinstance(d["criterios_locales"], list)
    assert d["criterios_oficiales"]["id"] == "registro_I20" and d["criterios_oficiales"]["urgencias"] and "health.qld.gov.au" in d["criterios_oficiales"]["url"]
    assert {c["codigo"] for c in d["criterios_oficiales"]["criterios"]} >= {"alta.0", "media.0", "baja.0"} and d["criterios_oficiales"]["piso"] is None
    assert d["letalidad"]["nivel"] == puntaje.LETALIDAD_DX["I20"][0] and d["letalidad"]["fuente"]["constante"] == "puntaje.LETALIDAD_DX"
    assert d["regla_oncologica"]["prioridad"] == "alta" and d["regla_oncologica"]["equivalencia_a_validar"]   # Cardiología no tiene fila oncológica propia
    assert [v["pmid"] for v in d["rubrica"]["ventanas"]] == ["25656852", "25656852"] and all(p.startswith("I20:") for p in d["rubrica"]["pendientes_medicos"])
    assert "coronario_dolor_reposo" in [c["id"] for c in d["combinaciones"]["por_diagnostico"]]
    assert [c["criterio"] for c in d["orden"]["cascada"]][0] == "criterio_medico" and d["orden"]["estado"] == "fuente secundaria"
    assert "LACE" in d["orden"]["como_se_aplica"] and "desempate_lace" not in d["orden"]   # la angina no pesa en el Charlson del LACE
    assert d["plazo_referencia"]["dias_por_prioridad"] == puntaje.PLAZO_CATEGORIA
    assert bc.para_diagnostico(" i20 ")["codigo"] == bc.para_diagnostico("I20.0")["codigo"] == "I20"
    json.dumps(d)                                                            # se puede devolver por la API tal cual


def test_para_diagnostico_E11():
    d = bc.para_diagnostico("E11")
    assert d["ges"]["problema"] == 7 and d["ges"]["plazo_dias"] == 60 and "60 días" in d["ges"]["cita"] and d["ges"]["fuente"]["id"] == "ges_especialista"
    r = d["rubrica"]
    assert r["medicion_clave"] == "HbA1c" and r["medicion"]["umbral"]["valor"] == 7 and r["medicion"]["sube_a_fila"]
    assert r["medicion"]["umbral"]["fuente"] == {"id": "guias_umbrales", "version": _fuente("guias_umbrales")["version"],
                                                   "clave": "medicion.HbA1c.descompensado_umbral"}
    assert {v["evento"]: v["dias"] for v in r["ventanas"]} == {"hospitalizacion": 30, "visita_urgencia": 30}
    assert all(v["pmid"] and v["fuente"]["id"] == "pubmed_evidencia" for v in r["ventanas"])
    assert (d["si_se_descompensa"]["fila"], d["si_se_descompensa"]["prioridad"], d["si_se_descompensa"]["pagina"]) == ("DM2 descontrolada", "media", 101)
    reglas = d["reglas_con_el_registro"]                                     # leídas del código, no copiadas
    assert ["alta", "media"] == [x["efecto"] for x in reglas["reglas"]] and "HbA1c > 10%" in reglas["reglas"][0]["criterio"]
    assert reglas["fuente"]["id"] == "motor" and reglas["fuente"]["version"] == bc.paquete()["motor"]["huella"]
    assert "pie_diabetico_lesion" in [c["id"] for c in d["combinaciones"]["por_diagnostico"]] and d["letalidad"]["nivel"] == 3
    lace = d["orden"]["desempate_lace"]                                      # la diabetes sí cuenta en el Charlson del LACE (experimental)
    assert lace["charlson"] == puntaje.CHARLSON_LACE["E11"][0] and lace["experimental"] and lace["fuente"]["constante"] == "puntaje.CHARLSON_LACE"


def test_para_diagnostico_con_un_codigo_de_la_tabla():
    d = bc.para_diagnostico("HLF-CAR-13")                                    # arritmias supraventriculares: fila propia, media
    assert (d["tabla"]["fila"]["texto"], d["tabla"]["fila"]["prioridad"], d["tabla"]["fila"]["pagina"]) == ("Arritmias supraventriculares", "media", 85)
    s = d["si_se_descompensa"]                                               # si empeora: la fila más grave de la misma tabla
    assert (s["fila"], s["prioridad"], s["equivalencia_a_validar"]) == ("Fibrilación auricular no controlada", "alta", True)
    assert s["fuente"]["id"] == "diagnosticos_tabla_hlf" and s["fuente"]["clave"] == "HLF-CAR-04"
    assert d["criterios_oficiales"] is None and d["rubrica"] is None and d["letalidad"] is None
    e = bc.para_diagnostico("hlf-car-01")                                    # misma enfermedad que I20: hereda lo del registro
    assert e["cie10_base"] == "I20" and e["criterios_oficiales"]["id"] == "registro_I20" and e["letalidad"]["nivel"] == 2 and e["rubrica"]["ventanas"]
    assert e["tabla"]["fila"]["prioridad"] == "alta" and e["tabla"]["fuente"]["clave"] == "HLF-CAR-01"
    u = bc.para_diagnostico("HLF-END-01")                                    # DM2 con cetoacidosis: ALTA-URGENCIA y GES de la diabetes
    assert u["tabla"]["fila"]["urgencia"] and u["ges"]["problema"] == 7 and u["cie10_base"] == "E11"
    sin = bc.para_diagnostico("HLF-TRA-12")                                  # quiste de Baker: sin fila más grave
    assert sin["si_se_descompensa"]["fila"] is None and "revisión" in sin["si_se_descompensa"]["detalle"]


def test_para_diagnostico_que_no_existe():
    for malo in ("Z99", "XX", "", None, "HLF-XXX-99", "123"):
        assert bc.para_diagnostico(malo) is None


def test_para_diagnostico_no_muestra_reglas_que_no_se_aplican():
    """F32 usa los criterios por especialidad y no tiene criterios oficiales del registro. La alerta PHQ-9 de aplicar_registro
    sí le llega (antes la función terminaba antes de emitirla: se corrigió) y es lo único que se muestra del registro."""
    d = bc.para_diagnostico("F32")
    assert d["criterios_oficiales"] is None and d["criterios_clinicos"]["id"] == "psiquiatria_07" and d["criterios_clinicos"]["urgencias"]
    assert d["criterios_clinicos"]["fuente"]["id"] == "criterios_especialidad" and d["especialidad"] == "Salud Mental"
    assert d["si_se_descompensa"]["pagina"] == 110 and d["ges"]["plazo_dias"] == 30 and d["rubrica"]["medicion_clave"] == "PHQ9"
    assert "F32" not in puntaje.criterios_registro()
    assert [r["efecto"] for r in d["reglas_con_el_registro"]["reglas"]] == ["alerta"] and "PHQ-9" in d["reglas_con_el_registro"]["reglas"][0]["criterio"]
    # las reglas que sí exigen criterios oficiales (HbA1c, exacerbaciones…) siguen sin mostrarse donde no se aplican
    assert bc.para_diagnostico("E11")["reglas_con_el_registro"] and not any(
        r["efecto"] == "alerta" for r in bc.para_diagnostico("E11")["reglas_con_el_registro"]["reglas"])


def test_cada_bloque_cita_su_fuente_con_la_version_vigente():
    vigentes = {f["id"]: f["version"] for f in bc.fuentes()}
    vigentes["motor"] = bc.paquete()["motor"]["huella"]
    codigos = sorted(set(puntaje.tabla_hlf()) | set(criterios.cargar()["por_cie"]))   # todo lo que el sistema conoce
    assert len(codigos) > 250
    for codigo in codigos:
        d = bc.para_diagnostico(codigo)
        assert d and d["codigo"] == codigo and d["si_se_descompensa"] and d["orden"] and d["plazo_referencia"], codigo
        citadas = set()
        for b in BLOQUES:
            if d[b] is not None:
                f = d[b]["fuente"]
                assert f["version"] and vigentes[f["id"]] == f["version"], (codigo, b)
                citadas.add(f["id"])
        assert citadas <= {f["id"] for f in d["fuentes"]} and all(f["sha256"] for f in d["fuentes"]), codigo


# ---------- qué fuentes respaldan una decisión ----------
def test_fuentes_de_las_razones_reales_de_00002(perfs):
    r = puntaje.puntuar(perfs["PAC-HLF-00002"], CORTE)
    assert r["categoria"] == "alta" and r["riesgo_vital"]
    lista = bc.fuentes_de(r["razones"])
    fs, fichas = {f["id"]: f for f in lista}, {f["id"]: f for f in bc.fuentes()}
    assert len(fs) == len(lista) and "sin_catalogar" not in fs               # sin repetir y todo catalogado
    assert all(set(f) == {"id", "titulo", "tipo", "version", "sha256", "factores", "claves"} for f in lista)
    tabla = fs["diagnosticos_tabla_hlf"]                                     # la tabla del HLF, con su versión y su huella vigentes
    assert tabla["version"] == _fuente("diagnosticos_tabla_hlf")["version"] and tabla["sha256"] == fichas["diagnosticos_tabla_hlf"]["sha256"]
    assert tabla["claves"] == ["HLF-CAR-01"] and tabla["factores"] == ["riesgo_vital", "tabla_oficial"]   # la fila "Angina inestable", pág. 85
    assert fs["ssmso_hlf_2025"]["claves"] == ["I20"] and fs["ssmso_hlf_2025"]["version"] == _fuente("ssmso_hlf_2025")["version"]
    assert fs["registro_paciente"]["factores"] == ["prioridad_inicial", "evento"] and fs["registro_paciente"]["version"] is None
    assert fs["motor"]["version"] == bc.paquete()["motor"]["huella"] and {"puntaje.LETALIDAD_DX", "puntaje.PLAZO_CATEGORIA"} <= set(fs["motor"]["claves"])
    assert fs["ord536"]["claves"] == ["antiguedad_mayor_1_anio"] and fs["ord536"]["version"] == _fuente("ord536")["version"]
    # por dónde se leyó la fila: las reglas, de la constante del código; la fórmula (modo con IA), de la rúbrica consolidada
    assert "puntaje.FILA_DESCOMPENSADO" in fs["motor"]["claves"] and "rubrica_v1" not in fs
    con_rubrica = {f["id"]: f for f in bc.fuentes_de(_razones_rubrica(perfs["PAC-HLF-00002"], decisor.cargar_kb()))}
    assert con_rubrica["diagnosticos_tabla_hlf"]["claves"] == ["HLF-CAR-01"] and "sin_catalogar" not in con_rubrica
    assert con_rubrica["rubrica_v1"]["claves"] == ["I20"] and con_rubrica["rubrica_v1"]["version"] == _fuente("rubrica_v1")["version"]
    assert "puntaje.FILA_DESCOMPENSADO" not in con_rubrica["motor"]["claves"]
    assert "rubrica_v1" in {f["id"] for f in bc.fuentes_de(r["razones"], motor="ia_rubrica")}   # o lo dice quien llama (el dictamen)


def test_fuentes_de_cubre_todos_los_factores_del_motor(perfs):
    en_codigo = set()
    for n in ("puntaje.py", "decisor.py"):
        with open(os.path.join(RAIZ, "lambda", n), encoding="utf-8") as f:
            en_codigo |= set(re.findall(r'"factor":\s*"(\w+)"', f.read()))
    assert len(en_codigo) > 15 and en_codigo <= set(bc.FACTORES), en_codigo - set(bc.FACTORES)   # un factor nuevo se cataloga aquí
    kb, usos = decisor.cargar_kb(), {}
    for p in perfs.values():                                                 # y con las razones reales de toda la lista, en los dos modos
        r = puntaje.puntuar(p, CORTE)
        if not r or r.get("excluido"):
            continue
        for razones in (r["razones"], _razones_rubrica(p, kb)):
            for f in bc.fuentes_de(razones):
                assert f["id"] != "sin_catalogar", (p["id_paciente"], f)
                for factor in f["factores"]:
                    usos.setdefault((factor, f["id"]), set()).update(f["claves"])
    assert any(c.endswith(".ventana_dias") for c in usos[("ventana", "pubmed_evidencia")]) and ("ventana", "rubrica_v1") in usos
    assert "medicion.HbA1c.descompensado_umbral" in usos[("medicion", "guias_umbrales")] and "E11" in usos[("medicion", "ssmso_hlf_2025")]
    assert any(c.startswith("GES ") for c in usos[("ges", "ges_especialista")]) and any(c.startswith("registro_") for c in usos[("criterio_registro", "criterios_registro")])
    assert ("medicion", "registro_paciente") in usos and ("lace", "motor") in usos and ("plazo", "criterios_registro") in usos


def test_fuentes_de_criterios_combinaciones_y_cancer(perfs):
    """Razones que solo aparecen cuando la IA leyó un texto: se arman con los mismos eventos que registra el sistema."""
    comb = combinaciones.cargar()["por_id"]

    def aplicada(cid):
        return {"id": cid, "cita_gatillo": "frase del texto", "cita_base": None, **{k: comb[cid].get(k) for k in ("nombre", "efecto", "desenlace", "fuente", "estado", "letalidad", "riesgo")}}

    def clasificado(cie, nivel, con_urgencia):
        enf = criterios.enfermedad_de(cie)
        crit, urg = criterios.opciones(enf)
        return {"enfermedad": enf["enfermedad"], "nivel": nivel, "criterio": crit[nivel + ".0"][1], "cita": "frase del texto", "riesgo": enf.get("riesgo"),
                "urgencia": urg["urgencia.0"] if con_urgencia else None, "cita_urgencia": "frase del texto" if con_urgencia else None,
                "fuente": enf.get("fuente_url") or criterios.FUENTE.format(v=criterios.cargar()["kb"]["version"])}

    p = copy.deepcopy(perfs["PAC-HLF-00002"])                                # I20, Cardiología
    p["paciente"].update(grupo_proteccion="PRAIS", acg="G3")
    d = {"aplicadas": [aplicada("coronario_dolor_reposo"), aplicada("pie_diabetico_lesion"), aplicada("asplenia_fiebre")],
         "alertas": [{"descripcion": "combinación que no está en la lista", "cita": "frase del texto"}], "lecturas": 3, "errores": []}
    p["eventos_clinicos"] = p["eventos_clinicos"] + [
        criterios.evento(clasificado("I20", "alta", True), "2026-10-01"), combinaciones.evento(d, "2026-10-02"),
        {"fecha_evento": "2026-10-03", "tipo_evento": "hallazgo_oncologico", "subtipo": "sospecha de cáncer", "severidad": "grave", "detalle": ""}]
    r = puntaje.puntuar(p, CORTE)
    assert {"urgencia", "criterio_clinico", "combinacion", "alerta_combinacion", "oncologico", "grupo_proteccion", "acg"} <= {x["factor"] for x in r["razones"]}
    fs = {f["id"]: f for f in bc.fuentes_de(r["razones"])}
    assert "sin_catalogar" not in fs and "registro_I20" in fs["criterios_registro"]["claves"]
    assert {"coronario_dolor_reposo", "pie_diabetico_lesion", "asplenia_fiebre"} <= set(fs["combinaciones_riesgo"]["claves"])
    assert {"urgencia", "combinacion", "alerta_combinacion"} <= set(fs["combinaciones_riesgo"]["factores"])
    assert "grupo_especial_proteccion" in fs["ord536"]["claves"] and "acg" in fs["registro_paciente"]["factores"]
    assert any("red de seguridad" in c for c in fs["motor"]["claves"]) and "puntaje.regla_oncologica" in fs["motor"]["claves"]
    assert "oncologico" in fs["diagnosticos_tabla_hlf"]["factores"]          # Cardiología: el patrón de la tabla, sin fila propia

    q = copy.deepcopy(perfs["PAC-HLF-00001"])                                # F32: criterios por especialidad (origen no confirmado)
    q["eventos_clinicos"] = q["eventos_clinicos"] + [criterios.evento(clasificado("F32", "alta", False), "2026-10-01")]
    fq = {f["id"]: f for f in bc.fuentes_de(puntaje.puntuar(q, CORTE)["razones"])}
    assert fq["criterios_especialidad"]["claves"] == ["psiquiatria_07"] and fq["criterios_especialidad"]["version"] == _fuente("criterios_especialidad")["version"]

    for especialidad, filas in (("Broncopulmonar", ["HLF-BRP-01"]), ("Traumatología", ["HLF-TRA-01", "HLF-TRA-02"])):   # fila oncológica propia
        t = copy.deepcopy(next(x for x in perfs.values() if x["lista_espera"]["especialidad"] == especialidad
                               and (y := puntaje.puntuar(x, CORTE)) and not y.get("excluido")))
        t["eventos_clinicos"] = t["eventos_clinicos"] + [{"fecha_evento": "2026-10-03", "tipo_evento": "hallazgo_oncologico",
                                                          "subtipo": "cáncer confirmado", "severidad": "grave", "detalle": ""}]
        onc = [x for x in puntaje.puntuar(t, CORTE)["razones"] if x["factor"] == "oncologico"]
        assert bc.fuentes_de(onc)[0]["id"] == "diagnosticos_tabla_hlf" and bc.fuentes_de(onc)[0]["claves"] == filas, especialidad


def test_fuentes_de_criterio_local_factor_desconocido_y_razones_raras():
    local = {"factor": "criterio_local", "valor": "Hipertensión esencial con visita a urgencia grave → prioridad alta",
             "fuente": "Criterio local HLF CL-0001 v1 · aprobado por Dra. Prueba el 2026-11-13 · basado en 3 revisión(es) de especialista"}
    fs = bc.fuentes_de([local, {"factor": "inventado", "valor": "x", "fuente": "y"}, {"factor": "tabla_oficial"}, None, "texto", {}])
    assert [f["id"] for f in fs] == ["criterios_locales", "sin_catalogar", "diagnosticos_tabla_hlf", "ssmso_hlf_2025"]
    assert fs[0]["claves"] == ["CL-0001 v1"] and fs[0]["tipo"] == "capa_local" and fs[1]["claves"] == ["inventado", "None"]
    assert bc.fuentes_de(None) == [] and bc.fuentes_de([]) == []


# ---------- capa local y rutas ----------
def test_capa_local_registrada_aparece_en_la_consulta():
    def capa(cie10):
        return [{"id": "CL-0001", "version": 1, "estado": "vigente", "diagnostico": cie10}]

    def rota(cie10):
        raise RuntimeError("sin tabla")
    previas = list(bc._CAPAS)                                                # las que haya registrado otro módulo (aprendizaje.py)
    bc._CAPAS.clear()
    try:
        d = bc.para_diagnostico("I10")
        assert d["criterios_locales"] == [] and "avisos" not in d            # sin capas: lista vacía
        assert bc.registrar_capa_local(capa, version=lambda: 3) is capa
        bc.registrar_capa_local(capa)                                        # registrarla dos veces no la duplica
        bc.registrar_capa_local(rota)
        d = bc.para_diagnostico("I10")
        assert d["criterios_locales"] == [{"id": "CL-0001", "version": 1, "estado": "vigente", "diagnostico": "I10"}]
        assert len(d["avisos"]) == 1 and "rota" in d["avisos"][0]            # una capa que falla no bota la consulta
        assert bc.para_diagnostico("hlf-car-11")["criterios_locales"][0]["diagnostico"] == "HLF-CAR-11"   # recibe el código normalizado
        assert bc.rutear("GET", ["conocimiento"], {}, {})[1]["capa_local"] == {"capas": 2, "version": 3}
    finally:
        bc._CAPAS[:] = previas


def test_rutas():
    s, d = bc.rutear("GET", ["conocimiento"], {}, {})
    assert s == 200 and {"paquete", "fuentes", "motor"} <= set(d) and d["integridad"]["integro"] and set(d["capa_local"]) == {"capas", "version"}
    assert d["paquete"] == bc.paquete() and d["paquete"]["etiqueta"] and d["paquete"]["motor"]["archivos"] == len(emp.MOTOR)
    assert len(d["fuentes"]) == len([n for n in os.listdir(KB) if n.endswith(".json")]) - 1 and d["motor"]["constantes"] and d["motor"]["reglas_en_codigo"]
    assert d["avisos"] == _json(os.path.join(KB, "manifiesto.json"))["avisos"]   # la deuda conocida de las fuentes queda a la vista
    json.dumps(d)
    s, d = bc.rutear("GET", ["conocimiento", "diagnostico", "I20"], {}, {})
    assert s == 200 and d["si_se_descompensa"]["fila"] == "Angina inestable"
    assert bc.rutear("GET", ["conocimiento", "diagnostico", "hlf-car-01"], {}, {})[1]["codigo"] == "HLF-CAR-01"
    s, d = bc.rutear("GET", ["conocimiento", "diagnostico", "Z99"], {}, {})
    assert s == 404 and "Z99" in d["error"]
    for method, partes in (("GET", ["pacientes"]), ("GET", []), ("POST", ["conocimiento"]), ("GET", ["conocimiento", "otra"]),
                           ("GET", ["conocimiento", "diagnostico"]), ("GET", ["conocimiento", "diagnostico", "I20", "x"])):
        assert bc.rutear(method, partes, {}, {}) is None                     # lo demás lo resuelve el enrutador principal
