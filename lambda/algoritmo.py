"""Algoritmo decisor 'rúbrica + fórmula fija' (variante E+F): el LLM lee, el código decide.

evaluar_paciente: lee el historial N veces con la rúbrica (Bedrock, en paralelo), aplica la fórmula fija a cada
lectura, corre los controles y devuelve el registro auditable. Si un control falla, la categoría final es la de las
reglas actuales (puntaje.py) y el paciente queda 'requiere_revision'.
"""
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import controles
import decisor
import puntaje
import rubrica

CORRIDAS = 3


def evaluar_paciente(perfil, corte, cliente, kb=None, corridas=CORRIDAS):
    kb = kb or decisor.cargar_kb()
    reglas = puntaje.puntuar(perfil, corte)
    if reglas is None or reglas.get("excluido"):
        return None  # no está en la lista a esa fecha (aún no ingresa, fallecido o atendido): nada que decidir
    dx = decisor.kb_diagnostico(kb, perfil["lista_espera"]["diagnostico_cie10"])
    hist = rubrica.historial(perfil, corte)
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=corridas) as ex:
        crudas = list(ex.map(lambda _: rubrica.leer_rubrica(perfil, corte, dx, cliente), range(corridas)))
    lecturas = [(r, m, rubrica.validar_citas(r, hist) if r else []) for r, m in crudas]
    resultados = [decisor.decidir(perfil, r, corte, kb) if r else None for r, _, _ in lecturas]
    motivos = controles.evaluar(lecturas, resultados, reglas)
    bloquea = [m for m in motivos if m["motivo"] in controles.BLOQUEANTES]
    propuesto = next((x for x in resultados if x), None)
    if bloquea or not propuesto:
        final_cat, final_grave, final_razones = reglas["categoria"], reglas["riesgo_vital"], reglas["razones"]
    else:
        final_cat, final_grave, final_razones = propuesto["categoria"], propuesto["descompensacion_grave"], propuesto["razones"]
    no_bloq = [rv for rv in (propuesto or {}).get("revision", []) if not rv["bloqueante"]]
    return {
        "id_paciente": perfil["id_paciente"], "fecha_corte": corte.isoformat(), "firma": rubrica.firma(perfil, corte),
        "fecha": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        "algoritmo": "rubrica", "version_rubrica": rubrica.VERSION_RUBRICA, "version_kb": kb["version"],
        "hash_prompt": rubrica.hash_prompt(), "modelo": getattr(cliente, "model_id", "?"), "corridas": corridas,
        "lecturas": [{"respuestas": r.model_dump() if r else None, "meta": m, "citas_invalidas": cm} for r, m, cm in lecturas],
        "categoria_reglas": reglas["categoria"], "categoria_rubrica": propuesto and propuesto["categoria"],
        "categorias_corridas": [x and x["categoria"] for x in resultados],
        "controles": motivos, "requiere_revision": bool(bloquea),
        "categoria_final": final_cat, "descompensacion_grave_final": final_grave,
        "estado_clinico_rubrica": propuesto and propuesto["estado_clinico"],
        "razones": final_razones, "revision_sugerida": no_bloq,
        "movido_por_rubrica": (not bloquea) and bool(propuesto) and propuesto["categoria"] != reglas["categoria"],
        "latencia_s": round(time.perf_counter() - t0, 2),
        "tokens_entrada": sum((m.get("tokens_entrada") or 0) for _, m, _ in lecturas),
        "tokens_salida": sum((m.get("tokens_salida") or 0) for _, m, _ in lecturas),
    }
