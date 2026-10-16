"""POST /pacientes/{id}/informe: lee un informe (texto o foto con Textract). Con IA, lo verificado y estable se registra
solo; sin IA, se proponen eventos para que el equipo confirme."""
import copy
import re
import time
import uuid

import informe
import puntaje
from datos import ahora, fecha_de, guardar_evento, perfiles_combinados
from evaluacion_ia import algoritmo_activo, cliente_llm, evaluar_y_guardar
from ingreso import _aplicar_combinaciones, _aplicar_criterios
from lista import fila_de
from modelos import Lectura, normalizar


def post_informe(pid, body):
    """Lee un informe (texto o foto con Amazon Textract), PROPONE eventos validados con Pydantic y no guarda nada:
    el equipo clínico elige y confirma con POST /eventos."""
    perfs, _ = perfiles_combinados()
    if pid not in perfs:
        return 404, {"error": "paciente no existe"}
    corte = fecha_de(body)
    texto = (body.get("texto") or "").strip()
    try:
        if texto:
            lectura = Lectura(origen="texto", texto=texto)
        elif body.get("imagen_base64"):
            lectura = informe.leer_foto(body["imagen_base64"])
        else:
            return 400, {"error": "falta 'texto' o 'imagen_base64' del informe"}
    except Exception as e:
        print(f"Textract no pudo leer la foto: {e}")
        return 200, {"id_paciente": pid, "eventos": [], "evento": None,
                     "mensaje": "No se pudo leer la foto con Amazon Textract (OCR). Verifique la conexión a AWS o "
                                "escriba el texto del informe."}
    if algoritmo_activo() == "rubrica":  # lo lee la IA (_informe_con_ia); aquí solo la legibilidad de la foto
        eventos, descartados, avisos = [], [], [] if lectura.legible else [
            f"Foto poco legible (confianza media {lectura.confianza_media}%): repita la foto con buena luz y el documento completo."]
    else:
        eventos, descartados, avisos = informe.analizar(lectura, corte)

    # Identidad: el error más grave sería registrar el evento en otro paciente
    pac = perfs[pid]["paciente"]
    doc = normalizar(lectura.texto)
    menciona = normalizar(pac["nombre_fantasia"]) in doc or normalizar(pid) in doc
    otros = sorted({o for o in re.findall(r"pac-[a-z]+-\d{3,}", doc) if o != normalizar(pid)})
    if otros:
        avisos.insert(0, f"¡Atención! El documento menciona a otro paciente ({', '.join(o.upper() for o in otros)}). No lo registre aquí.")
    elif lectura.origen == "foto" and not menciona:
        avisos.insert(0, f"El documento no menciona a {pac['nombre_fantasia']} ni su ID: confirme que corresponde a este paciente.")

    if algoritmo_activo() == "rubrica":  # la IA lee el documento y lo verificado se registra solo
        dudoso = bool(otros) or (lectura.origen == "foto" and (not menciona or not lectura.legible))
        return 200, _informe_con_ia(pid, lectura, corte, perfs, avisos, dudoso, menciona, body)

    antes = puntaje.puntuar(perfs[pid], corte)
    propuestas = []
    for ev in eventos:
        e = ev.model_dump(mode="json")
        e["fecha_evento"] = e["fecha_evento"] or corte.isoformat()
        sim = copy.deepcopy(perfs[pid])
        sim.setdefault("eventos_clinicos", []).append({**e, "id_evento": "EV-PREVIEW", "detalle": e["evidencia"]})
        despues = puntaje.puntuar(sim, corte)
        propuestas.append({**e, "categoria_propuesta": despues and despues.get("categoria"),
                           "razones_propuestas": despues and [r for r in despues["razones"] if r["factor"] == "tabla_oficial"]})
    out = {"id_paciente": pid, "lectura": lectura.resumen(), "transcripcion": lectura.texto if lectura.origen == "foto" else None,
           "eventos": propuestas, "evento": propuestas[0] if propuestas else None, "descartados": descartados,
           "advertencias": avisos, "identidad_en_documento": menciona, "otro_paciente": bool(otros),
           "categoria_actual": antes and antes.get("categoria"),
           "fuente": propuestas[0]["detectado_por"] if propuestas else "reglas"}
    if propuestas:
        out["categoria_propuesta"] = propuestas[0]["categoria_propuesta"]
        out["razones_propuestas"] = propuestas[0]["razones_propuestas"]
    else:
        out["mensaje"] = ("No encontré en el informe un evento del registro (urgencia, hospitalización, examen alterado, "
                          "cambio de fármaco o control APS). Puede registrarlo manualmente.")
    return 200, out


def _vista_previa(perfil, e, corte):
    """Categoría que tendría el paciente si se registra el evento (para que el equipo confirme sabiendo el efecto)."""
    sim = copy.deepcopy(perfil)
    sim.setdefault("eventos_clinicos", []).append({**e, "id_evento": "EV-PREVIEW"})
    r = puntaje.puntuar(sim, corte)
    return {"categoria_propuesta": r and r.get("categoria"),
            "razones_propuestas": r and [x for x in r["razones"] if x["factor"] in ("tabla_oficial", "oncologico")]}


def _informe_con_ia(pid, lectura, corte, perfs, avisos, dudoso, menciona, body):
    """Claude lee el documento 3 veces (lector_documento). Lo verificado, estable y que no puede bajar a nadie se registra
    solo y la lista se recalcula; lo demás queda como propuesta para que el equipo confirme."""
    import lector_documento
    t0 = time.perf_counter()
    le = perfs[pid]["lista_espera"]
    r = lector_documento.leer_documento(lectura.texto, cliente_llm(), diagnostico=f'{le["diagnostico_texto"]} ({le["diagnostico_cie10"]}, {le["especialidad"]})')
    clasif = combs = None
    if not dudoso:
        pos0 = (fila_de(pid, corte) or {}).get("posicion")
        clasif = _aplicar_criterios(pid, le["diagnostico_cie10"], lectura.texto, corte.isoformat(), body)
        combs = _aplicar_combinaciones(pid, perfs[pid], lectura.texto, corte.isoformat(), body)
    aceptados = r["aceptados"]
    if dudoso and aceptados:  # identidad o legibilidad en duda: nada se registra solo
        r["propuestos"] = [{**h, "motivo": "no se pudo confirmar que el documento sea de este paciente o es poco legible"} for h in aceptados] + r["propuestos"]
        aceptados = []
    existentes = {(e["fecha_evento"], e["tipo_evento"], e["subtipo"], e.get("motivo") or "") for e in perfs[pid].get("eventos_clinicos", [])}
    registrados, pos_antes, fila = [], None, None
    if (clasif and (clasif["nivel"] or clasif["urgencia"])) or (combs and (combs["aplicadas"] or combs["alertas"])):
        pos_antes = pos0
        fila = fila_de(pid, corte)
    if aceptados:
        pos_antes = pos_antes if pos_antes is not None else (fila_de(pid, corte) or {}).get("posicion")
        marca = ahora()
        for h in aceptados:
            ev = lector_documento.evento_registrable(h, corte)
            if (ev["fecha_evento"], ev["tipo_evento"], ev["subtipo"], ev.get("motivo") or "") in existentes:
                continue
            ev.update(id_evento="EV-DOC-" + uuid.uuid4().hex[:6].upper(), registrado=marca, usuario=body.get("usuario", "equipo clínico"))
            guardar_evento(pid, ev)
            registrados.append(ev)
            existentes.add((ev["fecha_evento"], ev["tipo_evento"], ev["subtipo"], ev.get("motivo") or ""))
        if registrados:
            evaluar_y_guardar(pid, corte)
            fila = fila_de(pid, corte)
    perfil = perfiles_combinados()[0][pid]
    propuestas = []
    for h in r["propuestos"]:
        e = {"tipo_evento": h["tipo_evento"], "subtipo": h["subtipo"], "severidad": h["severidad"],
             "fecha_evento": h["fecha"] if h["fecha"] and h["fecha"] <= corte.isoformat() else corte.isoformat(),
             "fecha_en_documento": h["fecha_en_documento"], "evidencia": h["cita"], "detectado_por": "ia", "motivo": h["motivo"],
             **({"motivo_clinico": h["motivo_clinico"]} if h.get("motivo_clinico") else {}),
             **({"relacionado": h["relacionado"]} if h.get("relacionado") is not None else {})}
        propuestas.append({**e, **_vista_previa(perfil, e, corte)})
    out = {"id_paciente": pid, "modo": "ia", "lectura": lectura.resumen(),
           "transcripcion": lectura.texto if lectura.origen == "foto" else None,
           "registrados": registrados, "posicion_antes": pos_antes, "posicion_despues": fila and fila["posicion"],
           "paciente": fila, "categoria_actual": (fila or {}).get("categoria") or (puntaje.puntuar(perfil, corte) or {}).get("categoria"),
           "eventos": propuestas, "evento": propuestas[0] if propuestas else None,
           "descartados": [{"subtipo": d["tipo"], "motivo": d["motivo"], "cita": d["cita"]} for d in r["descartados"]],
           "informativos": r["informativos"], "advertencias": avisos, "identidad_en_documento": menciona,
           "otro_paciente": any("otro paciente" in a for a in avisos), "fuente": "ia",
           "ia": {k: r[k] for k in ("version", "lecturas", "errores", "tokens_entrada", "tokens_salida")}, "criterio": clasif, "combinaciones": combs,
           "segundos": round(time.perf_counter() - t0, 1)}
    if not registrados and not propuestas and not (clasif and (clasif["nivel"] or clasif["urgencia"])) and not (combs and combs["aplicadas"]):
        out["mensaje"] = ("La IA no encontró en el informe un hallazgo que cambie la prioridad (cáncer, hospitalización, "
                          "descompensación, examen alterado o cambio de tratamiento)." +
                          (" Hubo un error al leerlo: " + r["errores"][0] if r["errores"] else ""))
    return out
