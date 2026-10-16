"""Combinaciones de riesgo (conocimiento/combinaciones_riesgo.json): una condición de base del paciente + un evento o
hallazgo que juntos aumentan el riesgo de muerte o daño irreversible (p. ej. diabetes + uña encarnada = pie diabético;
anticoagulado + golpe en la cabeza = hemorragia intracraneal). Mismo principio: la IA LEE, el código DECIDE.

1. Claude lee el texto 3 veces y marca qué combinaciones de la lista cerrada se cumplen, copiando la frase del GATILLO y,
   si la condición de base no está en el registro, la frase que la muestra. Aparte, puede señalar una combinación
   peligrosa que NO está en la lista (red de seguridad): queda como alerta visible, no cambia la prioridad.
2. El código verifica: la frase del gatillo está en el texto, no está negada y contiene un término obligatorio del
   gatillo (no puede hablar de otra cosa); la base está en el registro del paciente
   (diagnóstico, comorbilidades, edad) o en una frase verificada del texto que la nombra. 2 de 3 lecturas iguales.
3. Efecto: "urgencia" (derivar hoy, primero, contactar hoy), "alta" (sube) o "alerta". Nunca baja a nadie.
"""
import json
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import List

from pydantic import BaseModel, ValidationError, field_validator

import informe
from modelos import buscar_cita, normalizar

LECTURAS = 3
_KB = {}


def cargar():
    if "kb" not in _KB:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "conocimiento", "combinaciones_riesgo.json"), encoding="utf-8") as f:
            _KB["kb"] = json.load(f)
        _KB["por_id"] = {c["id"]: c for c in _KB["kb"]["combinaciones"]}
    return _KB


def condiciones(perfil):
    """Lo que el registro sabe del paciente: códigos CIE-10 (diagnóstico de la SIC y comorbilidades), nombres y edad."""
    pac, le = perfil["paciente"], perfil["lista_espera"]
    import puntaje  # fila de la tabla del HLF → CIE-10 del registro equivalente (si es la misma enfermedad)
    cies = [puntaje.cie_base(le.get("diagnostico_cie10") or "")] + [c.get("cie10") or "" for c in pac.get("comorbilidades", [])]
    nombres = [le.get("diagnostico_texto") or ""] + [c.get("nombre") or c.get("condicion") or "" for c in pac.get("comorbilidades", [])]
    return {"cie10": [c.upper() for c in cies if c], "nombres": [normalizar(n) for n in nombres if n], "edad": pac.get("edad")}


def base_en_registro(comb, cond):
    b = comb["base"]
    if b.get("cualquiera"):
        return True
    if b.get("edad_min") and (cond["edad"] or 0) >= b["edad_min"]:
        return True
    if any(c.startswith(p) for c in cond["cie10"] for p in b.get("cie10", [])):
        return True
    return any(normalizar(t) in n for t in b.get("terminos", []) for n in cond["nombres"])


def gatillo_en_cita(comb, cita):
    """La frase del gatillo debe hablar de lo que dice el gatillo (términos obligatorios de cada combinación)."""
    c = normalizar(cita or "")
    return any(normalizar(t) in c for t in comb.get("gatillo_terminos", [])) if comb.get("gatillo_terminos") else True


def base_en_cita(comb, cita):
    c = normalizar(cita or "")
    return bool(c) and any(normalizar(t) in c for t in comb["base"].get("terminos", []))


class Marca(BaseModel):
    id: str
    cita_gatillo: str
    cita_base: str = ""


class Otra(BaseModel):
    descripcion: str
    cita: str


class Lectura(BaseModel):
    combinaciones: List[Marca] = []
    otras: List[Otra] = []

    @field_validator("combinaciones", "otras", mode="before")
    @classmethod
    def lista_en_texto(cls, v):  # a veces el modelo entrega la lista como texto JSON: se acepta si es una lista válida
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except ValueError:
                return []
        if isinstance(v, dict):  # un solo elemento sin lista, o la lista dentro de otra clave
            v = next((x for x in v.values() if isinstance(x, list)), [v])
        return [json.loads(x) if isinstance(x, str) and x.strip().startswith("{") else x for x in (v or [])]


def herramienta():
    ids = list(cargar()["por_id"])
    return {"toolSpec": {"name": "marcar_combinaciones", "description": "Combinaciones de riesgo que se cumplen, con citas textuales.",
                         "inputSchema": {"json": {"type": "object", "properties": {
                             "combinaciones": {"type": "array", "items": {"type": "object", "properties": {
                                 "id": {"type": "string", "enum": ids}, "cita_gatillo": {"type": "string"}, "cita_base": {"type": "string"}},
                                 "required": ["id", "cita_gatillo"]}},
                             "otras": {"type": "array", "items": {"type": "object", "properties": {
                                 "descripcion": {"type": "string"}, "cita": {"type": "string"}}, "required": ["descripcion", "cita"]}}},
                             "required": ["combinaciones", "otras"]}}}}


SISTEMA = """Revisas un texto clínico buscando COMBINACIONES DE RIESGO: una condición de base del paciente + un evento o
hallazgo que juntos ponen en riesgo su vida o le pueden causar un daño irreversible. No asignas prioridades.
Reglas:
- Marca solo combinaciones de la lista cuyo GATILLO aparece en el texto. "cita_gatillo" es UNA frase continua copiada
  textual del texto (sin "..."). Si la condición de base NO está en "lo que se sabe del paciente" pero el texto la nombra,
  copia esa frase en "cita_base"; si ya se sabe, deja "cita_base" vacío.
- Un hallazgo negado o descartado ("sin fiebre", "niega dolor torácico") NO es un gatillo.
- No inventes datos ni umbrales. Si dudas, no marques.
- En "otras", anota solo combinaciones claramente peligrosas que NO estén en la lista (con su frase textual). Si no hay,
  deja la lista vacía."""


def armar_prompt(cond, edad, sexo, texto):
    lista = "\n".join(f'{c["id"]}: {c["nombre"]}. Base: {c["base"]["descripcion"]}. Gatillo: {c["gatillo"]}.'
                      for c in cargar()["kb"]["combinaciones"])
    sabe = f'Edad {edad}, sexo {sexo}. Diagnóstico y comorbilidades: {"; ".join(cond) or "sin registro"}.'
    return f"LO QUE SE SABE DEL PACIENTE: {sabe}\n\nCOMBINACIONES (lista cerrada):\n{lista}\n\nTEXTO:\n{texto}"


def detectar(texto, perfil, cliente, lecturas=LECTURAS):
    """Devuelve {aplicadas: [...], alertas: [...], lecturas, errores, tokens}."""
    kb, cond = cargar(), condiciones(perfil)
    pac, le = perfil["paciente"], perfil["lista_espera"]
    descr = [f'{le.get("diagnostico_cie10")} {le.get("diagnostico_texto")}'] + \
            [f'{c.get("cie10") or ""} {c.get("nombre") or c.get("condicion") or ""}'.strip() for c in pac.get("comorbilidades", [])]
    usuario = armar_prompt(descr, pac.get("edad"), pac.get("sexo"), texto)
    doc = normalizar(texto)

    def una(_):
        try:
            crudo, uso = cliente.leer(SISTEMA, usuario, herramienta(), 900)
            return Lectura.model_validate(crudo), uso, None
        except ValidationError as e:
            return None, {}, f"json_invalido: {e.errors()[0]['msg']}"
        except Exception as e:  # timeout, permisos, throttling
            return None, {}, f"fallo_llm: {type(e).__name__}: {str(e)[:160]}"
    with ThreadPoolExecutor(max_workers=lecturas) as ex:
        crudas = list(ex.map(una, range(lecturas)))
    votos, citas, otras = Counter(), {}, {}
    for r, _, _ in crudas:
        if r is None:
            continue
        vistos = set()
        for m in r.combinaciones:
            comb = kb["por_id"].get(m.id)
            if not comb or m.id in vistos:
                continue
            i = buscar_cita(m.cita_gatillo, doc)
            if i < 0 or informe._negado(doc, i) or not gatillo_en_cita(comb, m.cita_gatillo):
                continue                                     # gatillo inventado, negado o que habla de otra cosa
            if not base_en_registro(comb, cond):
                j = buscar_cita(m.cita_base, doc)
                if j < 0 or informe._negado(doc, j) or not base_en_cita(comb, m.cita_base):
                    continue                                 # la base no está ni en el registro ni en una frase verificada
            vistos.add(m.id)
            votos[m.id] += 1
            citas.setdefault(m.id, (m.cita_gatillo, m.cita_base))
        for o in r.otras:
            if buscar_cita(o.cita, doc) >= 0:
                otras.setdefault(normalizar(o.cita), {"descripcion": o.descripcion[:200], "cita": o.cita})
    aplicadas = []
    for cid, n in votos.items():
        if n >= 2:                                           # 2 de 3 lecturas
            c = kb["por_id"][cid]
            aplicadas.append({"id": cid, "nombre": c["nombre"], "efecto": c["efecto"], "desenlace": c["desenlace"],
                              "cita_gatillo": citas[cid][0], "cita_base": citas[cid][1] or None,
                              "fuente": c["fuente"], "estado": c["estado"], "letalidad": c.get("letalidad"), "riesgo": c.get("riesgo")})
    return {"aplicadas": aplicadas, "alertas": list(otras.values()),
            "lecturas": len([r for r, _, _ in crudas if r]), "errores": [e for _, _, e in crudas if e],
            "tokens_entrada": sum((u.get("tokens_entrada") or 0) for _, u, _ in crudas),
            "tokens_salida": sum((u.get("tokens_salida") or 0) for _, u, _ in crudas), "version": kb["kb"]["version"]}


def evento(d, fecha):
    """Evento del registro con las combinaciones verificadas (o alertas). La regla de puntaje.py lo aplica: solo sube."""
    if not d["lecturas"] and d["errores"]:
        # la IA no pudo leer: un riesgo no puede pasar en silencio → alerta visible para que una persona lea el texto
        d = {**d, "alertas": [{"descripcion": "la IA no pudo revisar este texto en busca de combinaciones de riesgo; léalo una persona",
                               "cita": d["errores"][0][:120]}]}
    # combinaciones sin fuente verificada: solo alerta visible (no mueven a nadie)
    sin_fuente = [{"descripcion": f'{a["nombre"]} (sin fuente verificada)', "cita": a["cita_gatillo"], "riesgo": a.get("riesgo")}
                  for a in d["aplicadas"] if a["efecto"] == "alerta"]
    d = {**d, "aplicadas": [a for a in d["aplicadas"] if a["efecto"] != "alerta"], "alertas": d["alertas"] + sin_fuente}
    if not d["aplicadas"] and not d["alertas"]:
        return None
    urg = [a for a in d["aplicadas"] if a["efecto"] == "urgencia"]
    alta = [a for a in d["aplicadas"] if a["efecto"] == "alta"]
    def txt(a):
        return f'{a["nombre"]}: "{a["cita_gatillo"]}" → riesgo de {a["desenlace"]}'
    return {"fecha_evento": fecha, "tipo_evento": "combinacion_riesgo",
            "subtipo": "urgencia" if urg else ("prioridad alta" if alta else "alerta"),
            "severidad": "grave" if urg else ("moderada" if alta else "leve"),
            "detalle": "; ".join(txt(a) for a in d["aplicadas"]) or "; ".join(f'{o["descripcion"]}: "{o["cita"]}"' for o in d["alertas"]),
            "origen": "combinaciones_ia", "urgencia": bool(urg), "nivel_criterio": "alta" if (urg or alta) else None,
            "texto_urgencia": "; ".join(txt(a) for a in urg) or None, "texto_criterio": "; ".join(txt(a) for a in alta) or None,
            "combinaciones": d["aplicadas"], "alertas": d["alertas"],
            "letalidad": min((a["letalidad"] for a in d["aplicadas"] if a.get("letalidad")), default=None),
            "fuente": "; ".join(sorted({a["fuente"]["documento"] for a in d["aplicadas"]})) or "Combinaciones de riesgo (sin coincidencia en la lista)"}
