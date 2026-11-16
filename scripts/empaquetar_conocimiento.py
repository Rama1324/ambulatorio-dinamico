"""Empaqueta la base de conocimiento: genera lambda/conocimiento/manifiesto.json, el registro único de qué versión de
cada fuente médica está vigente (docs/diseno/ESPECIFICACION_MVP.md §4 · docs/conocimiento/README.md).

Por qué: cada JSON de conocimiento trae una `version` escrita a mano y parte de las reglas son constantes del código. Sin
un registro con huellas, nada impide cambiar una fuente sin cambiar su versión, y una decisión no puede decir con
exactitud qué usó. El manifiesto anota por fuente su versión y su huella (sha256 del contenido, no del formato), la huella
de los archivos con reglas o prompts (el "motor") y las constantes clínicas del código con el comentario que dice de
dónde salen. Un test falla si un archivo cambia y el manifiesto no, y este script no acepta una fuente cuyo contenido
cambió con la misma versión.

Uso, desde la raíz del repo:
  python scripts/empaquetar_conocimiento.py                           regenera (no toca nada si nada cambió)
  python scripts/empaquetar_conocimiento.py --etiqueta kb-2026.11.1   regenera con otra etiqueta de paquete
  python scripts/empaquetar_conocimiento.py --verificar               para CI: sale con 1 y lista qué cambió
  python scripts/empaquetar_conocimiento.py --huella ARCHIVO          huella de un archivo, para auditar
Corre en desarrollo, nunca en la Lambda. Sin dependencias.
"""
import argparse
import ast
import io
import json
import os
import re
import sys
import tokenize
from collections import Counter
from datetime import datetime, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "lambda"))
import base_conocimiento as bc  # noqa: E402  (las huellas se definen una sola vez: las mismas en el script y en la Lambda)

ETIQUETA_INICIAL = "kb-2026.11.0"   # kb-AAAA.MM.N
# Archivos con reglas o prompts: un cambio en cualquiera cambia la huella del paquete
MOTOR = ["puntaje.py", "decisor.py", "controles.py", "algoritmo.py", "rubrica.py", "criterios.py", "combinaciones.py", "lector_documento.py"]
# Constantes de puntaje.py que son convenciones del programa, no conocimiento clínico
NO_CLINICAS = {"FUENTE_TABLA", "ORDEN_CAT", "PUNTAJE_PRIORIDAD", "FACTORES_REGLA"}
# Otras constantes clínicas fuera de puntaje.py (equivalencia CIE-10 → enfermedad, definida por el equipo)
OTRAS_CONSTANTES = {"criterios.py": {"CIE10"}}
PROPIOS = {"base_conocimiento.py", "empaquetar_conocimiento.py"}   # este servicio lee todas las fuentes: no cuenta como "quién la usa"
README = "docs/conocimiento/README.md"
INICIO = "<!-- fuentes:inicio · lo escribe scripts/empaquetar_conocimiento.py; no editar a mano -->"
FIN = "<!-- fuentes:fin -->"
NOTA = ("Generado por scripts/empaquetar_conocimiento.py: no editar a mano. sha256 = huella del contenido canónico de cada JSON (claves "
        "ordenadas, sin espacios) o del texto de cada .py con saltos de línea \\n; no depende del formato del archivo.")

# Estados posibles de una fuente. Salen de los propios JSON y de docs/CRITERIO_PRIORIZACION.md §3 (no se inventan).
VERIFICADO, EN_PARTE = "verificado en la fuente", "verificado en parte"
SECUNDARIA, NO_CONFIRMADO, CONSOLIDADO = "fuente secundaria", "origen no confirmado: solo sube", "consolidado de otras fuentes"


def leer(ruta):
    with open(ruta, encoding="utf-8-sig") as f:
        return f.read()


def _cuenta(valores):
    """'25 urgencia · 10 alta' (de más a menos)."""
    return " · ".join(f"{n} {k}" for k, n in sorted(Counter(valores).items(), key=lambda x: (-x[1], str(x[0]))))


def _fecha(j):
    """La fecha que traiga el JSON: `fecha`, `generado` o `consultado` (arriba o dentro de `fuente`)."""
    f = j.get("fuente") if isinstance(j.get("fuente"), dict) else {}
    return j.get("fecha") or j.get("generado") or j.get("consultado") or f.get("consultado")


def _enfermedades(j):
    return [e for s in j["especialidades"] for e in s["enfermedades"]]


# ---------- cómo se describe cada fuente: origen, fecha, estado y número de entradas, leídos de su propio JSON ----------
def _ssmso(j):
    dx = list(j["diagnosticos"].values())
    n = Counter(d["estado"] for d in dx)
    return {"origen": {"documento": j["fuente"]["ref"], "url": j["fuente"].get("url"), "metodo": j["fuente"].get("metodo")},
            "entradas": len(dx), "estado": VERIFICADO,
            "detalle": f'{n["con_fuente"]} diagnósticos con fila de descompensación ({sum(1 for d in dx if d.get("equivalencia"))} con equivalencia a '
                       f'validar por médico), {n["a_validar_por_medico"]} con fila candidata a validar por médico y {n["sin_fila"]} sin fila'}


def _tabla(j):
    dx = j["diagnosticos"]
    return {"origen": {"documento": j["fuente"]["documento"], "url": j["fuente"].get("url"), "metodo": j["fuente"].get("metodo")},
            "entradas": len(dx), "estado": VERIFICADO,
            "detalle": f'{_cuenta(d["verificacion"] for d in dx)}. Equivalencias del equipo, a validar por el especialista: '
                       f'{sum(1 for d in dx if d.get("cie10_base"))} filas con cie10_base y {sum(1 for d in dx if d.get("fila_si_empeora"))} con fila_si_empeora'}


def _ord536(j):
    f = j["fuente"]
    return {"origen": {"documento": f["ref"], "url": f.get("url")}, "entradas": len(j["cascada"]),
            "estado": {"fuente_secundaria": SECUNDARIA, "verificado": VERIFICADO}.get(f.get("estado"), f.get("estado")),
            "detalle": "Pendiente: " + f["pendiente"] if f.get("pendiente") else None}


def _ges(j):
    p = j["problemas"]
    ok = sum(1 for x in p if x.get("cita") and x.get("url"))
    return {"origen": {"documento": j["objeto"].split(". ")[0].rstrip(".") + ".", "url": j.get("fuente_general")}, "entradas": len(p),
            "estado": VERIFICADO if ok == len(p) else EN_PARTE,
            "detalle": f'{ok} de {len(p)} problemas con la cita textual y la URL de su página oficial; {len(j.get("excluidos") or {})} garantías '
                       "excluidas con su motivo (no fijan un plazo de consulta con especialista)"}


def _registro(j):
    e = _enfermedades(j)
    documento, _, url = j["fuente_general"].partition(" — ")
    ok = sum(1 for x in e if str(x.get("fuente_url") or "").startswith("http"))
    return {"origen": {"documento": documento, "url": url or None}, "entradas": len(e), "estado": VERIFICADO if ok == len(e) else EN_PARTE,
            "detalle": f"{ok} de {len(e)} enfermedades con la URL de su página oficial (Queensland CPC; NICE en salud mental). Guía extranjera: la "
                       "equivalencia con alta/media/baja del SSMSO es una propuesta del equipo; solo sube la prioridad"}


def _especialidad(j):
    e = _enfermedades(j)
    return {"origen": {"documento": j.get("objeto"), "url": None}, "entradas": len(e), "estado": NO_CONFIRMADO,
            "detalle": f'{len(e)} enfermedades de {len(j["especialidades"])} especialidades y {sum(len(x.get("excepciones_de_urgencia") or []) for x in e)} '
                       "excepciones de urgencia. Dataset aportado al equipo, sin validación clínica externa: se usa solo para subir, nunca para "
                       "bajar de lo que dice la tabla oficial (docs/CRITERIO_PRIORIZACION.md §3)"}


def _combinaciones(j):
    c = j["combinaciones"]
    v = [x for x in c if x["estado"] == "verificado"]
    return {"origen": {"documento": "cada combinación cita su documento, su cita textual y su URL o página (campo fuente)", "url": None},
            "entradas": len(c), "estado": VERIFICADO if len(v) == len(c) else EN_PARTE,
            "detalle": f'{len(v)} de {len(c)} verificadas en el documento oficial ({_cuenta(x["efecto"] for x in v)}); {len(c) - len(v)} sin verificar: '
                       "solo generan una alerta visible, no mueven a nadie"}


def _pubmed(j):
    e = j["entradas"]
    con = [x for x in e if x.get("estado") == "con_fuente"]
    return {"origen": {"documento": "cada ventana cita su PMID (campo fuente)", "url": None, "generado_por": j.get("script")},
            "entradas": len(e), "estado": VERIFICADO if len(con) == len(e) else EN_PARTE,
            "detalle": f'{len(con)} de {len(e)} ventanas con fuente ({sum(1 for x in con if (x.get("fuente") or {}).get("verificado_ncbi"))} con el PMID '
                       f"confirmado en NCBI); {len(e) - len(con)} a validar por médico: sin fuente, el evento no vence"}


def _umbrales(j):
    e = j["entradas"]
    con = [x for x in e if x.get("estado") == "con_fuente"]
    return {"origen": {"documento": "cada umbral cita su guía o su PMID (campo fuente)", "url": None, "generado_por": j.get("script")},
            "entradas": len(e), "estado": VERIFICADO if len(con) == len(e) else EN_PARTE,
            "detalle": f'{len(con)} de {len(e)} umbrales con fuente ({_cuenta((x.get("fuente") or {}).get("tipo") for x in con)}); '
                       f"{len(e) - len(con)} a validar por médico"}


def _rubrica(j):
    dx = list(j["diagnosticos"].values())
    v = [x for d in dx for x in (d.get("ventanas") or {}).values()]
    return {"origen": {"documento": "consolidado de " + ", ".join(CATALOGO["rubrica_v1"]["derivada_de"]), "url": None,
                       "generado_por": "scripts/consolidar_rubrica.py"},
            "entradas": len(dx), "estado": CONSOLIDADO,
            "detalle": f'{len(j.get("pendientes_medicos") or [])} pendientes para médicos; {len(v)} ventanas de vigencia '
                       f'({sum(1 for x in v if x.get("estado") == "con_fuente")} con fuente) y {sum(1 for d in dx if d.get("medicion"))} mediciones clave'}


# En orden de autoridad (docs/CRITERIO_PRIORIZACION.md §3). Toda fuente nueva se declara aquí: título, tipo y cómo se describe.
CATALOGO = {
    "ssmso_hlf_2025": {"titulo": "Tabla de priorización SSMSO 2025, sección HLF: fila que se usa si un diagnóstico del registro se descompensa",
                       "tipo": "tabla_oficial", "describir": _ssmso,
                       "nota": "las mismas filas están como constante en puntaje.FILA_DESCOMPENSADO; un test exige que coincidan"},
    "diagnosticos_tabla_hlf": {"titulo": "Tabla de priorización SSMSO 2025, sección HLF: diagnósticos y síntomas de las 7 especialidades (códigos HLF-…)",
                               "tipo": "tabla_oficial", "describir": _tabla},
    "ord536": {"titulo": "MINSAL Ord. C N°536 (21-03-2025): orden de la lista de espera No GES", "tipo": "norma", "describir": _ord536},
    "ges_especialista": {"titulo": "Garantías GES de oportunidad para la atención por especialista (Ley 19.966)", "tipo": "garantia_ges",
                         "describir": _ges},
    "criterios_registro": {"titulo": "Criterios oficiales por diagnóstico del registro (Queensland CPC y NICE)", "tipo": "criterios_clinicos",
                           "describir": _registro},
    "criterios_especialidad": {"titulo": "Criterios clínicos por enfermedad y especialidad (dataset aportado al equipo)", "tipo": "criterios_clinicos",
                               "describir": _especialidad},
    "combinaciones_riesgo": {"titulo": "Combinaciones de riesgo: condición de base del paciente + evento o hallazgo", "tipo": "combinaciones",
                             "describir": _combinaciones},
    "pubmed_evidencia": {"titulo": "Ventanas de riesgo tras un evento (PubMed)", "tipo": "evidencia", "describir": _pubmed},
    "guias_umbrales": {"titulo": "Umbrales de las mediciones clave (guías MINSAL e internacionales)", "tipo": "evidencia", "describir": _umbrales},
    "rubrica_v1": {"titulo": "Rúbrica consolidada que lee la fórmula: tabla, Ord. 536, ventanas y umbrales", "tipo": "rubrica", "describir": _rubrica,
                   "derivada_de": ["ssmso_hlf_2025", "ord536", "pubmed_evidencia", "guias_umbrales"]},
}


def describir_fuentes(raiz):
    kb = os.path.join(raiz, "lambda", "conocimiento")
    presentes = sorted(n[:-5] for n in os.listdir(kb) if n.endswith(".json") and n != bc.MANIFIESTO)
    nuevas = [n for n in presentes if n not in CATALOGO]
    if nuevas:
        raise SystemExit(f"Fuente sin catalogar: {', '.join(nuevas)}. Declara su título, tipo y estado en CATALOGO ({os.path.basename(__file__)}).")
    codigo = {}   # qué módulo nombra cada archivo: así `usado_por` sale del código y no de una lista escrita a mano
    for carpeta in ("lambda", "scripts"):
        d = os.path.join(raiz, carpeta)
        for n in (sorted(os.listdir(d)) if os.path.isdir(d) else []):
            if n.endswith(".py") and n not in PROPIOS:
                codigo[f"{carpeta}/{n}"] = leer(os.path.join(d, n))
    out = []
    for fid in (f for f in CATALOGO if f in presentes):
        j = json.loads(leer(os.path.join(kb, fid + ".json")))
        if not isinstance(j, dict) or not j.get("version"):
            raise SystemExit(f"{fid}.json no trae `version`: toda fuente debe declarar la suya.")
        c = CATALOGO[fid]
        try:
            d = c["describir"](j)
        except (KeyError, TypeError, AttributeError) as e:
            raise SystemExit(f"{fid}.json no tiene la forma esperada ({type(e).__name__}: {e}); revisa su descripción en CATALOGO.")
        ficha = {"id": fid, "titulo": c["titulo"], "tipo": c["tipo"], "archivo": f"lambda/conocimiento/{fid}.json", "version": j["version"],
                 "sha256": bc.huella_objeto(j), "fecha": _fecha(j), "origen": {k: v for k, v in d["origen"].items() if v},
                 "origen_url": d["origen"].get("url"), "estado": d["estado"], "estado_detalle": d["detalle"], "entradas": d["entradas"],
                 "usado_por": sorted(ruta for ruta, texto in codigo.items() if f"{fid}.json" in texto)}
        ficha.update({k: c[k] for k in ("derivada_de", "nota") if k in c})
        out.append(ficha)
    return out


# ---------- lo que vive en el código: se lee del fuente (ast), no se copia ----------
def _comentarios(fuente):
    """{línea: (texto, ocupa_toda_la_línea)}. Con tokenize: un '#' dentro de un texto no es un comentario."""
    out = {}
    for t in tokenize.generate_tokens(io.StringIO(fuente).readline):
        if t.type == tokenize.COMMENT:
            texto = t.string.lstrip("#").strip()
            if texto.startswith("---"):   # título de sección: "---------- Evidencia … ----------"
                texto = texto.strip("- ").rstrip(".") + "."
            out[t.start[0]] = (texto, t.line.strip().startswith("#"))
    return out


def _canonico(v):
    """Valor de una constante como JSON estable: los conjuntos se ordenan y las tuplas pasan a listas."""
    if isinstance(v, dict):
        return {str(k): _canonico(x) for k, x in v.items()}
    if isinstance(v, (set, frozenset)):
        return sorted(_canonico(x) for x in v)
    if isinstance(v, (list, tuple)):
        return [_canonico(x) for x in v]
    return v if v is None or isinstance(v, (str, int, float, bool)) else repr(v)   # bytes u otro literal raro: su texto


def constantes_de(ruta, solo=None, excluir=()):
    """Constantes en MAYÚSCULAS con valor literal de un módulo: nombre, huella del valor, cuántas entradas trae y su
    `fuente`, que es el comentario que la explica en el código (el bloque de arriba, el de la misma línea o, si no tiene,
    el de la constante inmediatamente anterior). Si alguien cambia una constante o su comentario, cambia el manifiesto."""
    fuente = leer(ruta)
    comentarios, modulo = _comentarios(fuente), os.path.splitext(os.path.basename(ruta))[0]
    out, previa = [], None
    for n in ast.parse(fuente).body:
        es_constante = isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) \
            and re.fullmatch(r"[A-Z][A-Z0-9_]*", n.targets[0].id)
        try:
            valor = ast.literal_eval(n.value) if es_constante else None
        except (ValueError, SyntaxError, TypeError):   # se calcula a partir de otra cosa (p. ej. se carga de un JSON): no es una constante
            es_constante = False
        if not es_constante:
            previa = None
            continue
        bloque, k = [], n.lineno - 1
        while k in comentarios and comentarios[k][1]:
            bloque.insert(0, comentarios[k][0])
            k -= 1
        en_linea = comentarios.get(n.end_lineno)
        texto = " ".join(bloque + ([en_linea[0]] if en_linea and not en_linea[1] else []))
        if not texto and previa and previa[0] == n.lineno - 1:
            texto = previa[1]
        previa = (n.end_lineno, texto)
        nombre = n.targets[0].id
        if nombre in excluir or (solo is not None and nombre not in solo) or valor in ([], {}, (), set()):
            continue   # una lista vacía no es conocimiento: es un registro que se llena al ejecutar
        c = {"nombre": f"{modulo}.{nombre}", "archivo": f"lambda/{os.path.basename(ruta)}", "sha256": bc.huella_objeto(_canonico(valor))[:12]}
        simple = (str, int, float)
        if isinstance(valor, (int, float)) or (isinstance(valor, str) and len(valor) <= 100):
            c["valor"] = valor       # un número o un texto corto se muestra tal cual
        elif isinstance(valor, (list, tuple, set, frozenset)) and len(valor) <= 8 and all(isinstance(x, simple) for x in valor):
            c["valor"] = _canonico(valor)
        elif not isinstance(valor, str):
            c["entradas"] = len(valor)   # de lo demás basta saber cuántas entradas trae: el detalle está en el código
        out.append({**c, "fuente": texto or None})
    return out


def reglas_registro(ruta):
    """Reglas que puntaje.aplicar_registro calcula con el registro, leídas del código: cada `if cie in (...)` con sus
    llamadas `sube(nivel, criterio, …)` y sus alertas. Sirven para que para_diagnostico las muestre sin copiarlas a mano."""
    fn = next((n for n in ast.parse(leer(ruta)).body if isinstance(n, ast.FunctionDef) and n.name == "aplicar_registro"), None)
    out, requiere = [], {}
    for nodo in (fn.body if fn else []):
        t = nodo.test if isinstance(nodo, ast.If) else None
        if isinstance(t, ast.UnaryOp) and isinstance(t.op, ast.Not) and isinstance(t.operand, ast.Name) and t.operand.id == "enf" \
                and any(isinstance(x, ast.Return) for x in nodo.body):
            requiere = {"requiere": "criterios_registro"}   # `if not enf: return …`: lo que sigue solo corre si el diagnóstico tiene criterios oficiales
        if not (isinstance(t, ast.Compare) and len(t.ops) == 1 and isinstance(t.ops[0], ast.In) and isinstance(t.left, ast.Name) and t.left.id == "cie"):
            continue
        try:
            dxs = [str(x) for x in ast.literal_eval(t.comparators[0])]
        except (ValueError, SyntaxError, TypeError):
            continue
        regla = {"funcion": "puntaje.aplicar_registro", "diagnosticos": dxs, **requiere}
        for sub in sorted((s for s in ast.walk(nodo) if isinstance(s, (ast.Call, ast.Dict))), key=lambda s: (s.lineno, s.col_offset)):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id == "sube" and len(sub.args) >= 2 \
                    and all(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in sub.args[:2]):
                out.append({**regla, "efecto": sub.args[0].value, "criterio": sub.args[1].value})
            elif isinstance(sub, ast.Dict):
                d = {k.value: v.value for k, v in zip(sub.keys, sub.values) if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)}
                if d.get("factor") == "alerta_clinica" and d.get("fuente"):
                    out.append({**regla, "efecto": "alerta", "criterio": d["fuente"], **({"riesgo": d["riesgo"]} if d.get("riesgo") else {})})
    return out


def describir_motor(raiz):
    def ruta(n):
        return os.path.join(raiz, "lambda", n)
    falta = [n for n in MOTOR if not os.path.exists(ruta(n))]
    if falta:
        raise SystemExit(f"Falta un archivo del motor: {', '.join(falta)} (revisa MOTOR en {os.path.basename(__file__)}).")
    archivos = [{"archivo": f"lambda/{n}", "sha256": bc.huella_archivo(ruta(n))} for n in MOTOR]
    sha = bc.huella_conjunta({a["archivo"]: a["sha256"] for a in archivos})
    constantes = constantes_de(ruta("puntaje.py"), excluir=NO_CLINICAS)
    for n, nombres in OTRAS_CONSTANTES.items():
        constantes += constantes_de(ruta(n), solo=nombres)
    return {"huella": sha[:12], "sha256": sha, "archivos": archivos, "constantes": constantes, "reglas_en_codigo": reglas_registro(ruta("puntaje.py"))}


def avisos_de(raiz, fuentes, motor):
    """Deuda visible (no impide empaquetar): versiones repetidas, fuentes sin fecha, constantes sin fuente y reglas del
    código que nunca se aplican."""
    out, por_version = [], {}
    for f in fuentes:
        por_version.setdefault(f["version"], []).append(f["id"])
    out += [f"versión repetida: '{v}' identifica a {' y '.join(ids)} (cada fuente debería tener la suya)"
            for v, ids in sorted(por_version.items()) if len(ids) > 1]
    sin_fecha = [f["id"] for f in fuentes if not f["fecha"]]
    if sin_fecha:
        out.append("el JSON no trae fecha (fecha, generado o consultado): " + ", ".join(sin_fecha))
    sin_fuente = [c["nombre"] for c in motor["constantes"] if not c.get("fuente")]
    if sin_fuente:
        out.append("constantes del código sin un comentario que diga su fuente: " + ", ".join(sin_fuente))
    ruta = os.path.join(raiz, "lambda", "conocimiento", "criterios_registro.json")
    con_criterios = {c for e in _enfermedades(json.loads(leer(ruta))) for c in e["cie10"]} if os.path.exists(ruta) else set()
    for r in motor["reglas_en_codigo"]:
        if r.get("requiere") == "criterios_registro" and not con_criterios & set(r["diagnosticos"]):
            out.append(f'regla del código que nunca se aplica: {r["funcion"]} "{r["criterio"]}" es para {", ".join(r["diagnosticos"])}, pero la función '
                       "termina antes para los diagnósticos que no están en criterios_registro.json")
    return out


def construir(raiz=RAIZ, etiqueta=ETIQUETA_INICIAL, generado=None):
    fuentes, motor = describir_fuentes(raiz), describir_motor(raiz)
    return {"esquema": 1, "nota": NOTA,
            "paquete": {"etiqueta": etiqueta, "huella": bc.huella_paquete(fuentes, motor["archivos"]), "generado": generado},
            "fuentes": fuentes, "motor": motor, "avisos": avisos_de(raiz, fuentes, motor)}


# ---------- comparar con lo guardado ----------
def leer_manifiesto(ruta):
    """El manifiesto guardado, o None si no existe o está dañado (verificar falla; regenerar lo reescribe)."""
    try:
        m = json.loads(leer(ruta))
        sano = isinstance(m["paquete"], dict) and all(x["id"] and x["archivo"] for x in m["fuentes"]) and all(x["archivo"] for x in m["motor"]["archivos"])
        return m if sano else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _por(lista, clave):
    return {x.get(clave): x for x in lista or []}


def sin_subir_version(nuevo, anterior):
    """Fuentes cuyo contenido cambió y cuya `version` sigue igual: justo lo que el manifiesto debe impedir."""
    a = _por((anterior or {}).get("fuentes"), "id")
    return [f["id"] for f in nuevo["fuentes"]
            if f["id"] in a and a[f["id"]].get("sha256") != f["sha256"] and a[f["id"]].get("version") == f["version"]]


def diferencias(nuevo, anterior):
    """Qué cambió entre el manifiesto guardado y los archivos, en palabras. Lista vacía = está al día."""
    if anterior is None:
        return ["no existe lambda/conocimiento/manifiesto.json (o está dañado)"]
    out = []
    a, n = _por(anterior.get("fuentes"), "id"), _por(nuevo["fuentes"], "id")
    for fid in sorted(set(a) | set(n)):
        if fid not in a:
            out.append(f"fuente {fid}: es nueva y no está en el manifiesto")
        elif fid not in n:
            out.append(f"fuente {fid}: está en el manifiesto pero el archivo ya no existe")
        elif a[fid].get("sha256") != n[fid]["sha256"]:
            version = f"su versión sigue en '{n[fid]['version']}'" if a[fid].get("version") == n[fid]["version"] else \
                f"versión '{a[fid].get('version')}' → '{n[fid]['version']}'"
            out.append(f"fuente {fid}: cambió el contenido (huella {str(a[fid].get('sha256'))[:12]} → {n[fid]['sha256'][:12]}; {version})")
        elif a[fid] != n[fid]:
            out.append(f"fuente {fid}: cambió " + ", ".join(sorted(k for k in set(a[fid]) | set(n[fid]) if a[fid].get(k) != n[fid].get(k))))
    am, nm = anterior.get("motor") or {}, nuevo["motor"]
    aa, na = _por(am.get("archivos"), "archivo"), _por(nm["archivos"], "archivo")
    for arch in sorted(set(aa) | set(na)):
        if aa.get(arch) != na.get(arch):
            out.append(f"motor {arch}: " + ("cambió" if arch in aa and arch in na else "no está en el manifiesto" if arch in na else "ya no es parte del motor"))
    ac, nc = _por(am.get("constantes"), "nombre"), _por(nm["constantes"], "nombre")
    for nombre in sorted(set(ac) | set(nc)):
        if ac.get(nombre) != nc.get(nombre):
            que = "es nueva" if nombre not in ac else "ya no existe" if nombre not in nc else \
                "cambió su valor" if ac[nombre].get("sha256") != nc[nombre].get("sha256") else \
                "cambió su comentario de fuente" if ac[nombre].get("fuente") != nc[nombre].get("fuente") else "cambió su descripción"
            out.append(f"motor: la constante {nombre} {que}")
    if am.get("reglas_en_codigo") != nm["reglas_en_codigo"]:
        out.append("motor: cambiaron las reglas de puntaje.aplicar_registro")
    if not out and anterior != nuevo:   # mismas huellas, pero el archivo no es el que se generaría (etiqueta, avisos, edición a mano)
        ap, np_ = anterior.get("paquete") or {}, nuevo["paquete"]
        if ap.get("etiqueta") != np_["etiqueta"]:
            out.append(f"paquete: la etiqueta es '{ap.get('etiqueta')}' y se pidió '{np_['etiqueta']}'")
        resto = sorted(k for k in set(anterior) | set(nuevo) if anterior.get(k) != nuevo.get(k) and (k != "paquete" or not out))
        if resto:
            out.append("manifiesto: su contenido no es el que genera el script (" + ", ".join(resto) + ")")
    return out


# ---------- tabla de fuentes del README: se escribe desde el manifiesto para que nunca quede vieja ----------
def bloque_readme(m):
    p = m["paquete"]
    lineas = [INICIO, f'Paquete vigente: **`{p["etiqueta"]}`** · huella `{p["huella"]}` · motor `{m["motor"]["huella"]}` · generado {p["generado"]}', "",
              "| Fuente (`id`) | Qué es | Versión | Estado | Entradas | Quién la usa |", "|---|---|---|---|---|---|"]
    for f in m["fuentes"]:
        usa = ", ".join(f"`{u.replace('lambda/', '')}`" for u in f["usado_por"]) or "—"
        lineas.append(f'| `{f["id"]}` | {f["titulo"]} | `{f["version"]}` | {f["estado"]} | {f["entradas"]} | {usa} |')
    return "\n".join(lineas + [FIN])


def readme_al_dia(raiz, m):
    """(texto nuevo del README o None si no hay que tocarlo, mensaje). Sin README o sin marcas no se hace nada."""
    ruta = os.path.join(raiz, *README.split("/"))
    if not os.path.exists(ruta):
        return None, None
    texto = leer(ruta).replace("\r\n", "\n")
    patron = re.escape(INICIO) + r".*?" + re.escape(FIN)
    if not re.search(patron, texto, flags=re.S):
        return None, f"{README}: no tiene las marcas de la tabla de fuentes"
    nuevo = re.sub(patron, lambda _: bloque_readme(m), texto, count=1, flags=re.S)
    return (None, None) if nuevo == texto else (nuevo, f"{README}: la tabla de fuentes no corresponde al manifiesto")


def escribir(ruta, texto):
    with open(ruta, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)


def main(argv=None):
    for flujo in (sys.stdout, sys.stderr):   # consola de Windows: que un "→" no bote el script
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Genera o verifica lambda/conocimiento/manifiesto.json")
    ap.add_argument("--verificar", action="store_true", help="no escribe: sale con 1 y lista qué cambió si el manifiesto no corresponde a los archivos")
    ap.add_argument("--etiqueta", help=f"etiqueta del paquete, kb-AAAA.MM.N (por defecto, la que ya tiene el manifiesto o {ETIQUETA_INICIAL})")
    ap.add_argument("--permitir-misma-version", action="store_true",
                    help="acepta una fuente cuyo contenido cambió sin subir su `version` (la huella igual cambia); evítalo")
    ap.add_argument("--huella", metavar="ARCHIVO", help="muestra la huella de un archivo y termina")
    ap.add_argument("--raiz", default=RAIZ, help=argparse.SUPPRESS)   # para los tests: otra copia del repo
    a = ap.parse_args(argv)
    if a.huella:
        try:
            print(bc.huella_archivo(a.huella), a.huella)
        except (OSError, ValueError) as e:
            print(f"No se pudo calcular la huella de {a.huella}: {e}")
            return 2
        return 0
    if a.etiqueta and not re.fullmatch(r"kb-\d{4}\.\d{2}\.\d+", a.etiqueta):
        print(f"Etiqueta inválida: '{a.etiqueta}'. Formato: kb-AAAA.MM.N (p. ej. {ETIQUETA_INICIAL}).")
        return 2
    ruta = os.path.join(a.raiz, "lambda", "conocimiento", bc.MANIFIESTO)
    anterior = leer_manifiesto(ruta)
    paq = (anterior or {}).get("paquete") or {}
    etiqueta = a.etiqueta or paq.get("etiqueta") or ETIQUETA_INICIAL
    nuevo = construir(a.raiz, etiqueta, paq.get("generado"))
    difs = diferencias(nuevo, anterior)
    if a.verificar:
        if not difs:   # el manifiesto está al día: falta ver que la tabla del README sea la suya
            _, aviso = readme_al_dia(a.raiz, anterior)
            difs = [aviso] if aviso else []
        if difs:
            print("El manifiesto NO corresponde a los archivos:")
            print("\n".join(f" - {d}" for d in difs))
            print("Si el cambio es intencional, regenera con\n  python scripts/empaquetar_conocimiento.py\n"
                  "(si cambió una fuente, sube antes su `version`: docs/conocimiento/README.md §4)")
            return 1
        print(f'Manifiesto al día: {paq.get("etiqueta")} · huella {paq.get("huella")} · {len(nuevo["fuentes"])} fuentes · motor {nuevo["motor"]["huella"]}')
        return 0
    repetidas = sin_subir_version(nuevo, anterior)
    if repetidas and not a.permitir_misma_version:
        print("No se regeneró el manifiesto: cambió el contenido de una fuente y su `version` sigue igual.")
        print("\n".join(f" - {fid}: sube la `version` dentro de lambda/conocimiento/{fid}.json" for fid in repetidas))
        print("Así una decisión antigua y una nueva no quedan citando la misma versión con contenidos distintos.")
        return 2
    if difs:
        nuevo["paquete"]["generado"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        escribir(ruta, json.dumps(nuevo, ensure_ascii=False, indent=1) + "\n")
        print(f'Manifiesto generado: {etiqueta} · huella {nuevo["paquete"]["huella"]} · {len(nuevo["fuentes"])} fuentes '
              f'({sum(f["entradas"] for f in nuevo["fuentes"])} entradas) · motor {nuevo["motor"]["huella"]}')
        if anterior:
            print("\n".join(f" - {d}" for d in difs))
        cambio_de_fondo = any(d.startswith("fuente ") and ("el contenido" in d or "es nueva" in d or "ya no existe" in d) for d in difs)
        if anterior and paq.get("etiqueta") == etiqueta and cambio_de_fondo:
            print("Cambió una fuente: si este paquete se va a desplegar, súbele la etiqueta (--etiqueta kb-AAAA.MM.N).")
    else:
        print(f'Sin cambios: {etiqueta} · huella {nuevo["paquete"]["huella"]} (no se tocó el manifiesto)')
    texto, aviso = readme_al_dia(a.raiz, nuevo)
    if texto:
        escribir(os.path.join(a.raiz, *README.split("/")), texto)
        print(f"{README}: tabla de fuentes actualizada")
    elif aviso:
        print("Aviso: " + aviso)
    if nuevo["avisos"]:
        print("Deuda de las fuentes (no impide empaquetar):")
        print("\n".join(f" - {x}" for x in nuevo["avisos"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
