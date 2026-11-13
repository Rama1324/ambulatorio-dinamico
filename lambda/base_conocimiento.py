"""Base de conocimiento versionada y trazable (docs/diseno/ESPECIFICACION_MVP.md §4 · docs/conocimiento/README.md).

El conocimiento médico del sistema (tabla SSMSO/HLF, Ord. 536, GES, criterios, combinaciones, evidencia) vive en los JSON
de conocimiento/ y en constantes del código. Este módulo no decide nada ni repite reglas: lee lo mismo que lee el motor,
con sus mismas funciones, y responde tres preguntas con recuperación exacta por clave (CIE-10, código de la tabla, factor
de la razón), sin búsqueda por similitud:

  ¿qué versiones están vigentes?                        paquete(), fuentes(), motor(), integridad()
  ¿qué sabe y aplica el sistema para un diagnóstico?    para_diagnostico(cie10)
  ¿qué fuentes respaldan una decisión?                  fuentes_de(razones)

conocimiento/manifiesto.json (lo genera scripts/empaquetar_conocimiento.py) declara cada fuente con su versión y su
huella. Al primer uso en cada proceso se recalculan las huellas de los archivos reales: lo que se informa, y lo que queda
anotado en cada decisión, es lo que hay en disco. Si no coincide con el manifiesto, `integro` queda en False: nunca se
certifica una versión que no se leyó.
"""
import copy
import hashlib
import json
import os
import re
from urllib.parse import unquote

DIR = os.path.dirname(os.path.abspath(__file__))
DIR_KB = os.path.join(DIR, "conocimiento")
MANIFIESTO = "manifiesto.json"
_C = {}       # por proceso: estado (manifiesto + huellas reales), índices por clave y JSON leídos
_CAPAS = []   # capas locales registradas por aprendizaje.py: [(función, versión)]


# ---------- huellas: no dependen del formato (el repo usa core.autocrlf y un JSON se puede reindentar) ----------
def _texto(datos):
    """bytes o str → str sin BOM y con saltos de línea \\n."""
    if isinstance(datos, bytes):
        datos = datos.decode("utf-8-sig")
    return datos.replace("\r\n", "\n").replace("\r", "\n")


def huella_objeto(obj):
    """sha256 del JSON canónico de un objeto: claves ordenadas, sin espacios, UTF-8."""
    canonico = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def huella_json(datos):
    """sha256 del CONTENIDO de un JSON (no de sus bytes): no cambia con la sangría, el orden de las claves ni CRLF/LF."""
    return huella_objeto(json.loads(_texto(datos)))


def huella_texto(datos):
    """sha256 de un archivo de código con los saltos de línea normalizados a \\n."""
    return hashlib.sha256(_texto(datos).encode("utf-8")).hexdigest()


def huella_archivo(ruta):
    with open(ruta, "rb") as f:
        datos = f.read()
    return huella_json(datos) if ruta.lower().endswith(".json") else huella_texto(datos)


def huella_conjunta(pares):
    """sha256 de un conjunto de huellas {nombre: sha256}, ordenadas por nombre (el orden de entrada no importa)."""
    return hashlib.sha256("\n".join(f"{k}:{v}" for k, v in sorted(pares.items())).encode("utf-8")).hexdigest()


def huella_paquete(fuentes, archivos_motor):
    """Huella corta (12) del paquete: todas las huellas, de las fuentes y de los archivos del motor, ordenadas."""
    pares = {f["id"]: f["sha256"] for f in fuentes}
    pares.update({"motor/" + a["archivo"]: a["sha256"] for a in archivos_motor})
    return huella_conjunta(pares)[:12]


# ---------- qué está vigente: el manifiesto contrastado con los archivos reales ----------
def _leer_real(ruta):
    """Huella (y versión, si es un JSON de conocimiento) del archivo tal como está en disco; None si no se puede leer."""
    try:
        with open(ruta, "rb") as f:
            datos = f.read()
        if not ruta.lower().endswith(".json"):
            return {"sha256": huella_texto(datos)}
        obj = json.loads(_texto(datos))
        return {"sha256": huella_objeto(obj), "version": obj.get("version") if isinstance(obj, dict) else None}
    except (OSError, ValueError):
        return None


def _manifiesto():
    """(manifiesto, diferencias). Si falta o no tiene la forma esperada devuelve {} con el motivo: el servicio sigue."""
    try:
        with open(os.path.join(DIR_KB, MANIFIESTO), encoding="utf-8-sig") as f:
            man = json.load(f)
        fichas = man["fuentes"] + man["motor"]["archivos"]
        if not all(isinstance(x, dict) and x.get("archivo") for x in fichas) or not all(x.get("id") for x in man["fuentes"]):
            raise ValueError("ficha sin id o sin archivo")
        return man, []
    except (OSError, ValueError, KeyError, TypeError):
        return {}, [f"falta conocimiento/{MANIFIESTO} o no tiene la forma esperada: ejecutar scripts/empaquetar_conocimiento.py"]


def _estado():
    """Manifiesto + huellas reales, una vez por proceso. Nunca lanza: sin manifiesto informa lo que encuentra en disco."""
    if "estado" in _C:
        return _C["estado"]
    man, difs = _manifiesto()
    fuentes, vistos = [], set()
    for f in man.get("fuentes", []):
        nombre = os.path.basename(f["archivo"])
        vistos.add(nombre)
        real = _leer_real(os.path.join(DIR_KB, nombre))
        if not real:
            difs.append(f'{f["id"]}: no se pudo leer {f["archivo"]}')
            real = {"sha256": None}
        elif (real["sha256"], real["version"]) != (f.get("sha256"), f.get("version")):
            difs.append(f'{f["id"]}: el archivo no corresponde al manifiesto (en disco: versión {real["version"]}, huella {real["sha256"][:12]})')
        fuentes.append({**f, **real})
    for nombre in (sorted(os.listdir(DIR_KB)) if os.path.isdir(DIR_KB) else []):
        real = _leer_real(os.path.join(DIR_KB, nombre)) if nombre.endswith(".json") and nombre != MANIFIESTO and nombre not in vistos else None
        if real:   # un JSON que el manifiesto no declara: se informa igual (con su huella), marcado como no catalogado
            difs.append(f"{nombre[:-5]}: fuente sin registrar en el manifiesto")
            fuentes.append({"id": nombre[:-5], "titulo": nombre[:-5], "tipo": "sin_catalogar", "archivo": f"lambda/conocimiento/{nombre}", **real})
    mot = dict(man.get("motor") or {})
    archivos = []
    for a in mot.get("archivos", []):
        real = _leer_real(os.path.join(DIR, os.path.basename(a["archivo"])))
        if not real or real["sha256"] != a.get("sha256"):
            difs.append(f'motor: {a["archivo"]} no corresponde al manifiesto')
        archivos.append({**a, "sha256": real and real["sha256"]})
    sha_motor = huella_conjunta({a["archivo"]: a["sha256"] for a in archivos})
    mot.update(archivos=archivos, sha256=sha_motor, huella=sha_motor[:12])
    declarado = man.get("paquete") or {}
    huella = huella_paquete(fuentes, archivos)
    if man and not difs and declarado.get("huella") != huella:
        difs.append("la huella del paquete en el manifiesto no corresponde a sus fuentes (¿editado a mano?)")
    paq = {"etiqueta": declarado.get("etiqueta"), "huella": huella, "generado": declarado.get("generado"), "integro": not difs}
    if difs and declarado.get("huella") not in (None, huella):
        paq["huella_manifiesto"] = declarado["huella"]
    _C["estado"] = {"paquete": paq, "fuentes": fuentes, "por_id": {f["id"]: f for f in fuentes}, "motor": mot, "diferencias": difs,
                    "avisos": list(man.get("avisos") or [])}
    return _C["estado"]


def paquete():
    """Versión vigente del conocimiento: {etiqueta, huella, generado, integro, motor: {huella, archivos}}.
    `huella` identifica el contenido exacto (fuentes + reglas en el código); `etiqueta` es su nombre legible."""
    e = _estado()
    return {**e["paquete"], "motor": {"huella": e["motor"]["huella"], "archivos": len(e["motor"]["archivos"])}}


def fuentes():
    """El manifiesto: una ficha por fuente (id, título, tipo, archivo, versión, sha256, fecha, origen, estado, entradas,
    usado_por), con la versión y la huella de lo que realmente está en disco."""
    return copy.deepcopy(_estado()["fuentes"])


def motor():
    """Reglas que viven en el código: huella de cada archivo, constantes clínicas con su fuente y reglas de aplicar_registro."""
    return copy.deepcopy(_estado()["motor"])


def integridad():
    """¿Los archivos desplegados son los que declara el manifiesto? {integro, diferencias[]}."""
    e = _estado()
    return {"integro": not e["diferencias"], "diferencias": list(e["diferencias"])}


def reiniciar():
    """Olvida lo leído (para los tests y para un proceso local que cambia los archivos)."""
    _C.clear()


PSEUDO = {  # lo que respalda una razón y no es un archivo de conocimiento
    "registro_paciente": ("Registro del paciente: prioridad inicial de la SIC, eventos y mediciones del hospital", "registro"),
    "criterios_locales": ("Criterios locales del HLF aprobados por jefatura (nacen de la revisión de los especialistas)", "capa_local"),
    "sin_catalogar": ("Razón con un factor que la base de conocimiento no tiene catalogado", "sin_catalogar"),
}


def _ficha(fid):
    """Lo que queda en una decisión por cada fuente: id, título, tipo, versión y huella."""
    e = _estado()
    if fid == "motor":
        return {"id": "motor", "titulo": "Reglas y constantes escritas en el código (motor de priorización)", "tipo": "motor",
                "version": e["motor"]["huella"], "sha256": e["motor"]["sha256"]}
    if fid in e["por_id"]:
        return {k: e["por_id"][fid].get(k) for k in ("id", "titulo", "tipo", "version", "sha256")}
    titulo, tipo = PSEUDO.get(fid, PSEUDO["sin_catalogar"])
    return {"id": fid, "titulo": titulo, "tipo": tipo, "version": None, "sha256": None}


def _ref(fid, **extra):
    """Cita de una fuente dentro de un bloque: id + versión vigente (más la clave exacta, si se conoce)."""
    return {"id": fid, "version": _ficha(fid)["version"], **{k: v for k, v in extra.items() if v is not None}}


def _constante(nombre):
    """Cita de una constante clínica del código; el manifiesto trae el comentario que dice de dónde sale."""
    c = next((c for c in _estado()["motor"].get("constantes", []) if c.get("nombre") == nombre), {})
    return _ref("motor", constante=nombre, origen=c.get("fuente"))


# ---------- índices por clave, armados una vez por proceso con las mismas funciones que usa el motor ----------
def _json(fid):
    """Fuente que ningún módulo del motor expone tal cual (p. ej. las otras filas de la tabla o la cascada del Ord. 536)."""
    cache = _C.setdefault("json", {})
    if fid not in cache:
        try:
            with open(os.path.join(DIR_KB, fid + ".json"), encoding="utf-8-sig") as f:
                cache[fid] = json.load(f)
        except (OSError, ValueError):
            cache[fid] = {}
    return cache[fid]


def _indices():
    if "idx" in _C:
        return _C["idx"]
    import combinaciones
    import criterios
    import decisor
    import puntaje
    from modelos import normalizar
    tabla, kb, crit = puntaje.tabla_hlf(), decisor.cargar_kb(), criterios.cargar()
    ssmso = _json("ssmso_hlf_2025").get("diagnosticos", {})
    por_base, filas = {}, {}   # filas: página → [(texto normalizado, id de la fuente, clave)], para ubicar la fila que cita una razón
    especialidad = {c: s["especialidad"] for s in crit["registro"]["especialidades"] for e in s["enfermedades"] for c in e["cie10"]}
    for x in tabla.values():
        filas.setdefault(x["pagina"], []).append((normalizar(x["texto"]), "diagnosticos_tabla_hlf", x["codigo"]))
        if x.get("cie10_base"):
            por_base.setdefault(x["cie10_base"], []).append(x)
            especialidad.setdefault(x["cie10_base"], x["especialidad"])
    for cie, d in ssmso.items():
        for f in [d.get("fila_descompensado"), d.get("candidata"), *(d.get("otras_filas") or [])]:
            if f:
                filas.setdefault(f["pagina"], []).append((normalizar(f["texto_pdf"]), "ssmso_hlf_2025", cie))
    de_especialidad = {e["id"] for s in crit["kb"]["especialidades"] for e in s["enfermedades"]}
    medidas = [d["medicion"]["umbral"] for d in kb["diagnosticos"].values() if d.get("medicion")]
    _C["idx"] = {
        "puntaje": puntaje, "decisor": decisor, "criterios": criterios, "combinaciones": combinaciones, "normalizar": normalizar,
        "tabla": tabla, "por_base": por_base, "ssmso": ssmso, "kb": kb, "especialidad": especialidad, "filas": filas,
        "de_especialidad": de_especialidad,
        # texto que trae la razón → clave de la entrada que la respalda
        "url_registro": {e["fuente_url"]: e["id"] for e in puntaje.criterios_registro().values()},
        "combinacion": {c["nombre"]: c["id"] for c in combinaciones.cargar()["kb"]["combinaciones"]},
        "enfermedad": {e["enfermedad"]: k for k, e in crit["por_id"].items() if k in de_especialidad},
        "ventana": {v["fuente"]: v.get("id") for d in kb["diagnosticos"].values() for v in (d.get("ventanas") or {}).values()},
        "umbral": {u["fuente"]: u.get("id") for u in medidas},
    }
    return _C["idx"]


# ---------- qué sabe y aplica el sistema para un diagnóstico ----------
def _fila(x):
    return {k: x.get(k) for k in ("codigo", "texto", "prioridad", "pagina")}


def _doc(fn):
    return " ".join((fn.__doc__ or "").split())


def _tabla(codigo, base, i):
    """Fila propia (si el diagnóstico es un código HLF-…) y las otras filas de la tabla que son la misma enfermedad."""
    fila = i["tabla"].get(codigo)
    hermanas = [_fila(x) for x in i["por_base"].get(base, []) if x["codigo"] != codigo]
    if not fila and not hermanas:
        return None
    propia = fila and {**_fila(fila), "urgencia": fila["urgencia"], "seccion_pdf": fila["seccion_pdf"], "verificacion": fila["verificacion"],
                       "uso": "piso de la prioridad: si al ingresar se le asignó una menor, el sistema la sube a esta; nunca la baja"}
    return {"fila": propia or None, "misma_enfermedad": hermanas, "fuente": _ref("diagnosticos_tabla_hlf", clave=codigo if fila else None)}


def _si_se_descompensa(codigo, base, i):
    """La fila que se usa si el paciente se descompensa: la elige puntaje.fila_descompensado (aquí solo se dice de dónde sale)."""
    puntaje, t, reg = i["puntaje"], i["tabla"].get(codigo), i["ssmso"].get(base) or {}
    fila, equivalencia = puntaje.fila_descompensado(codigo)
    # filas relacionadas que la tabla trae y el sistema no usa para subir (se muestran para que el especialista las vea)
    extra = {k: reg[k] for k in ("candidata", "otras_filas") if reg.get(k)}
    if not fila:
        fuente = _ref("ssmso_hlf_2025", clave=base) if reg else _ref("diagnosticos_tabla_hlf", clave=codigo) if t else \
            _constante("puntaje.FILA_DESCOMPENSADO")   # un CIE-10 que no está en la tabla: lo dice la lista del código
        return {"fila": None, "estado": reg.get("estado") or "sin_fila",
                "detalle": reg.get("detalle") or "la tabla del HLF no tiene fila para este diagnóstico descompensado: mantiene su prioridad y "
                                                  "queda para revisión clínica", **extra, "fuente": fuente}
    if base in puntaje.FILA_DESCOMPENSADO and fila == puntaje.FILA_DESCOMPENSADO[base]:
        origen, fuente = "fila 'descompensado' del diagnóstico del registro", _ref("ssmso_hlf_2025", clave=base, constante="puntaje.FILA_DESCOMPENSADO")
    elif t and t.get("fila_si_empeora") and fila[0] == i["tabla"][t["fila_si_empeora"]]["texto"]:
        origen, fuente = "fila más grave de la misma enfermedad en la tabla", _ref("diagnosticos_tabla_hlf", clave=t["fila_si_empeora"])
    else:
        origen, fuente = "su propia fila ya es de prioridad alta", _ref("diagnosticos_tabla_hlf", clave=codigo)
    return {"fila": fila[0], "prioridad": fila[1], "pagina": fila[2], "equivalencia_a_validar": bool(equivalencia), "equivalencia": equivalencia,
            "origen": origen, **extra, "fuente": fuente}


def _regla_oncologica(especialidad, i):
    """Qué pasa si un informe trae un cáncer confirmado o sospechoso: la fila que devuelve puntaje.regla_oncologica."""
    o = i["puntaje"].regla_oncologica([{"tipo_evento": "hallazgo_oncologico"}], especialidad)
    fila, prioridad, pagina = o["fila"]
    return {"especialidad": especialidad, "fila": fila, "prioridad": prioridad, "pagina": pagina, "equivalencia_a_validar": o["a_validar"],
            "fuente": _constante("puntaje.PATRON_ONCOLOGICO" if o["a_validar"] else "puntaje.FILA_ONCOLOGICA")}


def _ges(codigo, i):
    puntaje = i["puntaje"]
    g = puntaje.GES_ESPECIALISTA.get(codigo)   # por el código tal cual (CIE-10 o HLF-…), como en puntaje.puntuar
    if not g:
        return None
    det = puntaje.GES_DETALLE[g[0]]
    return {"problema": g[0], "nombre": g[1], "plazo_dias": g[2], "edad_minima": g[3], "condicion": det["condicion"], "cita": det["cita"],
            "url": det["url"], "aviso_por_vencer_dias": puntaje.GES_POR_VENCER_DIAS,
            "nota": "el plazo se cuenta desde el ingreso a la lista: verificar el hito en SIGGES",
            "fuente": _ref("ges_especialista", clave=f"GES {g[0]}")}


def _criterios(enf, fid, i):
    """Lista cerrada de una enfermedad (la misma que recibe la IA: criterios.opciones), con su justificación y su riesgo."""
    if not enf:
        return None
    crit, urg = i["criterios"].opciones(enf)
    opcionales = {k: enf[c] for k, c in (("riesgo", "riesgo"), ("url", "fuente_url"), ("precision_para_clasificar", "precision_para_clasificar")) if enf.get(c)}
    return {"id": enf["id"], "enfermedad": enf["enfermedad"],
            "criterios": [{"codigo": k, "nivel": n, "texto": t} for k, (n, t) in crit.items()],
            "justificacion": {n: enf["niveles"][n].get("justificacion") for n in ("alta", "media", "baja")},
            "urgencias": [{"codigo": k, "texto": t} for k, t in urg.items()],
            "piso": enf.get("piso"), **opcionales, "fuente": _ref(fid, clave=enf["id"])}


def _reglas_con_el_registro(base, i):
    """Reglas que el código calcula solo con el registro (puntaje.aplicar_registro). El manifiesto las lee del código;
    las marcadas `requiere: criterios_registro` solo corren si el diagnóstico tiene criterios oficiales (la función
    termina antes para los demás), así que no se muestran donde no se aplican."""
    con_criterios = base in i["puntaje"].criterios_registro()
    reglas = [{"criterio": r["criterio"], "efecto": r["efecto"], **({"riesgo": r["riesgo"]} if r.get("riesgo") else {})}
              for r in _estado()["motor"].get("reglas_en_codigo", [])
              if base in r.get("diagnosticos", []) and (con_criterios or r.get("requiere") != "criterios_registro")]
    return {"reglas": reglas, "nota": "se calculan con el registro, sin IA; solo suben la prioridad o alertan",
            "fuente": _ref("motor", funcion="puntaje.aplicar_registro")} if reglas else None


def _rubrica(codigo, base, i):
    """Lo que recibe la fórmula (decisor.kb_diagnostico): medición clave y umbral, ventanas de vigencia y pendientes."""
    kb = i["kb"]
    if base not in kb["diagnosticos"]:
        return None
    dx = i["decisor"].kb_diagnostico(kb, codigo)
    med, medicion = dx.get("medicion"), None
    if med:
        u = med.get("umbral") or {}
        medicion = {"tipo": med["tipo"], "sube_a_fila": bool(med.get("sube_a_fila")), "definida_por": med.get("definida_por"),
                    "fila_por_medicion": dx.get("fila_por_medicion"),
                    "umbral": {"valor": u.get("valor"), "unidad": u.get("unidad"), "sentido": u.get("sentido"), "estado": u.get("estado"),
                               "cita": u.get("fuente"), "fuente": _ref("guias_umbrales", clave=u.get("id"))}}
    ventanas = []
    for evento, v in (dx.get("ventanas") or {}).items():
        pmid = re.search(r"PMID:?\s*(\d+)", v.get("fuente") or "")
        opcionales = {k: x for k, x in (("nota", v.get("nota")), ("pmid", pmid and pmid.group(1))) if x}
        ventanas.append({"evento": evento, "dias": v.get("valor"), "estado": v.get("estado"), **opcionales, "cita": v.get("fuente"),
                         "fuente": _ref("pubmed_evidencia", clave=v.get("id"))})
    return {"medicion_clave": dx.get("medicion_clave"), "medicion": medicion, "ventanas": ventanas,
            "pendientes_medicos": [p for p in kb.get("pendientes_medicos", []) if p.startswith(base + ":")],
            "fuente": _ref("rubrica_v1", clave=base)}


def _letalidad(base, i):
    if base not in i["puntaje"].LETALIDAD_DX:
        return None
    nivel, detalle = i["puntaje"].LETALIDAD_DX[base]
    return {"nivel": nivel, "detalle": detalle, "fuente": _constante("puntaje.LETALIDAD_DX")}


def _combinaciones(codigo, texto, i):
    """Combinaciones de riesgo cuya condición de base calza con el diagnóstico (combinaciones.base_en_registro, sin
    comorbilidades ni edad: eso depende de cada paciente). Devuelve (las propias del diagnóstico, bloque)."""
    comb = i["combinaciones"]
    cond = comb.condiciones({"paciente": {}, "lista_espera": {"diagnostico_cie10": codigo, "diagnostico_texto": texto or ""}})
    todas, propias, generales = comb.cargar()["kb"]["combinaciones"], [], []
    for c in todas:
        if c["base"].get("cualquiera"):
            generales.append({"id": c["id"], "nombre": c["nombre"], "efecto": c["efecto"]})
        elif comb.base_en_registro(c, cond):
            propias.append({"id": c["id"], "nombre": c["nombre"], "gatillo": c["gatillo"], "efecto": c["efecto"], "estado": c["estado"],
                            "letalidad": c.get("letalidad"), "desenlace": c["desenlace"], "riesgo": c.get("riesgo"),
                            "documento": c["fuente"].get("documento"), "url": c["fuente"].get("url")})
    return propias, {"por_diagnostico": propias, "para_cualquier_paciente": generales,
                     "nota": f"de {len(todas)} combinaciones; las demás dependen de las comorbilidades, la edad o los fármacos de cada paciente",
                     "fuente": _ref("combinaciones_riesgo")}


def _orden(base, i):
    puntaje = i["puntaje"]
    out = {"cascada": _json("ord536").get("cascada", []), "estado": (_estado()["por_id"].get("ord536") or {}).get("estado"),
           "como_se_aplica": _doc(puntaje.clave_orden), "fuente": _ref("ord536")}
    if base in puntaje.CHARLSON_LACE:   # el desempate LACE (experimental) cuenta este diagnóstico como condición de Charlson
        peso, condicion = puntaje.CHARLSON_LACE[base]
        out["desempate_lace"] = {"charlson": peso, "condicion": condicion, "experimental": True, "fuente": _constante("puntaje.CHARLSON_LACE")}
    return out


def _plazo(i):
    return {"dias_por_prioridad": dict(i["puntaje"].PLAZO_CATEGORIA), "riesgo_de_esperar": i["puntaje"].RIESGO_ESPERA,
            "fuente": _constante("puntaje.PLAZO_CATEGORIA")}


def _criterios_locales(codigo):
    """Lo que devuelven las capas registradas (hoy ninguna). Una capa que falla no bota la consulta: queda como aviso."""
    items, avisos = [], []
    for fn, _ in _CAPAS:
        try:
            r = fn(codigo)
        except Exception as e:
            avisos.append(f"capa local {getattr(fn, '__name__', '?')}: {type(e).__name__}: {str(e)[:160]}")
            continue
        items += list(r) if isinstance(r, (list, tuple)) else [r] if r else []
    return items, avisos


def _citadas(x, ids):
    """Ids de las fuentes citadas en los bloques, en orden de aparición."""
    if isinstance(x, dict):
        f = x.get("fuente")
        if isinstance(f, dict) and f.get("id") and f["id"] not in ids:
            ids.append(f["id"])
        for v in x.values():
            _citadas(v, ids)
    elif isinstance(x, list):
        for v in x:
            _citadas(v, ids)
    return ids


def para_diagnostico(cie10):
    """Todo lo que el sistema sabe y aplica para un diagnóstico, cada bloque con su `fuente` (id + versión). Acepta un
    CIE-10 (`I20`, `e11.9`) o un código de la tabla del HLF (`HLF-CAR-01`). Devuelve None si no hay nada específico para
    ese código (el enrutador responde 404)."""
    i = _indices()
    consulta = unquote(str(cie10 or "")).strip().upper()
    if consulta in i["tabla"]:
        codigo = consulta
    elif re.match(r"[A-Z]\d{2}", consulta):
        codigo = consulta[:3]   # CIE-10 de 3 caracteres, como los normaliza el importador
    else:
        return None
    puntaje, criterios = i["puntaje"], i["criterios"]
    base = puntaje.cie_base(codigo)   # fila de la tabla que es la misma enfermedad que un diagnóstico del registro
    fila, reg, enf = i["tabla"].get(codigo), i["kb"]["diagnosticos"].get(base), criterios.enfermedad_de(codigo)
    texto = (fila or {}).get("texto") or (reg or {}).get("texto") or (enf or {}).get("enfermedad")
    especialidad = (fila or {}).get("especialidad") or i["especialidad"].get(base) or (enf or {}).get("especialidad")
    tabla, ges, letalidad = _tabla(codigo, base, i), _ges(codigo, i), _letalidad(base, i)
    oficiales = _criterios(puntaje.criterios_registro().get(base), "criterios_registro", i)
    clinicos = _criterios(enf if enf and enf["id"] in i["de_especialidad"] else None, "criterios_especialidad", i)
    propias, combinaciones = _combinaciones(codigo, texto, i)
    if not (tabla or reg or oficiales or clinicos or ges or letalidad or propias):
        return None
    locales, avisos = _criterios_locales(codigo)
    paq = _estado()["paquete"]
    out = {"consulta": str(cie10), "codigo": codigo, "cie10_base": base, "diagnostico": texto, "especialidad": especialidad,
           "paquete": {k: paq[k] for k in ("etiqueta", "huella", "integro")},
           "tabla": tabla,
           "si_se_descompensa": _si_se_descompensa(codigo, base, i),
           "regla_oncologica": _regla_oncologica(especialidad, i),
           "ges": ges,
           "criterios_oficiales": oficiales,
           "criterios_clinicos": clinicos,
           "reglas_con_el_registro": _reglas_con_el_registro(base, i),
           "rubrica": _rubrica(codigo, base, i),
           "letalidad": letalidad,
           "combinaciones": combinaciones,
           "orden": _orden(base, i),
           "plazo_referencia": _plazo(i),
           "criterios_locales": locales}
    if avisos:
        out["avisos"] = avisos
    out["fuentes"] = [_ficha(fid) for fid in _citadas(out, [])]
    return copy.deepcopy(out)   # nada de lo devuelto comparte memoria con las cachés del motor


# ---------- qué fuentes respaldan una decisión ----------
TABLA = [("diagnosticos_tabla_hlf", None), ("ssmso_hlf_2025", None)]   # la tabla oficial, en sus dos transcripciones


def _pagina(fuente):
    paginas = re.findall(r"pág\. (\d+)", fuente)
    return int(paginas[-1]) if paginas else None


def _filas_citadas(fila, pagina):
    """[(id de fuente, clave)] de las transcripciones de la tabla oficial que traen esa fila en esa página."""
    i = _indices()
    n, out = i["normalizar"](fila or ""), []
    for texto, fid, clave in (i["filas"].get(pagina, []) if n else []):
        if (n == texto or n.startswith(texto + " (")) and (fid, clave) not in out:
            out.append((fid, clave))
    return out


def _letal(r):
    """La cifra de 'qué puede pasar' de una descompensación sale de una constante del código."""
    return [("motor", "puntaje.LETALIDAD_DX")] if r.get("riesgo") else []


def _fila_usada(m, r):
    """La fila de la tabla que cita la razón: las transcripciones que la traen y por dónde la leyó el motor. La fórmula
    (modo con IA) la lee de la rúbrica consolidada; las reglas, de la constante del código. Si la fila no se puede
    ubicar (p. ej. "la tabla no tiene fila para este diagnóstico"), respaldan las dos transcripciones."""
    refs = (_filas_citadas(m.group(1), _pagina(r["fuente"])) if m else []) or list(TABLA)
    del_registro = [clave for fid, clave in refs if fid == "ssmso_hlf_2025" and clave]
    if r.get("_formula"):
        return refs + ([("rubrica_v1", c) for c in del_registro] or [("rubrica_v1", None)])
    return refs + ([("motor", "puntaje.FILA_DESCOMPENSADO")] if del_registro else [])


def _r_tabla(r):
    return _fila_usada(re.match(r'"(.+?)" → prioridad', r["valor"]), r) + _letal(r)


def _r_vital(r):
    m = re.search(r"Descompensación grave \((.+)\) sin registro", r["valor"])
    return _fila_usada(m, r) + [("motor", "regla de descompensación grave")] + _letal(r)


def _r_oncologico(r):
    m, refs = re.search(r'pág\. ([\d, ]+): "(.+)"$', r["fuente"]), []
    if m and m.group(1).strip().isdigit():   # fila propia de la especialidad (puede unir dos filas con " / ")
        for parte in m.group(2).split(" / "):
            refs += [x for x in _filas_citadas(parte, int(m.group(1))) if x not in refs]
    return (refs or [("diagnosticos_tabla_hlf", None)]) + [("motor", "puntaje.regla_oncologica")]


def _r_registro(r):
    return [("criterios_registro", _indices()["url_registro"].get(r["fuente"].rsplit(" · ", 1)[-1].strip()))]


def _r_combinacion(r):
    nombre = re.split(r': "| \(sin fuente verificada\)', r["valor"], maxsplit=1)[0]
    return [("combinaciones_riesgo", _indices()["combinacion"].get(nombre))]


def _r_criterio(r):
    """Criterio o urgencia: viene de una combinación de riesgo, de los criterios oficiales del registro (su fuente es la
    URL de la guía) o de los criterios clínicos por especialidad."""
    i = _indices()
    if r["valor"].startswith("combinación de riesgo · "):
        return _r_combinacion({**r, "valor": r["valor"].split(" · ", 1)[1]})
    if r["fuente"].strip() in i["url_registro"]:
        return _r_registro(r)
    if "especialidad" in r["fuente"]:
        return [("criterios_especialidad", i["enfermedad"].get(r["valor"].split(", criterio ", 1)[0]))]
    return [("criterios_registro", None), ("criterios_especialidad", None)]


def _r_alerta_combinacion(r):
    if "(sin fuente verificada)" in r["valor"]:   # está en la lista, pero su fuente no se ha verificado: solo alerta
        return _r_combinacion(r)
    return [("motor", "red de seguridad de la IA: combinación que no está en la lista (combinaciones.py)")]


def _r_medicion(r):
    if "supera el umbral" not in r["valor"]:      # puntaje.py: dos mediciones estables seguidas fuera de rango
        return [("registro_paciente", "mediciones"), ("motor", "puntaje.MEDICIONES_ESTABLES")]
    m = re.search(r'→ "(.+?)" \(prioridad', r["valor"])   # decisor.py: umbral de guía + fila de la tabla, leídos de la rúbrica
    return [("guias_umbrales", _indices()["umbral"].get(r["fuente"].rsplit(" · ", 1)[0]))] + _fila_usada(m, {**r, "_formula": True})


def _r_ventana(r):
    pmid = re.search(r"PMID:?\s*(\d+)", r["fuente"])
    return [("pubmed_evidencia", _indices()["ventana"].get(r["fuente"]) or (pmid and "PMID:" + pmid.group(1))), ("rubrica_v1", None)]


def _r_ges(r):
    m = re.search(r"/index/(\d+)", r["fuente"]) or re.search(r"GES N°(\d+)", r["valor"])
    return [("ges_especialista", m and "GES " + m.group(1))]


def _r_evento(r):
    principio = [("motor", "principio: el sistema no baja la prioridad solo")] if r["fuente"].startswith("Principio de diseño") else []
    return [("registro_paciente", "eventos clínicos")] + principio


def _r_local(r):
    return [("criterios_locales", c) for c in re.findall(r"CL-\d+(?: v\d+)?", r["fuente"])] or [("criterios_locales", None)]


# factor de la razón → [(id de la fuente, clave de la entrada)]. Están todos los que producen puntaje.py y decisor.py
# (un test lo exige) y el de la capa de criterios locales (ESPECIFICACION_MVP §6.3).
FACTORES = {
    "prioridad_inicial": lambda r: [("registro_paciente", "prioridad inicial de la SIC")],
    "evento": _r_evento,
    "tabla_oficial": _r_tabla,
    "riesgo_vital": _r_vital,
    "oncologico": _r_oncologico,
    "criterio_registro": _r_registro,
    "piso": _r_registro,
    "criterio_clinico": _r_criterio,
    "urgencia": _r_criterio,
    "combinacion": _r_combinacion,
    "alerta_combinacion": _r_alerta_combinacion,
    "alerta_clinica": lambda r: [("motor", "puntaje.aplicar_registro")],
    "medicion": _r_medicion,
    "ventana": _r_ventana,
    "ges": _r_ges,
    "dias_espera": lambda r: [("ord536", "antiguedad_mayor_1_anio")],
    "grupo_proteccion": lambda r: [("ord536", "grupo_especial_proteccion")],
    "lace": lambda r: [("motor", "puntaje.indice_lace")],
    "acg": lambda r: [("registro_paciente", "estratificación ACG"), ("motor", "puntaje.ACG_NIVELES")],
    "plazo": lambda r: [("motor", "puntaje.PLAZO_CATEGORIA"), ("criterios_registro", None)],
    "criterio_local": _r_local,
}


def fuentes_de(razones, motor=None):
    """Fuentes que respaldan las razones de una decisión, sin repetir y en orden de aparición:
    [{id, titulo, tipo, version, sha256, factores[], claves[]}]. `claves` dice qué entrada exacta de esa fuente se usó
    (fila de la tabla, problema GES, enfermedad, combinación, PMID). Además de las fuentes del manifiesto aparecen
    `motor` (lo que vive en el código), `registro_paciente` (la prioridad inicial de la SIC y los hechos del paciente) y
    `criterios_locales`. Nunca lanza: una razón que no se reconoce queda en `sin_catalogar`, a la vista.
    `motor` (opcional): el del dictamen (`ia_rubrica` | `reglas` | `reglas_respaldo`). Sin él se deduce de las razones:
    solo la fórmula escribe una ventana o un evento con "(cita verificada)". Sirve para citar por dónde se leyó la fila
    de la tabla: la rúbrica consolidada (fórmula) o la constante del código (reglas)."""
    razones = [r for r in razones or [] if isinstance(r, dict)]
    formula = motor == "ia_rubrica" if motor else any(r.get("factor") == "ventana" or "(cita verificada)" in str(r.get("fuente")) for r in razones)
    orden, usos = [], {}
    for r in razones:
        factor = str(r.get("factor"))
        r = {**r, "valor": str(r.get("valor") or ""), "fuente": str(r.get("fuente") or ""), "_formula": formula}
        try:
            refs = FACTORES[factor](r) if factor in FACTORES else [("sin_catalogar", factor)]
        except Exception:   # una razón con forma inesperada no puede botar el registro de la decisión
            refs = [("sin_catalogar", factor)]
        for fid, clave in refs:
            if fid not in usos:
                orden.append(fid)
            u = usos.setdefault(fid, {"factores": [], "claves": []})
            if factor not in u["factores"]:
                u["factores"].append(factor)
            if clave and clave not in u["claves"]:
                u["claves"].append(clave)
    return [{**_ficha(fid), **usos[fid]} for fid in orden]


# ---------- capa local y rutas ----------
def registrar_capa_local(fn, version=None):
    """Gancho para el conocimiento que nace de la retroalimentación (aprendizaje.py; vive en DynamoDB, no aquí).
    `fn(cie10) -> list[dict]`: criterios locales vigentes que calzan con ese diagnóstico (CIE-10 o código HLF-…);
    para_diagnostico los entrega en `criterios_locales`. `version` (opcional): número, o función sin argumentos, con la
    versión de la capa local; se muestra en GET /conocimiento."""
    if all(f is not fn for f, _ in _CAPAS):
        _CAPAS.append((fn, version))
    return fn


def _capa_local():
    version = None
    for _, v in _CAPAS:
        try:
            version = v() if callable(v) else v
        except Exception:
            version = None
        if version is not None:
            break
    return {"capas": len(_CAPAS), "version": version}


def rutear(method, partes, qs=None, body=None):
    """GET /conocimiento → {paquete, fuentes, motor, capa_local, integridad, avisos}
    GET /conocimiento/diagnostico/{cie10} → para_diagnostico(cie10) o 404.
    Cualquier otra ruta → None (la resuelve el enrutador principal)."""
    if method != "GET" or not partes or partes[0] != "conocimiento":
        return None
    if len(partes) == 1:   # `avisos`: la deuda conocida de las fuentes que detecta el script al empaquetar
        return 200, {"paquete": paquete(), "fuentes": fuentes(), "motor": motor(), "capa_local": _capa_local(), "integridad": integridad(),
                     "avisos": list(_estado()["avisos"])}
    if len(partes) == 3 and partes[1] == "diagnostico":
        d = para_diagnostico(partes[2])
        return (200, d) if d else (404, {"error": f"el sistema no tiene conocimiento específico para el diagnóstico '{unquote(partes[2])}'"})
    return None
