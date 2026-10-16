"""Lo que registra el equipo clínico, siempre con trazabilidad: eventos, revisiones, contactos, decisiones, gestión,
ajustes manuales de posición y novedades del paciente. Ninguna acción borra: cada una es un registro nuevo."""
import copy
import json
import time
import uuid
from datetime import date, datetime, timezone

import puntaje
from catalogo import AJUSTE_MANUAL, DECISIONES, MIN_EXPLICACION, MOTIVOS_PENDIENTE, RESULTADOS_CONTACTO, TIPOS_EVENTO, catalogo
from datos import ahora, fecha_de, fecha_valida, guardar, guardar_evento, perfiles_combinados
from evaluacion_ia import algoritmo_activo, evaluar_y_guardar
from lista import fila_de, lista
from modelos import SUBTIPOS


def post_gestion(pid, body):
    """Asigna responsable, próxima acción, fecha de seguimiento y motivo del pendiente (con trazabilidad)."""
    perfs, _ = perfiles_combinados()
    if pid not in perfs:
        return 404, {"error": "paciente no existe"}
    usuario = (body.get("usuario") or "").strip()
    if not usuario:
        return 400, {"error": "indique su nombre y cargo: la gestión queda registrada a su nombre"}
    corte = fecha_de(body)
    motivo = body.get("motivo_pendiente") or None
    if motivo and motivo not in MOTIVOS_PENDIENTE:
        return 400, {"error": f"motivo_pendiente debe ser uno de {sorted(MOTIVOS_PENDIENTE)}"}
    if motivo == "otro" and len((body.get("nota") or "").strip()) < MIN_EXPLICACION:
        return 400, {"error": f"si el motivo es 'otro', documéntelo en la nota (mínimo {MIN_EXPLICACION} caracteres)"}
    seguimiento = body.get("seguimiento") or None
    if seguimiento:
        try:
            if date.fromisoformat(seguimiento) < corte:
                return 400, {"error": "la fecha de seguimiento no puede ser anterior a hoy"}
        except ValueError:
            return 400, {"error": "seguimiento inválido (formato AAAA-MM-DD)"}
    g = {"responsable": (body.get("responsable") or "").strip() or None, "proxima_accion": (body.get("proxima_accion") or "").strip() or None,
         "seguimiento": seguimiento, "motivo_pendiente": motivo, "nota": (body.get("nota") or "").strip(), "usuario": usuario,
         "fecha_corte": corte.isoformat(), "fecha": ahora()}
    guardar({"id_paciente": pid, "sk": f"gestion#{g['fecha']}", "gestion": json.dumps(g, ensure_ascii=False)})
    esp = perfs[pid]["lista_espera"]["especialidad"]
    fila = fila_de(pid, corte, esp)
    return 200, {"id_paciente": pid, "gestion": g, "paciente": fila}


def post_evento(body):
    t0 = time.perf_counter()
    pid = body.get("id_paciente")
    perfs, _ = perfiles_combinados()
    if pid not in perfs:
        return 404, {"error": "paciente no existe"}
    if body.get("tipo_evento") not in TIPOS_EVENTO:
        return 400, {"error": f"tipo_evento debe ser uno de {sorted(TIPOS_EVENTO)}"}
    corte = fecha_de(body)
    # El subtipo debe existir en el vocabulario del registro y la severidad es la que le corresponde (no la que venga)
    subtipos = SUBTIPOS[body["tipo_evento"]]
    if body.get("subtipo") not in subtipos:
        return 400, {"error": f"subtipo debe ser uno de {sorted(subtipos)} para {body['tipo_evento']}"}
    fecha_ev, err = fecha_valida(body.get("fecha_evento") or corte.isoformat(), corte, "fecha del evento")
    if err:
        return 400, {"error": err}
    especialidad = perfs[pid]["lista_espera"]["especialidad"]
    vista = especialidad if body.get("especialidad") else None  # el front ve la lista de una especialidad: los puestos son de esa lista
    antes = lista(corte, vista)
    pos_antes = next((p["posicion"] for p in antes["pacientes"] if p["id_paciente"] == pid), None)
    ev = {
        "id_evento": "EV-DEMO-" + uuid.uuid4().hex[:6].upper(),
        "fecha_evento": fecha_ev,
        "tipo_evento": body["tipo_evento"],
        "subtipo": body["subtipo"],
        "severidad": subtipos[body["subtipo"]],
        "detalle": body.get("detalle") or f'{body.get("subtipo", body["tipo_evento"])} ({especialidad})',
        **({"motivo": str(body["motivo"])[:300]} if body.get("motivo") else {}),
        **({"relacionado": str(body["relacionado"]).strip().lower() not in ("false", "0", "no", "")} if body.get("relacionado") is not None else {}),
        "registrado": ahora(),
        "usuario": body.get("usuario", "equipo clínico"),
    }
    guardar_evento(pid, ev)
    evaluacion = None
    if algoritmo_activo() == "rubrica":  # el disparador: solo este paciente se reevalúa, en el momento
        evaluacion = evaluar_y_guardar(pid, corte)
    despues = lista(corte, vista)
    fila = next((p for p in despues["pacientes"] if p["id_paciente"] == pid), None)
    ms = round((time.perf_counter() - t0) * 1000)
    out = {"evento": ev, "paciente": fila, "posicion_antes": pos_antes, "posicion_despues": fila and fila["posicion"],
           "total": despues["total"], "reevaluado_en_ms": ms}
    if evaluacion:
        out["evaluacion"] = evaluacion
    return 200, out


def post_novedad(pid, body):
    """Novedad registrada por el equipo: comorbilidad, cambio de diagnóstico o egreso (fallecimiento / atención)."""
    perfs, _ = perfiles_combinados()
    if pid not in perfs:
        return 404, {"error": "paciente no existe"}
    tipo = body.get("tipo")
    corte = fecha_de(body)
    fecha, err = fecha_valida(body.get("fecha") or corte.isoformat(), corte)
    if err:
        return 400, {"error": err}
    if tipo in ("fallecimiento", "atendido") and fecha < perfs[pid]["lista_espera"]["fecha_ingreso_lista"]:
        return 400, {"error": f"la fecha {fecha} es anterior al ingreso a la lista ({perfs[pid]['lista_espera']['fecha_ingreso_lista']})"}
    p = copy.deepcopy(perfs[pid])
    cat = {d["diagnostico_cie10"]: d for d in catalogo()["diagnosticos"]}
    if tipo == "comorbilidad":
        cond, cie = body.get("condicion"), body.get("cie10")
        if cond in puntaje.PESO_CHARLSON:
            nueva = {"condicion": cond, "nombre": cond, "fecha": fecha}
        elif cie in cat:
            nueva = {"cie10": cie, "nombre": f'{cie} {cat[cie]["diagnostico_texto"]}', "fecha": fecha}
        else:
            return 400, {"error": "indique 'condicion' (lista de Charlson) o 'cie10' del catálogo"}
        p["paciente"].setdefault("comorbilidades", []).append(nueva)
        texto = f'comorbilidad registrada: {nueva["nombre"]}'
    elif tipo == "diagnostico":
        dx = cat.get(body.get("cie10"))
        if not dx:
            return 400, {"error": "cie10 debe estar en el catálogo"}
        p["lista_espera"].update({k: dx[k] for k in ("especialidad", "sub_especialidad", "diagnostico_cie10", "diagnostico_texto")})
        texto = f'diagnóstico cambiado a {dx["diagnostico_cie10"]} {dx["diagnostico_texto"]}'
    elif tipo == "riesgo":
        grupo, acg = body.get("grupo_proteccion") or None, body.get("acg") or None
        if grupo and grupo not in puntaje.GRUPOS_PROTECCION or acg and acg not in puntaje.ACG_NIVELES:
            return 400, {"error": "grupo_proteccion o acg no válido"}
        p["paciente"]["grupo_proteccion"], p["paciente"]["acg"] = grupo, acg
        texto = "datos de riesgo: " + ", ".join(x for x in [grupo and f"grupo {grupo}", acg and f"ACG {acg}"] if x) if grupo or acg else "datos de riesgo borrados"
    elif tipo == "fallecimiento":
        p["paciente"].update({"fallecido": True, "fecha_defuncion": fecha})
        p["lista_espera"]["estado"] = "fallecido"
        texto = f"fallecimiento el {fecha} (causal de egreso 9)"
    elif tipo == "atendido":
        p["lista_espera"].update({"estado": "atendido", "fecha_atencion": fecha})
        texto = f"atendido en consulta nueva de especialidad el {fecha}: sale de la lista"
    else:
        return 400, {"error": "tipo debe ser comorbilidad, diagnostico, riesgo, fallecimiento o atendido"}
    p["eventos_clinicos"] = [e for e in p.get("eventos_clinicos", []) if not e.get("id_evento", "").startswith("EV-DEMO")]
    marca = datetime.now(timezone.utc).isoformat(timespec="seconds")
    guardar({"id_paciente": pid, "sk": "paciente#", "perfil": json.dumps(p, ensure_ascii=False, default=str)})
    guardar({"id_paciente": pid, "sk": f"novedad#{marca}", "novedad": json.dumps(
        {"tipo": tipo, "detalle": texto, "usuario": body.get("usuario", "equipo clínico"), "fecha": marca}, ensure_ascii=False)})
    fila = fila_de(pid, corte)
    return 200, {"id_paciente": pid, "mensaje": texto, "paciente": fila, "en_lista": fila is not None}


def post_revision(pid, body):
    if pid not in perfiles_combinados()[0]:
        return 404, {"error": "paciente no existe"}
    accion = body.get("accion")
    if accion not in ("confirmar", "ajustar"):
        return 400, {"error": "accion debe ser 'confirmar' o 'ajustar'"}
    if not (body.get("usuario") or "").strip():
        return 400, {"error": "escriba su nombre y cargo arriba a la derecha: la revisión queda a su nombre"}
    if accion == "ajustar" and (body.get("categoria_ajustada") not in puntaje.ORDEN_CAT or len((body.get("motivo") or "").strip()) < MIN_EXPLICACION):
        return 400, {"error": f"cambiar la prioridad requiere categoria_ajustada (alta|media|baja) y un motivo clínico de al menos {MIN_EXPLICACION} caracteres"}
    corte = fecha_de(body)
    previa = fila_de(pid, corte)
    rev = {"accion": accion, "categoria_ajustada": body.get("categoria_ajustada") if accion == "ajustar" else None,
           "categoria_sistema": previa and previa["categoria_sistema"],  # para medir concordancia (kappa)
           "motivo": body.get("motivo"), "fecha_corte": corte.isoformat(),
           "usuario": body.get("usuario", "equipo clínico"), "fecha": ahora()}
    guardar({"id_paciente": pid, "sk": f"revision#{rev['fecha']}", "revision": json.dumps(rev, ensure_ascii=False)})
    return 200, {"id_paciente": pid, "revision": rev}


def post_contacto(pid, body):
    """Registra el contacto con un paciente 'contactar hoy' (reconoce la alerta, con motivo y trazabilidad)."""
    if pid not in perfiles_combinados()[0]:
        return 404, {"error": "paciente no existe"}
    if body.get("resultado") not in RESULTADOS_CONTACTO:
        return 400, {"error": f"resultado debe ser uno de {sorted(RESULTADOS_CONTACTO)}"}
    corte = fecha_de(body)
    c = {"resultado": body["resultado"], "texto": RESULTADOS_CONTACTO[body["resultado"]], "nota": body.get("nota", ""),
         "fecha_corte": corte.isoformat(), "usuario": body.get("usuario", "equipo clínico"),
         "fecha": ahora()}
    guardar({"id_paciente": pid, "sk": f"contacto#{c['fecha']}", "contacto": json.dumps(c, ensure_ascii=False)})
    fila = fila_de(pid, corte)
    return 200, {"id_paciente": pid, "contacto": c, "paciente": fila}


def post_decision(pid, body):
    """Decisión clínica ante una descompensación: la registra un profesional identificado y cierra la alerta."""
    if pid not in perfiles_combinados()[0]:
        return 404, {"error": "paciente no existe"}
    if body.get("decision") not in DECISIONES:
        return 400, {"error": f"decision debe ser uno de {sorted(DECISIONES)}"}
    responsable = (body.get("responsable") or "").strip()
    if not responsable:
        return 400, {"error": "indique el profesional responsable de la decisión"}
    corte = fecha_de(body)
    seguimiento = None
    if body.get("seguimiento"):
        try:
            seguimiento = date.fromisoformat(body["seguimiento"])
        except ValueError:
            return 400, {"error": "seguimiento inválido (formato AAAA-MM-DD)"}
        if seguimiento < corte:
            return 400, {"error": "la fecha de seguimiento no puede ser anterior a hoy"}
    dc = {"decision": body["decision"], "texto": DECISIONES[body["decision"]], "responsable": responsable,
          "nota": body.get("nota", ""), "seguimiento": seguimiento and seguimiento.isoformat(), "fecha_corte": corte.isoformat(),
          "fecha": ahora()}
    guardar({"id_paciente": pid, "sk": f"decision#{dc['fecha']}", "decision": json.dumps(dc, ensure_ascii=False)})
    fila = fila_de(pid, corte)
    return 200, {"id_paciente": pid, "decision": dc, "paciente": fila}


def post_orden(pid, body):
    """Ajuste manual de la posición: {posicion (en su especialidad), motivo, explicacion, usuario} o {quitar, explicacion, usuario}."""
    perfs, _ = perfiles_combinados()
    if pid not in perfs:
        return 404, {"error": "paciente no existe"}
    usuario = (body.get("usuario") or "").strip()
    explicacion = (body.get("explicacion") or "").strip()
    if not usuario:
        return 400, {"error": "indique su nombre y cargo: el ajuste manual queda registrado a su nombre"}
    if len(explicacion) < MIN_EXPLICACION:
        return 400, {"error": f"explique el motivo del ajuste (mínimo {MIN_EXPLICACION} caracteres)"}
    corte = fecha_de(body)
    esp = perfs[pid]["lista_espera"]["especialidad"]
    actual = fila_de(pid, corte, esp)
    if not actual:
        return 400, {"error": "el paciente no está en la lista a esa fecha"}
    marca = ahora()
    if body.get("quitar"):
        a = {"quitar": True, "explicacion": explicacion, "usuario": usuario, "fecha_corte": corte.isoformat(), "fecha": marca}
    else:
        if body.get("motivo") not in AJUSTE_MANUAL:
            return 400, {"error": f"motivo debe ser uno de {sorted(AJUSTE_MANUAL)}"}
        total = lista(corte, esp)["total"]
        try:
            posicion = int(body.get("posicion"))
        except (TypeError, ValueError):
            posicion = 0
        if not 1 <= posicion <= total:
            return 400, {"error": f"la posición debe estar entre 1 y {total} (lista de {esp})"}
        a = {"posicion": posicion, "posicion_anterior": actual["posicion_especialidad"], "motivo": body["motivo"],
             "motivo_texto": AJUSTE_MANUAL[body["motivo"]], "explicacion": explicacion, "usuario": usuario,
             "especialidad": esp, "fecha_corte": corte.isoformat(), "fecha": marca}
    guardar({"id_paciente": pid, "sk": f"orden#{marca}", "orden": json.dumps(a, ensure_ascii=False)})
    fila = fila_de(pid, corte, esp)
    return 200, {"id_paciente": pid, "ajuste": a, "paciente": fila}
