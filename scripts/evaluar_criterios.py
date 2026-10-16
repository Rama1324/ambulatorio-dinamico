"""Evaluación de los criterios clínicos por enfermedad (lambda/criterios.py) con Bedrock real.

1. Para cada enfermedad del JSON y cada nivel (alta, media, baja), Claude escribe una nota de interconsulta breve y realista
   que cumple el PRIMER criterio de ese nivel, SIN copiar sus palabras (paráfrasis clínica). Igual para cada urgencia.
2. Cada nota se clasifica con criterios.clasificar (3 lecturas, citas verificadas, 2 de 3).
3. Se mide: nivel correcto, nivel más alto (sobretriage), más bajo (subtriage), no determinable, y urgencias detectadas.
Las notas y lecturas se guardan en data/evaluacion/criterios_cache (no van al repo) para repetir sin costo.
Uso: $env:AWS_PROFILE="hack"; python -X utf8 scripts/evaluar_criterios.py
"""
import collections
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "lambda"))
import criterios  # noqa: E402
import rubrica  # noqa: E402

CACHE = os.path.join(RAIZ, "data", "evaluacion", "criterios_cache")
ORDEN = {"alta": 3, "media": 2, "baja": 1}
GEN = ("Eres médico de atención primaria en Chile. Escribe UNA nota breve de interconsulta (2 a 3 frases, español clínico "
       "chileno) de un paciente que cumple exactamente la situación indicada. Usa tus propias palabras: NO copies la frase de "
       "la situación. Incluye solo datos compatibles con esa situación (no agregues signos de mayor o menor gravedad).")
HERR_GEN = {"toolSpec": {"name": "nota", "description": "Nota de interconsulta.",
                         "inputSchema": {"json": {"type": "object", "properties": {"nota": {"type": "string"}}, "required": ["nota"]}}}}


class Cache:
    """Cliente que guarda cada respuesta en disco (clave = nombre)."""
    def __init__(self, real, nombre):
        self.real, self.nombre, self.n, self.model_id = real, nombre, 0, real.model_id

    def leer(self, sistema, texto, herramienta, max_tokens=900):
        self.n += 1
        ruta = os.path.join(CACHE, f"{self.nombre}_{self.n}.json")
        if os.path.exists(ruta):
            with open(ruta, encoding="utf-8") as f:
                d = json.load(f)
            return d["crudo"], d["uso"]
        crudo, uso = self.real.leer(sistema, texto, herramienta, max_tokens)
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump({"crudo": crudo, "uso": uso}, f, ensure_ascii=False)
        return crudo, uso


def casos():
    for i, e in criterios.cargar()["por_id"].items():
        for n in ("alta", "media", "baja"):
            if not e["niveles"][n]["criterios_detallados"]:  # algunas enfermedades no tienen criterios para todos los niveles
                continue
            yield {"id": f"{i}.{n}", "enf": e, "esperado": n, "situacion": e["niveles"][n]["criterios_detallados"][0], "urgencia": False}
        for k, u in enumerate(e.get("excepciones_de_urgencia", [])):
            yield {"id": f"{i}.urg{k}", "enf": e, "esperado": "alta", "situacion": u["condicion"], "urgencia": True}


def correr(c, real):
    cg = Cache(real, f"gen_{c['id']}")
    nota = cg.leer(GEN, f"Enfermedad: {c['enf']['enfermedad']} ({c['enf']['especialidad']}).\nSituación: {c['situacion']}", HERR_GEN, 300)[0]["nota"]
    r = criterios.clasificar(nota, c["enf"], Cache(real, f"cls_{c['id']}"))
    return {**{k: v for k, v in c.items() if k != "enf"}, "enfermedad": c["enf"]["enfermedad"], "nota": nota,
            "nivel": r["nivel"], "criterio": r["criterio_id"], "urgencia_detectada": bool(r["urgencia"]), "errores": r["errores"]}


def main():
    os.makedirs(CACHE, exist_ok=True)
    real = rubrica.ClienteBedrock(timeout_s=40, reintentos=6)
    lista = list(casos())
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(lambda c: correr(c, real), lista))
    niveles = [r for r in res if not r["urgencia"]]
    urg = [r for r in res if r["urgencia"]]
    def tipo(r):
        if r["nivel"] is None:
            return "no_determinable"
        d = ORDEN[r["nivel"]] - ORDEN[r["esperado"]]
        return "correcto" if d == 0 else ("sobre" if d > 0 else "sub")
    cuenta = collections.Counter(tipo(r) for r in niveles)
    por_nivel = {n: collections.Counter(tipo(r) for r in niveles if r["esperado"] == n) for n in ("alta", "media", "baja")}
    urg_ok = sum(r["urgencia_detectada"] for r in urg)
    falsas = sum(r["urgencia_detectada"] for r in niveles if r["esperado"] != "alta")
    n = len(niveles)
    lineas = [
        "# Evaluación de los criterios clínicos por enfermedad", "",
        f"Bedrock `{real.model_id}` · {len(criterios.cargar()['por_id'])} enfermedades · {n} notas de nivel + {len(urg)} notas de urgencia, "
        "escritas por Claude parafraseando el primer criterio de cada nivel (no copia sus palabras). Clasificación con "
        "`lambda/criterios.py` (3 lecturas, citas verificadas, 2 de 3).", "",
        "| Resultado | Notas | % |", "|---|---|---|",
        *[f"| {t} | {cuenta[t]} | {round(100 * cuenta[t] / n, 1)} |" for t in ("correcto", "sobre", "sub", "no_determinable")], "",
        "| Nivel esperado | Correcto | Sobretriage | Subtriage | No determinable |", "|---|---|---|---|---|",
        *[f"| {k} | {v['correcto']} | {v['sobre']} | {v['sub']} | {v['no_determinable']} |" for k, v in por_nivel.items()], "",
        f"- **Urgencias detectadas:** {urg_ok} de {len(urg)}.",
        f"- **Urgencias falsas** en notas de nivel media o baja: {falsas}.",
        "- Recordatorio: en la app el criterio **solo sube** la prioridad; un subtriage aquí significa que el paciente se queda "
        "con la prioridad que ya tenía (no baja). Un 'no determinable' tampoco cambia nada.", "",
        "## Casos que no coinciden", "",
        *[f"- `{r['id']}` esperado **{r['esperado']}**, obtuvo **{r['nivel'] or 'no determinable'}** · {r['nota'][:220]}"
          for r in niveles if tipo(r) != "correcto"],
        *[f"- `{r['id']}` URGENCIA no detectada · {r['nota'][:220]}" for r in urg if not r["urgencia_detectada"]], "",
    ]
    with open(os.path.join(RAIZ, "docs", "algoritmo", "EVALUACION_CRITERIOS.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lineas))
    print("\n".join(lineas[:20]))


if __name__ == "__main__":
    main()
