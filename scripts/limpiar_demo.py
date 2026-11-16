"""Deja la demo publicada en su estado inicial (el registro del hospital tal como se cargó):
  - borra de DynamoDB todo lo registrado después de la carga inicial (eventos, revisiones, llamadas, decisiones, gestión,
    ajustes, novedades, dictámenes, enmiendas, pacientes ingresados o importados, lotes, criterios locales…): todo ítem
    que no tenga origen = "registro_base";
  - devuelve a su contenido original los perfiles del registro que se modificaron (fallecido, atendido, diagnóstico…);
  - conserva las evaluaciones de la IA de los pacientes del registro (salvo --todo) y las particiones que se indiquen;
  - cambia la época del marcador: cada contenedor de la aplicación vuelve a leer la tabla en su próxima solicitud.
Es el único lugar donde se borra: la aplicación solo agrega.

Uso, desde la raíz del repo (perfil AWS "hack" con credenciales vigentes):
  python scripts/limpiar_demo.py                     # muestra qué hay; no borra nada
  python scripts/limpiar_demo.py --borrar            # limpia; conserva las evaluaciones de la IA
  python scripts/limpiar_demo.py --borrar --todo     # borra también las evaluaciones (habría que volver a correr el barrido)
  python scripts/limpiar_demo.py --borrar --conservar _kb     # no toca esas particiones (aquí, los criterios locales)
Opciones: --tabla <nombre> (si no, la busca en el stack), --stack ambulatorio-hlf, --region us-east-1, --perfil hack.
"""
import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lambda"))


def revisar(cliente, tabla, todo=False, conservar=()):
    """Lee la tabla y separa (a borrar, perfiles a restaurar, evaluaciones que se conservan)."""
    from almacen_dynamo import con_nombres, de_dynamo
    from datos import META, PERFIL, REGISTRO_BASE
    items, kw = [], con_nombres({"TableName": tabla, "ProjectionExpression": "#pk, #sk, #origen, #base", "ConsistentRead": True})
    while True:
        r = cliente.scan(**kw)
        items += [de_dynamo(i) for i in r.get("Items", [])]
        if "LastEvaluatedKey" not in r:
            break
        kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]
    del_registro = {i["id_paciente"] for i in items if i["sk"] == PERFIL and i.get("origen") == REGISTRO_BASE}
    borrar, restaurar, evaluaciones = [], [], 0
    for i in items:
        pk, sk = i["id_paciente"], i["sk"]
        if pk == META or pk in conservar:
            continue
        if i.get("origen") == REGISTRO_BASE:
            if sk == PERFIL and i.get("perfil_base"):
                restaurar.append(i)
        elif sk.startswith("evaluacion#") and not todo and pk in del_registro:
            # Las evaluaciones de la IA sobre pacientes del registro (barrido nocturno, ~USD 0,03 c/u) se conservan: si se
            # borra un evento de la demo, su firma deja de coincidir y esa evaluación ya no se usa.
            evaluaciones += 1
        else:
            borrar.append((pk, sk))
    return borrar, restaurar, evaluaciones


def limpiar(sesion, tabla, borrar=False, todo=False, conservar=(), avisar=print):
    """Muestra lo que hay y, con borrar=True, limpia. Devuelve {"borrados", "restaurados", "evaluaciones", "epoca"}."""
    from almacen_dynamo import cambiar_epoca, clave, con_nombres
    cliente = sesion.client("dynamodb")
    a_borrar, a_restaurar, evaluaciones = revisar(cliente, tabla, todo, conservar)
    tipos = collections.Counter(pk if pk.startswith("_") else sk.split("#")[0] for pk, sk in a_borrar)
    avisar(f"Tabla {tabla}: {len(a_borrar)} registros de la demo " + (str(dict(tipos)) if a_borrar else "") +
           f" · {len(a_restaurar)} perfiles del registro modificados" +
           (f" · se conservan {evaluaciones} evaluaciones de la IA (--todo las borra)" if evaluaciones else ""))
    out = {"borrados": 0, "restaurados": 0, "evaluaciones": evaluaciones, "epoca": None}
    if not borrar:
        avisar("No se borró nada. Para limpiar: python scripts/limpiar_demo.py --borrar")
        return out
    for i in a_restaurar:  # el perfil vuelve a ser el que vino en el registro
        especialidad = (json.loads(i["perfil_base"]).get("lista_espera") or {}).get("especialidad")
        cliente.update_item(**con_nombres({
            "TableName": tabla, "Key": clave(i["id_paciente"], i["sk"]), "ConditionExpression": "attribute_exists(#base)",
            "UpdateExpression": "SET #perfil = :p" + (", #esp = :e" if especialidad else "") + " REMOVE #base",
            "ExpressionAttributeValues": {":p": {"S": i["perfil_base"]}, **({":e": {"S": especialidad}} if especialidad else {})}}))
    with sesion.resource("dynamodb").Table(tabla).batch_writer() as lote:
        for pk, sk in a_borrar:
            lote.delete_item(Key={"id_paciente": pk, "sk": sk})
    out.update(borrados=len(a_borrar), restaurados=len(a_restaurar))
    if a_borrar or a_restaurar:  # los contenedores de la aplicación descartan su copia y vuelven a leer la tabla
        out["epoca"] = cambiar_epoca(cliente, tabla)
    avisar(f'Listo: {out["borrados"]} registros borrados y {out["restaurados"]} perfiles restaurados. La demo quedó en su estado inicial.')
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deja la demo publicada en su estado inicial (sin --borrar solo muestra).")
    ap.add_argument("--borrar", action="store_true", help="borra lo registrado en la demo y restaura los perfiles modificados")
    ap.add_argument("--todo", action="store_true", help="borra también las evaluaciones de la IA")
    ap.add_argument("--conservar", default="", help="particiones que no se tocan, separadas por coma (p. ej. _kb)")
    ap.add_argument("--tabla", default="", help="nombre de la tabla; si no se indica, se busca en el stack")
    ap.add_argument("--stack", default="ambulatorio-hlf")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--perfil", default="hack", help='perfil de AWS ("" = credenciales por defecto)')
    a = ap.parse_args(argv)
    import boto3
    sesion = boto3.Session(profile_name=a.perfil or None, region_name=a.region)
    tabla = a.tabla
    if not tabla:
        salidas = sesion.client("cloudformation").describe_stacks(StackName=a.stack)["Stacks"][0]["Outputs"]
        tabla = next(o["OutputValue"] for o in salidas if o["OutputKey"] == "TableName")
    return limpiar(sesion, tabla, a.borrar, a.todo, tuple(p.strip() for p in a.conservar.split(",") if p.strip()))


if __name__ == "__main__":
    main()
