"""Arma lambda/conocimiento/rubrica_v1.json (la base que usan la rúbrica y la fórmula) desde:
  - ssmso_hlf_2025.json   filas de la Tabla de priorización SSMSO 2025 del HLF (página por página)
  - ord536.json           cascada de orden MINSAL Ord. 536/2025
  - pubmed_evidencia.json ventanas de riesgo tras un evento (PMID verificados con scripts/buscar_pubmed.py)
  - guias_umbrales.json   umbrales de las mediciones clave (guías MINSAL / internacionales)
Valores sin fuente quedan "a_validar_por_medico" con valor null → la fórmula usa la opción conservadora (no baja a nadie).
Uso: python scripts/consolidar_rubrica.py
"""
import json
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB = os.path.join(RAIZ, "lambda", "conocimiento")

# Medición clave de cada diagnóstico (decisión de diseño del equipo, a validar por médico).
# sube_a_fila: solo si la tabla define el estado por control metabólico (DM2 "descontrolada"); el resto solo genera revisión.
MEDICION_CLAVE = {
    "E11": {"tipo": "HbA1c", "umbral_id": "medicion.HbA1c.descompensado_umbral", "unidad_registro": "%", "sube_a_fila": True},
    "J44": {"tipo": "saturacion_o2", "umbral_id": "medicion.SatO2.EPOC_moderado_umbral", "unidad_registro": "%", "sube_a_fila": False},
    "J45": {"tipo": "peak_flow", "umbral_id": "medicion.PEF.asma_descompensado_umbral", "unidad_registro": "L/min", "sube_a_fila": False},
    "F32": {"tipo": "PHQ9", "umbral_id": "medicion.PHQ9.descompensado_umbral", "unidad_registro": "puntos", "sube_a_fila": False},
    "I10": {"tipo": "presion_sistolica", "umbral_id": "medicion.PAS.descompensado_umbral", "unidad_registro": "mmHg", "sube_a_fila": False},
    "M17": {"tipo": "escala_dolor_eva", "umbral_id": "medicion.EVA.severo_umbral", "unidad_registro": "puntos", "sube_a_fila": False},
    "M54": {"tipo": "escala_dolor_eva", "umbral_id": "medicion.EVA.severo_umbral", "unidad_registro": "puntos", "sube_a_fila": False},
    "M75": {"tipo": "escala_dolor_eva", "umbral_id": "medicion.EVA.severo_umbral", "unidad_registro": "puntos", "sube_a_fila": False},
}
# Eventos a los que aplica cada ventana del borrador
EVENTOS_DE = {"hospitalizacion": ["hospitalizacion"], "visita_urgencia": ["visita_urgencia"],
              "visita_urgencia_o_hospitalizacion": ["visita_urgencia", "hospitalizacion"], "evento_grave": ["visita_urgencia", "hospitalizacion"]}


def cargar(nombre, defecto=None):
    p = os.path.join(KB, nombre)
    if not os.path.exists(p):
        return defecto
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def fuente_txt(e):
    f = e.get("fuente") or {}
    return f"{f.get('ref', '')} — {f.get('detalle', '')}".strip(" —")


def main():
    ssmso, ord536 = cargar("ssmso_hlf_2025.json"), cargar("ord536.json")
    evid = {e["id"]: e for e in (cargar("pubmed_evidencia.json", {"entradas": []})["entradas"])}
    umb = {e["id"]: e for e in (cargar("guias_umbrales.json", {"entradas": []})["entradas"])}
    pendientes, dxs = [], {}
    for cie, d in ssmso["diagnosticos"].items():
        x = {k: d.get(k) for k in ("texto", "fila_descompensado", "estado", "equivalencia", "detalle", "candidata")}
        # ventanas por tipo de evento (la del evento citado). Sin fuente para ese tipo: no vence (conservador, no baja a nadie)
        x["ventanas"] = {}
        for i, e in evid.items():
            if not (i.startswith(f"{cie}.") and i.endswith(".ventana_dias")):
                continue
            evento = i.split(".")[1]
            for tipo in EVENTOS_DE.get(evento, [evento]):
                if e.get("estado") == "con_fuente" and e.get("valor"):
                    if tipo not in x["ventanas"] or e["valor"] > x["ventanas"][tipo]["valor"]:
                        x["ventanas"][tipo] = {"valor": e["valor"], "unidad": "días", "fuente": fuente_txt(e), "id": e["id"], "estado": "con_fuente"}
        if x["fila_descompensado"]:
            for tipo in ("visita_urgencia", "hospitalizacion"):
                if tipo not in x["ventanas"]:
                    pendientes.append(f"{cie}: ¿cuántos días tras una {tipo.replace('_', ' ')} grave sigue vigente la fila descompensado? (sin fuente: no vence)")
        m = MEDICION_CLAVE.get(cie)
        if m:
            u = umb.get(m["umbral_id"])
            sentido = {">=": "mayor_igual", ">": "mayor_igual", "<": "menor", "<=": "menor_igual"}.get((u or {}).get("operador"), "mayor_igual")
            if u and u.get("valor") is not None and str(u.get("unidad", "")).split(" ")[0] != m["unidad_registro"].split(" ")[0]:
                umbral = {"valor": None, "sentido": sentido, "estado": "a_validar_por_medico",
                          "fuente": f"{fuente_txt(u)} · NO APLICABLE: la guía usa {u.get('unidad')} y el registro trae {m['unidad_registro']}"}
            elif u and u.get("valor") is not None:
                umbral = {"valor": u["valor"], "unidad": u.get("unidad"), "sentido": sentido, "fuente": fuente_txt(u), "estado": u.get("estado", "con_fuente"), "id": u["id"]}
            else:
                umbral = {"valor": None, "sentido": sentido, "estado": "a_validar_por_medico", "fuente": "sin fuente"}
            x["medicion"] = {"tipo": m["tipo"], "umbral": umbral, "sube_a_fila": m["sube_a_fila"], "definida_por": "equipo (a validar por médico)"}
            if m["sube_a_fila"] and d.get("fila_descompensado"):
                x["fila_por_medicion"] = d["fila_descompensado"]
            if umbral["estado"] != "con_fuente":
                pendientes.append(f"{cie}: umbral de {m['tipo']} que define descompensación")
        x["medicion_clave"] = m["tipo"] if m else None
        if d.get("estado") == "a_validar_por_medico" or d.get("equivalencia"):
            pendientes.append(f"{cie}: {(d.get('equivalencia') or {}).get('detalle') or d.get('detalle')}")
        dxs[cie] = x
    rub = {"version": "rubrica_v1", "generado": "2026-10-15",
           "fuentes": {"ssmso": "Tabla SSMSO 2025, HLF", "ssmso_ref": ssmso["fuente"], "ord536": ord536["fuente"]},
           "cascada_orden": ord536["cascada"], "diagnosticos": dxs, "pendientes_medicos": pendientes}
    with open(os.path.join(KB, "rubrica_v1.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(rub, f, ensure_ascii=False, indent=1)
    print(f"rubrica_v1.json: {len(dxs)} diagnósticos, {len(pendientes)} pendientes para médicos")


if __name__ == "__main__":
    main()
