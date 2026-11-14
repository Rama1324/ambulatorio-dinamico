"""Datos sintéticos para probar y demostrar la ingesta continua (lambda/ingesta.py), deterministas y sin AWS.

    python scripts/generar_escenarios.py                 # deja los archivos en data/demo/
    python scripts/generar_escenarios.py --salida RUTA   # en otra carpeta

Genera, a partir del registro sintético (DATA_DIR/perfiles.json, fecha de referencia 2026-10-13):
  eventos_urgencia.csv        export "tipo hospital" (encabezados distintos a los nuestros) para la zona de carga S3
  eventos_api.json            cuerpo listo para POST /ingesta/eventos
  mediciones_laboratorio.csv  HbA1c y PHQ-9 que hacen cruzar umbrales a pacientes concretos (para POST /importar)
  informes/*.txt              4 textos clínicos breves para POST /pacientes/{id}/informe
  ESPERADO.md                 qué debe pasar con cada archivo: se calcula EJECUTANDO la tubería en local, no a mano

Los pacientes se eligen por criterio (especialidad, diagnóstico, prioridad, sin eventos previos, orden por id), no al azar:
el mismo registro da siempre los mismos archivos. La única "semilla" es el orden de las filas del export de urgencia,
que se baraja con random.Random(SEMILLA) para que parezca un export real.
"""
import argparse
import base64
import io
import json
import os
import random
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["LOCAL"] = "1"
os.environ.setdefault("DATA_DIR", os.path.join(RAIZ, "data"))
os.environ["FECHA_REFERENCIA"] = "2026-10-13"
os.environ["ALGORITMO"] = "reglas"            # ESPERADO.md describe las reglas (la IA solo puede subir más y deja su dictamen)
os.environ.pop("MODEL_ID", None)
os.environ.pop("COLA_EVALUACION_URL", None)   # en local no hay cola: la evaluación se hace en línea
os.environ.pop("TEMA_ALERTAS_ARN", None)
sys.path.insert(0, os.path.join(RAIZ, "lambda"))

from datetime import date  # noqa: E402

CORTE = date(2026, 10, 13)
SEMILLA = 2026
COMANDO = "python scripts/generar_escenarios.py"

# Motivo de consulta en urgencia, coherente con el diagnóstico por el que espera (relacionado) o ajeno a él
MOTIVO = {"Cardiología": "dolor torácico opresivo", "Broncopulmonar": "disnea y tos, exacerbación", "Endocrinología": "hiperglicemia sintomática",
          "Salud Mental": "crisis de angustia con ideación", "Neurología": "crisis convulsiva", "Gastroenterología": "dolor epigástrico y vómitos",
          "Traumatología": "dolor articular invalidante"}
AJENO = "esguince de tobillo por caída"
# RUT ficticios (dígito verificador válido) de personas que NO están en la lista: urgencia manda a todo el hospital
DEMO = {"PAC-HLF-00001", "PAC-HLF-00002", "PAC-HLF-00009", "PAC-HLF-00020", "PAC-HLF-00028"}  # CLAUDE.md: pacientes de demo
FUERA = ["11.111.111-1", "12.345.678-5", "9.876.543-3", "15.555.555-K", "16.666.666-5"]


def _app():
    import app
    import datos
    return app, datos


def elegir(perfs, especialidad=None, cie=None, prioridad=None, n=1, sin_eventos=True, excluir=()):
    """Pacientes en espera que cumplen el criterio, en orden de id (determinista)."""
    out = []
    for pid, p in sorted(perfs.items()):
        le = p["lista_espera"]
        if le["estado"] != "en_espera" or p["paciente"].get("fallecido") or pid in excluir:
            continue
        if (especialidad and le["especialidad"] != especialidad) or (cie and le["diagnostico_cie10"] not in cie) \
                or (prioridad and le["prioridad_inicial"] not in prioridad) or (sin_eventos and p["eventos_clinicos"]):
            continue
        out.append(pid)
        if len(out) == n:
            break
    if n is not None and len(out) < n:
        raise SystemExit(f"no hay {n} paciente(s) para {especialidad} {cie} {prioridad} en el registro")
    return out


# ---------- archivos ----------
def export_urgencia(perfs, usados):
    """~40 filas: urgencias ESI 1 a 5 sobre pacientes del registro, 3 filas repetidas, una fecha inválida, un subtipo
    desconocido y 5 personas que no están en la lista. Encabezados como los exporta un sistema de urgencia."""
    filas, esi = [], ["ESI 1", "ESI 2", "ESI 2", "ESI 3", "ESI 3", "ESI 4", "ESI 5"]
    i = 0
    for esp in sorted(MOTIVO):  # 7 especialidades × 4 pacientes de prioridad baja o media sin eventos previos
        for pid in elegir(perfs, esp, prioridad=("baja", "media"), n=4, excluir=usados):
            usados.add(pid)
            nivel = esi[i % len(esi)]
            ajeno = nivel in ("ESI 4", "ESI 5") and i % 2 == 0
            filas.append({"Ficha": pid, "Fecha": f"{1 + i % 12:02d}/10/2026", "Tipo": "Urgencia", "Categorización": nivel,
                          "Gravedad": "leve", "Motivo consulta": AJENO if ajeno else MOTIVO[esp],
                          "Relacionado con diagnóstico": "No" if ajeno else "", "Box urgencia": f"BOX-U{1 + i % 6}"})
            i += 1
    repetidas = [dict(filas[k]) for k in (0, 5, 10)]                         # el sistema reenvía filas ya enviadas
    mala_fecha = {**filas[1], "Fecha": "31/09/2026", "Categorización": "ESI 3"}  # 31 de septiembre no existe
    raro = {**filas[2], "Categorización": "Triage verde", "Fecha": "13/10/2026"}  # subtipo que no está en el registro
    fuera = [{"Ficha": rut, "Fecha": "12/10/2026", "Tipo": "Urgencia", "Categorización": "ESI 2", "Gravedad": "grave",
              "Motivo consulta": "politraumatismo", "Relacionado con diagnóstico": "", "Box urgencia": "BOX-U1"} for rut in FUERA]
    todas = filas + repetidas + [mala_fecha, raro] + fuera
    random.Random(SEMILLA).shuffle(todas)
    cab = list(filas[0])
    return "﻿" + ";".join(cab) + "\n" + "".join(";".join(str(f[c]) for c in cab) + "\n" for f in todas)


def cuerpo_api(perfs, usados):
    epoc = elegir(perfs, cie=("J44",), excluir=usados, n=2)
    ic = elegir(perfs, cie=("I50",), prioridad=("baja", "media"), excluir=usados)[0]
    dm = elegir(perfs, cie=("E11",), sin_eventos=False, excluir=usados, n=2)
    hta = elegir(perfs, cie=("I10",), excluir=usados)[0]
    angina = elegir(perfs, cie=("I20",), prioridad=("baja",), excluir=usados)[0]
    usados.update(epoc + dm + [ic, hta, angina])
    eventos = [
        {"id_evento": "HOSP-2026-0101", "id_paciente": epoc[0], "fecha_evento": "2026-10-08", "tipo_evento": "hospitalizacion",
         "subtipo": "ingreso hospitalario", "motivo": "exacerbación de EPOC con insuficiencia respiratoria"},
        {"id_evento": "HOSP-2026-0102", "id_paciente": ic, "fecha_evento": "2026-10-09", "tipo_evento": "hospitalizacion",
         "subtipo": "ingreso UCI", "motivo": "insuficiencia cardíaca descompensada"},
        {"id_evento": "LAB-2026-0201", "id_paciente": dm[0], "fecha_evento": "2026-10-10", "tipo_evento": "examen_alterado",
         "subtipo": "resultado alterado", "detalle": "creatinina 2,1 mg/dL"},
        {"id_evento": "LAB-2026-0202", "id_paciente": hta, "fecha_evento": "2026-10-11", "tipo_evento": "examen", "subtipo": "Resultado alterado",
         "detalle": "potasio 6,0 mEq/L"},
        # sin relación con el diagnóstico por el que espera: queda registrado, pero no le sube la prioridad
        {"id_evento": "HOSP-2026-0103", "id_paciente": angina, "fecha_evento": "2026-10-07", "tipo_evento": "hospitalizacion",
         "subtipo": "ingreso hospitalario", "motivo": "fractura de cadera por caída", "relacionado": False},
        {"id_evento": "HOSP-2026-0104", "id_paciente": epoc[1], "fecha_evento": "2026-10-12", "tipo": "hospitalizado",
         "sub_tipo": "Ingreso hospitalario", "gravedad": "leve", "motivo_ingreso": "neumonía con exacerbación de EPOC"},
    ]
    mediciones = [
        {"id_paciente": dm[0], "fecha_medicion": "2026-10-10", "tipo_medicion": "HbA1c", "valor": 10.9, "unidad": "%"},
        {"id_paciente": dm[1], "fecha_medicion": "2026-10-10", "examen": "glucosa", "resultado": 312, "unidad": "mg/dL"},
        {"id_paciente": hta, "fecha_medicion": "2026-10-11", "tipo_medicion": "PAS", "valor": 186, "unidad": "mmHg"},
    ]
    return {"origen": "his-hlf", "fecha_corte": CORTE.isoformat(), "eventos": eventos, "mediciones": mediciones}


def mediciones_laboratorio(perfs, usados):
    """HbA1c que cruza 10% y 8% (sube la prioridad de diabetes con deterioro) y PHQ-9 que cruza 16 (alerta clínica)."""
    def ultima(pid, tipo):
        serie = sorted((m for m in perfs[pid]["mediciones"] if m["tipo_medicion"] == tipo), key=lambda m: m["fecha_medicion"])
        return serie[-1] if serie else None
    dm = [pid for pid in elegir(perfs, cie=("E11",), prioridad=("baja", "media"), sin_eventos=False, n=None, excluir=usados)
          if (ultima(pid, "HbA1c") or {"valor": 99})["valor"] < 8][:3]
    dep = [pid for pid in elegir(perfs, cie=("F32",), sin_eventos=False, n=None, excluir=usados)
           if (ultima(pid, "PHQ9") or {"valor": 99})["valor"] < 16][:2]
    usados.update(dm + dep)
    filas = [(dm[0], "2026-10-09", "HbA1c", "10,8", "%"),      # cruza 10%: con deterioro → alta
             (dm[1], "2026-10-09", "HbA1c", "8,6", "%"),       # cruza 8%: con deterioro → media
             (dm[2], "2026-10-09", "HbA1c", "6,9", "%"),       # fuera de rango, pero bajo 8%: no cambia la prioridad
             (dep[0], "2026-10-08", "PHQ-9", "19", "puntos"),  # ≥ 16: alerta (no cambia la prioridad por sí solo)
             (dep[1], "2026-10-08", "PHQ-9", "7", "puntos")]   # normal
    return "﻿Ficha;Fecha examen;Examen;Resultado;Unidades\n" + "".join(";".join(f) + "\n" for f in filas)


def informes(perfs, usados):
    ic = elegir(perfs, cie=("I50",), prioridad=("baja", "media"), excluir=usados)[0]
    gastro = elegir(perfs, cie=("K21",), excluir=usados, n=2)
    otro = elegir(perfs, especialidad="Neurología", excluir=usados, n=2)
    usados.update([ic, *gastro, *otro])
    return {
        "01_epicrisis_hospitalizacion": (ic, (
            "EPICRISIS. Servicio de Medicina, Hospital Clínico La Florida.\n"
            "Ingreso: 03-10-2026. Egreso: 09-10-2026.\n"
            "Paciente se hospitaliza por insuficiencia cardíaca descompensada, con disnea de reposo y edema de extremidades.\n"
            "Evoluciona favorablemente con diuréticos endovenosos. Se indica control precoz con cardiología.\n")),
        "02_biopsia_cancer": (gastro[0], (
            "INFORME DE ANATOMÍA PATOLÓGICA. Fecha: 06-10-2026.\n"
            "Muestra: biopsia endoscópica de unión gastroesofágica.\n"
            "Diagnóstico: adenocarcinoma moderadamente diferenciado. Cáncer confirmado por histología.\n")),
        "03_hallazgo_negado": (gastro[1], (
            "INFORME DE ENDOSCOPÍA DIGESTIVA ALTA. Fecha: 07-10-2026.\n"
            "Esofagitis grado A. No se observan lesiones sugerentes de neoplasia.\n"
            "Biopsia: negativa para malignidad. Se descarta cáncer.\n")),
        "04_otro_paciente": (otro[0], (
            f"INFORME DE URGENCIA. Paciente {otro[1]}.\n"
            "Fecha: 11-10-2026. Consulta por crisis convulsiva prolongada. Se hospitaliza para observación.\n")),
    }


# ---------- lo esperado: se calcula ejecutando la tubería ----------
def foto(app, pids):
    """Categoría y puesto en la lista de su especialidad de cada paciente (una lista por especialidad)."""
    perfs = app.perfiles_combinados()[0]
    out = {}
    for esp in sorted({perfs[p]["lista_espera"]["especialidad"] for p in pids if p in perfs}):
        filas = {f["id_paciente"]: f for f in app.lista(CORTE, esp)["pacientes"]}
        for p in pids:
            if p in filas:
                alertas = [r["valor"] for r in filas[p].get("razones", []) if r["factor"] == "alerta_clinica"]
                out[p] = (filas[p]["categoria"], filas[p]["posicion"], esp, filas[p].get("riesgo_vital"), alertas)
    return out


def cambios(app, antes, pids):
    """Los pacientes del archivo cuya prioridad cambia, que abren una alerta o reciben una alerta clínica nueva
    (los demás del archivo solo se mueven de puesto porque cambió el orden de otros, o no cambian)."""
    despues = foto(app, pids)
    perfs = app.perfiles_combinados()[0]
    lineas, iguales = [], 0
    for p in sorted(pids):
        a, d = antes.get(p), despues.get(p)
        if not a or not d:
            continue
        nuevas = [x for x in d[4] if x not in a[4]]
        if a[0] == d[0] and a[3] == d[3] and not nuevas:
            iguales += 1
            continue
        dx = perfs[p]["lista_espera"]["diagnostico_cie10"]
        nota = "; ".join((["abre alerta de descompensación grave (evaluación médica en 72 h)"] if d[3] and not a[3] else []) + nuevas)
        lineas.append(f"| {p} | {d[2]} · {dx} | {a[0]} → **{d[0]}** | {a[1]} → **{d[1]}** | {nota or '—'} |")
    return lineas, iguales


def tabla_cambios(resultado):
    lineas, iguales = resultado
    pie = f"\nLos otros {iguales} paciente(s) del archivo mantienen su prioridad (pueden moverse de puesto por el orden de los demás).\n"
    if not lineas:
        return "Nadie cambia de prioridad." + pie
    return ("| Paciente | Lista · CIE-10 | Prioridad | Puesto en su especialidad | Además |\n|---|---|---|---|---|\n" +
            "\n".join(lineas) + "\n" + pie)


def conteos(r):
    pt = r["por_tabla"]
    filas = [f"| {t} | {c['recibidos']} | {c['registrados']} | {c['duplicados']} | {c['rechazados']} | {c['fuera_de_lista']} |"
             for t, c in pt.items() if c["recibidos"]]
    rech = "\n".join(f"- {x['tabla']}, fila/índice {x['indice']}: {x['motivo']}" for x in r["rechazados"]) or "- ninguno"
    return ("| Tabla | Recibidos | Registrados | Duplicados | Rechazados | Fuera de lista |\n|---|---|---|---|---|---|\n" +
            "\n".join(filas) + f"\n\nRechazados:\n{rech}\n")


class S3Local:
    """Lo mínimo de S3 que usa ingesta.s3_handler, en memoria (para calcular lo esperado sin AWS)."""
    def __init__(self, objetos):
        self.objetos = dict(objetos)

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.objetos[Key])}

    def put_object(self, Bucket, Key, Body, **_):
        self.objetos[Key] = Body


def esperado(salida, perfs, archivos):
    app, datos = _app()
    import ingesta
    partes = [f"# Escenarios de ingesta — lo esperado\n\nGenerado por `{COMANDO}` (fecha de referencia {CORTE}, "
              "ALGORITMO=reglas, sin cola: evaluación en línea). Cada escenario parte del registro recién cargado. "
              "Para repetir el cálculo: vuelva a correr el mismo comando (es determinista).\n\n"
              "Con `ALGORITMO=rubrica` los conteos son los mismos (la recepción no depende de la IA); la IA solo puede subir "
              "más la prioridad, y cada paciente con información clínica nueva queda con su dictamen.\n"]

    # 1) export de urgencia por la zona de carga S3 (lo mismo que hace s3_handler con un objeto nuevo en entrada/)
    datos.restablecer()
    key = "entrada/urgencia/eventos_urgencia.csv"
    s3 = S3Local({key: archivos["eventos_urgencia.csv"].encode("utf-8")})
    pids = sorted({l.split(";")[0] for l in archivos["eventos_urgencia.csv"].lstrip("﻿").splitlines()[1:]} & set(perfs))
    antes = foto(app, pids)
    hecho = ingesta._procesar_objeto(s3, "bucket", key, "entrada/")
    r = json.loads(s3.objetos[hecho["resultado"]])
    col = next(i for i in r["informe"] if i.get("tabla"))
    partes.append("\n## 1. `eventos_urgencia.csv` → zona de carga S3 (`s3://<bucket>/entrada/urgencia/`)\n\n"
                  f"Columnas del hospital reconocidas: {', '.join(c['original'] + ' → ' + c['campo'] for c in col['columnas'])}. "
                  f"Ignoradas: {', '.join(col['ignoradas']) or 'ninguna'}. La columna Gravedad no se usa: la severidad sale del subtipo.\n\n"
                  f"Resultado en `procesados/urgencia/eventos_urgencia.csv.resultado.json` (canal `s3`, origen `urgencia`):\n\n"
                  + conteos(r) + f"\nPacientes con información clínica nueva: {r['pacientes_afectados']}. "
                  "Los 5 RUT que no están en la lista no dejan nada guardado. Hay rechazos, así que con `TEMA_ALERTAS_ARN` "
                  "sale un aviso SNS (solo archivo y conteos).\n\nCambios de prioridad:\n\n" + tabla_cambios(cambios(app, antes, pids)) +
                  "\nSubido por `POST /importar` (canal `archivo`) los conteos son los mismos. Reenviarlo: todo duplicado.\n")

    # 2) API para sistemas
    datos.restablecer()
    cuerpo = json.loads(archivos["eventos_api.json"])
    pids = sorted({x["id_paciente"] for t in ("eventos", "mediciones") for x in cuerpo[t]})
    antes = foto(app, pids)
    s, r = app._rutear("POST", ["ingesta", "eventos"], {}, cuerpo, {"idempotency-key": "demo-api-0001"})
    s2, r2 = app._rutear("POST", ["ingesta", "eventos"], {}, cuerpo, {"idempotency-key": "demo-api-0001"})
    s3_, r3 = app._rutear("POST", ["ingesta", "eventos"], {}, cuerpo, {})
    partes.append("\n## 2. `eventos_api.json` → `POST /ingesta/eventos`\n\n"
                  f"Respuesta {s} (evaluación {r['evaluacion']}):\n\n" + conteos(r) +
                  "\nEl evento de fractura de cadera (`relacionado: false`) queda registrado pero no sube la prioridad del paciente "
                  "de angina. La última hospitalización usa sinónimos (`tipo: hospitalizado`, `sub_tipo`, `gravedad: leve`): se lee "
                  "igual y su severidad es la del subtipo (grave).\n\nCambios de prioridad:\n\n" + tabla_cambios(cambios(app, antes, pids)) +
                  f"\nReenvío con la misma `Idempotency-Key`: respuesta {s2}, mismo `id_lote` ({'sí' if r2['id_lote'] == r['id_lote'] else 'NO'}), "
                  f"nada se procesa de nuevo. Reenvío sin clave: {s3_}, registrados {r3['registrados']}, duplicados {r3['duplicados']}.\n")

    # 3) Laboratorio por la app (POST /importar)
    datos.restablecer()
    pids = sorted({l.split(";")[0] for l in archivos["mediciones_laboratorio.csv"].lstrip("﻿").splitlines()[1:]})
    antes = foto(app, pids)
    b64 = base64.b64encode(archivos["mediciones_laboratorio.csv"].encode("utf-8")).decode()
    s, r = app.post_importar({"archivos": [{"nombre": "mediciones_laboratorio.csv", "contenido_base64": b64}], "confirmar": True,
                              "usuario": "Laboratorio HLF", "fecha_corte": CORTE.isoformat()})
    lote = ingesta.lote(r["id_lote"])
    partes.append("\n## 3. `mediciones_laboratorio.csv` → `POST /importar` (confirmar)\n\n" + conteos({**lote, "rechazados": lote["rechazados"]}) +
                  "\nHbA1c: sube la prioridad de diabetes con deterioro reciente (≥ 8% → media; > 10% → alta). PHQ-9 ≥ 16 deja la alerta "
                  "\"depresión más grave\" (NICE NG222), que no cambia la prioridad por sí sola.\n\nCambios de prioridad:\n\n" +
                  tabla_cambios(cambios(app, antes, pids)))

    # 4) Informes: sin IA (reglas) se PROPONEN eventos; con IA lo verificado se registra y deja dictamen (canal informe)
    partes.append("\n## 4. `informes/*.txt` → `POST /pacientes/{id}/informe` con `{\"texto\": ...}`\n\n"
                  "Con `ALGORITMO=reglas` el informe se lee con reglas y solo **propone** eventos (nada se guarda hasta que el equipo "
                  "confirma con `POST /eventos`). Con `ALGORITMO=rubrica` la IA lee 3 veces; lo verificado que solo puede subir se "
                  "registra por la tubería de ingesta (canal `informe`, origen `documento_ia`) y deja dictamen.\n\n"
                  "| Archivo | Paciente | Propone | Advertencias |\n|---|---|---|---|\n")
    for nombre, (pid, texto) in sorted(archivos["_informes"].items()):
        datos.restablecer()
        s, r = app.post_informe(pid, {"texto": texto, "fecha_corte": CORTE.isoformat()})
        prop = ", ".join(f'{e["tipo_evento"]} · {e["subtipo"]} → {e.get("categoria_propuesta")}' for e in r.get("eventos", [])) or "nada"
        partes.append(f"| `{nombre}.txt` | {pid} | {prop} | {'; '.join(r.get('advertencias') or []) or '—'} |\n")
    partes.append("\nLa tabla es lo que hace el lector por reglas (sin IA). Lo que registra la IA no se calcula aquí: depende del "
                  "modelo (Bedrock, o el lector simulado con `MODEL_ID=simulado`). Lo que se espera de ella: la epicrisis registra "
                  "la hospitalización; la biopsia, el hallazgo oncológico (cáncer confirmado → alta por las filas oncológicas de la "
                  "tabla HLF); el hallazgo negado no registra nada; el informe de otro paciente no registra nada (identidad en duda).\n")
    with open(os.path.join(salida, "ESPERADO.md"), "w", encoding="utf-8") as f:
        f.write("".join(partes))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--salida", default=os.path.join(os.environ["DATA_DIR"], "demo"))
    a = ap.parse_args()
    app, datos = _app()
    datos.restablecer()
    perfs = datos.perfiles_combinados()[0]
    usados = set(DEMO)  # los pacientes del guion de la demo no se tocan: su historia debe verse igual
    archivos = {"eventos_urgencia.csv": export_urgencia(perfs, usados),
                "eventos_api.json": json.dumps(cuerpo_api(perfs, usados), ensure_ascii=False, indent=2),
                "mediciones_laboratorio.csv": mediciones_laboratorio(perfs, usados)}
    archivos["_informes"] = informes(perfs, usados)
    os.makedirs(os.path.join(a.salida, "informes"), exist_ok=True)
    for nombre, contenido in archivos.items():
        if not nombre.startswith("_"):
            with open(os.path.join(a.salida, nombre), "w", encoding="utf-8", newline="\n") as f:
                f.write(contenido)
    for nombre, (pid, texto) in archivos["_informes"].items():
        with open(os.path.join(a.salida, "informes", f"{nombre}.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write(texto)  # a qué paciente va cada informe lo dice ESPERADO.md (el texto no debe nombrarlo)
    esperado(a.salida, perfs, archivos)
    print(f"Escenarios en {a.salida}: eventos_urgencia.csv, eventos_api.json, mediciones_laboratorio.csv, informes/ (4) y ESPERADO.md")


if __name__ == "__main__":
    main()
