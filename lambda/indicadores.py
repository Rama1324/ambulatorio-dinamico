"""Indicadores del hospital: actualización tras un evento, concordancia con el especialista (kappa), cobertura,
espera, trabajo pendiente, contactabilidad y resumen por especialidad."""
import json
from datetime import datetime

import puntaje
from catalogo import ESTADOS_GESTION
from datos import contactos, perfiles_combinados, registros
from lista import lista


def _kappa(pares, cats=("alta", "media", "baja")):
    """Kappa de Cohen entre la categoría propuesta por el sistema y la decisión del equipo clínico."""
    n = len(pares)
    if not n:
        return None
    po = sum(a == b for a, b in pares) / n
    pe = sum((sum(a == c for a, _ in pares) / n) * (sum(b == c for _, b in pares) / n) for c in cats)
    return round((po - pe) / (1 - pe), 2) if pe < 1 else 1.0


N_KAPPA_RECOMENDADO = 50  # con menos revisiones el intervalo de confianza del kappa es demasiado ancho


def _mediana(xs):
    xs = sorted(xs)
    return None if not xs else (xs[len(xs) // 2] if len(xs) % 2 else (xs[len(xs) // 2 - 1] + xs[len(xs) // 2]) / 2)


TRAMOS_ESPERA = [(0, 90, "Menos de 3 meses"), (90, 180, "3 a 6 meses"), (180, 365, "6 meses a 1 año"),
                 (365, 500, "1 año a 500 días"), (500, None, "Más de 500 días")]


def _resumen_especialidad(nombre, pacs, excluidos):
    dias = [p["dias_espera"] for p in pacs]
    return {"especialidad": nombre, "en_espera": len(pacs), **{c: sum(p["categoria"] == c for p in pacs) for c in puntaje.ORDEN_CAT},
            "mas_de_1_anio": sum(d > 365 for d in dias), "mas_de_500_dias": sum(d > 500 for d in dias),
            "mediana_dias": _mediana(dias), "maxima_dias": max(dias, default=0),
            "graves": sum(p["riesgo_vital"] for p in pacs),
            "graves_sin_revisar": sum(bool(p["riesgo_vital"] and p["contactar_hoy"]) for p in pacs),
            "pendientes_revision": sum(p["gestion"]["estado"] == "pendiente_revision" for p in pacs),
            "sin_responsable": sum(not p["gestion"]["responsable"] for p in pacs),
            "egresos": len(excluidos), "fallecidos": sum(e["motivo"] == "fallecido" for e in excluidos),
            "atendidos": sum(e["motivo"] == "atendido" for e in excluidos)}


def kpis(corte, especialidad=None):
    """Indicadores de resultado (todo el hospital o una especialidad): actualización inmediata tras un evento,
    concordancia con el especialista (kappa con su n), cobertura, espera, trabajo pendiente, contactabilidad,
    resumen por especialidad y tramos de espera."""
    todo = lista(corte)
    data = lista(corte, especialidad) if especialidad else todo
    perfs = perfiles_combinados()[0]
    pids = {pid for pid, x in perfs.items() if not especialidad or x["lista_espera"].get("especialidad") == especialidad}
    regs = [r for r in registros() if r["id_paciente"] in pids]
    revs = [json.loads(r["revision"]) for r in regs if r["sk"].startswith("revision#")]
    pares = [(r["categoria_sistema"], r.get("categoria_ajustada") or r["categoria_sistema"]) for r in revs if r.get("categoria_sistema")]
    # Tiempo desde que se registra un evento grave hasta la primera evaluación clínica (decisión o revisión) del paciente
    cierres = {}
    for r in regs:
        if r["sk"].startswith(("decision#", "revision#", "orden#")):
            cierres.setdefault(r["id_paciente"], []).append(json.loads(r.get("decision") or r.get("revision") or r["orden"])["fecha"])
    horas, sin_evaluar = [], 0
    for r in regs:
        if not r["sk"].startswith("evento#"):
            continue
        ev = json.loads(r["evento"])
        if not (ev.get("registrado") and puntaje.descompensa(ev)):
            continue
        despues = sorted(f for f in cierres.get(r["id_paciente"], []) if f >= ev["registrado"])
        if despues:
            horas.append((datetime.fromisoformat(despues[0]) - datetime.fromisoformat(ev["registrado"])).total_seconds() / 3600)
        else:
            sin_evaluar += 1
    vitales = [p for p in data["pacientes"] if p["riesgo_vital"]]
    estados = [p["evaluacion"]["estado"] for p in vitales]
    contactos_todos = [json.loads(r["contacto"]) for r in regs if r["sk"].startswith("contacto#")]
    efectivos = sum(c["resultado"] != "no_contesta" for c in contactos_todos)
    acuerdos = sum(a == b for a, b in pares)
    return {
        "fecha_corte": corte.isoformat(),
        "cobertura": {"evaluados": data["total"], "en_espera": data["total"], "pct": 100.0 if data["total"] else 0,
                      "criterio": "Tabla SSMSO 2025 (HLF) + orden MINSAL Ord. 536/2025, el mismo para toda la lista"},
        "reevaluacion": {
            "recalculo": "automático al registrar cada evento (milisegundos)",
            "eventos_graves_registrados": len(horas) + sin_evaluar, "evaluados": len(horas),
            "sin_evaluar": sin_evaluar, "mediana_horas": None if not horas else round(_mediana(horas), 1),
            "descompensados_en_lista": len(vitales), "evaluacion_pendiente": estados.count("pendiente"),
            "evaluacion_hecha": estados.count("evaluada")},
        "contactabilidad": {"intentos": len(contactos_todos), "efectivos": efectivos,
                            "pct": round(100 * efectivos / len(contactos_todos)) if contactos_todos else None,
                            "pacientes_con_reintentos": sum(c["intentos_sin_respuesta"] > 0 for pid, c in contactos().items() if pid in pids)},
        "concordancia": {"revisiones": len(pares), "acuerdos": acuerdos,
                         "acuerdo_pct": round(100 * acuerdos / len(pares)) if pares else None, "kappa": _kappa(pares),
                         "meta": 0.70, "n_recomendado": N_KAPPA_RECOMENDADO, "suficiente": len(pares) >= N_KAPPA_RECOMENDADO},
        "especialidad": especialidad,
        "por_especialidad": sorted((_resumen_especialidad(e, [p for p in todo["pacientes"] if p["especialidad"] == e],
                                                          [x for x in todo["excluidos"] if x["especialidad"] == e])
                                    for e in sorted({p["especialidad"] for p in todo["pacientes"]})), key=lambda x: -x["en_espera"]),
        "total_hospital": _resumen_especialidad("Todo el hospital", todo["pacientes"], todo["excluidos"]),
        "tramos_espera": [{"tramo": n, "desde": a, "hasta": b_, "pacientes": sum((a == 0 or p["dias_espera"] > a) and (b_ is None or p["dias_espera"] <= b_)
                                                                                   for p in data["pacientes"])} for a, b_, n in TRAMOS_ESPERA],
        "trabajo_pendiente": {"sin_responsable": sum(not p["gestion"]["responsable"] for p in data["pacientes"]),
                              "seguimiento_vencido": sum(p["gestion"]["seguimiento_vencido"] for p in data["pacientes"]),
                              "por_estado": {k: sum(p["gestion"]["estado"] == k for p in data["pacientes"]) for k in ESTADOS_GESTION}},
        "espera": {"mediana_dias": _mediana([p["dias_espera"] for p in data["pacientes"]]),
                   "mas_de_1_anio": sum(p["dias_espera"] > 365 for p in data["pacientes"]),
                   "mas_de_500_dias": sum(p["dias_espera"] > 500 for p in data["pacientes"]),
                   "maxima_dias": max((p["dias_espera"] for p in data["pacientes"]), default=0)},
        "ajustes_manuales": {"vigentes": sum(bool(p.get("ajuste_manual")) for p in data["pacientes"]),
                             "sin_efecto_por_evento": sum(bool(p.get("ajuste_manual_vencido")) for p in data["pacientes"]),
                             "registrados": sum(r["sk"].startswith("orden#") for r in regs)},
        "alertas": {"riesgo_vital": len(vitales), "contactados": sum(not p["contactar_hoy"] for p in vitales),
                    "pendientes": sum(p["contactar_hoy"] for p in vitales),
                    "revision_sugerida": sum(bool(p["revision_sugerida"]) for p in data["pacientes"])},
        "egresos": {"fallecidos": sum(e["motivo"] == "fallecido" for e in data["excluidos"]),
                    "atendidos": sum(e["motivo"] == "atendido" for e in data["excluidos"])},
    }
