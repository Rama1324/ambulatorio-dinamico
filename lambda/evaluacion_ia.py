"""Algoritmo con IA (ALGORITMO=rubrica): Claude lee con rúbrica cerrada y una fórmula fija decide (algoritmo.py).
Aquí se guardan las evaluaciones, se elige la vigente para cada fecha y se corre el barrido nocturno."""
import json
import os

import cliente_ia
import puntaje
from datos import evaluaciones_por_paciente, guardar, hoy, perfiles_combinados


_llm = {"cliente": None}


def algoritmo_activo():
    return os.environ.get("ALGORITMO", "reglas")


def cliente_llm(barrido=False):
    if _llm["cliente"] is not None:  # los tests inyectan un ClienteFalso
        return _llm["cliente"]
    import rubrica
    if cliente_ia.simulado():  # MODEL_ID=simulado: lector determinista sin red, rotulado "simulado"
        return _llm.setdefault("simulado", rubrica.ClienteSimulado())
    clave = "barrido" if barrido else "api"
    if clave not in _llm:
        _llm[clave] = rubrica.ClienteBedrock(timeout_s=20, reintentos=3) if barrido else rubrica.ClienteBedrock(timeout_s=12, reintentos=1)
    return _llm[clave]


def evaluacion_vigente(evs, perfil, corte, kb):
    import algoritmo
    import rubrica
    f = rubrica.firma(perfil, corte)
    return next((e for e in evs if algoritmo.vigente(e, perfil, corte, kb, f)), None)


def estabilidad(lecturas):
    """Qué control de estabilidad tuvo la evaluación (LECTURAS_IA). Con 3 y con 2 lecturas, si no coinciden manda el
    control 'inestable' (rigen las reglas); con 1 no hay con qué comparar: la lectura se verifica (citas, fórmula, no baja
    sola) pero no se sabe si es estable, y así queda escrito en el registro de la evaluación."""
    if lecturas >= 2:
        return {"lecturas": lecturas, "control": True, "nota": f"{lecturas} lecturas: si no coinciden, rigen las reglas"}
    return {"lecturas": 1, "control": False,
            "nota": "1 lectura (LECTURAS_IA=1): sin control de estabilidad; las citas se verifican igual y el resultado no baja a nadie"}


def evaluar_y_guardar(pid, corte, perfs=None, barrido=False):
    import algoritmo
    perfs = perfs or perfiles_combinados()[0]
    n = cliente_ia.lecturas_ia(algoritmo.CORRIDAS)
    reg = algoritmo.evaluar_paciente(perfs[pid], corte, cliente_llm(barrido), corridas=n)
    if reg:
        reg["estabilidad"] = estabilidad(n)
        guardar({"id_paciente": pid, "sk": f"evaluacion#{reg['fecha']}", "evaluacion": json.dumps(reg, ensure_ascii=False, default=str)})
    return reg


def _aplicar_rubrica(activos, perfs, corte, evs=None):
    import algoritmo
    import decisor
    kb, evs = decisor.cargar_kb(), evaluaciones_por_paciente() if evs is None else evs
    out = []
    for r in activos:
        perfil = perfs[r["id_paciente"]]
        e = evaluacion_vigente(evs.get(r["id_paciente"], []), perfil, corte, kb)
        if e:
            e = algoritmo.reaplicar(e, perfil, corte, kb, r)  # mismas lecturas, fórmula a esta fecha de corte (sin LLM)
            grave = e["descompensacion_grave_final"]
            r = {**r, "categoria": e["categoria_final"], "riesgo_vital": grave, "razones": e["razones"],
                 "fecha_descompensacion": e["fecha_descompensacion"] if grave else r.get("fecha_descompensacion"),
                 "registro_descompensacion": r.get("registro_descompensacion") if r.get("riesgo_vital") else (e["fecha"] if grave else None),
                 "algoritmo": "rubrica", "controles": e["controles"],
                 "rubrica": {k: e.get(k) for k in ("fecha", "fecha_corte", "fecha_corte_aplicada", "categoria_reglas", "categoria_rubrica",
                                                   "categorias_corridas", "requiere_revision", "respaldo_reglas", "movido_por_rubrica", "revision_sugerida",
                                                   "version_rubrica", "version_kb", "modelo", "hash_prompt")}}
            # Solo un cambio del algoritmo (sube al paciente) pide revisar de nuevo lo que el equipo ya decidió. Los controles
            # y notas se muestran, pero no anulan una decisión humana (si no, una falla de Bedrock bajaría a alguien).
            extra = [{"motivo": f"algoritmo: sube a {e['categoria_final']} por la rúbrica", "fecha": e["fecha_corte"], "registrado": e["fecha"],
                      "algoritmo": True}] if e["movido_por_rubrica"] else []
            # el detalle de los controles está en la ficha (Fundamento → "Cómo se calculó"); aquí basta un aviso corto
            if e["requiere_revision"]:
                extra.append({"motivo": "la evidencia sugiere que podría bajar de prioridad: lo decide el especialista (ver Fundamento)", "fecha": e["fecha_corte"],
                              "registrado": e["fecha"], "algoritmo": True, "informativa": True})
            r["senales"] = list(r.get("senales", [])) + extra
        else:
            r = {**r, "algoritmo": "reglas (sin evaluación vigente)", "controles": [], "rubrica": None}
        out.append(r)
    return out


def barrido(corte=None, limite=60, en_paralelo=3):
    """Evalúa a quienes no tienen una evaluación vigente o cuya última evaluación falló (lo llama EventBridge Scheduler
    cada noche). 3 pacientes en paralelo x 3 lecturas = 9 llamadas simultáneas a Bedrock (evita el throttling)."""
    import decisor
    from concurrent.futures import ThreadPoolExecutor
    corte = corte or hoy()
    kb = decisor.cargar_kb()
    perfs, _ = perfiles_combinados()
    activos, _ = puntaje.priorizar(list(perfs.values()), corte)
    evs = evaluaciones_por_paciente()

    def falta(pid):
        e = evaluacion_vigente(evs.get(pid, []), perfs[pid], corte, kb)
        return not e or any(m["motivo"] in ("fallo_llm", "error_formula") for m in e["controles"])
    faltan = [r["id_paciente"] for r in activos if falta(r["id_paciente"])][:limite]

    def uno(pid):
        try:
            return evaluar_y_guardar(pid, corte, perfs, barrido=True)
        except Exception as e:  # un paciente con error no corta el barrido
            print(f"barrido: {pid}: {type(e).__name__}: {e}")
            return None
    with ThreadPoolExecutor(max_workers=en_paralelo) as ex:
        regs = list(ex.map(uno, faltan))
    return {"evaluados": len([x for x in regs if x]), "pendientes_antes": len(faltan), "fecha_corte": corte.isoformat()}
