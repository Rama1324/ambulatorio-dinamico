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
  protección (el dataset no los trae), 3) antigüedad en lista > 1 año. Luego LACE (experimental, solo desempata)
  y orden de llegada (fecha de ingreso).
Capa 3 · Banderas (no cambian el orden)
  - Posible incumplimiento GES: verificar (el plazo corre desde un hito que el registro no trae).
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
# (I10 HTA, K21 ERGE, F41, G43, E66, M17, M54, M75) mantienen su prioridad y quedan marcados para revisión.
FILA_DESCOMPENSADO = {
    "I50": ("Insuficiencia cardíaca descompensada", "alta", 85),
    "I20": ("Angina inestable", "alta", 85),
    "J44": ("EPOC grave no controlado", "alta", 95),
    "J45": ("Asma grave no controlada", "alta", 95),
    "K70": ("Cirrosis hepática descompensada", "alta", 95),
    "E11": ("DM2 descontrolada", "media", 101),
    "E03": ("Hipotiroidismo sintomático", "media", 94),
    "G40": ("Epilepsia con crisis mensuales (deja de ser 'epilepsia controlada', baja)", "media", 103),
    "F32": ("Episodio depresivo", "alta", 110),  # PSIQUIATRÍA ADULTO, verificado en imagen de la pág. 110
}
# Equivalencias CIE-10 → fila de la tabla que son interpretación del equipo y deben validarse con el especialista.
EQUIVALENCIA_A_VALIDAR = {
    "K70": "K70 es enfermedad hepática alcohólica; se asimila a la fila de cirrosis",
    "I20": "I20 incluye toda angina de pecho; la fila oficial es solo angina inestable",
    "G40": "la tabla no tiene fila 'epilepsia descompensada'; se usa 'crisis mensuales'",
    "F32": "la fila 'Episodio depresivo' (alta) se usa para el episodio depresivo descompensado",
}
# Cáncer activo o sospechoso. En la sección del HLF de la tabla SSMSO 2025 TODA fila de cáncer activo o sospechoso es
# ALTA (verificado en imagen: págs. 88, 94, 95 y 111); "antecedente de neoplasia en remisión" es BAJA (pág. 102) y no sube.
# Especialidades con fila propia → esa fila; las demás usan el patrón de la tabla (equivalencia a validar).
FILA_ONCOLOGICA = {
    "Broncopulmonar": ("Cáncer de pulmón sospechoso", "alta", 95),
    "Traumatología": ("Osteosarcoma / tumores musculoesqueléticos", "alta", 111),
}
PATRON_ONCOLOGICO = ("toda fila de cáncer activo o sospechoso de la tabla del HLF es prioridad alta (págs. 88, 94, 95, 111)",
                     "alta", "88, 94, 95, 111")
# Mediciones que reflejan semanas o meses (no un momento): las únicas que pueden aparecer como razón de prioridad
MEDICIONES_ESTABLES = ("HbA1c", "PHQ9")

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

# Índice LACE — van Walraven C, et al. CMAJ 2010;182(6):551-7, Tabla 3 (riesgo de muerte o reingreso no planificado).
# L: días de estada (el dataset no los trae → 0) · A: ingreso de urgencia = 3 · C: Charlson → 0,1,2,3, ≥4 = 5
# · E: consultas en urgencia en los 6 meses previos → 0,1,2,3, ≥4 = 4.
LACE_FUENTE = "Índice LACE (van Walraven et al., CMAJ 2010)"
LACE_VENTANA_DIAS = 182  # "previous 6 months" del índice LACE
# Pesos de Charlson usados por el índice LACE (nota de la Tabla 3); CIE-10 según Quan et al., Med Care 2005.
CHARLSON_LACE = {
    "I50": (2, "insuficiencia cardíaca congestiva"),
    "J44": (2, "enfermedad pulmonar crónica"),
    "J45": (2, "enfermedad pulmonar crónica"),
    "K70": (2, "enfermedad hepática leve"),
    "E11": (1, "diabetes sin complicaciones"),
}
# Condiciones de Charlson con su peso en el índice LACE (nota de la Tabla 3, van Walraven 2010), para registrar comorbilidades.
CONDICIONES_CHARLSON = [
    ("infarto agudo al miocardio", 1), ("enfermedad vascular periférica", 1), ("enfermedad cerebrovascular", 1),
    ("diabetes sin complicaciones", 1), ("insuficiencia cardíaca congestiva", 2), ("enfermedad pulmonar crónica", 2),
    ("enfermedad hepática leve", 2), ("cáncer", 2), ("demencia", 3), ("enfermedad del tejido conectivo", 3),
    ("enfermedad hepática moderada a severa", 4), ("infección por VIH", 4), ("cáncer metastásico", 6),
]
PESO_CHARLSON = dict(CONDICIONES_CHARLSON)


def charlson(perfil):
    """Suma de pesos Charlson (LACE) del diagnóstico de la SIC + comorbilidades registradas, cada condición una vez."""
    conds = {}
    peso, nombre = CHARLSON_LACE.get(perfil["lista_espera"]["diagnostico_cie10"], (0, None))
    if nombre:
        conds[nombre] = peso
    for c in perfil["paciente"].get("comorbilidades", []):
        if c.get("condicion") in PESO_CHARLSON:
            conds[c["condicion"]] = PESO_CHARLSON[c["condicion"]]
        elif c.get("cie10") in CHARLSON_LACE:
            p, n = CHARLSON_LACE[c["cie10"]]
            conds[n] = p
    return sum(conds.values()), conds


def indice_lace(perfil, corte):
    """Devuelve el desglose LACE con los eventos con fecha ≤ corte."""
    desde = corte.toordinal() - LACE_VENTANA_DIAS
    evs = [e for e in perfil.get("eventos_clinicos", []) if desde <= d(e["fecha_evento"]).toordinal() <= corte.toordinal()]
    hosp = [e for e in evs if e["tipo_evento"] == "hospitalizacion"]
    urg = sum(1 for e in evs if e["tipo_evento"] == "visita_urgencia")
    total_c, conds = charlson(perfil)
    cond = ", ".join(f"{n} ({p})" for n, p in conds.items())
    otras = [c.get("nombre") for c in perfil["paciente"].get("comorbilidades", []) if c.get("condicion") not in PESO_CHARLSON
             and c.get("cie10") not in CHARLSON_LACE]
    if otras:
        cond = (cond + "; " if cond else "") + "sin peso Charlson: " + ", ".join(otras)
    partes = [
        {"letra": "L", "nombre": "Días de estada", "valor": "sin dato en el registro", "puntos": 0},
        {"letra": "A", "nombre": "Ingreso de urgencia (6 meses)", "valor": f'{len(hosp)} hospitalización(es)' if hosp else "no", "puntos": 3 if hosp else 0},
        {"letra": "C", "nombre": "Comorbilidad (Charlson)", "valor": f"Charlson {total_c}: {cond}" if cond else "sin condición de Charlson",
         "puntos": total_c if total_c < 4 else 5},
        {"letra": "E", "nombre": "Consultas en urgencia (6 meses)", "valor": str(urg), "puntos": min(urg, 4)},
    ]
    return {"total": sum(p["puntos"] for p in partes), "partes": partes, "fuente": LACE_FUENTE, "experimental": True,
            "datos_faltantes": ["días de estada (L): no vienen en el registro",
                                "comorbilidades: solo el diagnóstico de la SIC y las registradas por el equipo"],
            "uso": "solo desempata dentro de la misma categoría, después de la antigüedad; validado para reingreso o "
                   "muerte tras alta hospitalaria, no para listas de espera"}


def d(s): return date.fromisoformat(s)


def descompensa(ev):
    """Evento que el propio dataset etiqueta como descompensación o severidad grave
    (urgencia ESI 2, descompensación, hospitalización, UCI). Un hallazgo oncológico no es una descompensación."""
    if ev.get("tipo_evento") in ("hallazgo_oncologico", "criterio_clinico", "combinacion_riesgo") or no_relacionado(ev):
        return False
    return ev.get("severidad") == "grave" or "descompensaci" in (ev.get("subtipo") or "").lower()


def no_relacionado(ev):
    """El evento se registró como NO relacionado con el diagnóstico por el que espera (p. ej. una amputación traumática en
    un paciente de cardiología). Sin dato se asume relacionado, como trae el registro del hospital ("ESI 2 (Cardiología)")."""
    return ev.get("relacionado") is False


def regla_oncologica(eventos, especialidad):
    """Último hallazgo oncológico (cáncer confirmado o sospecha) y la fila de la tabla que lo respalda."""
    onco = [e for e in eventos if e.get("tipo_evento") == "hallazgo_oncologico"]
    if not onco:
        return None
    fila = FILA_ONCOLOGICA.get(especialidad)
    return {"evento": onco[-1], "fila": fila or PATRON_ONCOLOGICO, "a_validar": fila is None}


def regla_criterio(eventos):
    """Último resultado de los criterios clínicos por enfermedad (criterios.py) y si hubo una excepción de urgencia."""
    crit = [e for e in eventos if e.get("tipo_evento") == "criterio_clinico"]
    if not crit:
        return None
    u = crit[-1]
    return {"evento": u, "nivel": u.get("nivel_criterio"), "urgencia": any(e.get("urgencia") for e in crit)}


def aplicar_criterio(categoria, c, razones):
    """Solo sube (nunca baja: lo decide el especialista). La urgencia prevalece: prioridad alta. Devuelve la categoría."""
    e = c["evento"]
    fuente = e.get("fuente") or "Criterios clínicos por especialidad"
    nueva = categoria
    if c["nivel"]:
        crit = e.get("texto_criterio") or e["detalle"]
        if ORDEN_CAT[c["nivel"]] > ORDEN_CAT[categoria]:
            texto, nueva = f'{crit} → prioridad {c["nivel"]}', c["nivel"]
        elif ORDEN_CAT[c["nivel"]] < ORDEN_CAT[categoria]:
            texto = f'{crit} → sería {c["nivel"]}; se mantiene {categoria} (bajar lo decide el especialista)'
        else:
            texto = f'{crit} → prioridad {c["nivel"]} (coincide)'
        razones.append({"factor": "criterio_clinico", "valor": texto, "fuente": fuente, "riesgo": e.get("riesgo")})
    if c["urgencia"]:  # la urgencia prevalece sobre la clasificación electiva: alta y primera razón
        razones.insert(0, {"factor": "urgencia", "valor": e.get("texto_urgencia") or e["detalle"], "fuente": fuente, "riesgo": e.get("riesgo")})
        nueva = "alta"
    return nueva


def regla_combinacion(eventos):
    """Combinaciones de riesgo verificadas (combinaciones.py): urgencias, subidas a alta y alertas no listadas."""
    ev = [e for e in eventos if e.get("tipo_evento") == "combinacion_riesgo"]
    return {"eventos": ev, "urgencia": any(e.get("urgencia") for e in ev)} if ev else None


def aplicar_combinacion(categoria, c, razones, senales):
    """Solo sube. Urgencia: alta y primera razón. Alerta no listada: razón visible + señal para el equipo (no cambia)."""
    for e in c["eventos"]:
        for a in e.get("combinaciones", []):
            f = a.get("fuente") or {}
            fuente = f'{f.get("documento", "Combinaciones de riesgo")}' + (f': "{f["cita"]}"' if f.get("cita") else "") + (f' · {f["url"]}' if f.get("url") else "")
            valor = f'{a["nombre"]}: "{a["cita_gatillo"]}" → riesgo de {a["desenlace"]} (letalidad nivel {a.get("letalidad", "?")})'
            if a["efecto"] == "urgencia":
                razones.insert(0, {"factor": "urgencia", "valor": "combinación de riesgo · " + valor, "fuente": fuente, "riesgo": a.get("riesgo")})
            elif a["efecto"] == "alta":
                sube = ORDEN_CAT["alta"] > ORDEN_CAT[categoria]
                razones.append({"factor": "combinacion", "valor": valor + (" → prioridad alta" if sube else " (ya es alta)"), "fuente": fuente,
                                "riesgo": a.get("riesgo")})
        if e.get("nivel_criterio") == "alta":
            categoria = "alta"
        for a in e.get("alertas", []):
            razones.append({"factor": "alerta_combinacion", "valor": f'{a["descripcion"]}: "{a["cita"]}"' + ("" if a.get("riesgo") else " · no está en la lista de combinaciones con fuente"),
                            "fuente": a.get("fuente") or "Detectado por la IA en el texto (red de seguridad, sin regla con fuente)",
                            "riesgo": a.get("riesgo")})
            senales.append({"motivo": f'posible combinación de riesgo no listada: {a["descripcion"]}', "fecha": e["fecha_evento"],
                            "registrado": e.get("registrado")})
    return categoria


def agudeza(ev):
    """Gravedad del evento para ordenar entre descompensados de la misma prioridad (categorización de urgencia C1–C5 / ESI):
    3 = UCI o ESI/C1 (emergencia vital inmediata) · 2 = hospitalización, ESI/C2 o descompensación grave · 1 = moderada."""
    if not ev:
        return 0
    if ev.get("subtipo") in ("ingreso UCI", "triage ESI 1"):
        return 3
    return 2 if ev.get("severidad") == "grave" else 1


# ---------- Evidencia del informe de investigación (15-10-2026): reglas oficiales del registro, piso, letalidad, plazo ----------
# Letalidad de una descompensación por diagnóstico (1 = más letal). Ordinal y aproximado; cifras verificadas en PubMed.
LETALIDAD_DX = {
    "K70": (1, "cirrosis descompensada: hemorragia variceal 16% de mortalidad a 6 semanas (Reverter 2014, PMID 24148622); peritonitis bacteriana espontánea 31,5% a 1 mes y 66% a 1 año (Arvaniti 2010, PMID 20558165)"),
    "I50": (2, "tras hospitalizarse por insuficiencia cardíaca, 24,5–29,6% de mortalidad a 1 año (ICARO Chile, PMID 15332366; Ciapponi 2016, PMID 27553287)"),
    "J44": (2, "tras una exacerbación hospitalizada de EPOC, 23% de mortalidad a 1 año, 35% si estuvo en UCI (Groenewegen 2003, PMID 12907529)"),
    "I20": (2, "infarto: 14,2% de mortalidad hospitalaria en Chile (Nazzal 2011); síndrome coronario agudo ≈7,9% a 6 meses (GRACE, PMID 17032691)"),
    "I10": (2, "emergencia hipertensiva: 12,5% de mortalidad hospitalaria y 38,9% a 12 meses (Guiga 2017, PMID 28866866)"),
    "F32": (3, "tras un intento de suicidio, 1,6% de suicidio a 12 meses (Carroll 2014, PMID 24587141); tras un alta psiquiátrica el riesgo se concentra en los primeros 3 meses (Chung 2017, PMID 28564699)"),
    "E11": (3, "hipoglicemia grave: 28,3% de mortalidad a 3 años (Lee 2018, PMID 29127240); estado hiperosmolar 10–20% (Pasquel 2014, PMID 25342831)"),
    "G40": (3, "estado epiléptico convulsivo: 15,9% de mortalidad en adultos (Neligan 2019, PMID 31135807)"),
    "J45": (3, "asma hospitalizada sin ventilación ~0,4–1%; con ventilación mecánica 16,5% (Marquette 1992, PMID 1626819)"),
    "E03": (3, "el coma mixedematoso tiene 29,5% de mortalidad (Ono 2017, PMID 28142035), aunque es raro"),
}
# Plazo de referencia por prioridad (Queensland CPC: Cat 1 ≤30, Cat 2 ≤90, Cat 3 ≤365 días). La norma chilena no fija plazos
# No GES: es una referencia, no una regla que mueva a nadie.
PLAZO_CATEGORIA = {"alta": 30, "media": 90, "baja": 365}
RIESGO_ESPERA = ("Esperar más del plazo aumenta el riesgo: en lista de espera cardiológica, los pacientes 'no urgentes' acumularon más "
                 "muertes porque esperaron más (OR 1,66; Sobolev 2006, PMID 16799363); en cáncer, cada 4 semanas de retraso eleva la "
                 "mortalidad 6–8% (Hanna 2020, PMID 33148535)")
_REG = {}


def criterios_registro():
    """Criterios oficiales (Queensland CPC / NICE) de los diagnósticos del registro, por CIE-10."""
    if "por_cie" not in _REG:
        import json
        import os
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "conocimiento", "criterios_registro.json"), encoding="utf-8") as f:
            kb = json.load(f)
        _REG["por_cie"] = {c: e for s in kb["especialidades"] for e in s["enfermedades"] for c in e["cie10"]}
    return _REG["por_cie"]


def _razon_registro(enf, nivel, criterio, detalle):
    return {"factor": "criterio_registro", "valor": f"{criterio} ({detalle}) → prioridad {nivel}",
            "fuente": f'{enf["niveles"][nivel]["justificacion"]} · {enf["fuente_url"]}', "riesgo": enf.get("riesgo")}


def aplicar_registro(perfil, corte, categoria, razones):
    """Reglas oficiales que se calculan con el registro (sin IA), por diagnóstico. Solo suben. Devuelve la categoría."""
    le = perfil["lista_espera"]
    enf = criterios_registro().get(le["diagnostico_cie10"])
    if not enf:
        return categoria
    cie = le["diagnostico_cie10"]
    evs = [e for e in perfil.get("eventos_clinicos", []) if d(e["fecha_evento"]) <= corte and not no_relacionado(e)
           and e.get("tipo_evento") in ("visita_urgencia", "hospitalizacion")]
    def en(dias):
        return [e for e in evs if (corte - d(e["fecha_evento"])).days <= dias]

    def sube(nivel, criterio, detalle):
        nonlocal categoria
        if ORDEN_CAT[nivel] > ORDEN_CAT[categoria]:
            razones.append(_razon_registro(enf, nivel, criterio, detalle))
            categoria = nivel
    if cie in ("J45", "J46"):
        uci = [e for e in en(365) if e.get("subtipo") == "ingreso UCI"]
        if uci:
            sube("alta", "crisis de asma con UCI en los últimos 12 meses", f'UCI el {uci[-1]["fecha_evento"]}')
        hosp = [e for e in en(183) if e["tipo_evento"] == "hospitalizacion"]
        if hosp:
            sube("media", "hospitalización por asma en los últimos 6 meses", f'el {hosp[-1]["fecha_evento"]}')
    if cie in ("J44", "J43"):
        n = len(en(365))
        if n > 3:
            sube("media", "más de 3 exacerbaciones o consultas en urgencia en 12 meses", f"{n} en 12 meses")
    if cie in ("E11", "E10", "E13", "E14"):
        serie = sorted([m for m in perfil.get("mediciones", []) if m["tipo_medicion"] == "HbA1c" and d(m["fecha_medicion"]) <= corte],
                       key=lambda m: m["fecha_medicion"])[-2:]
        if len(serie) == 2 and serie[1]["valor"] > serie[0]["valor"]:
            v = serie[1]["valor"]
            det = f'HbA1c {serie[0]["valor"]:g} → {v:g}% ({serie[1]["fecha_medicion"]})'
            if v > 10:
                sube("alta", "HbA1c > 10% con deterioro reciente", det)
            elif v >= 8:
                sube("media", "HbA1c 8–10% con deterioro reciente", det)
    piso = enf.get("piso")
    if piso and ORDEN_CAT[piso] > ORDEN_CAT[categoria]:
        razones.append({"factor": "piso", "valor": f'{enf["enfermedad"]}: no tiene prioridad baja → prioridad {piso}',
                        "fuente": f'{enf["niveles"]["baja"]["justificacion"]} · {enf["fuente_url"]}', "riesgo": enf.get("riesgo")})
        categoria = piso
    if cie in ("F32", "F33"):
        phq = sorted([m for m in perfil.get("mediciones", []) if m["tipo_medicion"] == "PHQ9" and d(m["fecha_medicion"]) <= corte],
                     key=lambda m: m["fecha_medicion"])
        if phq and phq[-1]["valor"] >= 16:
            razones.append({"factor": "alerta_clinica", "valor": f'PHQ-9 = {phq[-1]["valor"]:g} ({phq[-1]["fecha_medicion"]}): depresión más grave',
                            "fuente": "NICE NG222: PHQ-9 ≥ 16 = \"more severe depression\" (no cambia la prioridad por sí solo)",
                            "riesgo": "Preguntar directamente por ideación suicida (NICE NG222); con plan o intención, derivar de inmediato."})
    return categoria



def razon_oncologica(o):
    e, (texto, prioridad, pag) = o["evento"], o["fila"]
    cita = (e.get("detalle") or "").replace("Informe (leído por IA): ", "")
    return {"factor": "oncologico", "valor": f'{e["subtipo"]} ({e["fecha_evento"]}){": " + cita if cita else ""} → prioridad {prioridad}' +
            (" · la especialidad no tiene fila oncológica propia: se aplica el criterio de la tabla para todo cáncer" if o["a_validar"] else ""),
            "fuente": f'{FUENTE_TABLA}, pág. {pag}: "{texto}"'}


def estabiliza(ev):
    """Evento que el dataset etiqueta como estabilización o buena respuesta."""
    return ev.get("tipo_evento") == "control_aps" and ev.get("subtipo") in ("estabilización", "buena respuesta")


def senal_revision(ev):
    """Señal de deterioro que no cambia la categoría pero pide revisión del especialista (planteamiento del HLF:
    exámenes alterados y cambios en el tratamiento farmacológico que el especialista no ve al priorizar la SIC)."""
    if ev.get("tipo_evento") == "examen_alterado":
        return "examen alterado"
    if ev.get("tipo_evento") == "cambio_farmaco" and "aument" in (ev.get("subtipo") or "").lower():
        return "aumento de dosis"
    return None


GRUPOS_PROTECCION = {"PRAIS", "NNA bajo protección del Estado", "Valech", "Rettig"}  # MINSAL Ord. 536/2025, criterio 2
ACG_NIVELES = {"G0": "sin clasificación", "G1": "bajo riesgo", "G2": "riesgo intermedio", "G3": "alto riesgo"}  # SSMSO (PDF HLF §4)


def fecha_atencion(perfil):
    """Fecha en que se resolvió la SIC: registrada por el equipo o la primera cita a la que asistió."""
    le = perfil["lista_espera"]
    if le.get("fecha_atencion"):
        return le["fecha_atencion"]
    asistio = sorted(c["fecha_cita"] for c in perfil.get("citaciones", []) if c["estado_cita"] == "asistio")
    return asistio[0] if asistio else None


def inasistencias_consecutivas(citas):
    """Máximo de inasistencias en citas consecutivas (causal 8: 'dos inasistencias consecutivas').
    Cualquier otra cita entre medio (asistió, reprogramó, canceló) corta la racha."""
    racha = mejor = 0
    for c in sorted(citas, key=lambda c: c["fecha_cita"]):
        racha = racha + 1 if c["estado_cita"] == "no_asistio" else 0
        mejor = max(mejor, racha)
    return mejor


def puntuar(perfil, corte):
    pac, le = perfil["paciente"], perfil["lista_espera"]
    if pac.get("fallecido") and pac.get("fecha_defuncion") and d(pac["fecha_defuncion"]) <= corte:
        return {"id_paciente": perfil["id_paciente"], "excluido": True, "motivo": "fallecido", "fecha": pac["fecha_defuncion"], "razones": []}
    ingreso = d(le["fecha_ingreso_lista"])
    if ingreso > corte:
        return None  # aún no ingresaba a la lista
    if le.get("estado") == "atendido":  # sale de la lista solo desde la fecha de atención (principio de fecha de corte)
        fa = fecha_atencion(perfil)
        if not fa or d(fa) <= corte:
            return {"id_paciente": perfil["id_paciente"], "excluido": True, "motivo": "atendido", "fecha": fa, "razones": []}

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
    validar = f' · equivalencia usada: {EQUIVALENCIA_A_VALIDAR[cie]}' if cie in EQUIVALENCIA_A_VALIDAR else ""
    if estado == "descompensado":
        if fila and ORDEN_CAT[fila[1]] > ORDEN_CAT[inicial]:
            categoria = fila[1]
            razones.append({"factor": "tabla_oficial", "valor": f'"{fila[0]}" → prioridad {fila[1]}{validar}',
                            "fuente": f"{FUENTE_TABLA}, pág. {fila[2]}"})
        elif fila:
            razones.append({"factor": "tabla_oficial", "valor": f'"{fila[0]}" → prioridad {fila[1]} (no supera la actual){validar}',
                            "fuente": f"{FUENTE_TABLA}, pág. {fila[2]}"})
        else:
            razones.append({"factor": "tabla_oficial", "valor": "la tabla del HLF no tiene fila para este diagnóstico descompensado: "
                                                                "se mantiene la prioridad y se sugiere revisión clínica",
                            "fuente": FUENTE_TABLA})
    onco = regla_oncologica(eventos, le["especialidad"])
    if onco:
        categoria = categoria if ORDEN_CAT[categoria] >= ORDEN_CAT[onco["fila"][1]] else onco["fila"][1]
        razones.append(razon_oncologica(onco))
    crit = regla_criterio(eventos)
    if crit:
        categoria = aplicar_criterio(categoria, crit, razones)
    comb = regla_combinacion(eventos)
    alertas_comb = []
    if comb:
        categoria = aplicar_combinacion(categoria, comb, razones, alertas_comb)
    categoria = aplicar_registro(perfil, corte, categoria, razones)
    urgencia_hoy = bool((crit and crit["urgencia"]) or (comb and comb["urgencia"]))
    # Letalidad (1 = más letal): de la descompensación de su diagnóstico y de las urgencias/combinaciones verificadas
    tiers = [e["letalidad"] for e in eventos if e.get("letalidad") and e.get("tipo_evento") in ("criterio_clinico", "combinacion_riesgo")]
    if estado == "descompensado" and cie in LETALIDAD_DX:
        tiers.append(LETALIDAD_DX[cie][0])
        for x in razones:
            if x["factor"] in ("tabla_oficial", "riesgo_vital") and "riesgo" not in x:
                x["riesgo"] = LETALIDAD_DX[cie][1][0].upper() + LETALIDAD_DX[cie][1][1:] + "."
    letalidad = min(tiers) if tiers else 9
    # la última urgencia (para saber si el especialista ya la revisó después: así sale del carril de urgencia)
    urg_ev = max((e for e in eventos if e.get("urgencia") and e.get("tipo_evento") in ("criterio_clinico", "combinacion_riesgo")),
                 key=lambda e: (e["fecha_evento"], e.get("registrado") or ""), default=None)
    if riesgo_vital:
        razones.insert(0, {"factor": "riesgo_vital",
                           "valor": f'Descompensación grave ({fila[0]}) sin registro posterior de estabilización: su prioridad '
                                    f'debe revisarla el especialista apenas el evento llega al sistema; el especialista decide',
                           "fuente": "MINSAL: criticidad / riesgo vital (SSMSO 2025, pág. 4) · " f"{FUENTE_TABLA}, pág. {fila[2]}"})
    elif estado == "estabilizado":
        razones.append({"factor": "evento", "valor": f'{ult_estab["subtipo"]} ({ult_estab["fecha_evento"]}): '
                                                    "el sistema no baja la prioridad solo; puede ajustarla el equipo clínico",
                        "fuente": "Principio de diseño: la herramienta propone, el equipo clínico decide"})

    # --- LACE: componente EXPERIMENTAL (validado para muerte/reingreso tras alta hospitalaria, no para ordenar
    # consultas de especialidad). Solo desempata al final; datos faltantes (días de estada) se informan. ---
    lace = indice_lace(perfil, corte)
    if lace["total"]:
        razones.append({"factor": "lace", "valor": f'{lace["total"]} puntos (' + ", ".join(
            f'{p["letra"]} {p["puntos"]}' for p in lace["partes"] if p["puntos"]) + ") · experimental, solo desempata",
            "fuente": LACE_FUENTE + " — adaptado; requiere validación local"})

    # --- Capa 2: criterios de orden MINSAL ----------------------------------------
    antiguo = dias_espera > DIAS_ANTIGUEDAD
    razones.append({"factor": "dias_espera", "valor": f"{dias_espera} días en lista" + (" (más de 1 año)" if antiguo else ""),
                    "fuente": "MINSAL Ord. 536/2025: antigüedad > 1 año"})

    # --- Capa 3: banderas ---------------------------------------------------------
    # GES: la garantía corre desde un hito clínico (p. ej. la derivación con confirmación diagnóstica) que el registro
    # no trae; se usa el ingreso a la lista como aproximación → se informa "posible incumplimiento: verificar".
    ges = GES_ESPECIALISTA.get(cie)
    ges_info = None
    if ges and pac["edad"] >= ges[3]:
        vencida = dias_espera > ges[2]
        ges_info = {"problema": ges[0], "nombre": ges[1], "plazo_dias": ges[2], "vencida": vencida, "verificar": vencida}
        razones.append({"factor": "ges", "valor": f"GES N°{ges[0]} {ges[1]}: especialista en {ges[2]} días desde la derivación" +
                        (f" — posible incumplimiento: {dias_espera} días desde el ingreso a la lista (verificar el hito real)"
                         if vencida else ""),
                        "fuente": f"auge.minsal.cl, problema de salud N°{ges[0]}"})

    # Señales que piden revisión del especialista (no cambian el orden): fecha y momento de registro para compararlas
    # con la última revisión clínica.
    senales = [{"motivo": senal_revision(e), "fecha": e["fecha_evento"], "registrado": e.get("registrado")}
               for e in eventos if senal_revision(e)]
    if estado == "descompensado" and not fila:
        senales.append({"motivo": "descompensación sin fila oficial en la tabla HLF", "fecha": ult_desc["fecha_evento"],
                        "registrado": ult_desc.get("registrado")})
    if estado == "descompensado" and fila:
        senales.append({"motivo": "descompensación (prioridad ajustada por tabla HLF)", "fecha": ult_desc["fecha_evento"],
                        "registrado": ult_desc.get("registrado")})
    for e in eventos:
        if no_relacionado(e) and e.get("severidad") == "grave":
            senales.append({"motivo": f'evento grave sin relación con {le["diagnostico_texto"]}: {e.get("motivo") or e["subtipo"]} '
                                      "(no cambia esta prioridad; revisar si requiere otra derivación)",
                            "fecha": e["fecha_evento"], "registrado": e.get("registrado")})
    senales += alertas_comb
    if onco:
        senales.append({"motivo": f'hallazgo oncológico: {onco["evento"]["subtipo"]} (prioridad alta por tabla HLF)',
                        "fecha": onco["evento"]["fecha_evento"], "registrado": onco["evento"].get("registrado")})

    grupo = pac.get("grupo_proteccion") if pac.get("grupo_proteccion") in GRUPOS_PROTECCION else None
    if grupo:
        razones.append({"factor": "grupo_proteccion", "valor": grupo, "fuente": "MINSAL Ord. 536/2025, criterio 2: grupos de especial protección"})
    acg = pac.get("acg") if pac.get("acg") in ACG_NIVELES else None
    if acg:
        razones.append({"factor": "acg", "valor": f"{acg} · {ACG_NIVELES[acg]}", "fuente": "Estratificación de riesgo ACG (SSMSO, ficha Rayen)"})

    citas = [c for c in perfil.get("citaciones", []) if d(c["fecha_cita"]) <= corte]
    no_show = sum(1 for c in citas if c["estado_cita"] == "no_asistio")
    consecutivas = inasistencias_consecutivas(citas)

    # Solo mediciones ESTABLES y SOSTENIDAS justifican: los signos vitales (presión, saturación, glicemia capilar, peak flow,
    # dolor) cambian en minutos y no describen el riesgo de las semanas de espera (observación del HLF). HbA1c refleja ~3
    # meses y el PHQ-9 las últimas 2 semanas: cuentan si las DOS últimas están fuera de rango.
    plazo = PLAZO_CATEGORIA[categoria]
    plazo_vencido = dias_espera > plazo
    if plazo_vencido:
        razones.append({"factor": "plazo", "valor": f"{dias_espera} días esperando: supera el plazo de referencia de su prioridad ({plazo} días)",
                        "fuente": "Queensland CPC: Cat 1 ≤ 30, Cat 2 ≤ 90, Cat 3 ≤ 365 días (referencia; la norma chilena No GES no fija plazos)",
                        "riesgo": RIESGO_ESPERA + "."})
    medicion_alerta = False
    for tipo in MEDICIONES_ESTABLES:
        serie = sorted([m for m in perfil.get("mediciones", []) if m["tipo_medicion"] == tipo and d(m["fecha_medicion"]) <= corte],
                       key=lambda m: m["fecha_medicion"])[-2:]
        if len(serie) == 2 and all(m["fuera_de_rango"] for m in serie):
            medicion_alerta = True
            razones.append({"factor": "medicion", "valor": f'{tipo} fuera de rango en dos mediciones seguidas: ' +
                            " y ".join(f'{m["valor"]:g} {m["unidad"]} ({m["fecha_medicion"]})' for m in serie),
                            "fuente": "Rangos de referencia del diccionario de datos HLF · medición estable (no signo vital)"})

    return {"id_paciente": perfil["id_paciente"], "excluido": False, "categoria": categoria,
            "estado_clinico": estado, "riesgo_vital": riesgo_vital, "urgencia_hoy": urgencia_hoy, "lace": lace,
            "urgencia_desde": urg_ev and {"fecha": urg_ev["fecha_evento"], "registrado": urg_ev.get("registrado")},
            "agudeza": agudeza(ult_desc) if estado == "descompensado" else 0, "letalidad": letalidad,
            "plazo_dias": plazo, "plazo_vencido": plazo_vencido, "antiguedad_mayor_1_anio": antiguo, "dias_espera": dias_espera,
            "ges": ges_info, "medicion_alerta": medicion_alerta, "senales": senales, "grupo_proteccion": grupo, "acg": acg,
            "fecha_descompensacion": ult_desc["fecha_evento"] if estado == "descompensado" else None,
            "dias_desde_descompensacion": (corte - d(ult_desc["fecha_evento"])).days if estado == "descompensado" else None,
            "registro_descompensacion": ult_desc.get("registrado") if estado == "descompensado" else None,
            "riesgo_inasistencia": consecutivas >= 2, "no_shows": no_show, "razones": razones}


def clave_orden(r, categoria=None):
    """MINSAL Ord. 536/2025: criterio médico (categoría, descompensación grave y cualquier descompensación vigente)
    → grupos de especial protección → antigüedad > 1 año → LACE (componente experimental, solo desempata) → orden de llegada.
    El criterio médico va antes que el grupo de protección: un descompensado no queda bajo uno estable de la misma prioridad."""
    return (-ORDEN_CAT[categoria or r["categoria"]], not r.get("urgencia_hoy"), not r["riesgo_vital"], r.get("letalidad", 9), -r.get("agudeza", 0),
            r.get("estado_clinico") != "descompensado", not r.get("grupo_proteccion"),
            not r["antiguedad_mayor_1_anio"], -r["lace"]["total"], -r["dias_espera"], r["id_paciente"])


def priorizar(perfiles, corte, especialidad=None):
    out = []
    for p in perfiles:
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
