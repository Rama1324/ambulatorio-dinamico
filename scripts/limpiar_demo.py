"""Deja la demo publicada en su estado inicial: borra de DynamoDB todo lo registrado desde la app
(eventos, revisiones, llamadas, decisiones, citas, novedades, pacientes ingresados e importaciones).
No toca perfiles.json (está en S3).

Uso, desde la raíz del repo (perfil AWS "hack" con credenciales vigentes):
  python scripts/limpiar_demo.py            # muestra cuántos registros hay, no borra
  python scripts/limpiar_demo.py --borrar   # borra lo registrado en la demo; conserva las evaluaciones de la IA
  python scripts/limpiar_demo.py --borrar --todo   # borra también las evaluaciones de la IA (habría que volver a correr el barrido)
"""
import collections
import sys

import boto3

PERFIL, REGION, STACK = "hack", "us-east-1", "ambulatorio-hlf"

sesion = boto3.Session(profile_name=PERFIL, region_name=REGION)
salidas = sesion.client("cloudformation").describe_stacks(StackName=STACK)["Stacks"][0]["Outputs"]
nombre = next(o["OutputValue"] for o in salidas if o["OutputKey"] == "TableName")
tabla = sesion.resource("dynamodb").Table(nombre)

items, kw = [], {"ProjectionExpression": "id_paciente, sk"}
while True:
    r = tabla.scan(**kw)
    items += r["Items"]
    if "LastEvaluatedKey" not in r:
        break
    kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]

# Las evaluaciones de la IA sobre pacientes del registro (barrido nocturno, ~USD 0,03 c/u) se conservan: si después se
# borra un evento de la demo, su firma deja de coincidir y esa evaluación ya no se usa. Con --todo se borran también.
if "--todo" not in sys.argv:
    conservar = [i for i in items if i["sk"].startswith("evaluacion#") and i["id_paciente"].startswith("PAC-HLF")]
    items = [i for i in items if i not in conservar]
    print(f"Se conservan {len(conservar)} evaluaciones de la IA (usar --todo para borrarlas)")
tipos = collections.Counter(i["sk"].split("#")[0] for i in items)
print(f"Tabla {nombre}: {len(items)} registros " + (str(dict(tipos)) if items else ""))
if "--borrar" not in sys.argv:
    print("No se borró nada. Para borrar: python scripts/limpiar_demo.py --borrar")
    sys.exit(0)
with tabla.batch_writer() as lote:
    for i in items:
        lote.delete_item(Key={"id_paciente": i["id_paciente"], "sk": i["sk"]})
print(f"Listo: {len(items)} registros borrados. La demo quedó en su estado inicial.")
