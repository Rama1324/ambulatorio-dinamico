"""Evaluación offline del algoritmo decisor sobre el dataset (desarrollo; llama a Bedrock de verdad).

Brazos:
  A    reglas actuales (lambda/puntaje.py)
  R    rúbrica respondida por CÓDIGO (lector determinista) + fórmula fija: mide si el LLM aporta algo
  E+F  rúbrica respondida por Bedrock (3 corridas) + fórmula fija + controles (lo que se propone activar)
  E0   Claude con un prompt genérico que asigna la prioridad directamente (control)

Uso (desde la raíz, perfil AWS con acceso a Bedrock):
  $env:AWS_PROFILE="hack"; python -X utf8 scripts/evaluar_algoritmo.py --corte 2026-10-13 --paralelo 8
Opcionales: --limite N (pacientes), --precio-entrada 3 --precio-salida 15 (USD por millón de tokens),
            --etiquetas data/etiquetado_30.csv (columnas id_paciente, medico_1, medico_2, ...: alta/media/baja)
Las lecturas se guardan en data/evaluacion/cache/ (no van al repo) para poder retomar sin volver a pagar.
Resultado: docs/algoritmo/EVALUACION.md y data/evaluacion/resultados.json
"""
import argparse
import collections
import csv
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCAL", "1")
os.environ.setdefault("DATA_DIR", os.path.join(RAIZ, "data"))
sys.path.insert(0, os.path.join(RAIZ, "lambda"))
import algoritmo  # noqa: E402
import controles  # noqa: E402
import decisor  # noqa: E402
import puntaje  # noqa: E402
import rubrica  # noqa: E402

ORD = decisor.ORDEN_CAT
CACHE = os.path.join(RAIZ, "data", "evaluacion", "cache")

E0_SISTEMA = """Eres médico especialista en un hospital público chileno. Debes asignar la prioridad clínica (alta, media o baja)
con que este paciente en lista de espera de consulta de especialidad debe ser atendido, según su historial.
Responde con la herramienta asignar_prioridad."""
E0_HERRAMIENTA = {"toolSpec": {"name": "asignar_prioridad", "description": "Prioridad clínica del paciente",
                               "inputSchema": {"json": {"type": "object", "properties": {
                                   "prioridad": {"type": "string", "enum": ["alta", "media", "baja"]},
                                   "justificacion": {"type": "string"}}, "required": ["prioridad"]}}}}


class ClienteCache:
    """Envuelve al cliente real: guarda cada lectura (brazo, paciente, corrida) en disco para retomar."""

    def __init__(self, real, brazo, pid, corrida_base=0):
        self.real, self.brazo, self.pid, self.model_id = real, brazo, pid, real.model_id
        self.n = corrida_base

    def leer(self, sistema, texto, herramienta, max_tokens=900):
        self.n += 1
        ruta = os.path.join(CACHE, f"{self.brazo}_{self.pid}_{self.n}.json")
        if os.path.exists(ruta):
            with open(ruta, encoding="utf-8") as f:
                d = json.load(f)
            if "error" in d:
                raise rubrica.ErrorLectura(d["error"])
            return d["crudo"], d["uso"]
        try:
            crudo, uso = self.real.leer(sistema, texto, herramienta, max_tokens)
            d = {"crudo": crudo, "uso": uso}
        except Exception as e:
            d = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        if "error" in d:
            raise rubrica.ErrorLectura(d["error"])
        return d["crudo"], d["uso"]


# ---------- métricas ----------
def kappa_ponderado(a, b, cats=("baja", "media", "alta")):
    """Kappa de Cohen con ponderación cuadrática (librería estándar)."""
    k = len(cats)
    idx = {c: i for i, c in enumerate(cats)}
    n = len(a)
    if not n:
        return None
    obs = [[0] * k for _ in range(k)]
    for x, y in zip(a, b):
        obs[idx[x]][idx[y]] += 1
    fa = [sum(obs[i]) for i in range(k)]
    fb = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    w = [[((i - j) ** 2) / ((k - 1) ** 2) for j in range(k)] for i in range(k)]
    num = sum(w[i][j] * obs[i][j] for i in range(k) for j in range(k))
    den = sum(w[i][j] * fa[i] * fb[j] / n for i in range(k) for j in range(k))
    return None if den == 0 else round(1 - num / den, 3)


def ic95_bootstrap(a, b, reps=2000, semilla=1):
    rnd = random.Random(semilla)
    vals = []
    for _ in range(reps):
        m = [rnd.randrange(len(a)) for _ in a]
        v = kappa_ponderado([a[i] for i in m], [b[i] for i in m])
        if v is not None:
            vals.append(v)
    vals.sort()
    return (vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals)) - 1]) if vals else (None, None)


def comparar(base, otro):
    sube = sum(ORD[o] > ORD[b] for b, o in zip(base, otro))
    baja = sum(ORD[o] < ORD[b] for b, o in zip(base, otro))
    return {"iguales": len(base) - sube - baja, "suben": sube, "bajan": baja, "kappa_vs_A": kappa_ponderado(base, otro)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corte", default="2026-10-13")
    ap.add_argument("--paralelo", type=int, default=8)
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--corridas", type=int, default=3)
    ap.add_argument("--sin-e0", action="store_true")
    ap.add_argument("--precio-entrada", type=float, default=None, help="USD por millón de tokens de entrada")
    ap.add_argument("--precio-salida", type=float, default=None, help="USD por millón de tokens de salida")
    ap.add_argument("--etiquetas", default=os.path.join(RAIZ, "data", "etiquetado_30.csv"))
    args = ap.parse_args()
    os.makedirs(CACHE, exist_ok=True)
    corte = date.fromisoformat(args.corte)
    kb = decisor.cargar_kb()
    import app
    perfs = [p for p in app.perfiles().values()]
    activos = [p for p in perfs if (r := puntaje.puntuar(p, corte)) and not r.get("excluido")]
    activos.sort(key=lambda p: p["id_paciente"])
    if args.limite:
        activos = activos[:args.limite]
    real = rubrica.ClienteBedrock(timeout_s=40, reintentos=6)
    print(f"{len(activos)} pacientes en lista al {corte} · modelo {real.model_id}")

    t0 = time.perf_counter()

    def eval_ef(p):
        return algoritmo.evaluar_paciente(p, corte, ClienteCache(real, f"EF-{rubrica.VERSION_RUBRICA}", p["id_paciente"]), kb, args.corridas)

    def eval_e0(p):
        cli = ClienteCache(real, "E0", p["id_paciente"])
        dx = decisor.kb_diagnostico(kb, p["lista_espera"]["diagnostico_cie10"])
        _, texto, _ = rubrica.armar_prompt(p, corte, dx)
        texto = texto.split("\n\nRÚBRICA")[0]  # mismo historial, sin rúbrica ni tabla
        try:
            crudo, uso = cli.leer(E0_SISTEMA, texto, E0_HERRAMIENTA, 400)
            return {"categoria": crudo.get("prioridad"), "uso": uso}
        except Exception as e:
            return {"categoria": None, "error": str(e)[:200]}

    with ThreadPoolExecutor(max_workers=args.paralelo) as ex:
        ef = list(ex.map(eval_ef, activos))
        print(f"E+F listo en {time.perf_counter() - t0:.0f} s")
        e0 = [] if args.sin_e0 else list(ex.map(eval_e0, activos))
    dur = time.perf_counter() - t0

    # brazo R: rúbrica respondida por código
    r_cats, r_mov = [], 0
    for p in activos:
        dx = decisor.kb_diagnostico(kb, p["lista_espera"]["diagnostico_cie10"])
        resp = rubrica.RespuestaRubrica.model_validate(rubrica.respuesta_determinista(rubrica.historial(p, corte), dx))
        d = decisor.decidir(p, resp, corte, kb)
        reg = puntaje.puntuar(p, corte)
        mot = controles.evaluar([(resp, {}, [])], [d], reg)
        bloq = [m for m in mot if m["motivo"] in controles.BLOQUEANTES]
        r_cats.append(reg["categoria"] if bloq else d["categoria"])

    A = [x["categoria_reglas"] for x in ef]
    EF = [x["categoria_final"] for x in ef]
    EFprop = [x["categoria_rubrica"] or x["categoria_reglas"] for x in ef]
    estables = sum(len(set(x["categorias_corridas"])) == 1 and None not in x["categorias_corridas"] for x in ef)
    motivos = collections.Counter(m["motivo"] for x in ef for m in x["controles"])
    pacientes_con_control = sum(any(m["motivo"] in controles.BLOQUEANTES for m in x["controles"]) for x in ef)
    lecturas = [l for x in ef for l in x["lecturas"]]
    fallidas = sum(1 for l in lecturas if l["meta"].get("error"))
    envueltas = sum(1 for l in lecturas if l["meta"].get("envoltorio_corregido"))
    # exactitud de lectura del LLM vs lector determinista (por pregunta, primera corrida válida)
    acuerdo = collections.Counter()
    total_q = collections.Counter()
    for p, x in zip(activos, ef):
        dx = decisor.kb_diagnostico(kb, p["lista_espera"]["diagnostico_cie10"])
        det = rubrica.respuesta_determinista(rubrica.historial(p, corte), dx)
        l = next((l["respuestas"] for l in x["lecturas"] if l["respuestas"]), None)
        if not l:
            continue
        for q in ("evento_grave", "estabilizado_despues", "tendencia_medicion", "cambio_tratamiento_por_mal_control"):
            total_q[q] += 1
            acuerdo[q] += l[q]["valor"] == det[q]["valor"]
    tok_in = sum(x["tokens_entrada"] for x in ef)
    tok_out = sum(x["tokens_salida"] for x in ef)
    lat = sorted(x["latencia_s"] for x in ef)
    e0_cats = [x["categoria"] for x in e0 if x.get("categoria")]
    e0_A = [a for a, x in zip(A, e0) if x.get("categoria")]
    e0_tok_in = sum(x.get("uso", {}).get("tokens_entrada", 0) for x in e0)
    e0_tok_out = sum(x.get("uso", {}).get("tokens_salida", 0) for x in e0)

    res = {
        "corte": args.corte, "modelo": real.model_id, "pacientes": len(activos), "corridas": args.corridas, "duracion_s": round(dur),
        "distribucion": {"A": collections.Counter(A), "R": collections.Counter(r_cats), "E+F": collections.Counter(EF),
                         "E+F_propuesta_sin_controles": collections.Counter(EFprop), "E0": collections.Counter(e0_cats)},
        "vs_A": {"R": comparar(A, r_cats), "E+F": comparar(A, EF), "E+F_propuesta_sin_controles": comparar(A, EFprop),
                 "E0": comparar(e0_A, e0_cats) if e0_cats else None},
        "kappa_EF_vs_R": kappa_ponderado(r_cats, EF),
        "estabilidad_3_corridas": {"estables": estables, "pct": round(100 * estables / len(ef), 1)},
        "controles": {"pacientes_con_control_bloqueante": pacientes_con_control, "motivos": motivos,
                      "revision_clinica": sum(bool(x["requiere_revision"]) for x in ef)},
        "movidos_por_rubrica": sum(x["movido_por_rubrica"] for x in ef),
        "lecturas": {"total": len(lecturas), "fallidas": fallidas, "envoltorio_corregido": envueltas},
        "acuerdo_llm_vs_lector_codigo": {q: round(100 * acuerdo[q] / total_q[q], 1) for q in total_q},
        "tokens": {"EF_entrada": tok_in, "EF_salida": tok_out, "E0_entrada": e0_tok_in, "E0_salida": e0_tok_out,
                   "por_evaluacion_EF": {"entrada": round(tok_in / len(ef)), "salida": round(tok_out / len(ef))}},
        "latencia_EF_s": {"mediana": lat[len(lat) // 2], "p95": lat[int(0.95 * len(lat)) - 1], "max": lat[-1]},
    }
    if args.precio_entrada is not None and args.precio_salida is not None:
        por_eval = (tok_in * args.precio_entrada + tok_out * args.precio_salida) / 1e6 / len(ef)
        res["costo_usd"] = {"precio_entrada_por_M": args.precio_entrada, "precio_salida_por_M": args.precio_salida,
                            "por_evaluacion_3_corridas": round(por_eval, 4), "esta_corrida_EF": round(por_eval * len(ef), 2),
                            "barrido_26356_on_demand": round(por_eval * 26356, 2), "barrido_26356_lote_50pct": round(por_eval * 26356 * 0.5, 2)}
    # 30 casos etiquetados por médicos (si existen)
    if os.path.exists(args.etiquetas):
        with open(args.etiquetas, encoding="utf-8") as f:
            filas = list(csv.DictReader(f))
        medicos = [c for c in filas[0] if c.startswith("medico")]
        por_id = {x["id_paciente"]: x for x in ef}
        brazos = {"A": lambda x: x["categoria_reglas"], "E+F": lambda x: x["categoria_final"]}
        et = {}
        for m in medicos:
            ok = [f for f in filas if f[m] in ORD and f["id_paciente"] in por_id]
            for nb, fn in brazos.items():
                a = [f[m] for f in ok]
                b = [fn(por_id[f["id_paciente"]]) for f in ok]
                et[f"{nb}_vs_{m}"] = {"n": len(ok), "kappa": kappa_ponderado(a, b), "ic95": ic95_bootstrap(a, b),
                                      "subtriage": sum(ORD[y] < ORD[x] for x, y in zip(a, b)),
                                      "sobretriage": sum(ORD[y] > ORD[x] for x, y in zip(a, b)),
                                      "errores_graves": sum(x == "alta" and y != "alta" for x, y in zip(a, b))}
        if len(medicos) >= 2:
            ok = [f for f in filas if f[medicos[0]] in ORD and f[medicos[1]] in ORD]
            et["medico_vs_medico"] = {"n": len(ok), "kappa": kappa_ponderado([f[medicos[0]] for f in ok], [f[medicos[1]] for f in ok])}
        res["etiquetas_medicas"] = et
    else:
        res["etiquetas_medicas"] = None
    os.makedirs(os.path.join(RAIZ, "data", "evaluacion"), exist_ok=True)
    with open(os.path.join(RAIZ, "data", "evaluacion", "resultados.json"), "w", encoding="utf-8") as f:
        json.dump({"resumen": res, "evaluaciones": ef}, f, ensure_ascii=False, indent=1, default=dict)
    ejemplos = [{"id": x["id_paciente"], "reglas": x["categoria_reglas"], "rubrica": x["categoria_rubrica"],
                 "controles": [m["motivo"] for m in x["controles"]], "detalle": (x["controles"] or [{}])[0].get("detalle", "")}
                for x in ef if any(m["motivo"] == "bajaria" for m in x["controles"])][:5]
    escribir_md(res, ejemplos)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=dict))
    return res


def escribir_md(r, ejemplos):
    """docs/algoritmo/EVALUACION.md a partir de los resultados medidos."""
    d, v = r["distribucion"], r["vs_A"]

    def dist(k):
        x = d.get(k) or {}
        return f'{x.get("alta", 0)} / {x.get("media", 0)} / {x.get("baja", 0)}'

    def fila(nombre, k):
        c = v.get(k)
        return (f"| {nombre} | {dist(k)} | {c['iguales']} | {c['suben']} | {c['bajan']} | {c['kappa_vs_A']} |" if c else f"| {nombre} | — | — | — | — | — |")
    et = r.get("etiquetas_medicas")
    costo = r.get("costo_usd") or {}
    inestable_pct = round(100 - r["estabilidad_3_corridas"]["pct"], 1)
    lineas = [
        "# Evaluación offline del algoritmo decisor", "",
        f"Generado por `scripts/evaluar_algoritmo.py` · fecha de corte {r['corte']} · modelo `{r['modelo']}` · "
        f"{r['pacientes']} pacientes en lista · {r['corridas']} corridas por paciente · duración {r['duracion_s']} s.", "",
        "## Brazos", "",
        "- **A:** reglas actuales (`puntaje.py`).",
        "- **R:** la misma rúbrica respondida por **código** (lector determinista) + fórmula + controles. Mide si el LLM aporta.",
        "- **E+F:** rúbrica respondida por **Bedrock** (3 lecturas) + fórmula fija + controles. Es lo que se propone activar.",
        "- **E+F sin controles:** lo que la fórmula habría hecho si no existieran los controles (para ver qué frenan).",
        "- **E0:** Claude con un prompt genérico que asigna la prioridad directamente (control, sin rúbrica ni tabla).", "",
        "## Resultados frente a las reglas actuales (A)", "",
        "| Brazo | Alta / Media / Baja | Iguales a A | Suben | Bajan | κ ponderado vs A |", "|---|---|---|---|---|---|",
        f"| A (reglas) | {dist('A')} | — | — | — | — |",
        fila("R (rúbrica por código)", "R"), fila("**E+F (rúbrica por LLM + fórmula + controles)**", "E+F"),
        fila("E+F sin controles", "E+F_propuesta_sin_controles"), fila("E0 (LLM decide solo)", "E0"), "",
        f"- κ entre E+F y R: **{r['kappa_EF_vs_R']}**.",
        f"- Pacientes que la rúbrica movió sola (todo cuadró): **{r['movidos_por_rubrica']}**.",
        f"- Estabilidad: **{r['estabilidad_3_corridas']['pct']} %** de los pacientes con las 3 lecturas iguales ({inestable_pct} % inestables).",
        f"- Lecturas: {r['lecturas']['total']} · fallidas: **{r['lecturas']['fallidas']}** · respuesta envuelta corregida: {r['lecturas']['envoltorio_corregido']}.", "",
        "## Controles (pacientes que la IA no mueve solos: se usan las reglas)", "",
        f"Pacientes con un control bloqueante: **{r['controles']['pacientes_con_control_bloqueante']}**. "
        f"De ellos, piden revisión del especialista (el resultado los bajaría): **{r['controles']['revision_clinica']}**; "
        "el resto usó las reglas por un motivo técnico, sin acción humana.", "",
        "| Motivo | Pacientes |", "|---|---|", *[f"| {k} | {n} |" for k, n in sorted(r["controles"]["motivos"].items(), key=lambda x: -x[1])], "",
        *(["Ejemplos de `bajaria` (la fórmula los habría bajado; el control lo impidió):", "",
           *[f"- {e['id']}: reglas {e['reglas']} → rúbrica {e['rubrica']} · {e['detalle']}" for e in ejemplos], ""] if ejemplos else []),
        "## Lectura del LLM frente al lector por código (% de acuerdo por pregunta)", "",
        "| Pregunta | Acuerdo |", "|---|---|", *[f"| {q} | {p} % |" for q, p in r["acuerdo_llm_vs_lector_codigo"].items()], "",
        "## Costo y latencia (medidos)", "",
        f"- Tokens por evaluación (3 lecturas): {r['tokens']['por_evaluacion_EF']['entrada']} de entrada y {r['tokens']['por_evaluacion_EF']['salida']} de salida.",
        *( [f"- Costo por evaluación: USD {costo['por_evaluacion_3_corridas']} · esta corrida: USD {costo['esta_corrida_EF']} · "
            f"barrido de 26.356 pacientes: USD {costo['barrido_26356_on_demand']} on-demand (el lote no existe para Sonnet 5; ver VIABILIDAD.md)."] if costo else []),
        "- Latencia por lectura (de la corrida con llamadas reales): ver VIABILIDAD.md (mediana 3,7 s, p95 6,0 s; las 3 lecturas van en paralelo).", "",
        "## Concordancia con médicos (30 casos etiquetados)", "",
        *( [f"| {k} | n = {x['n']} | κ = {x['kappa']} | IC95 {x.get('ic95')} | subtriage {x.get('subtriage', '—')} | sobretriage {x.get('sobretriage', '—')} | errores graves {x.get('errores_graves', '—')} |"
            for k, x in et.items()] if et else
           ["**Pendiente:** no hay etiquetas médicas (`data/etiquetado_30.csv`). El script queda listo: calcula κ ponderado cuadrático "
            "contra cada médico y el consenso con IC95 por bootstrap, κ médico–médico, sobretriage, subtriage y errores graves. "
            "Con n = 30 el IC95 del κ es de ±0,22–0,24; para ±0,10 se necesitan 110–200 casos."]), "",
        "## Regla de decisión", "",
        "Volver a `reglas` si E+F: (1) no supera a A por ≥ 0,10 de κ contra médicos; (2) es inestable en más del 10 % de los casos; "
        "o (3) produce algún subtriage grave.", "",
        f"- (1) **No evaluable sin etiquetas médicas.**",
        f"- (2) Inestabilidad: {inestable_pct} % → {'cumple' if inestable_pct <= 10 else 'NO cumple'}.",
        f"- (3) Subtriage frente a A: {v['E+F']['bajan']} pacientes bajan → {'cumple' if v['E+F']['bajan'] == 0 else 'NO cumple'} "
        "(los controles impiden bajar sin un humano).", "",
        "**Recomendación:** mantener `ALGORITMO=reglas` en la demo publicada hasta tener las etiquetas de los 30 casos. "
        "E+F queda implementado, probado y medido, listo para activarse cuando el equipo lo decida.", "",
    ]
    with open(os.path.join(RAIZ, "docs", "algoritmo", "EVALUACION.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lineas))


if __name__ == "__main__":
    main()
