"""Priorización clínica evolutiva HLF — solo reglas con fuente oficial (sin pesos inventados, sin LLM).

Capa 1 · Categoría (Alta / Media / Baja)
  - Base: la prioridad que asignó el especialista al leer la SIC (prioridad_inicial).
  - Si DESPUÉS de emitida la SIC el paciente se descompensa (evento posterior que el especialista no vio),
    la categoría sube a la fila "descompensada / no controlada" de la tabla oficial del HLF:
    SSMSO (2025) "Priorización diagnósticos especialidades médicas y odontológicas No GES", §11.1
    Hospital Dra. Eloísa Díaz Inzunza, págs. 84-111.
  - El sistema nunca baja una categoría solo: eso lo decide el equipo clínico (revisión con motivo).
Capa 2 · Orden dentro de la categoría — MINSAL Ord. C N°536 (21-03-2025), recogido en el Manual de Gestión
  de la Demanda SSMSO 2025 (RE 2679), pág. 13: 1) criterio médico (la categoría), 2) grupos de especial
  protección (el dataset no los trae), 3) antigüedad en lista > 1 año. Luego orden de llegada (fecha de ingreso).
Capa 3 · Banderas (no cambian el orden)
  - Garantía GES vencida (plazo de atención por especialista, auge.minsal.cl).
  - Posible causal 8 "inasistencias reiteradas": 2 inasistencias consecutivas (Manual SSMSO, Anexo 4).
  - Última medición fuera de rango (rangos de referencia del diccionario de datos).
Exclusión: causal 9 "fallecimiento" (Manual SSMSO, Anexo 4) desde fecha_defuncion; atendidos salen de la lista.

Uso: python puntaje.py perfiles.json [fecha_corte AAAA-MM-DD]
"""
import json, sys
from datetime import date

FUENTE_TABLA = "Tabla SSMSO 2025, HLF"
ORDEN_CAT = {"alta": 3, "media": 2, "baja": 1}

# Fila oficial de la tabla del HLF que describe el diagnóstico descompensado / no controlado.
# cie10: (fila tal como aparece en el documento, prioridad oficial, página).
# Solo se incluyen filas cuyo texto expresa descompensación o falta de control. Los diagnósticos sin esa fila
# (I10 HTA, K21 ERGE, F32, F41, G43, E66, M17, M54, M75) mantienen su prioridad y quedan marcados para revisión.
FILA_DESCOMPENSADO = {
    "I50": ("Insuficiencia cardíaca descompensada", "alta", 85),
    "I20": ("Angina inestable", "alta", 85),
    "J44": ("EPOC grave no controlado", "alta", 95),
    "J45": ("Asma grave no controlada", "alta", 95),
    "K70": ("Cirrosis hepática descompensada", "alta", 95),
    "E11": ("DM2 descontrolada", "media", 101),
    "E03": ("Hipotiroidismo sintomático", "media", 94),
    "G40": ("Epilepsia con crisis mensuales (deja de ser 'epilepsia controlada', baja)", "media", 103),
}

# Garantía GES de oportunidad: atención por especialista (días). auge.minsal.cl/problemasdesalud/index/<N°>
# cie10: (N° problema GES, nombre, días, edad mínima)
GES_ESPECIALISTA = {
    "F32": (34, "Depresión", 30, 15),
    "I10": (21, "Hipertensión arterial", 45, 15),
    "J44": (38, "EPOC", 45, 0),
    "E11": (7, "Diabetes mellitus tipo 2", 60, 0),
    "J45": (61, "Asma bronquial", 60, 15),
    "G40": (60, "Epilepsia", 60, 15),
    "M17": (41, "Artrosis de rodilla", 120, 55),
}

DIAS_ANTIGUEDAD = 365  # MINSAL Ord. 536/2025: "antigüedad en la lista de espera mayor a un año"


def d(s): return date.fromisoformat(s)


def descompensa(ev):
    """Evento que el propio dataset etiqueta como descompensación o severidad grave
    (urgencia ESI 2, descompensación, hospitalización, UCI)."""
    return ev.get("severidad") == "grave" or "descompensaci" in (ev.get("subtipo") or "").lower()


def estabiliza(ev):
    """Evento que el dataset etiqueta como estabilización o buena respuesta."""
    return ev.get("tipo_evento") == "control_aps" and ev.get("subtipo") in ("estabilización", "buena respuesta")


def inasistencias_consecutivas(citas):
    """Máximo de inasistencias seguidas (las reprogramaciones/cancelaciones no cortan la racha)."""
    racha = mejor = 0
    for c in sorted(citas, key=lambda c: c["fecha_cita"]):
        if c["estado_cita"] == "no_asistio":
            racha += 1; mejor = max(mejor, racha)
        elif c["estado_cita"] == "asistio":
            racha = 0
    return mejor


def puntuar(perfil, corte):
    pac, le = perfil["paciente"], perfil["lista_espera"]
    if pac.get("fallecido") and pac.get("fecha_defuncion") and d(pac["fecha_defuncion"]) <= corte:
        return {"id_paciente": perfil["id_paciente"], "excluido": True, "motivo": "fallecido", "razones": []}
    ingreso = d(le["fecha_ingreso_lista"])
    if ingreso > corte:
        return None  # aún no ingresaba a la lista

    cie = le["diagnostico_cie10"]
    inicial = le["prioridad_inicial"]
    dias_espera = (corte - ingreso).days
    razones = [{"factor": "prioridad_inicial", "valor": f"{inicial} (asignada por el especialista al priorizar la SIC)",
                "fuente": "Priorización de la SIC (CUD / Thalamus)"}]

    # --- Capa 1: estado clínico posterior a la SIC --------------------------------
    eventos = sorted([e for e in perfil.get("eventos_clinicos", []) if ingreso <= d(e["fecha_evento"]) <= corte],
                     key=lambda e: e["fecha_evento"])
    ult_desc = next((e for e in reversed(eventos) if descompensa(e)), None)
    ult_estab = next((e for e in reversed(eventos) if estabiliza(e)), None)
    estado = "sin_cambios"
    if ult_desc:
        estado = "estabilizado" if ult_estab and ult_estab["fecha_evento"] > ult_desc["fecha_evento"] else "descompensado"
    elif ult_estab:
        estado = "estabilizado"

    categoria = inicial
    fila = FILA_DESCOMPENSADO.get(cie)
    # Riesgo vital: descompensación grave sin estabilización posterior, en un diagnóstico cuya fila oficial es Alta.
    # MINSAL prioriza primero la "criticidad / riesgo vital" (Ord. C27 N°373/2021, citado en SSMSO 2025 pág. 4)
    # y el "impacto en la progresión de la enfermedad y complicaciones" (Ord. 536/2025, criterio 1).
    riesgo_vital = bool(estado == "descompensado" and fila and fila[1] == "alta" and ult_desc["severidad"] == "grave")
    if ult_desc:
        razones.append({"factor": "evento", "valor": f'{ult_desc["tipo_evento"].replace("_", " ")}: {ult_desc["subtipo"]} '
                                                    f'({ult_desc["severidad"]}, {ult_desc["fecha_evento"]})',
                        "fuente": "Registro clínico posterior a la SIC"})
    if estado == "descompensado":
        if fila and ORDEN_CAT[fila[1]] > ORDEN_CAT[inicial]:
            categoria = fila[1]
            razones.append({"factor": "tabla_oficial", "valor": f'"{fila[0]}" → prioridad {fila[1]}',
                            "fuente": f"{FUENTE_TABLA}, pág. {fila[2]}"})
        elif fila:
            razones.append({"factor": "tabla_oficial", "valor": f'"{fila[0]}" → prioridad {fila[1]} (no supera la actual)',
                            "fuente": f"{FUENTE_TABLA}, pág. {fila[2]}"})
        else:
            razones.append({"factor": "tabla_oficial", "valor": "la tabla del HLF no tiene fila para este diagnóstico descompensado: "
                                                                "se mantiene la prioridad y se sugiere revisión clínica",
                            "fuente": FUENTE_TABLA})
    if riesgo_vital:
        razones.insert(0, {"factor": "riesgo_vital",
                           "valor": f'{fila[0]} sin estabilización posterior: no esperar cupo, contactar hoy y '
                                    'evaluar derivación a urgencia según criterio médico',
                           "fuente": "MINSAL: criticidad / riesgo vital (SSMSO 2025, pág. 4) · " f"{FUENTE_TABLA}, pág. {fila[2]}"})
    elif estado == "estabilizado":
        razones.append({"factor": "evento", "valor": f'{ult_estab["subtipo"]} ({ult_estab["fecha_evento"]}): '
                                                    "el sistema no baja la prioridad solo; puede ajustarla el equipo clínico",
                        "fuente": "Principio de diseño: la herramienta propone, el equipo clínico decide"})

    # --- Capa 2: criterios de orden MINSAL ----------------------------------------
    antiguo = dias_espera > DIAS_ANTIGUEDAD
    razones.append({"factor": "dias_espera", "valor": f"{dias_espera} días en lista" + (" (más de 1 año)" if antiguo else ""),
                    "fuente": "MINSAL Ord. 536/2025: antigüedad > 1 año"})

    # --- Capa 3: banderas ---------------------------------------------------------
    ges = GES_ESPECIALISTA.get(cie)
    ges_info = None
    if ges and pac["edad"] >= ges[3]:
        vencida = dias_espera > ges[2]
        ges_info = {"problema": ges[0], "nombre": ges[1], "plazo_dias": ges[2], "vencida": vencida}
        razones.append({"factor": "ges", "valor": f"GES N°{ges[0]} {ges[1]}: especialista en {ges[2]} días" +
                        (f" — VENCIDA hace {dias_espera - ges[2]} días" if vencida else ""),
                        "fuente": f"auge.minsal.cl, problema de salud N°{ges[0]}"})

    citas = [c for c in perfil.get("citaciones", []) if d(c["fecha_cita"]) <= corte]
    no_show = sum(1 for c in citas if c["estado_cita"] == "no_asistio")
    consecutivas = inasistencias_consecutivas(citas)

    meds = sorted([m for m in perfil.get("mediciones", []) if d(m["fecha_medicion"]) <= corte], key=lambda m: m["fecha_medicion"])
    ult_med = meds[-1] if meds else None
    medicion_alerta = bool(ult_med and ult_med["fuera_de_rango"])
    if medicion_alerta:
        razones.append({"factor": "medicion", "valor": f'{ult_med["tipo_medicion"]} = {ult_med["valor"]:g} {ult_med["unidad"]} '
                                                      f'fuera de rango ({ult_med["fecha_medicion"]})',
                        "fuente": "Rangos de referencia del diccionario de datos HLF"})

    return {"id_paciente": perfil["id_paciente"], "excluido": False, "categoria": categoria,
            "estado_clinico": estado, "riesgo_vital": riesgo_vital, "antiguedad_mayor_1_anio": antiguo, "dias_espera": dias_espera,
            "ges": ges_info, "medicion_alerta": medicion_alerta,
            "riesgo_inasistencia": consecutivas >= 2, "no_shows": no_show, "razones": razones}


def clave_orden(r, categoria=None):
    """MINSAL: criterio médico (categoría y riesgo vital) → (grupos de protección: sin datos) → antigüedad > 1 año
    → orden de llegada."""
    return (-ORDEN_CAT[categoria or r["categoria"]], not r["riesgo_vital"], not r["antiguedad_mayor_1_anio"],
            -r["dias_espera"], r["id_paciente"])


def priorizar(perfiles, corte, especialidad=None):
    out = []
    for p in perfiles:
        if p["lista_espera"]["estado"] == "atendido": continue
        if especialidad and p["lista_espera"]["especialidad"] != especialidad: continue
        r = puntuar(p, corte)
        if r: out.append(r)
    activos = sorted([r for r in out if not r["excluido"]], key=clave_orden)
    for i, r in enumerate(activos, 1): r["posicion"] = i
    return activos, [r for r in out if r["excluido"]]


if __name__ == "__main__":
    perfiles = json.load(open(sys.argv[1], encoding="utf-8"))
    corte = d(sys.argv[2]) if len(sys.argv) > 2 else date(2026, 10, 13)
    activos, excl = priorizar(perfiles, corte)
    print(f"corte {corte}: {len(activos)} activos, {len(excl)} excluidos")
    for r in activos[:10]: print(r["posicion"], r["id_paciente"], r["categoria"], r["estado_clinico"], r["dias_espera"])
