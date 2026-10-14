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
    claves = [(-orden[p["categoria"]], not p["riesgo_vital"], -p["lace"]["total"], not p["grupo_proteccion"],
               not p["antiguedad_mayor_1_anio"], -p["dias_espera"]) for p in d["pacientes"]]
    assert claves == sorted(claves)

def test_lace_00002():
    """Angina sin Charlson; hospitalización (A=3) y 1 urgencia (E=1) en los 6 meses previos al 10-08."""
    _, d = call("GET", "/pacientes", {"fecha_corte": "2026-08-10"})
    l = fila(d, "PAC-HLF-00002")["lace"]
    assert {x["letra"]: x["puntos"] for x in l["partes"]} == {"L": 0, "A": 3, "C": 0, "E": 1} and l["total"] == 4

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

def _xlsx(hojas):
    """Excel mínimo (cadenas en línea) para probar la lectura sin librerías."""
    import base64, io, zipfile
    from xml.sax.saxutils import escape
    b = io.BytesIO()
    z = zipfile.ZipFile(b, "w")
    z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
    z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
               'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' +
               "".join(f'<sheet name="{n}" sheetId="{i}" r:id="rId{i}"/>' for i, n in enumerate(hojas, 1)) + "</sheets></workbook>")
    z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
               "".join(f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(hojas) + 1)) + "</Relationships>")
    for i, filas in enumerate(hojas.values(), 1):
        xml = "".join("<row>" + "".join(
            (f'<c r="{chr(65 + j)}{k + 1}"><v>{v}</v></c>' if isinstance(v, (int, float)) else
             f'<c r="{chr(65 + j)}{k + 1}" t="inlineStr"><is><t>{escape(str(v))}</t></is></c>') for j, v in enumerate(f)) + "</row>"
                      for k, f in enumerate(filas))
        z.writestr(f"xl/worksheets/sheet{i}.xml", f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{xml}</sheetData></worksheet>')
    z.close()
    return base64.b64encode(b.getvalue()).decode()

def test_importar_excel_y_csv():
    import base64
    excel = _xlsx({
        "Pacientes": [["RUT", "Nombre", "Edad", "Género"], ["11.111.111-1", "Ana Soto", 71, "Femenino"]],
        "Lista espera": [["RUT", "CIE10", "Prioridad", "Fecha ingreso"], ["11.111.111-1", "I50.9", "MEDIA", 46000]],
    })
    csv_ev = base64.b64encode("Rut;Fecha;Tipo;Subtipo;Gravedad\n11.111.111-1;01-10-2026;Hospitalización;ingreso hospitalario;Grave\n"
                              "99;xx;urgencia;;leve\n".encode("utf-8")).decode()
    archivos = [{"nombre": "export_hlf.xlsx", "contenido_base64": excel}, {"nombre": "eventos.csv", "contenido_base64": csv_ev}]
    s, rev = call("POST", "/importar", body={"archivos": archivos})
    assert s == 200 and not rev["cargado"]
    tablas = {i["tabla"]: i for i in rev["informe"]}
    assert tablas["pacientes"]["validas"] == 1 and tablas["lista_espera"]["validas"] == 1
    assert tablas["eventos_clinicos"]["validas"] == 1 and tablas["eventos_clinicos"]["errores"][0]["fila"] == 3
    assert rev["resumen"]["pacientes_nuevos"] == 1 and rev["resumen"]["eventos"] == 1
    s, carga = call("POST", "/importar", body={"archivos": archivos, "confirmar": True})
    assert carga["cargado"]
    _, d = call("GET", "/pacientes", {"fecha_corte": "2026-10-13"})
    p = fila(d, "11.111.111-1")
    assert p["especialidad"] == "Cardiología" and p["fecha_ingreso_lista"] == "2025-12-09"   # 46000 = fecha interna de Excel
    assert p["categoria"] == "alta" and p["riesgo_vital"]   # IC descompensada (pág. 85) tras la hospitalización importada

def test_novedades_comorbilidad_diagnostico_fallecimiento():
    _, d = call("GET", "/pacientes", {"fecha_corte": "2026-10-13"})
    p = next(x for x in d["pacientes"] if x["diagnostico_cie10"] == "M75" and x["lace"]["total"] == 0)
    pid = p["id_paciente"]
    s, r = call("POST", f"/pacientes/{pid}/novedad", body={"tipo": "comorbilidad", "cie10": "M54"})   # lumbago: sin peso Charlson
    assert s == 200 and r["paciente"]["lace"]["total"] == 0 and "sin peso Charlson" in r["paciente"]["lace"]["partes"][2]["valor"]
    s, r = call("POST", f"/pacientes/{pid}/novedad", body={"tipo": "comorbilidad", "condicion": "insuficiencia cardíaca congestiva"})
    assert r["paciente"]["lace"]["partes"][2]["puntos"] == 2 and r["paciente"]["lace"]["total"] == 2
    s, r = call("POST", f"/pacientes/{pid}/novedad", body={"tipo": "diagnostico", "cie10": "I20"})
    assert r["paciente"]["especialidad"] == "Cardiología"
    s, r = call("POST", f"/pacientes/{pid}/novedad", body={"tipo": "fallecimiento", "fecha": "2026-10-12"})
    assert s == 200 and not r["en_lista"]
    _, d = call("GET", "/pacientes", {"fecha_corte": "2026-10-13"})
    assert pid in [e["id_paciente"] for e in d["excluidos"]] and pid not in [x["id_paciente"] for x in d["pacientes"]]

def _otro(d, **cond):
    usados = {"PAC-HLF-00001", "PAC-HLF-00002", "PAC-HLF-00020", "PAC-HLF-00028", "PAC-HLF-00003"}
    return next(p for p in d["pacientes"] if p["id_paciente"].startswith("PAC-HLF") and p["id_paciente"] not in usados
                and p["estado_revision"] == "pendiente" and all(p[k] == v for k, v in cond.items()))

def test_bug_ajuste_no_tapa_descompensacion_posterior():
    """Un ajuste a 'baja' no puede ocultar una hospitalización registrada después."""
    _, d = call("GET", "/pacientes", {"fecha_corte": "2026-10-13"})
    p = _otro(d, diagnostico_cie10="I50", categoria="media", estado_clinico="sin_cambios")
    pid = p["id_paciente"]
    call("POST", f"/pacientes/{pid}/revision", body={"accion": "ajustar", "categoria_ajustada": "baja", "motivo": "estable", "fecha_corte": "2026-10-13"})
    _, d = call("GET", "/pacientes", {"fecha_corte": "2026-10-13"})
    assert fila(d, pid)["categoria"] == "baja" and fila(d, pid)["estado_revision"] == "ajustado"
    call("POST", "/eventos", body={"id_paciente": pid, "tipo_evento": "hospitalizacion", "subtipo": "ingreso hospitalario",
                                   "severidad": "grave", "fecha_corte": "2026-10-13"})
    _, d = call("GET", "/pacientes", {"fecha_corte": "2026-10-13"})
    q = fila(d, pid)
    assert q["categoria"] == "alta" and q["estado_revision"] == "requiere_revision" and q["revision_sugerida"]

def test_bug_contacto_apaga_alerta():
    _, d = call("GET", "/pacientes", {"fecha_corte": "2026-10-13"})
    p = next(x for x in d["pacientes"] if x["contactar_hoy"] and x["id_paciente"] != "PAC-HLF-00002")
    s, r = call("POST", f"/pacientes/{p['id_paciente']}/contacto", body={"resultado": "no_contesta", "fecha_corte": "2026-10-13"})
    assert s == 200 and r["paciente"]["contactar_hoy"]          # no contesta: la alerta sigue
    s, r = call("POST", f"/pacientes/{p['id_paciente']}/contacto", body={"resultado": "citado", "fecha_corte": "2026-10-13"})
    assert not r["paciente"]["contactar_hoy"] and r["paciente"]["riesgo_vital"]   # reconocida, sigue priorizado

def test_bug_atendido_respeta_fecha_de_corte():
    import json as _j
    perfs = app.perfiles()
    p = next(x for x in perfs.values() if x["lista_espera"]["estado"] == "atendido")
    fa = app.puntaje.fecha_atencion(p)
    antes = (date.fromisoformat(fa) - __import__("datetime").timedelta(days=1)).isoformat()
    _, d1 = call("GET", "/pacientes", {"fecha_corte": antes})
    _, d2 = call("GET", "/pacientes", {"fecha_corte": fa})
    if p["lista_espera"]["fecha_ingreso_lista"] <= antes:
        assert p["id_paciente"] in [x["id_paciente"] for x in d1["pacientes"]]
    assert any(e["id_paciente"] == p["id_paciente"] and e["motivo"] == "atendido" for e in d2["excluidos"])

def test_bug_negacion_en_informe():
    s, d = call("POST", "/pacientes/PAC-HLF-00003/informe", body={"texto": "Evaluado en urgencia, se descarta hospitalización. Alta a domicilio."})
    assert d["evento"] is None or d["evento"]["tipo_evento"] != "hospitalizacion"
    s, d = call("POST", "/pacientes/PAC-HLF-00003/informe", body={"texto": "Paciente sin hospitalizaciones previas. Hoy se hospitaliza por disnea."})
    assert d["evento"]["tipo_evento"] == "hospitalizacion" and "Hoy se hospitaliza" in d["evento"]["evidencia"]

def test_revision_sugerida_deterioro_00001():
    # antes de la confirmación de test_revision (fecha_corte 13-10): las señales piden revisión
    _, d = call("GET", "/pacientes", {"fecha_corte": "2026-10-01"})
    motivos = {s["motivo"] for s in fila(d, "PAC-HLF-00001")["revision_sugerida"]}
    assert {"examen alterado", "aumento de dosis"} <= motivos

def test_kpis_y_kappa():
    s, k = call("GET", "/kpis", {"fecha_corte": "2026-10-13"})
    assert s == 200 and k["cobertura"]["pct"] == 100.0 and k["concordancia"]["revisiones"] >= 1
    assert k["concordancia"]["kappa"] is None or -1 <= k["concordancia"]["kappa"] <= 1
    assert app._kappa([("alta", "alta"), ("baja", "baja"), ("media", "media")]) == 1.0

def test_grupo_proteccion_ordena_despues_de_lace():
    _, d = call("GET", "/pacientes", {"fecha_corte": "2026-10-13"})
    baja = [x for x in d["pacientes"] if x["categoria"] == "baja" and not x["riesgo_vital"] and x["lace"]["total"] == 0
            and x["estado_revision"] == "pendiente" and x["id_paciente"].startswith("PAC-HLF")]
    ultimo = baja[-1]
    call("POST", f"/pacientes/{ultimo['id_paciente']}/novedad", body={"tipo": "riesgo", "grupo_proteccion": "PRAIS", "acg": "G3"})
    _, d = call("GET", "/pacientes", {"fecha_corte": "2026-10-13"})
    q = fila(d, ultimo["id_paciente"])
    assert q["grupo_proteccion"] == "PRAIS" and q["acg"] == "G3" and q["posicion"] < ultimo["posicion"]

def test_plantilla():
    r = app.handler({"requestContext": {"http": {"method": "GET"}}, "rawPath": "/plantillas/lista_espera"})
    assert r["statusCode"] == 200 and "diagnostico_cie10" in r["body"]

def test_404():
    assert call("GET", "/nada")[0] == 404

# ---------- capa dinámica: criticidad y chat del paciente ----------
def test_criticidad_senal_temprana():
    """00001 (PHQ-9 de 4 a 19) tiene señal temprana; 00028 (mejora) no. La señal no cambia la categoría."""
    _, d = call("GET", "/pacientes", {"fecha_corte": "2026-10-01"})
    p, q = fila(d, "PAC-HLF-00001"), fila(d, "PAC-HLF-00028")
    assert p["senal_temprana"] and any(s["motivo"] == "mediciones empeorando" for s in p["revision_sugerida"])
    assert not q["senal_temprana"] and 0 <= q["criticidad"] <= 100
    assert any(r["factor"] == "criticidad" and "PHQ-9" in r["valor"] for r in p["razones"])

def test_chat_autoreporte_por_validar_y_validar():
    """El chat propone; la lista cambia recién cuando el equipo valida (los eventos entran a las reglas oficiales)."""
    pid = "PAC-HLF-00028"
    _, d = call("GET", "/pacientes", {"fecha_corte": "2026-10-13"})
    antes = fila(d, pid)
    s, r = call("POST", f"/pacientes/{pid}/autoreporte", body={
        "fecha_corte": "2026-10-13", "tendencia_autoreporte": 1,
        "eventos": [{"tipo_evento": "hospitalizacion", "subtipo": "ingreso hospitalario", "fecha_evento": "2026-10-10"}],
        "mediciones": [{"tipo_medicion": "PHQ9", "valor": 15, "unidad": "pts"}]})
    assert s == 200 and r["autoreporte"]["estado"] == "por_validar" and r["autoreporte"]["mediciones"][0]["fuera_de_rango"]
    assert r["paciente"]["autoreporte"] and r["paciente"]["categoria"] == antes["categoria"]   # aún no cambia
    s, v = call("POST", f"/pacientes/{pid}/autoreporte/validar", body={"fecha_corte": "2026-10-13"})
    assert s == 200 and v["posicion_despues"] < v["posicion_antes"] and v["paciente"]["estado_clinico"] == "descompensado"
    assert not v["paciente"]["autoreporte"]
    _, det = call("GET", f"/pacientes/{pid}", {"fecha_corte": "2026-10-13"})
    assert any(e.get("fuente") == "autoreporte" for e in det["eventos_clinicos"])
    assert any(m.get("fuente") == "autoreporte" for m in det["mediciones"])

def test_chat_bandera_roja_contactar_hoy_y_vocabulario():
    pid = "PAC-HLF-00020"
    s, r = call("POST", f"/pacientes/{pid}/autoreporte", body={"fecha_corte": "2026-10-13", "bandera_roja": "dolor_pecho"})
    assert s == 200 and r["paciente"]["contactar_hoy"] and r["paciente"]["alerta_chat"]
    assert r["paciente"]["razones"][0]["factor"] == "autoreporte"
    s, r = call("POST", f"/pacientes/{pid}/contacto", body={"resultado": "citado", "fecha_corte": "2026-10-13"})
    assert not r["paciente"]["contactar_hoy"]
    s, _ = call("POST", f"/pacientes/{pid}/autoreporte", body={"eventos": [{"tipo_evento": "visita_urgencia", "subtipo": "me siento mal"}]})
    assert s == 400
    s, r = call("POST", f"/pacientes/{pid}/autoreporte", body={"fecha_corte": "2026-10-13", "texto_libre": "No me hospitalizaron, pero fui a urgencia por descompensación"})
    assert s == 200 and [e["tipo_evento"] for e in r["autoreporte"]["eventos"]] == ["visita_urgencia"]
    assert r["autoreporte"]["bandera_roja"]   # el reporte nuevo conserva la bandera del anterior pendiente
    call("POST", f"/pacientes/{pid}/autoreporte/validar", body={"accion": "descartar", "fecha_corte": "2026-10-13"})
    _, d = call("GET", "/pacientes", {"fecha_corte": "2026-10-13"})
    assert not fila(d, pid)["autoreporte"]     # descartado: no reaparece el reporte reemplazado
