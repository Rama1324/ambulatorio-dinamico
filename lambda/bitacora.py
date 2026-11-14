"""Bitácora de decisiones: un dictamen por cada vez que el sistema evalúa a un paciente por un disparador
(evento, ingreso, novedad, informe, carga, criterio local, enmienda…). Contrato: docs/diseno/ESPECIFICACION_MVP.md §5.

El dictamen documenta qué se usó (antecedentes con su firma, fuentes y versiones del conocimiento, criterios locales,
precedentes de los especialistas y, si la hubo, la evaluación de la IA), el resultado antes/después y el fundamento con su
explicación en lenguaje simple (plantilla, sin IA). Solo se agrega: sk = dictamen#<ts>. El veredicto del especialista vive
en la revision# que lo cita (id_dictamen) y se une al leerlo.

La carga inicial del registro no crea dictámenes (es la "foto"): nacen con lo que llega después.
"""
import json
import uuid

import aprendizaje
import base_conocimiento
import datos
import puntaje
import rubrica

ORDEN = puntaje.ORDEN_CAT
CAMBIOS = ("sube", "baja", "igual", "ingresa", "sale")
ESTADOS = ("pendiente", "revisada", "todas")
# Qué razón explica mejor la prioridad (la "fuente que más pesó"), en este orden
PESO = ("urgencia", "criterio_local", "tabla_oficial", "oncologico", "criterio_clinico", "combinacion", "criterio_registro", "piso",
        "riesgo_vital", "medicion")
MOTIVO_SALIDA = {"fallecido": "fallecimiento (causal de egreso 9)", "atendido": "atendido en consulta de especialidad",
                 "datos_invalidos": "registro con datos inválidos"}


# ---------- estado de la lista: una lista por especialidad, no una por paciente ----------
def _listas(pids, corte):
    """{pid: (fila | None, total de su especialidad, exclusión | None)}. Una carga puede tocar cientos de pacientes: se
    calcula una lista por especialidad."""
    from lista import lista
    por_esp, out = {}, {}
    for pid in dict.fromkeys(pids):
        p = datos.perfil_de(pid)
        por_esp.setdefault(p and p["lista_espera"].get("especialidad"), []).append(pid)
    for esp, ps in por_esp.items():
        if esp is None:
            out.update({pid: (None, 0, None) for pid in ps})
            continue
        d = lista(corte, esp)
        filas, exc = {p["id_paciente"]: p for p in d["pacientes"]}, {e["id_paciente"]: e for e in d["excluidos"]}
        out.update({pid: (filas.get(pid), d["total"], exc.get(pid)) for pid in ps})
    return out


def fotos(pids, corte):
    """Estado de cada paciente en la lista ANTES del cambio: {id_paciente: fila | None}. Una lista por especialidad."""
    return {pid: x[0] for pid, x in _listas(pids, corte).items()}


# ---------- armar el dictamen ----------
def _cambio(antes, despues):
    a, d = antes and antes.get("categoria"), despues and despues.get("categoria")
    if not a and not d:
        return "igual"
    if not a:
        return "ingresa"
    if not d:
        return "sale"
    return "sube" if ORDEN[d] > ORDEN[a] else "baja" if ORDEN[d] < ORDEN[a] else "igual"


def _resultado(antes, fila, total, ev, disparador):
    a, f = antes or {}, fila or {}
    rv, urg = bool(f.get("riesgo_vital")), bool(f.get("urgencia_hoy"))
    requiere = bool(disparador.get("requiere_revision") or (ev or {}).get("requiere_revision") or f.get("criterios_propuestos")
                    or any(r.get("sin_regla") for r in f.get("razones") or [])
                    or (f.get("gestion") or {}).get("estado") == "pendiente_revision")
    return {"categoria_antes": a.get("categoria"), "categoria": f.get("categoria"), "cambio": _cambio(antes, fila),
            "riesgo_vital": rv, "urgencia_hoy": urg, "estado_clinico": f.get("estado_clinico"),
            "posicion_antes": a.get("posicion"), "posicion": f.get("posicion"), "total": total,
            "alerta_nueva": (rv and not a.get("riesgo_vital")) or (urg and not a.get("urgencia_hoy")),
            "requiere_revision": requiere}


def _fundamento(fila, exc):
    if fila:
        return [dict(r) for r in fila.get("razones") or []]
    if exc:
        return [{"factor": "evento", "valor": f'sale de la lista: {MOTIVO_SALIDA.get(exc["motivo"], exc["motivo"])}'
                                              + (f' ({exc["fecha"]})' if exc.get("fecha") else ""),
                 "fuente": "Manual de Gestión de la Demanda SSMSO 2025, Anexo 4: causales de egreso"}]
    return []


def _principal(fundamento):
    for factor in PESO:
        for r in fundamento:
            if r.get("factor") == factor and not r.get("sin_regla") and "(no supera" not in str(r.get("valor")):
                return r
    return next((r for r in fundamento if r.get("sin_regla")), None) or next((r for r in fundamento if r.get("factor") == "prioridad_inicial"), None)


def _sin_flecha(v):
    return str(v or "").split(" → ")[0]


def explicacion(resultado, fundamento, disparador, especialidad=None):
    """Texto corto en lenguaje simple, armado SOLO con el resultado y el fundamento (sin IA: reproducible y siempre
    disponible). Dice qué cambió, por qué y la fuente que más pesó."""
    r, p = resultado, _principal(fundamento)
    por = f'{_sin_flecha(p["valor"])} (fuente: {p["fuente"]})' if p else "no hubo una regla con fuente que la cambie"
    a, d = r["categoria_antes"], r["categoria"]
    if r["cambio"] == "sube":
        txt = f"Subió de prioridad {a} a {d} por: {por}."
    elif r["cambio"] == "baja":
        txt = f'Bajó de prioridad {a} a {d} por una decisión registrada por una persona ({disparador.get("descripcion") or disparador.get("tipo")}).'
    elif r["cambio"] == "ingresa":
        txt = f"Ingresa a la lista con prioridad {d}" + (f" por: {por}." if p and p.get("factor") != "prioridad_inicial" else
                                                        " (la asignada por el especialista al priorizar la interconsulta).")
    elif r["cambio"] == "sale":
        txt = f"Sale de la lista: {_sin_flecha(fundamento[0]['valor']).replace('sale de la lista: ', '')}." if fundamento else "Ya no está en la lista a esta fecha."
    elif p and p.get("sin_regla"):
        txt = f"Se mantiene en prioridad {d}: {p['valor']}."
    elif d:
        txt = f"Se mantiene en prioridad {d}" + (f": {por}." if p and p.get("factor") != "prioridad_inicial" else
                                                 ": el evento no cambia la prioridad según los criterios con fuente.")
    else:
        txt = "El paciente no está en la lista a esta fecha."
    if r.get("posicion") and r.get("posicion_antes") and r["posicion"] != r["posicion_antes"]:
        txt += f' Puesto {r["posicion_antes"]} → {r["posicion"]} de {r["total"]}' + (f" en {especialidad}." if especialidad else ".")
    if r.get("alerta_nueva"):
        txt += (" Abre una alerta de descompensación grave: el médico debe evaluarla dentro de 72 horas." if r["riesgo_vital"]
                else " Abre una alerta de urgencia: contactar hoy.")
    if r.get("requiere_revision"):
        txt += " Queda para revisión del especialista."
    return txt


def _citados(perfil, corte, disparador, det):
    """Los registros concretos que sostienen la decisión: el evento determinante, el que la disparó y la estabilización
    posterior, si la hay."""
    eventos = {e.get("id_evento"): e for e in perfil.get("eventos_clinicos", []) + perfil.get("eventos_anulados", [])}
    _, _, estab, estado = puntaje.linea_clinica(perfil, corte)
    out = []
    for rol, e in (("determinante", eventos.get((det or {}).get("id_evento"))), ("disparador", eventos.get(disparador.get("id_evento"))),
                   ("estabilizacion", estab if estado == "estabilizado" else None)):
        if e and not any(x["id_evento"] == e.get("id_evento") for x in out):
            out.append({"id_evento": e.get("id_evento"), "fecha": e.get("fecha_evento"), "tipo": e.get("tipo_evento"), "valor": e.get("subtipo"),
                        "severidad": e.get("severidad"), "rol": rol, **({"anulado": True} if "anulado" in e else {})})
    return out


def _antecedentes(perfil, corte, disparador, det):
    """Lo mismo que ve la IA (rubrica.historial), contado, con su firma y el período."""
    h = rubrica.historial(perfil, corte)
    fechas = [x["fecha"] for x in h["eventos"] + h["mediciones"]]
    return {"firma": rubrica.firma(perfil, corte), "eventos": len(h["eventos"]), "mediciones": len(h["mediciones"]),
            "comorbilidades": len(h["comorbilidades"]), "desde": min(fechas) if fechas else h["fecha_ingreso_lista"],
            "hasta": corte.isoformat(), "citados": _citados(perfil, corte, disparador, det)}


def _ia(ev):
    if not ev:
        return None
    return {"modelo": ev.get("modelo"), "version_rubrica": ev.get("version_rubrica"), "version_kb": ev.get("version_kb"),
            "huella_kb": ev.get("huella_kb"), "hash_prompt": ev.get("hash_prompt"), "lecturas": len(ev.get("lecturas") or []),
            "tokens_entrada": ev.get("tokens_entrada"), "tokens_salida": ev.get("tokens_salida"), "latencia_s": ev.get("latencia_s"),
            "controles": ev.get("controles") or [], "categoria_rubrica": ev.get("categoria_rubrica"),
            "categoria_reglas": ev.get("categoria_reglas"), "respaldo_reglas": bool(ev.get("respaldo_reglas")),
            "id_evaluacion": f'evaluacion#{ev.get("fecha")}'}


def _nuevo_id(fecha):
    return "DIC-" + fecha[:19].replace("-", "").replace(":", "") + "-" + uuid.uuid4().hex[:4].upper()


def armar(pid, corte, disparador, antes, fila, total, exc, *, canal="app", usuario=None, id_lote=None, evaluacion=None, vs=None,
          paquete=None):
    """Dictamen de un paciente (sin guardarlo). antes/fila: filas de la lista de su especialidad antes y después."""
    perfil = datos.perfil_de(pid)
    if not perfil:
        return None
    fecha = datos.ahora()
    motor = ("reglas_respaldo" if evaluacion.get("respaldo_reglas") else "ia_rubrica") if evaluacion else "reglas"
    det = puntaje.evento_determinante(perfil, corte)
    patron = aprendizaje.patron_de(perfil, corte, det)
    fundamento = _fundamento(fila, exc)
    resultado = _resultado(antes, fila, total, evaluacion, disparador)
    paq = paquete or base_conocimiento.paquete()
    esp = perfil["lista_espera"].get("especialidad")
    disp = {"tipo": disparador.get("tipo"), "canal": canal, "id_evento": disparador.get("id_evento"),
            "descripcion": disparador.get("descripcion"), "id_lote": id_lote, "usuario": usuario,
            **{k: v for k, v in disparador.items() if k not in ("tipo", "id_evento", "descripcion", "requiere_revision")}}
    return {
        "id_dictamen": _nuevo_id(fecha), "id_paciente": pid, "fecha": fecha, "fecha_corte": corte.isoformat(), "especialidad": esp,
        "disparador": disp, "motor": motor, "resultado": resultado, "fundamento": fundamento,
        "explicacion": explicacion(resultado, fundamento, disp, esp),
        "patron": patron, "evento_determinante": det,
        "informacion_utilizada": {
            "antecedentes": _antecedentes(perfil, corte, disparador, det),
            "conocimiento": {"paquete": {"etiqueta": paq.get("etiqueta"), "huella": paq.get("huella"), "integro": paq.get("integro"),
                                         "motor": (paq.get("motor") or {}).get("huella")},
                             "fuentes": base_conocimiento.fuentes_de(fundamento, motor),
                             "criterios_locales": [{"id": c["id"], "version": c["version"]} for c in (fila or {}).get("criterios_locales") or []],
                             "criterios_propuestos": [{"id": c["id"], "version": c["version"]} for c in (fila or {}).get("criterios_propuestos") or []],
                             "capa_local": {"version": aprendizaje.version_capa()}},
            "precedentes": aprendizaje.precedentes(patron, vs),
            "ia": _ia(evaluacion)},
        "revision": None,
    }


def guardar_dictamen(d):
    """Solo se agrega: sk = dictamen#<ts>#<id> (el id evita choques si dos dictámenes del paciente caen en el mismo instante)."""
    datos.guardar({"id_paciente": d["id_paciente"], "sk": f'dictamen#{d["fecha"]}#{d["id_dictamen"]}',
                   "dictamen": json.dumps({**d, "revision": None}, ensure_ascii=False, default=str)})
    return d


def registrar_lote(disparadores, corte, antes, *, canal="app", usuario=None, id_lote=None, evaluaciones=None, solo_si_cambia=False):
    """Arma y guarda un dictamen por paciente. disparadores: {id_paciente: {tipo, id_evento?, descripcion, requiere_revision?}}.
    antes: lo que devolvió fotos(). evaluaciones: {id_paciente: evaluación de la IA de este disparador}.
    solo_si_cambia: solo para quienes cambiaron de prioridad o de alerta (aprobar un criterio local). Devuelve los dictámenes."""
    if not disparadores:
        return []
    antes, evaluaciones = antes or {}, evaluaciones or {}
    despues = _listas(list(disparadores), corte)
    vs, paq, hechos = aprendizaje.veredictos(), base_conocimiento.paquete(), []
    for pid, disp in disparadores.items():
        fila, total, exc = despues[pid]
        prev = antes.get(pid)
        if solo_si_cambia and _cambio(prev, fila) == "igual" and bool((prev or {}).get("riesgo_vital")) == bool((fila or {}).get("riesgo_vital")) \
                and not disp.get("requiere_revision"):
            continue
        d = armar(pid, corte, disp, prev, fila, total, exc, canal=canal, usuario=usuario, id_lote=id_lote,
                  evaluacion=evaluaciones.get(pid), vs=vs, paquete=paq)
        if d:
            hechos.append(guardar_dictamen(d))
    return hechos


def registrar(pid, corte, disparador, antes, **kw):
    """Atajo de un paciente (antes = su fila previa o None)."""
    evaluacion = kw.pop("evaluacion", None)
    if evaluacion is not None:
        kw["evaluaciones"] = {pid: evaluacion}
    hechos = registrar_lote({pid: disparador}, corte, {pid: antes}, **kw)
    return hechos[0] if hechos else None


def revision_directa(pid, corte, usuario=None):
    """Dictamen con el estado vigente para un paciente que el especialista revisa sin que haya una decisión registrada
    (se guarda después de la revisión, con guardar_dictamen)."""
    fila, total, exc = _listas([pid], corte)[pid]
    return armar(pid, corte, {"tipo": "revision_directa", "descripcion": "revisión del especialista sin una decisión previa registrada"},
                 fila, fila, total, exc, canal="app", usuario=usuario)


# ---------- lectura ----------
def _leer(it):
    try:
        return json.loads(it["dictamen"])
    except (KeyError, TypeError, ValueError):
        return None


def _revisiones(pid=None):
    """(revisión por id_dictamen, última revisión no automática por paciente)."""
    por_dic, ultima = {}, {}
    for it in datos.registros_tipo("revision#", pid):
        try:
            r = json.loads(it["revision"])
        except (KeyError, TypeError, ValueError):
            continue
        if r.get("id_dictamen"):
            por_dic[r["id_dictamen"]] = r
        if not r.get("automatica"):
            ultima[it["id_paciente"]] = r
    return por_dic, ultima


def necesita_revision(d, rev_dictamen=None, ultima=None):
    """Dictamen sin veredicto y sin revisión posterior del paciente, que cambió la prioridad, abrió una alerta o trae
    requiere_revision (§5)."""
    if rev_dictamen or (ultima and (ultima.get("id_dictamen") == d["id_dictamen"] or (ultima.get("fecha") or "") >= d["fecha"])):
        return False
    r = d.get("resultado") or {}
    return r.get("cambio") in ("sube", "baja") or bool(r.get("alerta_nueva")) or bool(r.get("requiere_revision"))


def _con_revision(d, por_dic, ultima):
    rv = por_dic.get(d["id_dictamen"])
    return {**d, "revision": rv, "necesita_revision": necesita_revision(d, rv, ultima.get(d["id_paciente"]))}


def de_paciente(pid):
    """Dictámenes del paciente, el más reciente primero, cada uno con su revisión (veredicto) unida."""
    por_dic, ultima = _revisiones(pid)
    ds = [d for d in (_leer(it) for it in datos.registros_tipo("dictamen#", pid)) if d]
    return [_con_revision(d, por_dic, ultima) for d in reversed(ds)]


def ultimo(pid):
    """El último dictamen del paciente (sin revisión unida) o None."""
    its = datos.registros_tipo("dictamen#", pid)
    return _leer(its[-1]) if its else None


def dictamen_de(pid, id_dictamen):
    return next((d for d in (_leer(it) for it in datos.registros_tipo("dictamen#", pid)) if d and d["id_dictamen"] == id_dictamen), None)


def resumen(d, necesita=None):
    """Lo que va en las respuestas de ingesta y de resolver: id, fecha, cambio, motor, explicación y si necesita revisión."""
    r = d.get("resultado") or {}
    return {"id_dictamen": d["id_dictamen"], "id_paciente": d["id_paciente"], "fecha": d["fecha"], "cambio": r.get("cambio"),
            "categoria_antes": r.get("categoria_antes"), "categoria": r.get("categoria"), "motor": d.get("motor"),
            "disparador": (d.get("disparador") or {}).get("tipo"), "explicacion": d.get("explicacion"),
            "necesita_revision": necesita_revision(d) if necesita is None else necesita}


def resumenes(revs):
    """{pid: resumen corto del último dictamen} para las filas de la lista (§5: id_dictamen, fecha, cambio, motor,
    necesita_revision). revs: última revisión por paciente (la de la lista). Usa el índice de la copia en memoria
    (último dictamen por paciente), sin recorrer los ítems de cada uno."""
    out = {}
    for pid, d in datos.almacen().ultimos("dictamen#", "dictamen").items():
        rv = revs.get(pid)
        out[pid] = {"id_dictamen": d["id_dictamen"], "fecha": d["fecha"], "cambio": (d.get("resultado") or {}).get("cambio"),
                    "motor": d.get("motor"), "necesita_revision": necesita_revision(d, None, None if (rv or {}).get("automatica") else rv)}
    return out


def buscar(especialidad=None, estado="pendiente", limite=50, desde=None):
    """Dictámenes de la cola de revisión: estado = pendiente | revisada | todas. Pendientes: primero las alertas nuevas,
    luego los patrones con más desacuerdo histórico de los especialistas, luego los más recientes."""
    por_dic, ultima = _revisiones()
    ds = []
    for it in datos.registros_tipo("dictamen#"):
        d = _leer(it)
        if not d or (especialidad and d.get("especialidad") != especialidad) or (desde and d["fecha"] < desde):
            continue
        d = _con_revision(d, por_dic, ultima)
        revisada = bool(d["revision"]) or not d["necesita_revision"] and bool((ultima.get(d["id_paciente"]) or {}).get("fecha", "") >= d["fecha"])
        if estado == "pendiente" and not d["necesita_revision"] or estado == "revisada" and not revisada:
            continue
        ds.append(d)
    if estado == "pendiente":
        vs = aprendizaje.veredictos()
        cache = {}
        def clave(d):
            p = d.get("patron")
            if p not in cache:
                cache[p] = aprendizaje.desacuerdo(p, vs)
            frac, n = cache[p]
            return (not d["resultado"].get("alerta_nueva"), -frac, -n, _invertir(d["fecha"]))
        ds.sort(key=clave)
    else:
        ds.sort(key=lambda d: d["fecha"], reverse=True)
    return ds[:max(1, int(limite or 50))]


def _invertir(s):
    """Para ordenar una fecha ISO de más reciente a más antigua dentro de una clave ascendente."""
    return [-ord(c) for c in s]


# ---------- rutas ----------
def rutear(method, partes, qs, body):
    """GET /decisiones?especialidad=&estado=pendiente|revisada|todas&limite=&desde= · GET /decisiones/{id_dictamen} ·
    GET /pacientes/{id}/decisiones. None si la ruta no es de este módulo."""
    qs = qs or {}
    if method != "GET":
        return None
    if partes == ["decisiones"]:
        estado = qs.get("estado") or "pendiente"
        if estado not in ESTADOS:
            return 400, {"error": f"estado debe ser uno de {list(ESTADOS)}"}
        try:
            limite = int(qs.get("limite") or 50)
        except ValueError:
            return 400, {"error": "limite debe ser un número"}
        ds = buscar(qs.get("especialidad") or None, estado, limite, qs.get("desde") or None)
        return 200, {"estado": estado, "total": len(ds), "decisiones": ds}
    if len(partes) == 2 and partes[0] == "decisiones":
        por_dic, ultima = _revisiones()
        d = next((d for d in (_leer(it) for it in datos.registros_tipo("dictamen#")) if d and d["id_dictamen"] == partes[1]), None)
        return (200, _con_revision(d, por_dic, ultima)) if d else (404, {"error": f"no existe la decisión {partes[1]}"})
    if len(partes) == 3 and partes[0] == "pacientes" and partes[2] == "decisiones":
        if not datos.perfil_de(partes[1]):
            return 404, {"error": "paciente no existe"}
        return 200, {"id_paciente": partes[1], "decisiones": de_paciente(partes[1])}
    return None
