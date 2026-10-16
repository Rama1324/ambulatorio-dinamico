"""Criterios clínicos por enfermedad (conocimiento/criterios_especialidad.json: 5 especialidades, 46 enfermedades, criterios
alta/media/baja y excepciones de urgencia). Mismo principio que el resto: la IA LEE, el código DECIDE.

1. Claude lee el texto (motivo de la interconsulta, informe) 3 veces y elige UN criterio de la lista cerrada de esa
   enfermedad, copiando la frase del texto que lo respalda; aparte, si se cumple una excepción de urgencia.
2. El código verifica que la frase esté en el texto y no esté negada, y exige que 2 de 3 lecturas coincidan.
3. El nivel del criterio solo SUBE la prioridad (nunca baja: eso lo decide el especialista). Si la información no alcanza,
   no se asigna "baja" (regla del propio JSON: "no asignar baja por ausencia de datos").
4. Una excepción de urgencia ("derivar hoy a urgencia") prevalece sobre la clasificación electiva: prioridad alta,
   primera de la lista y "contactar hoy".
"""
import json
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, ValidationError

import informe
from modelos import buscar_cita, normalizar

LECTURAS = 3
FUENTE = "Criterios clínicos por especialidad (dataset_gravedad_por_especialidad.json, v{v})"
_KB = {}

# CIE-10 (3 caracteres, como los normaliza el importador) → enfermedad del JSON. El primero de cada lista va al catálogo.
CIE10 = {
    "oftalmologia_01": ["H25", "H26"], "oftalmologia_02": ["H33"], "oftalmologia_03": ["H50"], "oftalmologia_04": ["H52"],
    "oftalmologia_05": ["H35"], "oftalmologia_06": ["D31", "C69"], "oftalmologia_07": ["H02", "H00"],
    "otorrinolaringologia_01": ["H70"], "otorrinolaringologia_02": ["F80"], "otorrinolaringologia_03": ["C32", "C10", "C11", "C13", "C30"],
    "otorrinolaringologia_04": ["R49"], "otorrinolaringologia_05": ["R04"], "otorrinolaringologia_06": ["H80"],
    "otorrinolaringologia_07": ["H71"], "otorrinolaringologia_08": ["S02"], "otorrinolaringologia_09": ["J33"],
    "otorrinolaringologia_10": ["H91", "H90"], "otorrinolaringologia_11": ["H93"], "otorrinolaringologia_12": ["H81"],
    "otorrinolaringologia_13": ["J35"],
    "psiquiatria_01": ["R45", "X84"], "psiquiatria_02": ["F31"], "psiquiatria_03": ["F42"], "psiquiatria_04": ["F06"],
    "psiquiatria_05": ["F20", "F23", "F29"], "psiquiatria_06": ["F50"], "psiquiatria_07": ["F32", "F33"],
    "psiquiatria_08": ["F60"], "psiquiatria_09": ["F44"], "psiquiatria_10": ["F43"],
    "reumatologia_01": ["M32"], "reumatologia_02": ["M31", "M30"], "reumatologia_03": ["M33"], "reumatologia_04": ["M34"],
    "reumatologia_05": ["M13", "M10", "M11", "M02", "M07"], "reumatologia_06": ["M06", "M05"], "reumatologia_07": ["M45"],
    "reumatologia_08": ["M35"], "reumatologia_09": ["M81", "M80"],
    "urologia_01": ["C61"], "urologia_02": ["N40"], "urologia_03": ["N20"], "urologia_04": ["N31"], "urologia_05": ["N39", "R32"],
    "urologia_06": ["N43", "I86", "N50"], "urologia_07": ["R31"],
}


def cargar():
    if "kb" not in _KB:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conocimiento")
        with open(os.path.join(base, "criterios_especialidad.json"), encoding="utf-8") as f:
            kb = json.load(f)
        por_id = {}
        for s in kb["especialidades"]:
            for e in s["enfermedades"]:
                por_id[e["id"]] = {**e, "especialidad": s["especialidad"], "transversal": s.get("excepcion_transversal")}
        _KB["kb"], _KB["por_id"] = kb, por_id
        _KB["por_cie"] = {c: por_id[i] for i, cs in CIE10.items() for c in cs}
        # criterios oficiales de los diagnósticos del registro (Queensland CPC / NICE): cada enfermedad trae sus CIE-10
        with open(os.path.join(base, "criterios_registro.json"), encoding="utf-8") as f:
            reg = json.load(f)
        for s in reg["especialidades"]:
            for e in s["enfermedades"]:
                x = {**e, "especialidad": s["especialidad"], "transversal": None}
                _KB["por_id"][e["id"]] = x
                for c in e["cie10"]:
                    _KB["por_cie"].setdefault(c, x)   # si el JSON de especialidades ya lo cubre (F32), se mantiene ese
        _KB["registro"] = reg
    return _KB


def enfermedad_de(cie):
    import puntaje  # una fila de la tabla del HLF que es la misma enfermedad usa los criterios de ese diagnóstico
    return cargar()["por_cie"].get(puntaje.cie_base(cie or "").upper()[:3])


def catalogo():
    """Diagnósticos del JSON para ingresar interconsultas de esas especialidades (CIE-10 principal de cada enfermedad)."""
    return [{"especialidad": e["especialidad"], "sub_especialidad": e["especialidad"], "diagnostico_cie10": CIE10[i][0],
             "diagnostico_texto": e["enfermedad"]} for i, e in cargar()["por_id"].items() if i in CIE10]  # los del registro ya están en su catálogo


def opciones(enf):
    """Lista cerrada: criterios ('alta.0', 'media.0'…) y urgencias ('urgencia.0'…), con su texto."""
    crit = {f"{n}.{k}": (n, t) for n in ("alta", "media", "baja") for k, t in enumerate(enf["niveles"][n]["criterios_detallados"])}
    urg = [u["condicion"] + " → " + u["clasificacion_excepcional"] for u in enf.get("excepciones_de_urgencia", [])]
    if enf.get("transversal"):
        urg.append(enf["transversal"]["condicion"] + " → " + enf["transversal"]["clasificacion_excepcional"])
    return crit, {f"urgencia.{k}": t for k, t in enumerate(urg)}


class Lectura(BaseModel):
    criterio: str
    cita: str = ""
    urgencia: str = "ninguna"
    cita_urgencia: str = ""


def herramienta(enf):
    """Esquema con la lista cerrada de códigos de ESTA enfermedad (enum): la IA no puede responder otra cosa."""
    crit, urg = opciones(enf)
    return {"toolSpec": {"name": "clasificar_criterio", "description": "Código del criterio clínico que cumple el texto, con cita textual.",
                         "inputSchema": {"json": {"type": "object", "properties": {
                             "criterio": {"type": "string", "enum": list(crit) + ["no_determinable"]}, "cita": {"type": "string"},
                             "urgencia": {"type": "string", "enum": list(urg) + ["ninguna"]}, "cita_urgencia": {"type": "string"}},
                             "required": ["criterio", "cita", "urgencia", "cita_urgencia"]}}}}


def _codigo(valor, opciones_):
    """Acepta el código ('alta.0') o, si la IA devolvió el texto del criterio, lo traduce a su código."""
    if valor in opciones_:
        return valor
    v = normalizar(valor.split("]", 1)[-1] if valor.startswith("[") else valor)
    return next((k for k, t in opciones_.items() if len(v) >= 10 and normalizar(t[1] if isinstance(t, tuple) else t).startswith(v)), valor)


def armar_prompt(enf, texto):
    crit, urg = opciones(enf)
    kb = cargar()["kb"]["interpretacion"]
    sistema = ("Clasificas una interconsulta o informe con una lista CERRADA de criterios clínicos. No inventas datos ni "
               "asignas prioridades: eliges el criterio que el texto cumple y copias la frase TEXTUAL que lo respalda.\n"
               f"Reglas: {kb['informacion_insuficiente']} {kb['umbrales']} {kb['criterios']}\n"
               "- Responde con el CÓDIGO del criterio (p. ej. alta.0), no con su texto.\n"
               "- La cita es UNA frase continua copiada del texto (sin \"...\" ni cortes).\n"
               "- Si ningún criterio se cumple con lo que dice el texto, responde criterio = \"no_determinable\".\n"
               "- Un hallazgo negado o descartado no cumple el criterio.\n"
               "- Revisa aparte las excepciones de urgencia: si una se cumple, indícala con su cita; si no, urgencia = \"ninguna\".")
    lista = "\n".join(f"{k}: [{n.upper()}] {t}" for k, (n, t) in crit.items())
    lista_u = "\n".join(f"{k}: {t}" for k, t in urg.items()) or "(sin excepciones de urgencia)"
    nota = f"\nPrecisión para clasificar: {enf['precision_para_clasificar']}" if enf.get("precision_para_clasificar") else ""
    usuario = (f"ENFERMEDAD: {enf['enfermedad']} ({enf['especialidad']}){nota}\n\nCRITERIOS:\n{lista}\n\nEXCEPCIONES DE URGENCIA:\n{lista_u}\n\n"
               f"TEXTO:\n{texto}")
    return sistema, usuario


def _verifica(cita, doc):
    i = buscar_cita(cita or "", doc)
    return i >= 0 and not informe._negado(doc, i)


def clasificar(texto, enf, cliente, lecturas=LECTURAS):
    """Devuelve {nivel, criterio_id, criterio, cita, urgencia, cita_urgencia, lecturas, estable, errores}."""
    crit, urg = opciones(enf)
    sistema, usuario = armar_prompt(enf, texto)
    doc = normalizar(texto)

    def una(_):
        try:
            crudo, uso = cliente.leer(sistema, usuario, herramienta(enf), 500)
            return Lectura.model_validate(crudo), uso, None
        except ValidationError as e:
            return None, {}, f"json_invalido: {e.errors()[0]['msg']}"
        except Exception as e:  # timeout, permisos, throttling
            return None, {}, f"fallo_llm: {type(e).__name__}: {str(e)[:160]}"
    with ThreadPoolExecutor(max_workers=lecturas) as ex:
        crudas = list(ex.map(una, range(lecturas)))
    criterios, urgencias, citas = [], [], {}
    for r, _, _ in crudas:
        if r is None:
            continue
        r.criterio, r.urgencia = _codigo(r.criterio, crit), _codigo(r.urgencia, urg)
        if r.criterio in crit and _verifica(r.cita, doc):   # criterio inventado o cita que no está en el texto: no cuenta
            criterios.append(r.criterio)
            citas.setdefault(r.criterio, r.cita)
        if r.urgencia in urg and _verifica(r.cita_urgencia, doc):
            urgencias.append(r.urgencia)
            citas.setdefault(r.urgencia, r.cita_urgencia)
    mayor_c = Counter(criterios).most_common(1)
    mayor_u = Counter(urgencias).most_common(1)
    cid = mayor_c[0][0] if mayor_c and mayor_c[0][1] >= 2 else None    # 2 de 3 lecturas iguales y verificadas
    uid = mayor_u[0][0] if mayor_u and mayor_u[0][1] >= 2 else None
    return {"enfermedad_id": enf["id"], "enfermedad": enf["enfermedad"], "especialidad": enf["especialidad"],
            "nivel": crit[cid][0] if cid else None, "criterio_id": cid, "criterio": crit[cid][1] if cid else None,
            "cita": citas.get(cid), "urgencia": urg[uid] if uid else None, "cita_urgencia": citas.get(uid),
            "lecturas": len([r for r, _, _ in crudas if r]), "errores": [e for _, _, e in crudas if e],
            "tokens_entrada": sum((u.get("tokens_entrada") or 0) for _, u, _ in crudas),
            "tokens_salida": sum((u.get("tokens_salida") or 0) for _, u, _ in crudas),
            "fuente": enf.get("fuente_url") or FUENTE.format(v=cargar()["kb"].get("version", "?")), "riesgo": enf.get("riesgo")}


def evento(c, fecha):
    """Evento del registro con el resultado (solo si hay nivel o urgencia). La regla de puntaje.py lo aplica: solo sube."""
    if not c["nivel"] and not c["urgencia"]:
        return None
    sub = "urgencia" if c["urgencia"] else f'prioridad {c["nivel"]}'
    texto = (f'URGENCIA: {c["urgencia"]} ("{c["cita_urgencia"]}")' if c["urgencia"] else "") + \
            (("; " if c["urgencia"] else "") + f'{c["enfermedad"]}, {c["nivel"]}: {c["criterio"]} ("{c["cita"]}")' if c["nivel"] else "")
    return {"fecha_evento": fecha, "tipo_evento": "criterio_clinico", "subtipo": sub,
            "severidad": "grave" if c["urgencia"] else {"alta": "moderada"}.get(c["nivel"], "leve"),
            "detalle": texto, "origen": "criterios_ia", "nivel_criterio": c["nivel"], "urgencia": bool(c["urgencia"]), "riesgo": c.get("riesgo"),
            "texto_urgencia": c["urgencia"] and f'{c["urgencia"]} · "{c["cita_urgencia"]}"',
            "texto_criterio": c["nivel"] and f'{c["enfermedad"]}, criterio {c["nivel"]}: {c["criterio"]} · "{c["cita"]}"',
            "fuente": c["fuente"]}
