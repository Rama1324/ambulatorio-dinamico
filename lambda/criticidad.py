"""Capa de criticidad dinámica — señal temprana a partir de la evolución del paciente mientras espera.

NO cambia la categoría ni el orden MINSAL (eso lo deciden las reglas oficiales de puntaje.py y el equipo clínico).
Solo agrega:
  - `criticidad` (0–100): qué tan alterada está hoy la evolución del paciente (eventos recientes + mediciones).
  - `senal_temprana`: mediciones alteradas o empeorando → pide revisión del especialista ANTES de que llegue el evento.

Por qué: en el registro del HLF la prioridad inicial no distingue quién se agrava (eventos graves 16/15/11 % en
alta/media/baja), pero el % de mediciones fuera de rango sube de 6 % a 28 % en los 60 días previos a una urgencia u
hospitalización grave (mediana 18,5 días de anticipación). Detalle y validación en docs/criterios_oficiales.md (capa de criticidad).

Componentes (iguales al prototipo de priorización):
  A · Eventos: cada evento pesa w × 0,5^(días/60) y se combinan como 1 − ∏(1 − aporte).
  B · Mediciones (90 días): 0,55 × desviación media del rango + 0,30 × fracción fuera de rango
      + 0,60 × pendiente de empeoramiento (180 días) de la medición principal.
  Mejora: buena respuesta, reducción de dosis, estabilización o mediciones que bajan (resta hasta 12 puntos).
"""
from datetime import date

VIDA_MEDIA = 60  # días: un evento pesa la mitad a los 60 días
FUENTE = "Tendencia de eventos y mediciones (análisis del registro HLF; señal para revisión, no cambia la prioridad)"

PESO_EVENTO = {"ingreso UCI": 1.0, "ingreso hospitalario": .8, "descompensación grave": .8, "triage ESI 2": .7,
               "descompensación": .45, "resultado alterado": .35, "aumento dosis": .3}
PESO_MEJORA = {"buena respuesta": .35, "reducción dosis": .4, "estabilización": .35}

# Rangos del diccionario de datos + escala para normalizar la desviación (bajo, alto)
MED = {
    "presion_sistolica": (90, 139, 20, 40, "PA sistólica", "mmHg"),
    "presion_diastolica": (60, 89, 15, 20, "PA diastólica", "mmHg"),
    "HbA1c": (4, 6.4, 2, 3, "HbA1c", "%"),
    "glicemia": (70, 140, 20, 100, "Glicemia", "mg/dL"),
    "saturacion_o2": (95, 100, 7, 1, "Saturación O₂", "%"),
    "peak_flow": (350, 600, 200, 1e9, "Peak flow", "L/min"),
    "escala_dolor_eva": (0, 3, 1, 7, "Dolor EVA", "pts"),
    "PHQ9": (0, 9, 1, 18, "PHQ-9", "pts"),
}
# Señal temprana: la medición principal empeora de forma sostenida (pendiente > 0,08 por 90 días, ≥ 3 mediciones en 180 días).
# Validación retrospectiva en el registro (7.259 cortes quincenales): marca 12 % de los cortes; de ellos 55 % tiene un
# deterioro (descompensación, examen alterado, aumento de dosis u hospitalización) en los 60 días siguientes vs 16 % base.
# NO anticipa bien los eventos graves agudos (7 % vs 4,5 %): esos llegan sin aviso y los cubre la tabla HLF / riesgo vital.
UMBRAL_TENDENCIA = 0.08


def _d(s):
    return date.fromisoformat(s[:10])


def _clip(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def _desvio(t, v):
    lo, hi, s_lo, s_hi = MED[t][:4]
    return _clip((v - hi) / s_hi) if v > hi else _clip((lo - v) / s_lo) if v < lo else 0.0


def _maldad(t, v):
    """Valor continuo que sube cuando el paciente empeora (para medir la tendencia dentro o fuera de rango)."""
    lo, hi, s_lo, s_hi = MED[t][:4]
    if t in ("saturacion_o2", "peak_flow"):
        return (hi - v) / (hi - lo + s_lo)
    if t.startswith("presion"):
        return abs(v - (lo + hi) / 2) / (hi - lo + s_hi)
    return (v - lo) / (hi - lo + s_hi)


def _pendiente(serie, corte):
    if len(serie) < 3:
        return 0.0
    x0 = _d(serie[0]["fecha_medicion"])
    xs = [(_d(m["fecha_medicion"]) - x0).days / 90 for m in serie]
    ys = [_maldad(m["tipo_medicion"], float(m["valor"])) for m in serie]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    den = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den if den else 0.0


def calcular(perfil, corte):
    """Devuelve {criticidad, senal_temprana, componentes, razon} con los registros de fecha ≤ corte."""
    ingreso = _d(perfil["lista_espera"]["fecha_ingreso_lista"])
    eventos = [e for e in perfil.get("eventos_clinicos", []) if ingreso <= _d(e["fecha_evento"]) <= corte]
    meds = sorted([m for m in perfil.get("mediciones", []) if _d(m["fecha_medicion"]) <= corte and m.get("tipo_medicion") in MED],
                  key=lambda m: m["fecha_medicion"])

    no_a = no_m = 1.0
    for e in eventos:
        dec = 0.5 ** ((corte - _d(e["fecha_evento"])).days / VIDA_MEDIA)
        no_a *= 1 - PESO_EVENTO.get(e.get("subtipo"), 0) * dec
        no_m *= 1 - PESO_MEJORA.get(e.get("subtipo"), 0) * dec
    a = 1 - no_a

    b, tendencia, razon, oor = 0.0, 0.0, None, 0.0
    if meds:
        por_tipo = {}
        for m in meds:
            por_tipo.setdefault(m["tipo_medicion"], []).append(m)
        principal = max(por_tipo, key=lambda t: len(por_tipo[t]))
        recientes = [m for m in meds if (corte - _d(m["fecha_medicion"])).days <= 90] or meds[-3:]
        nivel = sum(_desvio(m["tipo_medicion"], float(m["valor"])) for m in recientes) / len(recientes)
        oor = sum(1 for m in recientes if m.get("fuera_de_rango")) / len(recientes)
        serie = [m for m in por_tipo[principal] if (corte - _d(m["fecha_medicion"])).days <= 180]
        tendencia = _pendiente(serie, corte)
        b = _clip(.55 * nivel + .3 * oor + .6 * max(0.0, tendencia))
        if tendencia < -.08:
            no_m *= 1 - _clip(-tendencia)
        nom, u = MED[principal][4], MED[principal][5]
        ult, pri = por_tipo[principal][-1], (serie[0] if serie else por_tipo[principal][-1])
        valores = f'{pri["valor"]:g} → {ult["valor"]:g}' if pri is not ult and pri["valor"] != ult["valor"] else f'{ult["valor"]:g}'
        estado = "en aumento" if tendencia > .05 else "mejorando" if tendencia < -.08 else "alterada" if oor else "estable"
        razon = f"{nom} {estado}: {valores} {u}" + (f" ({round(oor * 100)} % fuera de rango en 90 días)" if oor else "")
    mejora = 1 - no_m
    criticidad = round(_clip(100 * (.6 * a + .4 * b) - 12 * mejora, 0, 100))
    senal = tendencia > UMBRAL_TENDENCIA
    return {"criticidad": criticidad, "senal_temprana": senal,
            "componentes": {"eventos": round(a, 3), "mediciones": round(b, 3), "mejora": round(mejora, 3),
                            "tendencia": round(tendencia, 3), "fuera_de_rango_90d": round(oor, 3)},
            "razon": razon,
            "fecha_senal": meds[-1]["fecha_medicion"] if senal else None}
