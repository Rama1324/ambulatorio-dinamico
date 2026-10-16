"""La lista priorizada: puntaje de reglas (+ rúbrica si está activa), revisión del equipo, ajustes manuales y gestión."""
from datetime import date, timedelta

import explicar
import puntaje
import vecinos
from catalogo import ESTADOS_GESTION, MOTIVOS_PENDIENTE
from datos import (REGISTRO_AL, posterior, ajustes_orden, contactos, decisiones, evaluaciones_por_paciente, gestiones, hoy,
                   perfiles_combinados)
from evaluacion_ia import _aplicar_rubrica, algoritmo_activo


def _enriquecer(r, perfil, revision, pos_ant, corte=None, contacto=None, decision=None, ajuste=None):
    pac, le = perfil["paciente"], perfil["lista_espera"]
    corte_iso = (corte or hoy()).isoformat()
    out = {
        "id_paciente": r["id_paciente"],
        "nombre_fantasia": pac["nombre_fantasia"],
        "rut": pac.get("rut"),
        "edad": pac["edad"],
        "sexo": pac["sexo"],
        "comuna": pac["comuna"],
        "prevision": pac.get("prevision"),
        "comorbilidades": pac.get("comorbilidades", []),
        "especialidad": le["especialidad"],
        "diagnostico_cie10": le["diagnostico_cie10"],
        "diagnostico_texto": le["diagnostico_texto"],
        "prioridad_inicial": le["prioridad_inicial"],
        "puntaje_inicial": r.get("puntaje_inicial"),
        "prioridad_propuesta": r.get("prioridad_propuesta"),
        "puntaje_propuesto": r.get("puntaje_propuesto"),
        "estado_evaluacion": r.get("estado_evaluacion"),
        "fecha_ingreso_lista": le["fecha_ingreso_lista"],
        "dias_espera": r["dias_espera"],
        "categoria": r["categoria"],
        "categoria_sistema": r["categoria"],
        "estado_clinico": r["estado_clinico"],
        "riesgo_vital": r["riesgo_vital"],
        "urgencia_hoy": bool(r.get("urgencia_hoy")),
        "agudeza": r.get("agudeza", 0),
        "letalidad": r.get("letalidad", 9),
        "plazo_dias": r.get("plazo_dias"),
        "plazo_vencido": bool(r.get("plazo_vencido")),
        "lace": r["lace"],
        "antiguedad_mayor_1_anio": r["antiguedad_mayor_1_anio"],
        "ges": r["ges"],
        "medicion_alerta": r["medicion_alerta"],
        "posicion": r.get("posicion"),
        "posicion_anterior": pos_ant,
        "riesgo_inasistencia": r["riesgo_inasistencia"],
        "no_shows": r["no_shows"],
        "grupo_proteccion": r.get("grupo_proteccion"),
        "acg": r.get("acg"),
        "razones": r["razones"],
        "explicacion_ia": None,
        "estado_revision": "pendiente",
        "revision_sugerida": [],
        "contactar_hoy": r["riesgo_vital"] or bool(r.get("urgencia_hoy")),
        "contacto": None,
        "decision": None,
        "evaluacion": None,
    }
    senales = r.get("senales", [])
    # Una revisión vale solo para lo que el equipo vio: desde la fecha de corte en que revisó y hasta que llegue
    # un evento nuevo. Un evento posterior invalida la confirmación o el ajuste y vuelve a pedir revisión.
    if revision and revision.get("fecha_corte", "0000") <= corte_iso:
        nuevas = [s for s in senales if not s.get("informativa") and posterior(s, revision.get("fecha_corte", ""), revision.get("fecha", ""))]
        out["revision"] = revision
        if nuevas:
            out["estado_revision"] = "requiere_revision"
            out["revision_sugerida"] = nuevas
            out["revision_vencida_por"] = nuevas[-1]["motivo"]
            ajustada = revision.get("categoria_ajustada")
            if ajustada and all(s.get("algoritmo") for s in nuevas) and puntaje.ORDEN_CAT[ajustada] > puntaje.ORDEN_CAT[out["categoria"]]:
                out["categoria"] = ajustada  # el algoritmo subió al paciente, pero el equipo lo tenía más arriba: no baja sin humano
        else:
            out["estado_revision"] = "ajustado" if revision["accion"] == "ajustar" else "confirmado"
            if revision.get("categoria_ajustada"):
                out["categoria"] = revision["categoria_ajustada"]  # el equipo clínico decide
    else:
        out["revision_sugerida"] = senales
    # Descompensación grave: la PRIORIDAD debe revisarla el especialista (la lista ya se recalculó al instante).
    # La alerta se cierra solo con una revisión del especialista: decisión clínica, confirmar/ajustar la prioridad
    # o un ajuste manual de la posición, registrados después del evento. Llamar o citar no la cierran.
    def cierra_alerta(x):
        return bool(x) and x.get("fecha_corte", "0000") <= corte_iso and \
            x["fecha_corte"] >= (r.get("fecha_descompensacion") or "") and x["fecha"] >= (r.get("registro_descompensacion") or "")
    # Urgencia ("derivar hoy"): sale del carril cuando el especialista registra una decisión, una revisión o un ajuste
    # DESPUÉS de la urgencia. Sigue en prioridad alta (no baja); solo deja de estar primero y de pedir contacto hoy.
    if r.get("urgencia_hoy") and r.get("urgencia_desde"):
        u = r["urgencia_desde"]
        def tras_urgencia(x):
            return bool(x) and u["fecha"] <= x.get("fecha_corte", "0000") <= corte_iso and x["fecha"] >= (u.get("registrado") or "")
        quien = next(((n, x) for n, x in (("decision", decision), ("revision", revision), ("ajuste_manual", ajuste)) if tras_urgencia(x)), None)
        if quien:
            out["urgencia_hoy"] = False
            out["urgencia_cerrada"] = {"por": quien[0], "fecha": quien[1]["fecha"], "responsable": quien[1].get("responsable") or quien[1].get("usuario")}
            out["contactar_hoy"] = r["riesgo_vital"]
    if contacto and contacto.get("fecha_corte", "0000") <= corte_iso:
        out["contacto"] = contacto
    if decision and decision.get("fecha_corte", "0000") <= corte_iso:
        out["decision"] = decision
    cierre = None
    if r["riesgo_vital"]:
        if cierra_alerta(decision):
            cierre = {"por": "decision", "texto": decision["texto"], "responsable": decision["responsable"], "fecha": decision["fecha"]}
        elif cierra_alerta(revision):
            cierre = {"por": "revision", "texto": "prioridad revisada por el especialista", "responsable": revision.get("usuario"),
                      "fecha": revision["fecha"]}
        elif cierra_alerta(ajuste):
            cierre = {"por": "ajuste_manual", "texto": f'posición ajustada a mano: {ajuste["motivo_texto"]}', "responsable": ajuste.get("usuario"),
                      "fecha": ajuste["fecha"]}
        dias = r.get("dias_desde_descompensacion") or 0
        # Desde cuándo está en el sistema (dato informativo, sin plazo): fecha de registro en la app o, para el registro
        # cargado, la fecha de los datos. En simulación histórica, desde el evento.
        llegada = (r.get("registro_descompensacion") or "")[:10] or (
            REGISTRO_AL if corte_iso >= REGISTRO_AL else r.get("fecha_descompensacion"))
        llegada = max(llegada or corte_iso, r.get("fecha_descompensacion") or llegada or corte_iso)
        en_revision = max(0, (date.fromisoformat(corte_iso) - date.fromisoformat(llegada)).days)
        out["evaluacion"] = {"estado": "evaluada" if cierre else "pendiente",
                             "dias_desde_evento": dias, "fecha_evento": r.get("fecha_descompensacion"), "llego_al_sistema": llegada,
                             "dias_en_revision": en_revision, "cierre": cierre}
        out["contactar_hoy"] = not cierre or out["urgencia_hoy"]
    # ya se contactó después del evento (citado o derivado a urgencia): no se vuelve a pedir contactar hoy
    if out["contactar_hoy"] and contacto and contacto.get("resultado") in ("citado", "derivado_urgencia") and             contacto.get("fecha_corte", "0000") <= corte_iso and contacto["fecha_corte"] >= (r.get("fecha_descompensacion") or "") and             contacto["fecha"] >= (r.get("registro_descompensacion") or "") and             (not r.get("urgencia_desde") or contacto["fecha"] >= (r["urgencia_desde"].get("registrado") or "")):
        out["contactar_hoy"] = False
        out["contactado"] = {"resultado": contacto["resultado"], "texto": contacto["texto"], "fecha": contacto["fecha"], "usuario": contacto.get("usuario")}
    return out


def _gestion(p, g, corte):
    """Estado de gestión calculado con lo registrado + responsable, próxima acción y seguimiento asignados por el equipo."""
    c = p.get("contacto") or {}
    g = g if g and g.get("fecha_corte", "0000") <= corte.isoformat() else {}
    # el paciente pidió revisión humana y ningún especialista ha revisado desde entonces (Ley 21.719, art. 8 bis)
    pide_humano = g.get("motivo_pendiente") == "revision_humana" and not ((p.get("revision") or {}).get("fecha", "") >= g.get("fecha", ""))
    if pide_humano:
        estado = "pendiente_revision"
    elif c.get("resultado") == "citado":
        estado = "cita_reservada"
    elif p["estado_revision"] == "requiere_revision" or p.get("ajuste_manual_vencido") or (p.get("rubrica") or {}).get("requiere_revision"):
        # Solo lo que el sistema no puede resolver solo: un evento nuevo contradice lo que decidió una persona, o la
        # evidencia sugiere BAJAR (eso nunca lo hace el sistema). Lo que el sistema sube ya rige: no espera a nadie.
        estado = "pendiente_revision"
    elif c.get("resultado") == "no_contesta":
        estado = "pendiente_contacto"
    else:
        estado = "pendiente_cita"
    seguimiento = g.get("seguimiento")
    accion = ESTADOS_GESTION[estado][1]
    if pide_humano:
        accion = "El paciente pidió revisión humana: el especialista revisa y confirma o cambia la prioridad"
    elif estado == "pendiente_cita" and p.get("contactar_hoy"):
        accion = "Contactar hoy y citar con prioridad"
    elif estado == "pendiente_cita" and p["categoria"] != p["prioridad_inicial"]:
        accion = "Citar con la nueva prioridad"
    return {"estado": estado, "texto": ESTADOS_GESTION[estado][0],
            "proxima_accion": g.get("proxima_accion") or accion, "accion_asignada": bool(g.get("proxima_accion")),
            "responsable": g.get("responsable"), "seguimiento": seguimiento,
            "seguimiento_vencido": bool(seguimiento and seguimiento < corte.isoformat()),
            "motivo_pendiente": g.get("motivo_pendiente"), "motivo_texto": MOTIVOS_PENDIENTE.get(g.get("motivo_pendiente")),
            "nota": g.get("nota"), "actualizado_por": g.get("usuario"), "actualizado": g.get("fecha")}


def _aplicar_ajustes(pacientes, senales, corte):
    """Mueve a mano a los pacientes con ajuste vigente, en el orden en que se registraron los ajustes.
    La posición pedida es dentro de la lista de su especialidad, así la lista general y la filtrada coinciden.
    Un evento clínico posterior al ajuste lo deja sin efecto (vuelve al orden del sistema y pide revisar)."""
    corte_iso = corte.isoformat()
    ajustes = sorted(((pid, a) for pid, a in ajustes_orden().items() if a["fecha_corte"] <= corte_iso), key=lambda x: x[1]["fecha"])
    for pid, a in ajustes:
        i = next((k for k, q in enumerate(pacientes) if q["id_paciente"] == pid), None)
        if i is None:
            continue
        nuevas = [s for s in senales.get(pid, []) if not s.get("informativa") and posterior(s, a["fecha_corte"], a["fecha"])]
        if [s for s in nuevas if not s.get("algoritmo")]:
            pacientes[i]["ajuste_manual_vencido"] = {**a, "vencido_por": nuevas[-1]["motivo"]}
            continue
        if nuevas:
            pacientes[i]["ajuste_manual_revisar"] = nuevas[-1]["motivo"]
        p = pacientes.pop(i)
        misma = [k for k, q in enumerate(pacientes) if q["especialidad"] == p["especialidad"]]
        destino = misma[a["posicion"] - 1] if a["posicion"] - 1 < len(misma) else (misma[-1] + 1 if misma else len(pacientes))
        pacientes.insert(destino, p)
        p["ajuste_manual"] = a


def lista(corte, especialidad=None, perfs=None, revs=None):
    if perfs is None:
        perfs, revs = perfiles_combinados()
    vals = list(perfs.values())
    activos, excluidos = puntaje.priorizar(vals, corte, especialidad)
    rubrica_activa = algoritmo_activo() == "rubrica"
    if rubrica_activa:
        activos = _aplicar_rubrica(activos, perfs, corte)
    ant, _ = puntaje.priorizar(vals, corte - timedelta(days=14), especialidad)
    pos_ant = {r["id_paciente"]: r["posicion"] for r in ant}
    if rubrica_activa:  # misma vara antes y ahora: rúbrica y orden del Ord. 536
        import decisor
        ant = sorted(_aplicar_rubrica(ant, perfs, corte - timedelta(days=14)), key=decisor.clave_orden_536)
        pos_ant = {r["id_paciente"]: i for i, r in enumerate(ant, 1)}
    cont, dec, aj = contactos(), decisiones(), ajustes_orden()
    pacientes = [_enriquecer(r, perfs[r["id_paciente"]], revs.get(r["id_paciente"]), pos_ant.get(r["id_paciente"]), corte,
                             cont.get(r["id_paciente"]), dec.get(r["id_paciente"]), aj.get(r["id_paciente"])) for r in activos]
    if rubrica_activa:  # campos opcionales del algoritmo (solo con ALGORITMO=rubrica)
        for p, r in zip(pacientes, activos):
            p.update({k: r.get(k) for k in ("algoritmo", "controles", "rubrica")})
    # el equipo clínico decide: si ajustó la categoría, esa manda en el orden (mismos criterios MINSAL)
    import decisor
    pacientes.sort(key=decisor.clave_orden_536 if rubrica_activa else puntaje.clave_orden)
    for i, p in enumerate(pacientes, 1):
        p["posicion_sistema"] = i
    _aplicar_ajustes(pacientes, {r["id_paciente"]: r.get("senales", []) for r in activos}, corte)
    gest = gestiones()
    for p in pacientes:
        p["gestion"] = _gestion(p, gest.get(p["id_paciente"]), corte)
    por_esp = {}
    for i, p in enumerate(pacientes, 1):
        p["posicion"] = i
        por_esp[p["especialidad"]] = por_esp.get(p["especialidad"], 0) + 1
        p["posicion_especialidad"] = por_esp[p["especialidad"]]
    vecinos.agregar(pacientes, con_lace=True)  # por qué va antes o después de sus vecinos (el LACE desempata en ambos modos)
    exc = [{"id_paciente": r["id_paciente"], "motivo": r["motivo"], "fecha": r.get("fecha"),
            "nombre_fantasia": perfs[r["id_paciente"]]["paciente"].get("nombre_fantasia"),
            "especialidad": perfs[r["id_paciente"]]["lista_espera"].get("especialidad"),
            "fecha_defuncion": perfs[r["id_paciente"]]["paciente"].get("fecha_defuncion")} for r in excluidos]
    return {"fecha_corte": corte.isoformat(), "total": len(pacientes), "pacientes": pacientes, "excluidos": exc}


def fila_de(pid, corte, especialidad=None):
    """La fila del paciente en la lista a esa fecha (None si no está en la lista)."""
    return next((p for p in lista(corte, especialidad)["pacientes"] if p["id_paciente"] == pid), None)


def detalle(pid, corte):
    perfs, revs = perfiles_combinados()
    if pid not in perfs:
        return None
    data = lista(corte, perfs[pid]["lista_espera"]["especialidad"], perfs, revs)
    fila = next((p for p in data["pacientes"] if p["id_paciente"] == pid), None)
    p = perfs[pid]
    return {
        "paciente": fila,
        "excluido": next((e for e in data["excluidos"] if e["id_paciente"] == pid), None),
        "eventos_clinicos": [e for e in p.get("eventos_clinicos", []) if e["fecha_evento"] <= corte.isoformat()],
        "mediciones": [m for m in p.get("mediciones", []) if m["fecha_medicion"] <= corte.isoformat()],
        "citaciones": [c for c in p.get("citaciones", []) if c["fecha_cita"] <= corte.isoformat()],
        "lista_espera": p["lista_espera"],
        "datos_paciente": p["paciente"],
    }


INICIO_SERIE = date(2026, 4, 1)  # mismas quincenas que el control "Explorar fechas anteriores" del front


def estadisticas(corte, especialidad=None):
    """Evolución de la lista (una sola llamada): composición por prioridad cada 14 días hasta el corte, y para los
    pacientes que se descompensaron o subieron 10+ puestos, el evento clínico grave que lo explica (tipo exacto)."""
    perfs, _ = perfiles_combinados()
    vals = list(perfs.values())
    fechas, f = [], INICIO_SERIE
    while f < corte:
        fechas.append(f); f += timedelta(days=14)
    fechas.append(corte)
    serie = []
    for fc in fechas:
        activos, excluidos = puntaje.priorizar(vals, fc, especialidad)
        cat = {c: sum(r["categoria"] == c for r in activos) for c in puntaje.ORDEN_CAT}
        serie.append({"fecha": fc.isoformat(), "total": len(activos), **cat,
                      "graves": sum(r["riesgo_vital"] for r in activos),
                      "descompensados": sum(r["estado_clinico"] == "descompensado" for r in activos),
                      "fallecidos": sum(e["motivo"] == "fallecido" for e in excluidos),
                      "atendidos": sum(e["motivo"] == "atendido" for e in excluidos), "egresos": len(excluidos)})
    # Causas: evento grave más reciente (≤ corte) de quienes están descompensados o subieron 10+ puestos en 14 días
    data = lista(corte, especialidad, *perfiles_combinados())
    causas, eventos = {}, {}
    for p in data["pacientes"]:
        salto = (p["posicion_anterior"] - p["posicion"]) if p.get("posicion_anterior") else 0
        if p["estado_clinico"] != "descompensado" and salto < 10:
            continue
        evs = sorted((e for e in perfs[p["id_paciente"]].get("eventos_clinicos", [])
                      if e["fecha_evento"] <= corte.isoformat() and puntaje.descompensa(e)), key=lambda e: e["fecha_evento"])
        ev = evs[-1] if evs else None
        tipo = ev["tipo_evento"] if ev else "sin_evento"
        causas[tipo] = causas.get(tipo, 0) + 1
        if ev:
            eventos[p["id_paciente"]] = {k: ev.get(k) for k in ("tipo_evento", "subtipo", "severidad", "fecha_evento")}
    return {"fecha_corte": corte.isoformat(), "especialidad": especialidad, "serie": serie,
            "causas": [{"tipo_evento": k, "pacientes": v} for k, v in sorted(causas.items(), key=lambda x: -x[1])],
            "evento_causa": eventos}


def historia(pid, corte, especialidad=None):
    """Posición y categoría del paciente cada 14 días hasta la fecha de corte (mismas reglas que la lista). Con
    `especialidad`, los puestos son los de la lista de esa especialidad (como la ve el especialista)."""
    perfs, _ = perfiles_combinados()
    if pid not in perfs:
        return None
    if especialidad:
        perfs = {k: v for k, v in perfs.items() if v["lista_espera"]["especialidad"] == especialidad}
        if pid not in perfs:
            return None
    fechas, f = [], corte - timedelta(days=14 * 14)  # últimas 28 semanas
    while f < corte:
        fechas.append(f); f += timedelta(days=14)
    fechas.append(corte)
    vals, puntos = list(perfs.values()), []
    rubrica_activa = algoritmo_activo() == "rubrica"
    if rubrica_activa:  # misma vara que la lista: rúbrica vigente a cada fecha y orden del Ord. 536
        import decisor
        evs = evaluaciones_por_paciente()
    for fc in fechas:
        activos, excluidos = puntaje.priorizar(vals, fc)
        if rubrica_activa:
            activos = [{**x, "posicion": i} for i, x in enumerate(sorted(_aplicar_rubrica(activos, perfs, fc, evs), key=decisor.clave_orden_536), 1)]
        r = next((x for x in activos if x["id_paciente"] == pid), None)
        if r:
            puntos.append({"fecha": fc.isoformat(), "posicion": r["posicion"], "total": len(activos),
                           "categoria": r["categoria"], "riesgo_vital": r["riesgo_vital"]})
        elif any(x["id_paciente"] == pid for x in excluidos):
            puntos.append({"fecha": fc.isoformat(), "excluido": True})
    # el punto de hoy sale del mismo cálculo que la lista (revisiones, ajustes manuales, cierre de urgencias): cuadra con la ficha
    hoy_fila = next((x for x in lista(corte, especialidad)["pacientes"] if x["id_paciente"] == pid), None)
    if hoy_fila and puntos and puntos[-1].get("fecha") == corte.isoformat() and not puntos[-1].get("excluido"):
        puntos[-1].update(posicion=hoy_fila["posicion"], categoria=hoy_fila["categoria"], riesgo_vital=hoy_fila["riesgo_vital"])
    eventos = [e for e in perfs[pid].get("eventos_clinicos", []) if e["fecha_evento"] <= corte.isoformat()
               and puntaje.descompensa(e) or (puntaje.estabiliza(e) and e["fecha_evento"] <= corte.isoformat())]
    return {"id_paciente": pid, "puntos": puntos, "eventos": eventos}


def post_explicar(pid, corte):
    d = detalle(pid, corte)
    if not d or not d["paciente"]:
        return 404, {"error": "paciente no está en la lista a esa fecha"}
    # el riesgo con cifra y fuente sale de las reglas (con la rúbrica activa, las razones de la lista no lo traen)
    reglas = puntaje.puntuar(perfiles_combinados()[0][pid], corte) or {}
    d["riesgos"] = list(dict.fromkeys(r["riesgo"] for r in (d["paciente"].get("razones") or []) + (reglas.get("razones") or [])
                                      if r.get("riesgo") and r.get("factor") != "plazo"))[:3]
    secciones, fuente = explicar.resumen_equipo(d, corte)
    texto = " ".join([secciones["en_pocas_palabras"], *secciones["mientras_esperaba"], secciones["por_que_importa"], *secciones["que_hacer"]])
    return 200, {"id_paciente": pid, "resumen": secciones, "explicacion_ia": texto + " Propuesta sujeta a validación clínica.", "fuente": fuente}
