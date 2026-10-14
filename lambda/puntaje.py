"""Puntaje de prioridad dinámica HLF (reglas explicables, sin LLM).
Uso: python puntaje.py perfiles.json [fecha_corte AAAA-MM-DD]"""
import json, sys
from datetime import date

BASE = {"alta": 30, "media": 15, "baja": 5}
PESO_EVENTO = {  # (tipo, subtipo) -> puntos
    ("hospitalizacion", "ingreso UCI"): 30,
    ("hospitalizacion", "ingreso hospitalario"): 22,
    ("visita_urgencia", "descompensación grave"): 22,
    ("visita_urgencia", "triage ESI 2"): 18,
    ("visita_urgencia", "descompensación"): 10,
    ("examen_alterado", "resultado alterado"): 8,
    ("cambio_farmaco", "aumento dosis"): 6,
    ("control_aps", "buena respuesta"): -5,
    ("control_aps", "estabilización"): -4,
    ("cambio_farmaco", "reducción dosis"): -4,
}

# Plazo clínico máximo por prioridad: categorías 1/2/3 de consulta de especialidad de Queensland Health
# (Australia): 30/90/365 días. https://www.qld.gov.au/health/services/hospital-care/waiting-lists
PLAZO_DIAS = {"alta": 30, "media": 90, "baja": 365}

# Garantía GES de oportunidad para la atención por médico especialista (plazo legal en Chile, días desde
# derivación/indicación). Fuente: auge.minsal.cl/problemasdesalud/index/<N°>. Diagnósticos del dataset que no
# están aquí no son GES o su garantía no fija plazo de especialista (hipotiroidismo GES 76).
# cie10: (N° problema GES, nombre corto, días, edad mínima)
GES_ESPECIALISTA = {
    "F32": (34, "Depresión", 30, 15),
    "I10": (21, "Hipertensión arterial", 45, 15),
    "J44": (38, "EPOC", 45, 0),
    "E11": (7, "Diabetes mellitus tipo 2", 60, 0),
    "J45": (61, "Asma bronquial", 60, 15),
    "G40": (60, "Epilepsia", 60, 15),
    "M17": (41, "Artrosis de rodilla", 120, 55),
}

def plazo_paciente(le, edad):
    """El plazo más exigente entre la categoría clínica y la garantía GES (si aplica)."""
    plazo, fuente = PLAZO_DIAS[le["prioridad_inicial"]], f'categoría {le["prioridad_inicial"]}'
    ges = GES_ESPECIALISTA.get(le["diagnostico_cie10"])
    if ges and edad >= ges[3] and ges[2] < plazo:
        plazo, fuente = ges[2], f"garantía GES N°{ges[0]} {ges[1]}"
    return plazo, fuente
PUNTOS_PLAZO = 8     # al cumplirse el plazo
PUNTOS_VENCIDO = 4   # extra si ya lo superó

def d(s): return date.fromisoformat(s)

def factor_recencia(dias):
    if dias <= 30: return 1.0
    if dias <= 90: return 0.6
    if dias <= 180: return 0.3
    return 0.1

def puntuar(perfil, corte):
    pac, le = perfil["paciente"], perfil["lista_espera"]
    if pac.get("fallecido") and pac.get("fecha_defuncion") and d(pac["fecha_defuncion"]) <= corte:
        return {"id_paciente": perfil["id_paciente"], "excluido": True, "motivo": "fallecido", "puntaje": None, "razones": []}
    if d(le["fecha_ingreso_lista"]) > corte:
        return None  # aún no ingresaba a la lista
    razones, pts = [], 0.0

    b = BASE[le["prioridad_inicial"]]; pts += b
    razones.append({"factor": "prioridad_inicial", "valor": le["prioridad_inicial"], "puntos": b})

    # Espera relativa al plazo oficial (no en días absolutos): el diagnóstico pesa vía su garantía GES.
    dias_espera = (corte - d(le["fecha_ingreso_lista"])).days
    plazo, fuente = plazo_paciente(le, pac["edad"])
    pe = round(min(dias_espera / plazo, 1) * PUNTOS_PLAZO, 1); pts += pe
    razones.append({"factor": "dias_espera", "valor": f"{dias_espera} de {plazo} días ({fuente})", "puntos": pe})
    if dias_espera > plazo:
        pts += PUNTOS_VENCIDO
        razones.append({"factor": "plazo_vencido", "valor": f"{dias_espera - plazo} días sobre el plazo ({fuente})", "puntos": PUNTOS_VENCIDO})

    ev_pts = 0.0
    for ev in perfil.get("eventos_clinicos", []):
        fe = d(ev["fecha_evento"])
        if fe > corte: continue
        w = PESO_EVENTO.get((ev["tipo_evento"], ev["subtipo"]), 0)
        if w == 0: continue
        p = round(w * factor_recencia((corte - fe).days), 1)
        ev_pts += p
        razones.append({"factor": "evento", "valor": f'{ev["tipo_evento"]}: {ev["subtipo"]} ({ev["fecha_evento"]})', "puntos": p})
    ev_pts = max(min(ev_pts, 40), -10); pts += ev_pts

    meds = sorted([m for m in perfil.get("mediciones", []) if d(m["fecha_medicion"]) <= corte], key=lambda m: m["fecha_medicion"])
    ult = meds[-3:]
    if ult:
        fr = sum(1 for m in ult if m["fuera_de_rango"]) / len(ult)
        pm = round(fr * 10, 1); pts += pm
        if pm: razones.append({"factor": "mediciones_fuera_rango", "valor": f"{sum(1 for m in ult if m['fuera_de_rango'])}/{len(ult)} últimas", "puntos": pm})

    if pac["edad"] >= 75:
        pts += 3; razones.append({"factor": "edad", "valor": pac["edad"], "puntos": 3})

    no_show = sum(1 for c in perfil.get("citaciones", []) if c["estado_cita"] == "no_asistio" and d(c["fecha_cita"]) <= corte)
    pts = round(max(0, min(100, pts)), 1)
    cat = "critica" if pts >= 70 else "alta" if pts >= 50 else "media" if pts >= 30 else "baja"
    return {"id_paciente": perfil["id_paciente"], "excluido": False, "puntaje": pts, "categoria": cat,
            "riesgo_inasistencia": no_show >= 2, "no_shows": no_show, "dias_espera": dias_espera, "razones": razones}

def priorizar(perfiles, corte, especialidad=None):
    out = []
    for p in perfiles:
        if p["lista_espera"]["estado"] == "atendido": continue
        if especialidad and p["lista_espera"]["especialidad"] != especialidad: continue
        r = puntuar(p, corte)
        if r: out.append(r)
    # desempate: más días esperando primero, luego id (orden estable y reproducible)
    activos = sorted([r for r in out if not r["excluido"]], key=lambda r: (-r["puntaje"], -r["dias_espera"], r["id_paciente"]))
    for i, r in enumerate(activos, 1): r["posicion"] = i
    return activos, [r for r in out if r["excluido"]]

if __name__ == "__main__":
    perfiles = json.load(open(sys.argv[1], encoding="utf-8"))
    corte = d(sys.argv[2]) if len(sys.argv) > 2 else date(2026, 10, 13)
    activos, excl = priorizar(perfiles, corte)
    print(f"corte {corte}: {len(activos)} activos, {len(excl)} excluidos")
    for r in activos[:10]: print(r["posicion"], r["id_paciente"], r["puntaje"], r["categoria"])
