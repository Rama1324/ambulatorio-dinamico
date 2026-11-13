"""Mide cuánto tarda y cuánto pesa la lista a distintas escalas, clonando el registro sintético en memoria.

No toca AWS ni guarda nada. Sirve para decidir con números (y repetir la medición cuando cambie el motor):
  - cuánto tarda calcular la lista de una especialidad y la de todo el hospital;
  - cuánto pesa la respuesta JSON, con y sin gzip (una Lambda no puede responder más de 6 MB);
  - cuánto ocupa el registro en memoria.

Uso, desde la raíz del repo:
  python -X utf8 scripts/medir_escala.py                 # 500 (registro), 4.000 (piloto) y 26.000 (red)
  python -X utf8 scripts/medir_escala.py 500 2000 8000   # tamaños a elección
"""
import copy
import gzip
import json
import os
import sys
import time
import tracemalloc
from datetime import date

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCAL", "1")
os.environ.setdefault("DATA_DIR", os.path.join(RAIZ, "data"))
os.environ.setdefault("FECHA_REFERENCIA", "2026-10-13")
sys.path.insert(0, os.path.join(RAIZ, "lambda"))

import datos  # noqa: E402
import lista as lista_mod  # noqa: E402
import puntaje  # noqa: E402

CORTE = date(2026, 10, 13)
ESPECIALIDAD = "Cardiología"


def clonar(base, n):
    """n perfiles: los del registro repetidos con otro id (misma mezcla de diagnósticos, eventos y mediciones)."""
    originales, out, k = list(base.values()), {}, 0
    while len(out) < n:
        for p in originales:
            if len(out) >= n:
                break
            if k == 0:
                out[p["id_paciente"]] = p
            else:
                q = copy.deepcopy(p)
                q["id_paciente"] = f'{p["id_paciente"]}-C{k}'
                q["paciente"]["nombre_fantasia"] = f'{p["paciente"]["nombre_fantasia"]} c{k}'
                out[q["id_paciente"]] = q
        k += 1
    return out


def medir(fn, repeticiones=3):
    mejor, res = float("inf"), None
    for _ in range(repeticiones):
        t = time.perf_counter()
        res = fn()
        mejor = min(mejor, time.perf_counter() - t)
    return mejor, res


def una_escala(base, n):
    tracemalloc.start()
    perfs = clonar(base, n)
    memoria = tracemalloc.get_traced_memory()[0] / 1e6
    tracemalloc.stop()
    vals = list(perfs.values())
    t_motor, _ = medir(lambda: puntaje.priorizar(vals, CORTE))
    t_esp, d_esp = medir(lambda: lista_mod.lista(CORTE, ESPECIALIDAD, perfs, {}))
    t_todo, d_todo = medir(lambda: lista_mod.lista(CORTE, None, perfs, {}), repeticiones=1 if n > 5000 else 2)

    def peso(d):
        crudo = json.dumps(d, ensure_ascii=False, default=str).encode()
        return len(crudo) / 1e6, len(gzip.compress(crudo, 5)) / 1e6
    p_esp, p_todo = peso(d_esp), peso(d_todo)
    resumen = [{k: p[k] for k in ("id_paciente", "nombre_fantasia", "rut", "edad", "sexo", "comuna", "prevision", "especialidad",
                                  "diagnostico_cie10", "diagnostico_texto", "categoria", "prioridad_inicial", "fecha_ingreso_lista",
                                  "dias_espera", "posicion", "posicion_especialidad", "riesgo_vital", "estado_clinico")}
               for p in d_esp["pacientes"]]
    p_res = peso({"pacientes": resumen})
    return {"pacientes": n, "en_lista": d_todo["total"], "en_especialidad": d_esp["total"], "memoria_mb": memoria,
            "motor_ms": t_motor * 1000, "lista_especialidad_ms": t_esp * 1000, "lista_todo_ms": t_todo * 1000,
            "json_especialidad_mb": p_esp[0], "gzip_especialidad_mb": p_esp[1], "json_todo_mb": p_todo[0], "gzip_todo_mb": p_todo[1],
            "resumen_especialidad_mb": p_res[0], "resumen_gzip_mb": p_res[1]}


def main():
    tamanos = [int(x) for x in sys.argv[1:]] or [500, 4000, 26000]
    base = datos.perfiles()
    filas = [una_escala(base, n) for n in tamanos]
    print(f"Fecha de corte {CORTE} · especialidad de referencia: {ESPECIALIDAD} · límite de respuesta de Lambda: 6 MB\n")
    print("| Pacientes | En lista | Memoria del registro | Motor (toda la lista) | Lista de 1 especialidad | Lista completa | "
          "JSON 1 esp. | gzip 1 esp. | JSON todo | gzip todo | Resumen 1 esp. (gzip) |")
    print("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for f in filas:
        print(f'| {f["pacientes"]:,} | {f["en_lista"]:,} | {f["memoria_mb"]:.0f} MB | {f["motor_ms"]:.0f} ms | '
              f'{f["lista_especialidad_ms"]:.0f} ms ({f["en_especialidad"]:,} pac.) | {f["lista_todo_ms"]:.0f} ms | '
              f'{f["json_especialidad_mb"]:.1f} MB | {f["gzip_especialidad_mb"]:.2f} MB | {f["json_todo_mb"]:.1f} MB | '
              f'{f["gzip_todo_mb"]:.2f} MB | {f["resumen_especialidad_mb"]:.2f} MB ({f["resumen_gzip_mb"]:.2f}) |'.replace(",", "."))
    return filas


if __name__ == "__main__":
    main()
