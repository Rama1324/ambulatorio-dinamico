"""Lector de documentos clínicos con IA (epicrisis, informe de urgencia, biopsia, interconsulta escrita).

Mismo principio que la rúbrica: el LLM LEE, el código DECIDE.
1. Claude (Bedrock, tool use forzado) lee el documento 3 veces y responde una lista cerrada de hallazgos, cada uno con la
   frase COPIADA del documento.
2. El código verifica cada hallazgo: la frase está textual en el documento y, si es cáncer, menciona un cáncer (si no,
   se descarta con su motivo). Si hay una negación cerca ("se descarta neoplasia"), no se registra solo: lo ve una persona.
3. Un hallazgo que aparece en las 3 lecturas y no puede bajar a nadie se registra solo como evento del paciente; las
   reglas (y la tabla del HLF) recalculan la lista al instante. Lo que podría bajar (estabilización) o no fue estable
   queda como propuesta para que el equipo lo confirme.
"""
import re
from concurrent.futures import ThreadPoolExecutor
from typing import List, Literal

from pydantic import BaseModel, Field, ValidationError

import informe
from modelos import SUBTIPOS, normalizar

VERSION = "lector_documento_v1"
LECTURAS = 3

# hallazgo → evento del registro (tipo, subtipo). None: no se registra (solo se informa)
EVENTO_DE = {
    "cancer_confirmado": ("hallazgo_oncologico", "cáncer confirmado"),
    "sospecha_cancer": ("hallazgo_oncologico", "sospecha de cáncer"),
    "antecedente_cancer": None,  # en remisión / antecedente: la tabla del HLF lo deja en BAJA (pág. 102), no sube
    "ingreso_uci": ("hospitalizacion", "ingreso UCI"),
    "hospitalizacion": ("hospitalizacion", "ingreso hospitalario"),
    "descompensacion_grave": ("visita_urgencia", "descompensación grave"),
    "descompensacion": ("visita_urgencia", "descompensación"),
    "examen_alterado": ("examen_alterado", "resultado alterado"),
    "aumento_tratamiento": ("cambio_farmaco", "aumento dosis"),
    "estabilizacion": ("control_aps", "estabilización"),
}
NO_AUTOMATICO = {"estabilizacion"}  # podría bajar la prioridad: siempre lo confirma una persona
ONCOLOGICO = re.compile(r"c[aá]ncer|carcinoma|adenocarcinoma|neoplasia|neoplasico|tumor maligno|malign|linfoma|leucemia|sarcoma|"
                        r"melanoma|mieloma|metast|blastoma|\bca\.? de\b|bi-?rads\s*[45]|lesion sospechosa", re.IGNORECASE)


class Hallazgo(BaseModel):
    tipo: Literal["cancer_confirmado", "sospecha_cancer", "antecedente_cancer", "ingreso_uci", "hospitalizacion",
                  "descompensacion_grave", "descompensacion", "examen_alterado", "aumento_tratamiento", "estabilizacion"]
    cita: str = Field(min_length=4, max_length=400)


class LecturaDocumento(BaseModel):
    hallazgos: List[Hallazgo] = []


SISTEMA = """Lees documentos clínicos (epicrisis, informes de urgencia, biopsias, interconsultas) de un hospital público
chileno. NO asignas prioridades: solo listas los hallazgos del documento que estén en esta lista cerrada:
- cancer_confirmado: cáncer o tumor maligno confirmado (biopsia, anatomía patológica, diagnóstico establecido).
- sospecha_cancer: sospecha de cáncer (lesión sospechosa, "probable neoplasia", "estudio por sospecha de malignidad").
- antecedente_cancer: cáncer antiguo, tratado o en remisión (no activo).
- ingreso_uci: ingreso a UCI / UTI / UPC.
- hospitalizacion: hospitalización (ingreso a sala).
- descompensacion_grave: descompensación grave de su enfermedad o triage ESI 1-2.
- descompensacion: descompensación no grave.
- examen_alterado: examen o laboratorio alterado relevante.
- aumento_tratamiento: aumento de dosis o nuevo fármaco por mal control.
- estabilizacion: el paciente está estable, compensado o con buena respuesta.
Reglas:
1. "cita" es una frase COPIADA TEXTUAL del documento (sin cambiar palabras), de 4 a 400 caracteres.
2. Un hallazgo negado o descartado NO es un hallazgo ("se descarta neoplasia", "sin hospitalización").
3. Tumores benignos no son cáncer. No inventes. Si no hay hallazgos, responde una lista vacía."""

HERRAMIENTA = {"toolSpec": {"name": "listar_hallazgos", "description": "Hallazgos del documento con cita textual.",
                            "inputSchema": {"json": {"type": "object", "properties": {"hallazgos": {"type": "array", "items": {
                                "type": "object", "properties": {"tipo": {"type": "string", "enum": list(EVENTO_DE)},
                                                                 "cita": {"type": "string"}},
                                "required": ["tipo", "cita"]}}}, "required": ["hallazgos"]}}}}


def _leer(texto, cliente):
    try:
        crudo, uso = cliente.leer(SISTEMA, "DOCUMENTO:\n" + texto, HERRAMIENTA, 700)
        return LecturaDocumento.model_validate(crudo), uso, None
    except ValidationError as e:
        return None, {}, f"json_invalido: {e.errors()[0]['msg']}"
    except Exception as e:  # timeout, permisos, throttling
        return None, {}, f"fallo_llm: {type(e).__name__}: {str(e)[:160]}"


def verificar(h: Hallazgo, texto):
    """Devuelve (posición de la cita en el documento normalizado, motivo de rechazo o None)."""
    doc, cita = normalizar(texto), normalizar(h.cita)
    i = doc.find(cita)
    if i < 0:
        return None, "la frase citada no está en el documento"
    if h.tipo in ("cancer_confirmado", "sospecha_cancer", "antecedente_cancer") and not ONCOLOGICO.search(cita):
        return i, "la frase citada no menciona un cáncer"
    return i, None


def leer_documento(texto, cliente, lecturas=LECTURAS):
    """Lee el documento N veces y devuelve {aceptados, propuestos, descartados, informativos, lecturas, tokens}."""
    with ThreadPoolExecutor(max_workers=lecturas) as ex:
        crudas = list(ex.map(lambda _: _leer(texto, cliente), range(lecturas)))
    validas = [r for r, _, err in crudas if r is not None]
    errores = [err for _, _, err in crudas if err]
    por_tipo, descartados = {}, []
    for k, r in enumerate(validas):
        for h in r.hallazgos:
            pos, motivo = verificar(h, texto)
            if motivo:
                descartados.append({"tipo": h.tipo, "cita": h.cita, "motivo": motivo})
                continue
            por_tipo.setdefault(h.tipo, {"cita": h.cita, "pos": pos, "lecturas": set()})["lecturas"].add(k)
    doc = normalizar(texto)
    aceptados, propuestos, informativos = [], [], []
    for tipo, x in por_tipo.items():
        estable = len(x["lecturas"]) == lecturas and not errores
        fecha = informe._fecha_del_evento(doc, x["pos"])
        h = {"tipo": tipo, "cita": x["cita"], "fecha": fecha and fecha.isoformat(), "fecha_en_documento": fecha is not None,
             "lecturas": f"{len(x['lecturas'])}/{lecturas}"}
        if EVENTO_DE[tipo] is None:
            informativos.append({**h, "nota": "antecedente o remisión: la tabla del HLF lo deja en prioridad baja (pág. 102); no cambia la prioridad"})
            continue
        t, sub = EVENTO_DE[tipo]
        h.update(tipo_evento=t, subtipo=sub, severidad=SUBTIPOS[t][sub])
        negado = informe._negado(doc, x["pos"])  # NegEx puede equivocarse: si hay duda, decide una persona
        if tipo in NO_AUTOMATICO:
            propuestos.append({**h, "motivo": "podría bajar la prioridad: lo confirma el equipo clínico"})
        elif negado:
            propuestos.append({**h, "motivo": "hay una negación cerca de la frase (\"no\", \"sin\", \"descarta\"): lo confirma el equipo clínico"})
        elif not estable:
            propuestos.append({**h, "motivo": f"apareció en {h['lecturas']} lecturas: no es estable, lo confirma el equipo clínico"})
        else:
            aceptados.append(h)
    # una sola entrada por evento del registro (el más grave primero, como el resto del sistema)
    orden = list(EVENTO_DE)
    aceptados.sort(key=lambda h: orden.index(h["tipo"]))
    return {"version": VERSION, "aceptados": aceptados, "propuestos": propuestos, "descartados": descartados,
            "informativos": informativos, "lecturas": len(validas), "errores": errores,
            "tokens_entrada": sum((u.get("tokens_entrada") or 0) for _, u, _ in crudas),
            "tokens_salida": sum((u.get("tokens_salida") or 0) for _, u, _ in crudas)}


def evento_registrable(h, corte):
    """Evento listo para guardar (la fecha del documento, o la de hoy si no trae; nunca posterior al corte)."""
    f = h["fecha"] if h["fecha"] and h["fecha"] <= corte.isoformat() else corte.isoformat()
    return {"fecha_evento": f, "tipo_evento": h["tipo_evento"], "subtipo": h["subtipo"], "severidad": h["severidad"],
            "detalle": f'Informe (leído por IA): "{h["cita"]}"', "origen": "documento_ia", "cita": h["cita"]}
