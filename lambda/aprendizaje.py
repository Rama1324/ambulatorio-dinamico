"""Aprendizaje con la retroalimentación del especialista (docs/diseno/ESPECIFICACION_MVP.md §6).

  veredicto (acciones.post_revision) → precedente del patrón → criterio local PROPUESTO → jefatura lo aprueba → VIGENTE
  → el motor lo aplica (capa al final de puntaje.puntuar y de decisor.decidir) y cada decisión lo cita.

- Patrón = "<CIE-10 base>|<tipo del evento determinante o *>|<severidad o *>" (evento determinante = la descompensación
  vigente, puntaje.evento_determinante).
- Criterios locales en la partición reservada _kb: sk = criterio_local#<id>#<ts>. Solo se agrega: cada cambio de estado o
  precedente nuevo es un ítem nuevo y rige el último de cada id (el historial queda completo).
- Un criterio PROPUESTO no cambia ninguna prioridad: el paciente que calza lo muestra (criterios_propuestos) y queda para
  revisión. Uno VIGENTE solo sube (efecto subir_a), solo para fechas de corte ≥ vigente_desde (y < vigente_hasta si se
  retiró). Retirarlo no baja a nadie: quienes subió conservan su prioridad con una revisión automática y vuelven a la cola.
- Las correcciones hacia abajo nunca se vuelven regla: criterio_no_aplica deja la regla en "reglas a validar".
- Enmiendas de eventos (§6.4): POST /pacientes/{id}/eventos/{id_evento}/enmienda.
No se usa IA para aprender: todo es conteo y reglas aprobadas por personas.
"""
import json

import base_conocimiento
import datos
import puntaje
from catalogo import MIN_EXPLICACION, MOTIVOS_VEREDICTO

KB = "_kb"
PREFIJO = "criterio_local#"
ORDEN = puntaje.ORDEN_CAT
RESOLUCIONES = {"aprobar": ("propuesto", "vigente"), "rechazar": ("propuesto", "rechazado"), "retirar": ("vigente", "retirado")}
ACCIONES_ENMIENDA = {"anular": "anular el evento (no existió o es de otro paciente)",
                     "no_relacionado": "el evento no es por la enfermedad por la que espera",
                     "relacionado": "el evento sí es por la enfermedad por la que espera"}
MOTIVO_RETIRO = "criterio local retirado: requiere revisión individual"
TIPOS_LEGIBLES = {"visita_urgencia": "visita a urgencia", "hospitalizacion": "hospitalización"}


# ---------- patrón ----------
def patron_de(perfil, corte, det=False):
    """Patrón del paciente a esa fecha (det=False: se calcula con el registro)."""
    det = puntaje.evento_determinante(perfil, corte) if det is False else det
    cie = puntaje.cie_base(perfil["lista_espera"]["diagnostico_cie10"])
    return f'{cie}|{(det or {}).get("tipo_evento") or "*"}|{(det or {}).get("severidad") or "*"}'


def regla_principal(fundamento):
    """La razón con regla y fuente que sostiene la prioridad (la que un especialista puede objetar). Sin ninguna: la
    prioridad inicial de la SIC."""
    rz = [r for r in fundamento or [] if r.get("factor") in puntaje.FACTORES_REGLA and not r.get("sin_regla")]
    r = next((x for x in rz if x["factor"] != "riesgo_vital"), rz[0] if rz else None) or \
        next((x for x in fundamento or [] if x.get("factor") == "prioridad_inicial"), None)
    return r and {"factor": r["factor"], "valor": r.get("valor"), "fuente": r.get("fuente")}


# ---------- criterios locales: estado (último ítem de cada id) + índice por diagnóstico ----------
_CACHE = {"clave": None, "marca": None}


def _marca():
    """Huella barata de la partición _kb en la copia en memoria (cuántos ítems y el último que llegó): como ahí solo se
    agrega, si no cambió, los criterios tampoco. La capa se llama para cada paciente en cada cálculo de la lista: así no
    se vuelve a leer la partición 1.000 veces por solicitud. None si la copia aún no está cargada (entonces se lee)."""
    alm = datos.almacen()
    try:
        parte = alm._por_pk.get(KB) or {}
        return (id(alm), len(parte), next(reversed(parte), None)) if alm.cargado else None
    except (AttributeError, RuntimeError):   # otro almacén, o la partición cambió mientras se miraba: se lee
        return None


def _estado():
    """Criterios locales al día. Se vuelve a armar solo si llegó un ítem nuevo a _kb (solo se agrega: basta comparar las
    claves)."""
    marca = _marca()
    if marca is not None and marca == _CACHE["marca"]:
        return _CACHE
    items = datos.globales(KB, PREFIJO)
    _CACHE["marca"] = _marca()
    clave = tuple(i["sk"] for i in items)
    if _CACHE["clave"] == clave:
        return _CACHE
    actuales, historial, resoluciones = {}, {}, 0
    for it in items:
        try:
            c = json.loads(it["criterio_local"])
        except (KeyError, TypeError, ValueError):
            print(f"aprendizaje: {it.get('sk')}: criterio local ilegible, se omite")
            continue
        actuales[c["id"]] = c
        historial.setdefault(c["id"], []).append(c)
        resoluciones += c.get("evento") in RESOLUCIONES
    idx = {}
    for c in actuales.values():
        if c["estado"] in ("propuesto", "vigente", "retirado") and (c.get("efecto") or {}).get("tipo") == "subir_a":
            idx.setdefault(c["patron"]["diagnostico"], []).append(c)
    for cs in idx.values():
        cs.sort(key=lambda c: c["id"])
    _CACHE.update(clave=clave, actuales=actuales, historial=historial, idx=idx, version=resoluciones)
    return _CACHE


def version_capa():
    """Versión de la capa local = número de resoluciones registradas (aprobar, rechazar, retirar)."""
    return _estado()["version"]


def _rige(c, corte_iso):
    return c["estado"] in ("vigente", "retirado") and bool(c.get("vigente_desde")) and corte_iso >= c["vigente_desde"] and \
        (not c.get("vigente_hasta") or corte_iso < c["vigente_hasta"])


def _calza(c, det):
    p = c["patron"]
    return p.get("tipo_evento") in ("*", det.get("tipo_evento")) and p.get("severidad") in ("*", det.get("severidad"))


def fuente_de(c):
    n = len(c.get("precedentes") or [])
    aprobado = (c.get("aprobado") or {})
    return (f'Criterio local HLF {c["id"]} v{c["version"]} · aprobado por {aprobado.get("usuario") or c.get("resuelto_por")} el '
            f'{(aprobado.get("fecha") or c.get("fecha") or "")[:10]} (rige desde {c["vigente_desde"]}) · basado en {n} revisión(es) de especialista')


def capa(r, perfil, corte):
    """Capa de criterios locales: va al final de puntaje.puntuar (r con riesgo_vital) y de decisor.decidir (r con
    descompensacion_grave). Solo sube. Un criterio vigente que lleva a alta por un evento determinante grave deja al
    paciente en descompensación grave, igual que una fila de la tabla: es la misma situación clínica, definida por el equipo."""
    est = _estado()
    if not est["idx"]:
        return r
    cands = est["idx"].get(puntaje.cie_base(perfil["lista_espera"]["diagnostico_cie10"]))
    if not cands:
        return r
    det = r["evento_determinante"] if "evento_determinante" in r else puntaje.evento_determinante(perfil, corte)
    if not det:
        return r
    corte_iso, grave_k = corte.isoformat(), "riesgo_vital" if "riesgo_vital" in r else "descompensacion_grave"
    r = {**r, "razones": list(r.get("razones") or [])}
    aplicados, propuestos = [], []
    for c in cands:
        if c["estado"] == "propuesto" or not _calza(c, det) or not _rige(c, corte_iso):
            continue
        nueva = c["efecto"]["categoria"]
        sube = ORDEN[nueva] > ORDEN[r["categoria"]]
        grave = nueva == "alta" and det.get("severidad") == "grave" and not r.get(grave_k)
        if not (sube or grave):
            continue
        aplicados.append({"id": c["id"], "version": c["version"], "texto": c["texto"]})
        caso = c["texto"].split(" → ")[0]
        r["razones"].append({"factor": "criterio_local", "valor": f"{caso} → prioridad {nueva}" + ("" if sube else f" (ya era {nueva}: queda como descompensación grave)"),
                             "fuente": fuente_de(c)})
        if sube:
            r["categoria"] = nueva
            if "plazo_dias" in r:   # resultado de puntuar: los campos que dependen de la categoría quedan al día
                plazo, dias = puntaje.PLAZO_CATEGORIA[nueva], (corte - puntaje.d(det["fecha_evento"])).days
                r.update(prioridad_propuesta=nueva, puntaje_propuesto=puntaje.PUNTAJE_PRIORIDAD[nueva], estado_evaluacion="determinada",
                         plazo_dias=plazo, dias_en_prioridad=dias, plazo_vencido=dias > plazo)
                r["razones"] = [x for x in r["razones"] if x.get("factor") != "plazo" or dias > plazo]
        if grave:
            r[grave_k] = True
            r["razones"].insert(0, {"factor": "riesgo_vital",
                                    "valor": f"Descompensación grave según criterio local ({caso}) sin registro posterior de "
                                             "estabilización: la prioridad se actualizó apenas el evento llegó al sistema; el especialista puede cambiarla",
                                    "fuente": "MINSAL: criticidad / riesgo vital (SSMSO 2025, pág. 4) · " + fuente_de(c)})
    for c in cands:   # propuestos: no cambian nada; solo se muestran si subirían al paciente
        if c["estado"] == "propuesto" and _calza(c, det) and ORDEN[c["efecto"]["categoria"]] > ORDEN[r["categoria"]]:
            propuestos.append({"id": c["id"], "version": c["version"], "texto": c["texto"], "efecto": c["efecto"], "fecha": c["fecha"],
                               "de_este_paciente": any(p.get("id_paciente") == perfil["id_paciente"] for p in c.get("precedentes") or [])})
    if aplicados:
        r["criterios_locales"] = aplicados
    if propuestos:
        r["criterios_propuestos"] = propuestos
    return r


if capa not in puntaje.CAPAS:   # al importarse, el motor (reglas y fórmula) aplica los criterios locales vigentes
    puntaje.CAPAS.append(capa)


def para_diagnostico(cie10):
    """Capa local para base_conocimiento.para_diagnostico: criterios propuestos y vigentes de ese diagnóstico."""
    base = puntaje.cie_base(str(cie10 or "").strip().upper())
    return [publico(c) for c in _estado()["actuales"].values() if c["patron"]["diagnostico"] == base and c["estado"] in ("propuesto", "vigente")]


base_conocimiento.registrar_capa_local(para_diagnostico, version=version_capa)


def publico(c):
    """Lo que se muestra de un criterio local (sin repetir el historial)."""
    return {k: c.get(k) for k in ("id", "version", "estado", "patron", "efecto", "texto", "propuesto_por", "resuelto_por", "vigente_desde",
                                  "vigente_hasta", "motivo_resolucion", "fecha")} | {"precedentes": len(c.get("precedentes") or []),
                                                                                    "patron_texto": "|".join(c["patron"][k] for k in ("diagnostico", "tipo_evento", "severidad"))}


def _guardar(c):
    datos.guardar({"id_paciente": KB, "sk": f'{PREFIJO}{c["id"]}#{c["fecha"]}', "criterio_local": json.dumps(c, ensure_ascii=False, default=str)})
    return c


def _nuevo_id():
    """CL-0001, CL-0002…: el número se reserva con una escritura condicional (dos propuestas simultáneas no comparten id)."""
    n = len(_estado()["actuales"]) + 1
    while not datos.guardar({"id_paciente": KB, "sk": f"id#CL-{n:04d}"}, si_no_existe=True):
        n += 1
    return f"CL-{n:04d}"


# ---------- precedentes ----------
def veredictos():
    """Revisiones con veredicto (las automáticas no cuentan: no son el juicio de un especialista)."""
    out = []
    for it in datos.registros_tipo("revision#"):
        try:
            r = json.loads(it["revision"])
        except (KeyError, TypeError, ValueError):
            continue
        if r.get("veredicto") and not r.get("automatica"):
            out.append({**r, "id_paciente": it["id_paciente"]})
    return out


def precedentes(patron, vs=None):
    """Historial de veredictos del patrón: lo que ya dijeron los especialistas sobre casos iguales."""
    vs = veredictos() if vs is None else vs
    p = [v for v in vs if v.get("patron") == patron]
    return {"patron": patron, "total": len(p), "adecuadas": sum(v["veredicto"] == "adecuada" for v in p),
            "incorrectas": sum(v["veredicto"] == "incorrecta" for v in p),
            "ultimos": [{k: v.get(k) for k in ("veredicto", "motivo_codigo", "motivo", "usuario", "fecha", "id_paciente", "id_dictamen")}
                        for v in sorted(p, key=lambda v: v.get("fecha") or "", reverse=True)[:5]]}


def desacuerdo(patron, vs):
    """Fracción de veredictos 'incorrecta' del patrón (para ordenar la cola) y su n."""
    p = precedentes(patron, vs)
    return (p["incorrectas"] / p["total"] if p["total"] else 0.0), p["total"]


# ---------- veredicto → aprendizaje ----------
def al_revisar(pid, rev, dictamen, perfil, corte):
    """Lo que aprende el sistema de una revisión con veredicto. Devuelve {precedente, criterio_local, sugerencia, mensaje}."""
    patron = rev["patron"]
    out = {"precedente": precedentes(patron), "criterio_local": None, "sugerencia": None}
    n = out["precedente"]["total"]
    base = f'Queda como precedente del patrón {patron} ({n} revisión(es) de especialista: {out["precedente"]["adecuadas"]} adecuada(s), ' \
           f'{out["precedente"]["incorrectas"]} incorrecta(s)).'
    mc = rev.get("motivo_codigo")
    if rev["veredicto"] == "adecuada" or not mc:
        out["mensaje"] = base
    elif mc == "criterio_faltante":
        c, msg = _proponer(pid, rev, dictamen, perfil, corte)
        out["criterio_local"], out["mensaje"] = c and publico(c), base + " " + msg
    elif mc == "criterio_no_aplica":
        regla = rev.get("regla_objetada") or {}
        n_obj = len({v["usuario"] for v in veredictos() if v.get("motivo_codigo") == "criterio_no_aplica"
                     and (v.get("regla_objetada") or {}).get("fuente") == regla.get("fuente")})
        out["mensaje"] = base + (f' La regla «{regla.get("valor")}» ({regla.get("fuente")}) queda en "reglas a validar": '
                                 f'{n_obj} especialista(s) la han objetado. No baja a nadie: bajar lo decide el especialista en cada paciente.')
    elif mc in ("evento_no_relacionado", "lectura_incorrecta"):
        out["sugerencia"] = _sugerir_enmienda(pid, rev, dictamen)
        out["mensaje"] = base + (" Confirme la enmienda sugerida para corregir el evento." if out["sugerencia"] else
                                 " No hay un evento identificado que corregir: use la enmienda desde la historia del paciente.")
    elif mc == "informacion_no_registrada":
        out["mensaje"] = base + " La corrección vale solo para este paciente: no se generaliza."
    else:
        out["mensaje"] = base
    return out


def _proponer(pid, rev, dictamen, perfil, corte):
    """criterio_faltante: crea el criterio propuesto del patrón o suma el precedente al que ya existe (propuesto o vigente)."""
    cie, tipo, sev = rev["patron"].split("|")
    cat, sistema = rev.get("categoria_final"), rev.get("categoria_sistema")
    if not cat or not sistema or ORDEN.get(cat, 0) <= ORDEN.get(sistema, 0):
        return None, "No se propone un criterio: la prioridad indicada no es mayor que la del sistema (las correcciones hacia abajo no se vuelven regla)."
    if tipo == "*":
        return None, ("No se propone un criterio: el paciente no tiene un evento determinante (descompensación vigente) con el que "
                      "reconocer casos iguales. La corrección vale para este paciente.")
    prec = {"id_dictamen": rev.get("id_dictamen"), "id_paciente": pid, "usuario": rev.get("usuario"), "fecha": rev.get("fecha"),
            "motivo": rev.get("motivo")}
    patron = {"diagnostico": cie, "tipo_evento": tipo, "severidad": sev}
    existente = next((c for c in _estado()["actuales"].values() if c["patron"] == patron and c["efecto"]["categoria"] == cat
                      and c["estado"] in ("propuesto", "vigente")), None)
    if existente:
        if any(p.get("id_dictamen") == prec["id_dictamen"] and p.get("id_paciente") == pid for p in existente.get("precedentes") or []):
            return existente, f'El criterio {existente["id"]} ya incluye esta revisión.'
        c = _guardar({**existente, "evento": "precedente", "precedentes": list(existente.get("precedentes") or []) + [prec],
                      "usuario": rev.get("usuario"), "fecha": datos.ahora()})
        return c, f'Se suma como precedente al criterio local {c["id"]} ({c["estado"]}): ahora se basa en {len(c["precedentes"])} revisión(es).'
    texto = f'{perfil["lista_espera"].get("diagnostico_texto") or cie} con {TIPOS_LEGIBLES.get(tipo, tipo.replace("_", " "))} {sev} → prioridad {cat}'
    c = _guardar({"id": _nuevo_id(), "version": 1, "estado": "propuesto", "evento": "proponer", "patron": patron,
                  "efecto": {"tipo": "subir_a", "categoria": cat}, "texto": texto, "precedentes": [prec],
                  "propuesto_por": rev.get("usuario"), "resuelto_por": None, "vigente_desde": None, "vigente_hasta": None,
                  "motivo_resolucion": None, "usuario": rev.get("usuario"), "fecha": datos.ahora()})
    return c, (f'Se propuso el criterio local {c["id"]}: "{texto}". No cambia ninguna prioridad hasta que jefatura lo apruebe; '
               "mientras tanto, los pacientes que calzan quedan para revisión.")


def _sugerir_enmienda(pid, rev, dictamen):
    ide = ((dictamen or {}).get("disparador") or {}).get("id_evento") or ((dictamen or {}).get("evento_determinante") or {}).get("id_evento")
    if not ide:
        return None
    accion = "no_relacionado" if rev.get("motivo_codigo") == "evento_no_relacionado" else "anular"
    motivo = (rev.get("motivo") or "").strip()
    if len(motivo) < MIN_EXPLICACION:
        motivo = f'Revisión del especialista: {MOTIVOS_VEREDICTO[rev["motivo_codigo"]][0].lower()}'
    return {"accion": accion, "id_evento": ide, "metodo": "POST", "ruta": f"/pacientes/{pid}/eventos/{ide}/enmienda",
            "cuerpo": {"accion": accion, "motivo": motivo, "usuario": rev.get("usuario")},
            "texto": f'¿Confirmar la enmienda «{ACCIONES_ENMIENDA[accion]}» del evento {ide}? Cambia la prioridad de este paciente y queda registrada.'}


# ---------- resolver un criterio (jefatura) ----------
def resolver(cid, body):
    """POST /criterios-locales/{id}/resolver {accion: aprobar | rechazar | retirar, motivo (20+), usuario}."""
    import bitacora
    accion, motivo, usuario = body.get("accion"), (body.get("motivo") or "").strip(), (body.get("usuario") or "").strip()
    if accion not in RESOLUCIONES:
        return 400, {"error": f"accion debe ser una de {sorted(RESOLUCIONES)}"}
    if not usuario:
        return 400, {"error": "indique su nombre y cargo (jefatura): la resolución queda a su nombre"}
    if len(motivo) < MIN_EXPLICACION:
        return 400, {"error": f"explique la resolución (mínimo {MIN_EXPLICACION} caracteres)"}
    c = _estado()["actuales"].get(cid)
    if not c:
        return 404, {"error": f"no existe el criterio local {cid}"}
    desde, hacia = RESOLUCIONES[accion]
    if c["estado"] != desde:
        return 409, {"error": f"el criterio {cid} está {c['estado']}: solo se puede {accion} uno {desde}"}
    corte = datos.fecha_de(body)
    perfs = datos.perfiles_combinados()[0]
    cands = sorted(pid for pid, p in perfs.items() if puntaje.cie_base(p["lista_espera"]["diagnostico_cie10"]) == c["patron"]["diagnostico"])
    antes = bitacora.fotos(cands, corte)
    marca = datos.ahora()
    nuevo = {**c, "estado": hacia, "evento": accion, "resuelto_por": usuario, "rol": body.get("rol") or "jefatura",
             "motivo_resolucion": motivo, "usuario": usuario, "fecha": marca}
    if accion == "aprobar":
        nuevo.update(vigente_desde=corte.isoformat(), aprobado={"usuario": usuario, "fecha": marca})
    if accion == "retirar":
        nuevo["vigente_hasta"] = corte.isoformat()
    _guardar(nuevo)
    texto = f'criterio local {cid} v{c["version"]} {"aprobado" if accion == "aprobar" else "rechazado" if accion == "rechazar" else "retirado"} por {usuario}: {c["texto"]}'
    dics, afectados = [], []
    if accion == "aprobar":
        dics = bitacora.registrar_lote({pid: {"tipo": "criterio_local", "id_criterio": cid, "descripcion": texto} for pid in cands},
                                       corte, antes, canal="app", usuario=usuario, solo_si_cambia=True)
    elif accion == "retirar":
        # Quienes subió conservan su prioridad: retirar no puede bajar a nadie solo. Revisión automática a nombre de quien
        # retira (no cuenta como veredicto ni en la concordancia) y vuelven a la cola del especialista.
        afectados = [pid for pid, f in antes.items() if f and any(x["id"] == cid for x in f.get("criterios_locales") or [])]
        for pid in afectados:
            rv = {"accion": "ajustar", "categoria_ajustada": antes[pid]["categoria"], "categoria_sistema": antes[pid]["categoria_sistema"],
                  "motivo": MOTIVO_RETIRO, "fecha_corte": corte.isoformat(), "usuario": usuario, "fecha": datos.ahora(),
                  "automatica": True, "id_criterio": cid}
            datos.guardar({"id_paciente": pid, "sk": f"revision#{rv['fecha']}", "revision": json.dumps(rv, ensure_ascii=False)})
        dics = bitacora.registrar_lote({pid: {"tipo": "criterio_local", "id_criterio": cid, "requiere_revision": True,
                                              "descripcion": texto + " · conserva su prioridad hasta una revisión individual"} for pid in afectados},
                                       corte, antes, canal="app", usuario=usuario)
    return 200, {"criterio": publico(nuevo), "dictamenes": [bitacora.resumen(d) for d in dics], "pacientes_con_cambio": len(dics),
                 "conservan_prioridad": afectados, "capa_local": {"version": version_capa()}}


# ---------- enmiendas de eventos (§6.4) ----------
def post_enmienda(pid, ide, body):
    """Corrige un evento sin borrarlo: anular, no_relacionado o relacionado. Decisión humana sobre ESE paciente (puede
    bajarlo). Deja el ítem enmienda# (el perfil armado la aplica) y un dictamen."""
    import bitacora
    from evaluacion_ia import algoritmo_activo, evaluar_y_guardar
    from lista import fila_de
    perfil = datos.perfil_de(pid)
    if not perfil:
        return 404, {"error": "paciente no existe"}
    vigente = next((e for e in perfil.get("eventos_clinicos", []) if e.get("id_evento") == ide), None)
    anulado = next((e for e in perfil.get("eventos_anulados", []) if e.get("id_evento") == ide), None)
    ev = vigente or anulado
    if not ev:
        return 404, {"error": f"el evento {ide} no existe o no es de este paciente"}
    accion, motivo, usuario = body.get("accion"), (body.get("motivo") or "").strip(), (body.get("usuario") or "").strip()
    if accion not in ACCIONES_ENMIENDA:
        return 400, {"error": f"accion debe ser una de {sorted(ACCIONES_ENMIENDA)}"}
    if not usuario:
        return 400, {"error": "indique su nombre y cargo: la enmienda queda a su nombre"}
    if len(motivo) < MIN_EXPLICACION:
        return 400, {"error": f"explique la enmienda (mínimo {MIN_EXPLICACION} caracteres)"}
    if anulado:
        return 409, {"error": f"el evento {ide} ya está anulado"}
    corte = datos.fecha_de(body)
    antes = bitacora.fotos([pid], corte)
    en = {"id_evento": ide, "accion": accion, "motivo": motivo, "usuario": usuario, "fecha": datos.ahora()}
    datos.guardar({"id_paciente": pid, "sk": f"enmienda#{en['fecha']}", "enmienda": json.dumps(en, ensure_ascii=False)},
                  rev_vista=body.get("rev_vista"))
    evaluacion = None
    if algoritmo_activo() == "rubrica":
        try:
            evaluacion = evaluar_y_guardar(pid, corte)
        except Exception as e:   # si la IA falla, rigen las reglas: la enmienda no se pierde
            print(f"evaluación tras la enmienda {pid}: {type(e).__name__}: {e}")
    dic = bitacora.registrar(pid, corte, {"tipo": "enmienda", "id_evento": ide,
                                          "descripcion": f'enmienda «{ACCIONES_ENMIENDA[accion]}» del evento {ev.get("tipo_evento")} · '
                                                         f'{ev.get("subtipo")} ({ev.get("fecha_evento")})'},
                             antes.get(pid), canal="app", usuario=usuario, evaluacion=evaluacion)
    return 200, {"id_paciente": pid, "enmienda": en, "dictamen": dic, "paciente": fila_de(pid, corte)}


# ---------- indicadores (§6.5) ----------
def _grupo(clave, vs):
    a = sum(v["veredicto"] == "adecuada" for v in vs)
    return {**clave, "n": len(vs), "adecuadas": a, "incorrectas": len(vs) - a, "pct_adecuadas": round(100 * a / len(vs)) if vs else None}


def resumen(especialidad=None):
    """GET /aprendizaje: concordancia (global, por diagnóstico, por patrón, por regla; siempre con su n), criterios locales,
    precedentes recientes y reglas a validar."""
    from indicadores import N_KAPPA_RECOMENDADO, _kappa
    perfs = datos.perfiles_combinados()[0]
    def de_esp(pid):
        return not especialidad or (perfs.get(pid) or {}).get("lista_espera", {}).get("especialidad") == especialidad
    vs = [v for v in veredictos() if de_esp(v["id_paciente"])]
    pares = [(v["categoria_sistema"], v.get("categoria_final") or v["categoria_sistema"]) for v in vs if v.get("categoria_sistema")]
    por = {"diagnostico": {}, "patron": {}, "regla": {}}
    for v in vs:
        por["patron"].setdefault(v.get("patron") or "?", []).append(v)
        por["diagnostico"].setdefault((v.get("patron") or "?").split("|")[0], []).append(v)
        r = v.get("regla") or {}
        por["regla"].setdefault((r.get("factor") or "sin_regla", r.get("fuente") or ""), []).append(v)
    orden = lambda g: (-g["n"], g.get("diagnostico") or g.get("patron") or g.get("factor"))
    objeciones = {}
    for v in vs:
        if v.get("motivo_codigo") == "criterio_no_aplica":
            r = v.get("regla_objetada") or {}
            objeciones.setdefault((r.get("factor"), r.get("fuente")), []).append(v)
    criterios = [{**publico(c), "historial": [{k: h.get(k) for k in ("evento", "estado", "usuario", "fecha", "motivo_resolucion")}
                                                for h in _estado()["historial"][c["id"]]]}
                 for c in sorted(_estado()["actuales"].values(), key=lambda c: c["id"])
                 if not especialidad or any(de_esp(p.get("id_paciente")) for p in c.get("precedentes") or [])]
    return {"especialidad": especialidad,
            "concordancia": {"global": {**_grupo({}, vs), "kappa": _kappa(pares), "n_kappa": len(pares), "meta_kappa": 0.70,
                                        "n_recomendado": N_KAPPA_RECOMENDADO, "suficiente": len(pares) >= N_KAPPA_RECOMENDADO},
                             "por_diagnostico": sorted((_grupo({"diagnostico": k}, g) for k, g in por["diagnostico"].items()), key=orden),
                             "por_patron": sorted((_grupo({"patron": k}, g) for k, g in por["patron"].items()), key=orden),
                             "por_regla": sorted((_grupo({"factor": k[0], "fuente": k[1]}, g) for k, g in por["regla"].items()), key=orden)},
            "criterios_locales": criterios,
            "precedentes_recientes": [{k: v.get(k) for k in ("id_paciente", "patron", "veredicto", "motivo_codigo", "motivo", "usuario", "fecha",
                                                              "id_dictamen", "categoria_sistema", "categoria_final")}
                                      for v in sorted(vs, key=lambda v: v.get("fecha") or "", reverse=True)[:20]],
            "reglas_a_validar": sorted(({"factor": k[0], "fuente": k[1], "valor": g[-1].get("regla_objetada", {}).get("valor"),
                                         "objeciones": len(g), "especialistas": len({v.get("usuario") for v in g}),
                                         "pacientes": sorted({v["id_paciente"] for v in g})} for k, g in objeciones.items()),
                                       key=lambda x: (-x["especialistas"], -x["objeciones"])),
            "capa_local": {"version": version_capa()}}


# ---------- rutas ----------
def rutear(method, partes, qs, body):
    """GET /aprendizaje · GET /criterios-locales · POST /criterios-locales/{id}/resolver ·
    POST /pacientes/{id}/eventos/{id_evento}/enmienda. None si la ruta no es de este módulo."""
    qs, body = qs or {}, body or {}
    if method == "GET" and partes == ["aprendizaje"]:
        return 200, resumen(qs.get("especialidad") or None)
    if method == "GET" and partes == ["criterios-locales"]:
        cs = [publico(c) for c in sorted(_estado()["actuales"].values(), key=lambda c: c["id"])
              if not qs.get("estado") or c["estado"] == qs["estado"]]
        return 200, {"criterios": cs, "capa_local": {"version": version_capa()}}
    if method == "POST" and len(partes) == 3 and partes[0] == "criterios-locales" and partes[2] == "resolver":
        return resolver(partes[1], body)
    if method == "POST" and len(partes) == 5 and partes[0] == "pacientes" and partes[2] == "eventos" and partes[4] == "enmienda":
        return post_enmienda(partes[1], partes[3], body)
    return None
