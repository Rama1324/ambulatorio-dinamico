"""Controles antes de mover a un paciente. Si alguno falla, el paciente NO cambia de lugar solo: conserva la categoría
de las reglas actuales (puntaje.py). Solo 'bajaria' es una decisión clínica (pide revisión del especialista); los demás son
técnicos (la IA leyó mal o falló): se usan las reglas y queda registrado, sin pedirle nada a nadie."""
from decisor import ORDEN_CAT

BLOQUEANTES = ("fallo_llm", "cita_invalida", "inestable", "bajaria", "discrepancia", "dato_desconocido",
               "cita_no_respalda", "contradice_registro", "error_formula")
CLINICOS = ("bajaria",)


def evaluar(lecturas, resultados, reglas):
    """lecturas: [(RespuestaRubrica|None, meta, citas_malas)] · resultados: [dict de decisor.decidir | None] ·
    reglas: resultado de puntaje.puntuar. Devuelve lista de motivos [{motivo, detalle}]."""
    motivos = []
    fallos = [m.get("error") for r, m, _ in lecturas if r is None]
    if fallos:
        motivos.append({"motivo": "fallo_llm", "detalle": f"{len(fallos)} de {len(lecturas)} lecturas fallaron: {fallos[0]}"})
    malas = [c for r, _, cm in lecturas if r is not None for c in cm]
    if malas:
        motivos.append({"motivo": "cita_invalida", "detalle": f"{len(malas)} cita(s) no existen en el historial: {malas[0]}"})
    validos = [x for x in resultados if x]
    cats = {x["categoria"] for x in validos}
    if len(cats) > 1 or len({x["descompensacion_grave"] for x in validos}) > 1:
        motivos.append({"motivo": "inestable", "detalle": f"las {len(validos)} corridas no coinciden: {sorted(cats)}"})
    if validos:
        cat = validos[0]["categoria"]
        if ORDEN_CAT[cat] < ORDEN_CAT[reglas["categoria"]]:
            motivos.append({"motivo": "bajaria", "detalle": f"la rúbrica daría {cat} y la categoría vigente es {reglas['categoria']}: bajar requiere un humano"})
        elif reglas.get("riesgo_vital") and not all(x["descompensacion_grave"] for x in validos):
            # misma categoría pero sin la marca de descompensación grave: perdería la alerta de revisión y bajaría en el orden
            motivos.append({"motivo": "bajaria", "detalle": "la rúbrica quitaría la marca de descompensación grave (alerta de revisión y primer lugar dentro de "
                                                            "su prioridad): quitarla requiere un humano"})
        if abs(ORDEN_CAT[cat] - ORDEN_CAT[reglas["categoria"]]) > 1:
            motivos.append({"motivo": "discrepancia", "detalle": f"rúbrica {cat} vs reglas {reglas['categoria']} (más de 1 nivel)"})
        for x in validos:
            for rv in x["revision"]:
                if rv["bloqueante"] and not any(m["motivo"] == rv["motivo"] for m in motivos):
                    motivos.append({"motivo": rv["motivo"], "detalle": rv["detalle"]})
    return motivos
