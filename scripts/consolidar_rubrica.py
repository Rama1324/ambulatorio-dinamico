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
    "E11": {"tipo": "HbA1c", "umbral_id": "medicion.HbA1c.descompensado_umbral", "sentido": "mayor_igual", "sube_a_fila": True},
    "J44": {"tipo": "saturacion_o2", "umbral_id": "medicion.saturacion_o2.descompensado_umbral", "sentido": "menor_igual", "sube_a_fila": False},
    "J45": {"tipo": "peak_flow", "umbral_id": "medicion.peak_flow.descompensado_umbral", "sentido": "menor_igual", "sube_a_fila": False},
    "F32": {"tipo": "PHQ9", "umbral_id": "medicion.PHQ9.descompensado_umbral", "sentido": "mayor_igual", "sube_a_fila": False},
    "I10": {"tipo": "presion_sistolica", "umbral_id": "medicion.presion_sistolica.descompensado_umbral", "sentido": "mayor_igual", "sube_a_fila": False},
    "M17": {"tipo": "escala_dolor_eva", "umbral_id": "medicion.escala_dolor_eva.descompensado_umbral", "sentido": "mayor_igual", "sube_a_fila": False},
    "M54": {"tipo": "escala_dolor_eva", "umbral_id": "medicion.escala_dolor_eva.descompensado_umbral", "sentido": "mayor_igual", "sube_a_fila": False},
    "M75": {"tipo": "escala_dolor_eva", "umbral_id": "medicion.escala_dolor_eva.descompensado_umbral", "sentido": "mayor_igual", "sube_a_fila": False},
}


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
        # ventana: la MÁS LARGA con fuente entre los eventos graves del diagnóstico (conservador: no baja antes)
        vs = [e for i, e in evid.items() if i.startswith(f"{cie}.") and i.endswith(".ventana_dias") and e.get("estado") == "con_fuente" and e.get("valor")]
        if vs:
            v = max(vs, key=lambda e: e["valor"])
            x["ventana"] = {"valor": v["valor"], "unidad": "días", "fuente": fuente_txt(v), "id": v["id"], "estado": "con_fuente"}
        else:
            x["ventana"] = {"valor": None, "estado": "a_validar_por_medico", "fuente": "sin fuente: el evento grave sigue vigente hasta una estabilización (conservador)"}
            if x["fila_descompensado"]:
                pendientes.append(f"{cie}: ¿cuántos días después de una urgencia u hospitalización grave sigue vigente la fila 'descompensado'?")
        m = MEDICION_CLAVE.get(cie)
        if m:
            u = umb.get(m["umbral_id"])
            umbral = ({"valor": u["valor"], "unidad": u.get("unidad"), "sentido": m["sentido"], "fuente": fuente_txt(u), "estado": u.get("estado", "con_fuente")}
                      if u and u.get("valor") is not None else {"valor": None, "sentido": m["sentido"], "estado": "a_validar_por_medico", "fuente": "sin fuente"})
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
