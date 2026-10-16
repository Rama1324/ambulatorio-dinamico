"""Fórmula fija: convierte las respuestas de la rúbrica en categoría (función pura, sin LLM, sin E/S).

Base de conocimiento: lambda/conocimiento/rubrica_v1.json (Tabla SSMSO 2025 del HLF, Ord. MINSAL 536/2025, guías y
PubMed). Reglas:
- La categoría parte de la prioridad de la SIC y solo SUBE a la fila 'descompensado' de la tabla del HLF cuando la
  rúbrica lo respalda con citas. Nunca baja (bajar siempre requiere un humano: lo controla controles.py).
- Un evento grave sin estabilización posterior mantiene la fila 'descompensado' mientras esté dentro de su ventana
  (días con fuente). Sin ventana con fuente se usa la opción conservadora: sigue vigente (no baja a nadie).
- "desconocido" en evento_grave o estabilizado_despues no se trata como "no": lo responde el registro estructurado
  (¿hay una descompensación?, ¿hay un control de estabilización posterior?), que es un hecho y no un juicio clínico.
- El LLM no decide qué es una descompensación: el código comprueba en el registro que el evento citado lo sea, que la
  estabilización sea posterior y que la medición realmente empeore (usa los valores registrados, no los del LLM).
- Orden: cascada del Ord. 536 (criterio médico → grupo de especial protección → antigüedad > 1 año → llegada). Sin LACE.
"""
import json
import os
from datetime import date
from types import SimpleNamespace

import puntaje

ORDEN_CAT = {"alta": 3, "media": 2, "baja": 1}
DIAS_ANTIGUEDAD = 365
_KB = {}


def cargar_kb(ruta=None):
    ruta = ruta or os.path.join(os.path.dirname(os.path.abspath(__file__)), "conocimiento", "rubrica_v1.json")
    if ruta not in _KB:
        with open(ruta, encoding="utf-8") as f:
            _KB[ruta] = json.load(f)
    return _KB[ruta]


def kb_diagnostico(kb, cie):
    return kb["diagnosticos"].get(cie) or {"texto": cie, "fila_descompensado": None, "estado": "sin_fila"}


def _fecha(s):
    return date.fromisoformat(s[:10])


def _mayor(a, b):
    return a if ORDEN_CAT[a] >= ORDEN_CAT[b] else b


def _eventos(perfil, corte):
    le = perfil["lista_espera"]
    return [e for e in perfil.get("eventos_clinicos", []) if le["fecha_ingreso_lista"] <= e["fecha_evento"] <= corte.isoformat()]


def _registro(eventos, cita):
    """Evento del registro al que apunta la cita (el código verifica lo que dice el LLM; no le cree)."""
    return next((e for e in eventos if e["fecha_evento"] == cita.fecha and e["tipo_evento"] == cita.tipo), None)


def _cita_de(e):
    return SimpleNamespace(fecha=e["fecha_evento"], tipo=e["tipo_evento"], valor=e.get("subtipo") or "")


def serie_medicion(perfil, tipo, corte):
    """Valores registrados (fecha <= corte) de una medición, en orden: [(fecha, float)]."""
    out = []
    for m in sorted(perfil.get("mediciones", []), key=lambda m: m["fecha_medicion"]):
        if m["tipo_medicion"] == tipo and m["fecha_medicion"] <= corte.isoformat():
            try:
                out.append((m["fecha_medicion"], float(m["valor"])))
            except (TypeError, ValueError):
                pass
    return out


def tendencia(valores, tipo, tolerancia=0.05):
    """Primera vs última medición: 'empeora' / 'mejora' / 'estable' / 'desconocido' (menos de 2 valores)."""
    if len(valores) < 2:
        return "desconocido"
    a, b = valores[0], valores[-1]
    sube = (b - a) / abs(a) > tolerancia if a else b > a
    baja = (a - b) / abs(a) > tolerancia if a else b < a
    if tipo in ("saturacion_o2", "peak_flow"):  # en estas, peor es bajar
        sube, baja = baja, sube
    return "empeora" if sube else "mejora" if baja else "estable"


def decidir(perfil, resp, corte, kb):
    """perfil: dict del paciente · resp: RespuestaRubrica · corte: date · kb: rubrica_v1.
    Devuelve {categoria, descompensacion_grave, estado_clinico, razones[], revision[]} (revision = motivos no bloqueantes
    o bloqueantes, cada uno {motivo, detalle, bloqueante})."""
    le = perfil["lista_espera"]
    cie, base = le["diagnostico_cie10"], le["prioridad_inicial"]
    dx = kb_diagnostico(kb, cie)
    fuente_tabla = kb["fuentes"]["ssmso"]
    razones = [{"factor": "prioridad_inicial", "valor": f"{base} (asignada por el especialista al priorizar la SIC)",
                "fuente": "Priorización de la SIC (CUD / Thalamus)"}]
    revision = []
    categoria, grave, estado = base, False, "sin_cambios"
    fila = dx.get("fila_descompensado") if dx.get("estado") == "con_fuente" else None

    ev, est = resp.evento_grave, resp.estabilizado_despues
    eventos, fecha_ev = sorted(_eventos(perfil, corte), key=lambda e: e["fecha_evento"]), None
    ev_valor, ev_citas = ev.valor, list(ev.citas)
    if ev_valor == "desconocido":
        # Si la IA no puede leerlo, lo responde el registro estructurado (es un hecho, no un juicio clínico)
        desc = [e for e in eventos if puntaje.descompensa(e)]
        ev_valor, ev_citas = ("si", [_cita_de(desc[-1])]) if desc else ("no", [])
        revision.append({"motivo": "resuelto_con_registro", "bloqueante": False,
                         "detalle": "la IA no pudo determinar si hubo descompensación: se usó el registro"})
    # El LLM lee; el código comprueba en el registro que lo citado diga lo que el LLM afirma (si no, revisa un humano)
    respaldo = [c for c in ev_citas if (x := _registro(eventos, c)) and puntaje.descompensa(x)] if ev_valor == "si" else []
    solo_onco = ev_valor == "si" and ev_citas and all((x := _registro(eventos, c)) and x["tipo_evento"] == "hallazgo_oncologico" for c in ev_citas)
    if solo_onco:
        pass  # el LLM llamó "evento grave" a un hallazgo oncológico: lo resuelve la regla oncológica de abajo (código)
    elif ev_valor == "si" and not respaldo:
        revision.append({"motivo": "cita_no_respalda", "bloqueante": True,
                         "detalle": "lo citado como descompensación no figura así en el registro (severidad o subtipo)"})
    elif ev_valor == "si":
        cita_ult = max(respaldo, key=lambda c: c.fecha)
        fecha_ev = cita_ult.fecha
        cita_txt = "; ".join(f"{c.fecha} {c.tipo} {c.valor}" for c in respaldo)
        razones.append({"factor": "evento", "valor": f"evento grave: {cita_txt}", "fuente": "Registro clínico posterior a la SIC (cita verificada)"})
        estab_reg = [e for e in eventos if puntaje.estabiliza(e) and e["fecha_evento"] > fecha_ev]
        est_valor, est_citas = est.valor, list(est.citas)
        if est_valor == "desconocido":  # lo responde el registro: ¿hay un control de estabilización posterior?
            est_valor, est_citas = ("si", [_cita_de(estab_reg[-1])]) if estab_reg else ("no", [])
            revision.append({"motivo": "resuelto_con_registro", "bloqueante": False,
                             "detalle": "la IA no pudo determinar si se estabilizó: se usó el registro"})
        estab_ok = [c for c in est_citas if (x := _registro(eventos, c)) and puntaje.estabiliza(x) and c.fecha > fecha_ev]
        if est_valor == "si" and not estab_ok:
            revision.append({"motivo": "cita_no_respalda", "bloqueante": True,
                             "detalle": f"la estabilización citada no es un control de estabilización posterior al evento del {fecha_ev}"})
        elif est_valor == "no" and estab_reg:
            revision.append({"motivo": "contradice_registro", "bloqueante": True,
                             "detalle": f"el registro muestra estabilización el {estab_reg[-1]['fecha_evento']}, posterior al evento"})
        elif est_valor == "si":
            estado = "estabilizado"
            razones.append({"factor": "evento", "valor": "estabilización posterior: " + "; ".join(f"{c.fecha} {c.valor}" for c in estab_ok) +
                            " · el sistema no baja la prioridad solo", "fuente": "Principio de diseño: bajar requiere un humano"})
        else:
            # ventana del tipo de evento citado; si ese tipo no tiene ventana con fuente directa, no vence (conservador)
            v = (dx.get("ventanas") or {}).get(cita_ult.tipo)
            v = v if v and v.get("estado") == "con_fuente" and v.get("valor") else None
            vigente = not (v and (corte - _fecha(fecha_ev)).days > v["valor"])
            if not vigente:
                estado = "evento_fuera_de_ventana"
                razones.append({"factor": "ventana", "valor": f"el evento grave del {fecha_ev} supera la ventana de {v['valor']} días",
                                "fuente": v["fuente"]})
            else:
                estado = "descompensado"
                if v:
                    razones.append({"factor": "ventana", "valor": f"dentro de la ventana de {v['valor']} días tras el evento",
                                    "fuente": v["fuente"]})
                if fila:
                    categoria = _mayor(base, fila["prioridad"])
                    # la gravedad la decide el código con el registro citado (no el LLM): severidad 'grave' en el historial
                    grave = fila["prioridad"] == "alta" and _registro(eventos, cita_ult).get("severidad") == "grave"
                    nota = " (no supera la actual)" if categoria == base and ORDEN_CAT[fila["prioridad"]] <= ORDEN_CAT[base] else ""
                    eq = dx.get("equivalencia")
                    razones.append({"factor": "tabla_oficial", "valor": f'"{fila["texto_pdf"].capitalize()}" → prioridad {fila["prioridad"]}{nota}' +
                                    (f" · equivalencia usada: {eq['detalle']}" if eq else ""),
                                    "fuente": f"{fuente_tabla}, pág. {fila['pagina']}"})
                    if grave:
                        razones.insert(0, {"factor": "riesgo_vital", "valor": f'Descompensación grave ({fila["texto_pdf"].capitalize()}) sin registro '
                                           "posterior de estabilización: su prioridad debe revisarla el especialista; el especialista decide",
                                           "fuente": f"MINSAL: criticidad / riesgo vital · {fuente_tabla}, pág. {fila['pagina']}"})
                else:
                    revision.append({"motivo": "descompensacion_sin_fila", "bloqueante": False,
                                     "detalle": dx.get("detalle") or "la tabla del HLF no define fila de descompensación para este diagnóstico"})

    # Cáncer activo o sospechoso registrado (verificado al leer el documento): lo decide el código con la tabla del HLF
    onco = puntaje.regla_oncologica(eventos, le["especialidad"])
    if onco:
        categoria = _mayor(categoria, onco["fila"][1])
        razones.append(puntaje.razon_oncologica(onco))
        if onco["a_validar"]:
            revision.append({"motivo": "fila_a_validar", "bloqueante": False, "detalle": "hallazgo oncológico en una especialidad sin fila oncológica propia"})

    # Criterios clínicos por enfermedad (ya verificados al leer el texto): solo suben; la urgencia prevalece
    crit = puntaje.regla_criterio(eventos)
    if crit:
        categoria = puntaje.aplicar_criterio(categoria, crit, razones)
    comb = puntaje.regla_combinacion(eventos)
    if comb:
        categoria = puntaje.aplicar_combinacion(categoria, comb, razones, [])

    # Medición clave: el LLM dice si empeora; el código lo confirma con los valores registrados y compara el último
    # con el umbral con fuente (nunca usa el número que escribió el LLM)
    tm, med = resp.tendencia_medicion, dx.get("medicion")
    serie = serie_medicion(perfil, med["tipo"], corte) if med else []
    if med and tm.valor == "empeora":
        u = med.get("umbral") or {}
        ultima = serie[-1] if serie else None
        confirma = tendencia([x for _, x in serie], med["tipo"]) == "empeora"
        sobre = None
        if ultima and u.get("valor") is not None:
            sobre = {"mayor_igual": ultima[1] >= u["valor"], "menor": ultima[1] < u["valor"], "menor_igual": ultima[1] <= u["valor"]}[u.get("sentido", "mayor_igual")]
        if confirma and sobre and med.get("sube_a_fila") and u.get("estado") == "con_fuente" and dx.get("fila_por_medicion"):
            f2 = dx["fila_por_medicion"]
            categoria = _mayor(categoria, f2["prioridad"])
            estado = "descompensado" if estado == "sin_cambios" else estado
            razones.append({"factor": "medicion", "valor": f'{med["tipo"]} = {ultima[1]:g} ({ultima[0]}) supera el umbral {u["valor"]} y empeora → '
                            f'"{f2["texto_pdf"].capitalize()}" (prioridad {f2["prioridad"]})',
                            "fuente": f'{u["fuente"]} · {fuente_tabla}, pág. {f2["pagina"]}'})
            revision.append({"motivo": "fila_a_validar", "bloqueante": False,
                             "detalle": f'equivalencia del equipo: {med["tipo"]} sobre el umbral = "{f2["texto_pdf"].capitalize()}" ({med.get("definida_por")})'})
        else:
            revision.append({"motivo": "medicion_empeora", "bloqueante": False,
                             "detalle": f"{med['tipo']} empeora" + (f" (última {ultima[1]:g} el {ultima[0]})" if ultima else "") +
                                        ("" if confirma else " · el registro no lo confirma")})
    elif med and tm.valor == "desconocido" and len(serie) >= 2:
        revision.append({"motivo": "sin_dato", "bloqueante": False, "detalle": f"no se pudo leer la tendencia de {med['tipo']}"})
    if resp.cambio_tratamiento_por_mal_control.valor == "si":
        revision.append({"motivo": "cambio_tratamiento", "bloqueante": False,
                         "detalle": "aumento de dosis o cambio de fármaco por mal control: " +
                                    "; ".join(f"{c.fecha} {c.valor}" for c in resp.cambio_tratamiento_por_mal_control.citas)})
    elif resp.cambio_tratamiento_por_mal_control.valor == "desconocido":
        revision.append({"motivo": "sin_dato", "bloqueante": False, "detalle": "no se pudo determinar si hubo cambio de tratamiento por mal control"})
    if dx.get("estado") == "a_validar_por_medico" and estado == "descompensado":
        revision.append({"motivo": "fila_a_validar", "bloqueante": False, "detalle": dx.get("detalle", "")})
    if resp.senal_no_cubierta.strip():
        revision.append({"motivo": "senal_no_cubierta", "bloqueante": False, "detalle": resp.senal_no_cubierta.strip()[:300]})
    return {"categoria": categoria, "descompensacion_grave": grave, "estado_clinico": estado, "razones": razones, "revision": revision,
            "fecha_evento": fecha_ev if estado == "descompensado" else None}


def clave_orden_536(r):
    """Ord. MINSAL 536/2025: criterio médico (categoría, descompensación grave y cualquier descompensación vigente) →
    grupo de especial protección → antigüedad > 1 año → orden de llegada. Sin LACE. El criterio médico va antes que el
    grupo de protección: un paciente descompensado no puede quedar bajo uno estable de la misma prioridad."""
    return (-ORDEN_CAT[r["categoria"]], not r.get("urgencia_hoy"), not r.get("riesgo_vital"), -r.get("agudeza", 0),
            r.get("estado_clinico") != "descompensado", not r.get("grupo_proteccion"),
            not (r["dias_espera"] > DIAS_ANTIGUEDAD), -r["dias_espera"], r["id_paciente"])
