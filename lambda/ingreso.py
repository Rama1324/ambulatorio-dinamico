"""Ingreso de pacientes (formulario) y carga de archivos del hospital, con el impacto de cada carga en la lista."""
import json
import re
import uuid

import importar
import privacidad
import puntaje
from catalogo import catalogo
from datos import ahora, fecha_de, fecha_valida, guardar, guardar_evento, perfiles_combinados
from evaluacion_ia import algoritmo_activo, cliente_llm, evaluar_y_guardar
from lista import lista


def normalizar_rut(valor):
    """RUT chileno validado con el dígito verificador (módulo 11). Devuelve '12.345.678-5' o None si no es válido."""
    s = re.sub(r"[^0-9kK]", "", str(valor or "")).upper()
    if len(s) < 2 or not s[:-1].isdigit():
        return None
    cuerpo, dv = s[:-1].lstrip("0"), s[-1]
    if not cuerpo or len(cuerpo) > 8:
        return None
    suma, factor = 0, 2
    for d in reversed(cuerpo):
        suma += int(d) * factor
        factor = 2 if factor == 7 else factor + 1
    esperado = {11: "0", 10: "K"}.get(11 - suma % 11, str(11 - suma % 11))
    return f"{int(cuerpo):,}".replace(",", ".") + f"-{dv}" if dv == esperado else None


def post_paciente(body):
    """Ingresa una nueva interconsulta a la lista (la prioridad inicial la define quien prioriza la SIC)."""
    cat = {d["diagnostico_cie10"]: d for d in catalogo()["diagnosticos"]}
    dx = cat.get(body.get("diagnostico_cie10"))
    nombre = (body.get("nombre") or "").strip()
    try:
        edad = int(body.get("edad"))
    except (TypeError, ValueError):
        edad = -1
    if not nombre or not dx or body.get("prioridad_inicial") not in puntaje.ORDEN_CAT or not 0 <= edad <= 120 \
            or body.get("sexo") not in ("F", "M"):
        return 400, {"error": "requiere nombre, edad (0-120), sexo (F/M), diagnostico_cie10 del catálogo y prioridad_inicial (alta|media|baja)"}
    rut = None
    if body.get("rut"):
        rut = normalizar_rut(body["rut"])
        if not rut:
            return 400, {"error": f"RUT inválido: '{body['rut']}' (revise el dígito verificador)"}
        existente = next((pid for pid, x in perfiles_combinados()[0].items() if x["paciente"].get("rut") == rut
                          and x["lista_espera"].get("diagnostico_cie10") == body.get("diagnostico_cie10")), None)
        if existente:
            return 409, {"error": f"El RUT {rut} ya tiene una interconsulta por ese diagnóstico en la lista ({existente})"}
    corte = fecha_de(body)
    ingreso, err = fecha_valida(body.get("fecha_ingreso_lista") or corte.isoformat(), corte, "fecha de ingreso a la lista")
    if err:
        return 400, {"error": err}
    pid = "PAC-NUEVO-" + uuid.uuid4().hex[:5].upper()
    perfil = {
        "id_paciente": pid,
        "paciente": {"nombre_fantasia": nombre, "rut": rut, "edad": edad, "sexo": body["sexo"], "comuna": body.get("comuna") or "Sin dato",
                     "prevision": body.get("prevision") or "Sin dato", "nivel_socioeconomico": "", "fallecido": False,
                     "fecha_defuncion": None,
                     "grupo_proteccion": body.get("grupo_proteccion") if body.get("grupo_proteccion") in puntaje.GRUPOS_PROTECCION else None,
                     "acg": body.get("acg") if body.get("acg") in puntaje.ACG_NIVELES else None},
        "lista_espera": {"id_solicitud": "IC-" + pid, "especialidad": dx["especialidad"], "sub_especialidad": dx["sub_especialidad"],
                         "diagnostico_cie10": dx["diagnostico_cie10"], "diagnostico_texto": dx["diagnostico_texto"],
                         "prioridad_inicial": body["prioridad_inicial"], "fecha_ingreso_lista": ingreso,
                         "origen_derivacion": body.get("origen_derivacion") or "CESFAM/APS", "estado": "en_espera"},
        "eventos_clinicos": [], "mediciones": [], "citaciones": [],
    }
    guardar({"id_paciente": pid, "sk": "paciente#", "perfil": json.dumps(perfil, ensure_ascii=False)})
    motivo = (body.get("motivo_interconsulta") or "").strip()
    motivo = privacidad.ocultar(motivo, [nombre], [rut])  # a la IA no va el nombre ni el RUT
    clasif = _aplicar_criterios(pid, dx["diagnostico_cie10"], motivo, ingreso, body)
    combs = _aplicar_combinaciones(pid, perfil, motivo, ingreso, body)
    if algoritmo_activo() == "rubrica":  # el modelo evalúa al paciente al ingresar, cruzando lo registrado (no solo la SIC)
        try:
            evaluar_y_guardar(pid, corte)
        except Exception as e:  # si la IA falla, quedan las reglas: el ingreso no se pierde
            print(f"evaluación al ingresar {pid}: {type(e).__name__}: {e}")
    data = lista(corte)
    fila = next((p for p in data["pacientes"] if p["id_paciente"] == pid), None)
    return 200, {"id_paciente": pid, "paciente": fila, "criterio": clasif, "combinaciones": combs}


def _aplicar_combinaciones(pid, perfil, texto, fecha, body):
    """Combinaciones de riesgo (combinaciones.py): Claude marca base + gatillo citando el texto; el código verifica contra el
    registro del paciente; el resultado queda como evento y la regla de puntaje lo aplica (solo sube)."""
    import combinaciones
    if not (texto and algoritmo_activo() == "rubrica"):
        return None
    d = combinaciones.detectar(texto, perfil, cliente_llm())
    ev = combinaciones.evento(d, fecha)
    if ev:
        ev.update(id_evento="EV-COMB-" + uuid.uuid4().hex[:6].upper(), registrado=ahora(),
                  usuario=body.get("usuario", "equipo clínico"))
        guardar_evento(pid, ev)
    return d


def _aplicar_criterios(pid, cie, texto, fecha, body):
    """Si la enfermedad tiene criterios clínicos y el algoritmo con IA está activo, Claude lee el texto y elige el
    criterio (criterios.py); el resultado queda como evento y la regla de puntaje lo aplica (solo sube)."""
    import criterios
    enf = criterios.enfermedad_de(cie)
    if not (texto and enf and algoritmo_activo() == "rubrica"):
        return None
    c = criterios.clasificar(texto, enf, cliente_llm())
    ev = criterios.evento(c, fecha)
    if ev:
        ev.update(id_evento="EV-CRIT-" + uuid.uuid4().hex[:6].upper(), registrado=ahora(),
                  usuario=body.get("usuario", "equipo clínico"))
        guardar_evento(pid, ev)
    return c


def post_importar(body):
    """Revisa (confirmar=false) o carga (confirmar=true) archivos Excel/CSV con datos del hospital."""
    archivos = body.get("archivos") or []
    if not archivos:
        return 400, {"error": "envíe 'archivos': [{nombre, contenido_base64}]"}
    informe, datos = importar.procesar(archivos)
    existentes, _ = perfiles_combinados()
    cat = {d["diagnostico_cie10"]: d for d in catalogo()["diagnosticos"]}
    perfs, resumen, avisos = importar.combinar(datos, existentes, cat)
    out = {"informe": informe, "resumen": resumen, "avisos": avisos, "cargado": False,
           "impacto": _impacto(existentes, perfs, perfiles_combinados()[1], fecha_de(body))}
    if body.get("confirmar"):
        for pid, p in perfs.items():
            guardar({"id_paciente": pid, "sk": "paciente#", "perfil": json.dumps(p, ensure_ascii=False, default=str)})
        out["cargado"] = True
    return 200, out


def _impacto(existentes, nuevos, revs, corte, limite=100):
    """Qué le pasa a cada paciente del archivo si se carga: simula la lista antes y después (sin guardar nada) y explica
    el cambio con las razones nuevas del puntaje (evento, tabla del HLF, grupo de protección, cáncer…)."""
    if not nuevos:
        return []
    simulado = {**existentes, **nuevos}
    antes = {p["id_paciente"]: p for p in lista(corte, perfs=existentes, revs=revs)["pacientes"]}
    despues = {p["id_paciente"]: p for p in lista(corte, perfs=simulado, revs=revs)["pacientes"]}
    out = []
    for pid in list(nuevos)[:limite]:
        a, d = antes.get(pid), despues.get(pid)
        fila = {"id_paciente": pid, "nombre": (d or a or {}).get("nombre_fantasia") or nuevos[pid]["paciente"].get("nombre_fantasia", pid),
                "posicion_antes": a and a["posicion"], "posicion_despues": d and d["posicion"],
                "categoria_antes": a and a["categoria"], "categoria_despues": d and d["categoria"], "por_que": []}
        if not d:
            r = puntaje.puntuar(simulado[pid], corte) or {}
            fila["cambio"] = "sale" if a else "fuera"
            fila["por_que"] = [{"factor": "egreso", "valor": {"fallecido": "fallecimiento registrado", "atendido": "ya fue atendido"}.get(
                r.get("motivo"), "no está en la lista a esta fecha")}]
            out.append(fila)
            continue
        fila["cambio"] = "ingresa" if not a else ("sube" if d["posicion"] < a["posicion"] else "baja" if d["posicion"] > a["posicion"] else "igual")
        if a and a["categoria"] != d["categoria"]:
            fila["por_que"].append({"factor": "prioridad", "valor": f'prioridad {a["categoria"]} → {d["categoria"]}'})
        previas = {(r["factor"], r["valor"]) for r in (a or {}).get("razones", [])}
        fila["por_que"] += [{"factor": r["factor"], "valor": r["valor"], "fuente": r.get("fuente")} for r in d["razones"]
                            if (r["factor"], r["valor"]) not in previas and r["factor"] not in ("dias_espera", "lace")]
        if a and not fila["por_que"]:
            fila["por_que"] = [{"factor": "sin_cambio", "valor": "los datos nuevos no cambian su prioridad" +
                                (": se movió solo porque cambió el orden de otros pacientes" if fila["cambio"] != "igual" else "")}]
        out.append(fila)
    orden = {"sube": 0, "ingresa": 1, "baja": 2, "sale": 3, "igual": 4, "fuera": 5}
    return sorted(out, key=lambda f: (orden[f["cambio"]], f["posicion_despues"] or 10 ** 6))
