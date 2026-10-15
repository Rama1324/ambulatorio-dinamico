"""Fórmula fija: convierte las respuestas de la rúbrica en categoría (función pura, sin LLM, sin E/S).

Base de conocimiento: lambda/conocimiento/rubrica_v1.json (Tabla SSMSO 2025 del HLF, Ord. MINSAL 536/2025, guías y
PubMed). Reglas:
- La categoría parte de la prioridad de la SIC y solo SUBE a la fila 'descompensado' de la tabla del HLF cuando la
  rúbrica lo respalda con citas. Nunca baja (bajar siempre requiere un humano: lo controla controles.py).
- Un evento grave sin estabilización posterior mantiene la fila 'descompensado' mientras esté dentro de su ventana
  (días con fuente). Sin ventana con fuente se usa la opción conservadora: sigue vigente (no baja a nadie).
- "desconocido" en evento_grave o estabilizado_despues no se trata como "no": genera revisión.
- Orden: cascada del Ord. 536 (criterio médico → grupo de especial protección → antigüedad > 1 año → llegada). Sin LACE.
"""
import json
import os
from datetime import date

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
    if ev.valor == "desconocido":
        revision.append({"motivo": "dato_desconocido", "detalle": "no se pudo determinar si hubo un evento grave", "bloqueante": True})
    elif ev.valor == "si":
        cita_ult = max(ev.citas, key=lambda c: c.fecha, default=None)
        fecha_ev = cita_ult.fecha if cita_ult else None
        cita_txt = "; ".join(f"{c.fecha} {c.tipo} {c.valor}" for c in ev.citas)
        razones.append({"factor": "evento", "valor": f"evento grave: {cita_txt}", "fuente": "Registro clínico posterior a la SIC (cita verificada)"})
        if est.valor == "si":
            estado = "estabilizado"
            razones.append({"factor": "evento", "valor": "estabilización posterior: " + "; ".join(f"{c.fecha} {c.valor}" for c in est.citas) +
                            " · el sistema no baja la prioridad solo", "fuente": "Principio de diseño: bajar requiere un humano"})
        elif est.valor == "desconocido":
            revision.append({"motivo": "dato_desconocido", "detalle": "no se pudo determinar si se estabilizó", "bloqueante": True})
        else:
            # ventana del tipo de evento citado; si ese tipo no tiene ventana con fuente, no vence (conservador)
            v = (dx.get("ventanas") or {}).get(cita_ult.tipo) if cita_ult else None
            vigente = not (v and v.get("valor") and fecha_ev and (corte - _fecha(fecha_ev)).days > v["valor"])
            if not vigente:
                estado = "evento_fuera_de_ventana"
                razones.append({"factor": "ventana", "valor": f"el evento grave del {fecha_ev} supera la ventana de {v['valor']} días",
                                "fuente": v["fuente"]})
            else:
                estado = "descompensado"
                if v and v.get("valor"):
                    razones.append({"factor": "ventana", "valor": f"dentro de la ventana de {v['valor']} días tras el evento",
                                    "fuente": v["fuente"]})
                if fila:
                    categoria = _mayor(base, fila["prioridad"])
                    grave = fila["prioridad"] == "alta"
                    nota = " (no supera la actual)" if categoria == base and ORDEN_CAT[fila["prioridad"]] <= ORDEN_CAT[base] else ""
                    eq = dx.get("equivalencia")
                    razones.append({"factor": "tabla_oficial", "valor": f'"{fila["texto_pdf"].capitalize()}" → prioridad {fila["prioridad"]}{nota}' +
                                    (f" · equivalencia a validar: {eq['detalle']}" if eq else ""),
                                    "fuente": f"{fuente_tabla}, pág. {fila['pagina']}"})
                    if grave:
                        razones.insert(0, {"factor": "riesgo_vital", "valor": f'Descompensación grave ({fila["texto_pdf"].capitalize()}) sin registro '
                                           "posterior de estabilización: su prioridad debe revisarse dentro de 72 h; el especialista decide",
                                           "fuente": f"MINSAL: criticidad / riesgo vital · {fuente_tabla}, pág. {fila['pagina']}"})
                else:
                    revision.append({"motivo": "descompensacion_sin_fila", "bloqueante": False,
                                     "detalle": dx.get("detalle") or "la tabla del HLF no define fila de descompensación para este diagnóstico"})

    # Medición clave: el LLM cita los valores y la tendencia; el código compara con el umbral con fuente
    tm, med = resp.tendencia_medicion, dx.get("medicion")
    if med and tm.valor == "empeora":
        valores = [c for c in tm.citas if c.tipo == med["tipo"]]
        ultima = max(valores, key=lambda c: c.fecha) if valores else None
        u = med.get("umbral") or {}
        sobre = None
        if ultima and u.get("valor") is not None:
            x = float(ultima.valor)
            sobre = {"mayor_igual": x >= u["valor"], "menor": x < u["valor"], "menor_igual": x <= u["valor"]}[u.get("sentido", "mayor_igual")]
        if sobre and med.get("sube_a_fila") and u.get("estado") == "con_fuente" and dx.get("fila_por_medicion"):
            f2 = dx["fila_por_medicion"]
            categoria = _mayor(categoria, f2["prioridad"])
            estado = "descompensado" if estado == "sin_cambios" else estado
            razones.append({"factor": "medicion", "valor": f'{med["tipo"]} = {ultima.valor} ({ultima.fecha}) supera el umbral {u["valor"]} y empeora → '
                            f'"{f2["texto_pdf"].capitalize()}" (prioridad {f2["prioridad"]})',
                            "fuente": f'{u["fuente"]} · {fuente_tabla}, pág. {f2["pagina"]}'})
        else:
            revision.append({"motivo": "medicion_empeora", "bloqueante": False,
                             "detalle": f"{med['tipo']} empeora" + (f" (última {ultima.valor} el {ultima.fecha})" if ultima else "")})
    if resp.cambio_tratamiento_por_mal_control.valor == "si":
        revision.append({"motivo": "cambio_tratamiento", "bloqueante": False,
                         "detalle": "aumento de dosis o cambio de fármaco por mal control: " +
                                    "; ".join(f"{c.fecha} {c.valor}" for c in resp.cambio_tratamiento_por_mal_control.citas)})
    if dx.get("estado") == "a_validar_por_medico" and estado == "descompensado":
        revision.append({"motivo": "fila_a_validar", "bloqueante": False, "detalle": dx.get("detalle", "")})
    if resp.senal_no_cubierta.strip():
        revision.append({"motivo": "senal_no_cubierta", "bloqueante": False, "detalle": resp.senal_no_cubierta.strip()[:300]})
    return {"categoria": categoria, "descompensacion_grave": grave, "estado_clinico": estado, "razones": razones, "revision": revision}


def clave_orden_536(r):
    """Ord. MINSAL 536/2025: criterio médico (categoría y descompensación grave) → grupo de especial protección →
    antigüedad > 1 año → orden de llegada. Sin LACE."""
    return (-ORDEN_CAT[r["categoria"]], not r.get("riesgo_vital"), not r.get("grupo_proteccion"),
            not (r["dias_espera"] > DIAS_ANTIGUEDAD), -r["dias_espera"], r["id_paciente"])
