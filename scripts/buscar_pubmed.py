"""Verifica la evidencia de la base de conocimiento contra PubMed (NCBI E-utilities) y la congela en el repo.
Corre en DESARROLLO, nunca en la Lambda. Sin API key: máximo 3 solicitudes por segundo.

Entrada: un borrador JSON (lista de entradas {id, diagnostico, concepto, valor, unidad, fuente{tipo, ref, detalle}, estado}),
         armado a partir de la búsqueda bibliográfica.
Salida:  lambda/conocimiento/pubmed_evidencia.json  (ventanas de riesgo tras un evento: ids *.ventana_dias)
         lambda/conocimiento/guias_umbrales.json   (umbrales de mediciones: ids medicion.*)
Cada PMID se consulta con esummary y se guarda el título, la revista y el año devueltos por NCBI. Si un PMID no existe,
la entrada pasa a 'a_validar_por_medico' con valor null.
Uso: python scripts/buscar_pubmed.py ruta/borrador.json
Guía E-utilities: https://www.ncbi.nlm.nih.gov/books/NBK25497/
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB = os.path.join(RAIZ, "lambda", "conocimiento")
ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


def esummary(pmids):
    q = urllib.parse.urlencode({"db": "pubmed", "id": ",".join(pmids), "retmode": "json"})
    with urllib.request.urlopen(f"{ESUMMARY}?{q}", timeout=30) as r:
        return json.load(r)["result"]


def main(borrador):
    with open(borrador, encoding="utf-8") as f:
        entradas = json.load(f)
    pmids = sorted({e["fuente"]["ref"].split(":")[1].strip() for e in entradas
                    if ((e.get("fuente") or {}).get("ref") or "").upper().startswith("PMID:")})
    meta = {}
    for i in range(0, len(pmids), 20):
        res = esummary(pmids[i:i + 20])
        for p in pmids[i:i + 20]:
            d = res.get(p) or {}
            if d.get("title") and not d.get("error"):
                meta[p] = {"titulo": d["title"], "revista": d.get("source"), "anio": (d.get("pubdate") or "")[:4]}
        time.sleep(0.4)
    no_encontrados = []
    for e in entradas:
        ref = (e.get("fuente") or {}).get("ref") or ""
        if ref.upper().startswith("PMID:"):
            p = ref.split(":")[1].strip()
            if p in meta:
                e["fuente"]["verificado_ncbi"] = {**meta[p], "consultado": "2026-10-15"}
            else:
                no_encontrados.append(p)
                e.update({"estado": "a_validar_por_medico", "valor": None})
                e["fuente"]["verificado_ncbi"] = None
    ventanas = [e for e in entradas if e["id"].endswith(".ventana_dias")]
    umbrales = [e for e in entradas if e["id"].startswith("medicion.")]
    comun = {"version": "evidencia_v1", "generado": "2026-10-15", "script": "scripts/buscar_pubmed.py"}
    with open(os.path.join(KB, "pubmed_evidencia.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({**comun, "entradas": ventanas}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(KB, "guias_umbrales.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({**comun, "entradas": umbrales}, f, ensure_ascii=False, indent=1)
    print(f"PMID consultados: {len(pmids)} · verificados: {len(meta)} · no encontrados: {no_encontrados or 'ninguno'}")
    print(f"ventanas: {len(ventanas)} ({sum(e['estado'] == 'con_fuente' for e in ventanas)} con fuente) · "
          f"umbrales: {len(umbrales)} ({sum(e['estado'] == 'con_fuente' for e in umbrales)} con fuente)")


if __name__ == "__main__":
    main(sys.argv[1])
