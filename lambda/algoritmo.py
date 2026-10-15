"""Algoritmo decisor 'rúbrica + fórmula fija' (variante E+F): el LLM lee, el código decide.

evaluar_paciente: lee el historial N veces con la rúbrica (Bedrock, en paralelo), aplica la fórmula fija a cada
lectura, corre los controles y devuelve el registro auditable. Si un control falla, la categoría final es la de las
reglas actuales (puntaje.py). Solo pide revisión del especialista cuando el resultado BAJARÍA a alguien (decisión
clínica); un problema técnico de la IA (cita que no calza, lecturas distintas, falla) usa las reglas sin pedir nada a nadie.

combinar: la parte sin LLM (validar citas, fórmula, controles). Es pura: se guarda la lectura y se vuelve a combinar a
otra fecha de corte sin llamar al LLM (la ventana de un evento depende del corte).
"""
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import controles
import decisor
import puntaje
import rubrica

CORRIDAS = 3


def combinar(perfil, corte, crudas, kb, reglas=None):
    """crudas: [(RespuestaRubrica | None, meta)]. Devuelve el resultado de la fórmula y los controles."""
    reglas = reglas or puntaje.puntuar(perfil, corte)
    hist = rubrica.historial(perfil, corte)
    lecturas = [(r, m, rubrica.validar_citas(r, hist) if r else []) for r, m in crudas]
    resultados, errores = [], []
    for r, _, cm in lecturas:
        if r is None or cm:  # sin lectura o con citas que no existen: no se decide con ella (el control lo registra)
            resultados.append(None)
            continue
        try:
            resultados.append(decisor.decidir(perfil, r, corte, kb))
        except Exception as e:  # nunca tumba la lista ni el evento: queda con las reglas y lo revisa un humano
            resultados.append(None)
            errores.append(f"{type(e).__name__}: {str(e)[:160]}")
    motivos = controles.evaluar(lecturas, resultados, reglas)
    if errores:
        motivos.append({"motivo": "error_formula", "detalle": errores[0]})
    bloquea = [m for m in motivos if m["motivo"] in controles.BLOQUEANTES]
    # "bajaría" es una decisión clínica solo si la lectura está verificada; si la IA leyó mal, es un problema técnico
    tecnicos = [m for m in bloquea if m["motivo"] not in controles.CLINICOS + ("discrepancia",)]
    clinicos = [m for m in bloquea if m["motivo"] in controles.CLINICOS] if not tecnicos else []
    propuesto = next((x for x in resultados if x), None)
    if bloquea or not propuesto:
        final = {"categoria_final": reglas["categoria"], "descompensacion_grave_final": reglas["riesgo_vital"],
                 "fecha_descompensacion": reglas.get("fecha_descompensacion"), "razones": reglas["razones"]}
    else:
        grave = propuesto["descompensacion_grave"]
        final = {"categoria_final": propuesto["categoria"], "descompensacion_grave_final": grave,
                 "fecha_descompensacion": (reglas.get("fecha_descompensacion") or propuesto["fecha_evento"]) if grave else None,
                 "razones": propuesto["razones"]}
    return {"lecturas_validadas": lecturas, "categoria_reglas": reglas["categoria"], "categoria_rubrica": propuesto and propuesto["categoria"],
            "categorias_corridas": [x and x["categoria"] for x in resultados],
            "controles": motivos, "requiere_revision": bool(clinicos), "respaldo_reglas": bool(bloquea), **final,
            "estado_clinico_rubrica": propuesto and propuesto["estado_clinico"],
            "revision_sugerida": [rv for rv in (propuesto or {}).get("revision", []) if not rv["bloqueante"]],
            "movido_por_rubrica": (not bloquea) and bool(propuesto) and propuesto["categoria"] != reglas["categoria"]}


def evaluar_paciente(perfil, corte, cliente, kb=None, corridas=CORRIDAS):
    kb = kb or decisor.cargar_kb()
    reglas = puntaje.puntuar(perfil, corte)
    if reglas is None or reglas.get("excluido"):
        return None  # no está en la lista a esa fecha (aún no ingresa, fallecido o atendido): nada que decidir
    dx = decisor.kb_diagnostico(kb, perfil["lista_espera"]["diagnostico_cie10"])
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=corridas) as ex:
        crudas = list(ex.map(lambda _: rubrica.leer_rubrica(perfil, corte, dx, cliente), range(corridas)))
    c = combinar(perfil, corte, crudas, kb, reglas)
    lecturas = c.pop("lecturas_validadas")
    return {
        "id_paciente": perfil["id_paciente"], "fecha_corte": corte.isoformat(), "firma": rubrica.firma(perfil, corte),
        "fecha": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "algoritmo": "rubrica", "version_rubrica": rubrica.VERSION_RUBRICA, "version_kb": kb["version"],
        "hash_prompt": rubrica.hash_prompt(), "modelo": getattr(cliente, "model_id", "?"), "corridas": corridas,
        "lecturas": [{"respuestas": r.model_dump() if r else None, "meta": m, "citas_invalidas": cm} for r, m, cm in lecturas],
        **c,
        "latencia_s": round(time.perf_counter() - t0, 2),
        "tokens_entrada": sum((m.get("tokens_entrada") or 0) for _, m, _ in lecturas),
        "tokens_salida": sum((m.get("tokens_salida") or 0) for _, m, _ in lecturas),
    }


def vigente(e, perfil, corte, kb, firma=None):
    """¿La evaluación guardada sirve para esta fecha de corte? Mismo historial (firma), misma rúbrica, misma base de
    conocimiento y hecha a un corte anterior o igual (lo que vino después ya está en la firma)."""
    return bool(e) and e["fecha_corte"] <= corte.isoformat() and e.get("version_rubrica") == rubrica.VERSION_RUBRICA and \
        e.get("hash_prompt") == rubrica.hash_prompt() and e.get("version_kb") == kb["version"] and e["firma"] == (firma or rubrica.firma(perfil, corte))


def reaplicar(e, perfil, corte, kb, reglas=None):
    """Vuelve a combinar las lecturas guardadas a esta fecha de corte (sin LLM): ventanas y razones quedan al día."""
    crudas = [(rubrica.RespuestaRubrica.model_validate(x["respuestas"]) if x["respuestas"] else None, x["meta"]) for x in e["lecturas"]]
    c = combinar(perfil, corte, crudas, kb, reglas)
    c.pop("lecturas_validadas")
    return {**e, **c, "fecha_corte_aplicada": corte.isoformat()}
