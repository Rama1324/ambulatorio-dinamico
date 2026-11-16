"""Carga el registro del hospital (perfiles.json) a la tabla DynamoDB como ítems normalizados con origen = "registro_base":
un ítem "perfil" por paciente y uno por cada evento, medición y cita (docs/diseno/ESPECIFICACION_MVP.md §3.1).
Usa el mismo código que la aplicación (lambda/datos.py y lambda/almacen_dynamo.py).

Uso, desde la raíz del repo (perfiles.json no va al repo: está en data/):
  python scripts/cargar_registro.py --archivo data/perfiles.json --tabla <nombre> [--region us-east-1] [--perfil hack]
  (--perfil "" usa las credenciales por defecto del entorno)

Se puede repetir: cada ítem se escribe solo si no existe, así que lo ya cargado no se pisa ni se duplica, y lo que el
equipo registró después no se toca. Si se cargó algo nuevo, cambia la época del marcador para que cada contenedor de
la aplicación vuelva a leer la tabla en su próxima solicitud.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lambda"))


def cargar(perfiles, almacen, pacientes_por_lote=200, avisar=print):
    """Escribe los perfiles como ítems del registro base. Devuelve {"pacientes", "items", "nuevos"}."""
    import datos
    total = nuevos = 0
    for i in range(0, len(perfiles), pacientes_por_lote):  # por pacientes completos: su contador rev sube una sola vez
        items = [it for p in perfiles[i:i + pacientes_por_lote] for it in datos.items_de_perfil(p, origen=datos.REGISTRO_BASE)]
        nuevos += almacen.guardar_lote(items)
        total += len(items)
        avisar(f"  {min(i + pacientes_por_lote, len(perfiles))} de {len(perfiles)} pacientes · {total} ítems revisados · {nuevos} nuevos")
    if nuevos:
        almacen.cambiar_epoca()
    return {"pacientes": len(perfiles), "items": total, "nuevos": nuevos}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Carga perfiles.json a DynamoDB como ítems del registro base (se puede repetir).")
    ap.add_argument("--archivo", required=True, help="ruta a perfiles.json")
    ap.add_argument("--tabla", required=True, help="nombre de la tabla DynamoDB (salida TableName del stack)")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--perfil", default="hack", help='perfil de AWS ("" = credenciales por defecto)')
    a = ap.parse_args(argv)
    import boto3
    from almacen_dynamo import AlmacenDynamo
    with open(a.archivo, encoding="utf-8") as f:
        perfiles = json.load(f)
    sesion = boto3.Session(profile_name=a.perfil or None, region_name=a.region)
    print(f"Cargando {len(perfiles)} pacientes de {a.archivo} a la tabla {a.tabla} ({a.region})…")
    r = cargar(perfiles, AlmacenDynamo(a.tabla, sesion=sesion, hilos=32))
    if r["nuevos"]:
        print(f'Listo: {r["nuevos"]} ítems nuevos de {r["items"]}. Los contenedores recargan en su próxima solicitud.')
    else:
        print(f'Nada que cargar: los {r["items"]} ítems ya estaban en la tabla.')
    return r


if __name__ == "__main__":
    main()
