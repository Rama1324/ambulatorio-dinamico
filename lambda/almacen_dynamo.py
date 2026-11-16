"""Almacén sobre DynamoDB: tabla TABLE (id_paciente + sk) con el índice PorDia (dia HASH, ts RANGE, proyección ALL).

Lectura sin Scan por solicitud (docs/diseno/ESPECIFICACION_MVP.md §3.2):
  - cada contenedor lee la tabla una vez (Scan por segmentos en paralelo) y trabaja con una copia en memoria;
  - en cada solicitud lee el marcador _meta/ultimo (GetItem consistente): si no cambió, no lee nada más; si cambió, trae
    por el índice PorDia solo lo escrito desde lo último que vio, con 5 s de traslape (mezclar es idempotente por pk + sk);
  - si cambió la época del marcador (limpieza de la demo o carga masiva), vuelve a leer todo.
Escritura: solo PutItem y UpdateItem condicionales. La aplicación no borra ni usa BatchWriteItem, así que su rol puede
quedar sin esos permisos ("solo se agrega" también a nivel de IAM). Necesita GetItem, PutItem, UpdateItem, Query y Scan.
"""
import collections
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from decimal import Decimal

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

import datos
from datos import META, PERFIL, REGISTRO_BASE, ULTIMO

INDICE = "PorDia"
TRASLAPE_S = 5        # un ítem puede tardar en verse (reintentos de red, réplica del índice): siempre se relee ese margen
MARGEN_S = 60         # con el marcador más viejo que esto, se relee desde un minuto antes de la última sincronización
REINTENTOS = 6        # el índice es de consistencia eventual: se espera un momento a que alcance al marcador…
ESPERA_S = 0.05       # …6 intentos x 50 ms
CONFIRMAR_S = 2       # tras un cambio, una relectura de confirmación en la primera solicitud que llegue 2 s después
AMPLIA_S = 300        # red de seguridad: cada 5 min se relee todo lo escrito desde la relectura amplia anterior
MAX_DIAS = 3          # copia sin sincronizar hace más que esto: es más barato leer todo de nuevo que consultar día por día
YA_EXISTE = "ConditionalCheckFailedException"
# Los nombres de atributo van siempre con alias (#x): ninguno puede chocar con una palabra reservada de DynamoDB
NOMBRES = {"#pk": "id_paciente", "#sk": "sk", "#perfil": "perfil", "#base": "perfil_base", "#esp": "especialidad",
           "#origen": "origen", "#rev": "rev", "#ts": "ts", "#dia": "dia", "#expira": "expira", "#n": "n", "#epoca": "epoca"}
_SER, _DES = TypeSerializer(), TypeDeserializer()


def _sin_float(v):
    """DynamoDB no acepta float de Python: los números van como Decimal."""
    if isinstance(v, float):
        return Decimal(str(v))
    if isinstance(v, dict):
        return {k: _sin_float(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_sin_float(x) for x in v]
    return v


def _sin_decimal(v):
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, dict):
        return {k: _sin_decimal(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_sin_decimal(x) for x in v]
    return v


def a_dynamo(item):
    return {k: _SER.serialize(_sin_float(v)) for k, v in item.items() if v is not None}


def de_dynamo(item):
    """Casi todos los atributos son texto ({"S": ...}): se leen directo; el resto, con el deserializador de boto3."""
    return {k: v["S"] if "S" in v else _sin_decimal(_DES.deserialize(v)) for k, v in item.items()}


def clave(pk, sk):
    return {"id_paciente": {"S": pk}, "sk": {"S": sk}}


def con_nombres(kw):
    """Agrega ExpressionAttributeNames solo con los alias que la operación usa (DynamoDB rechaza los que sobran)."""
    usados = set(re.findall(r"#\w+", " ".join(str(kw.get(k) or "") for k in (
        "UpdateExpression", "ConditionExpression", "KeyConditionExpression", "ProjectionExpression", "FilterExpression"))))
    if usados:
        kw["ExpressionAttributeNames"] = {a: NOMBRES[a] for a in usados}
    return kw


def _restar(ts, segundos):
    return (datetime.fromisoformat(ts) - timedelta(seconds=segundos)).isoformat(timespec="microseconds")


def cliente_dynamo(sesion=None, conexiones=24):
    """Cliente de bajo nivel (el único de boto3 que se puede compartir entre hilos), con reintentos y tiempos acotados."""
    import boto3
    from botocore.config import Config
    cfg = Config(max_pool_connections=conexiones, retries={"max_attempts": 5, "mode": "standard"}, connect_timeout=3, read_timeout=15)
    return (sesion or boto3).client("dynamodb", config=cfg)


def crear_tabla(cliente, nombre):
    """La tabla que espera el almacén (en AWS la crea template.yaml; esto es para pruebas y entornos locales)."""
    cliente.create_table(
        TableName=nombre, BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": a, "AttributeType": "S"} for a in ("id_paciente", "sk", "dia", "ts")],
        KeySchema=[{"AttributeName": "id_paciente", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
        GlobalSecondaryIndexes=[{"IndexName": INDICE, "Projection": {"ProjectionType": "ALL"},
                                 "KeySchema": [{"AttributeName": "dia", "KeyType": "HASH"}, {"AttributeName": "ts", "KeyType": "RANGE"}]}])
    cliente.get_waiter("table_exists").wait(TableName=nombre)
    cliente.update_time_to_live(TableName=nombre, TimeToLiveSpecification={"Enabled": True, "AttributeName": "expira"})


def cambiar_epoca(cliente, tabla):
    """Avisa que la tabla cambió por fuera del flujo normal (limpieza de la demo o carga masiva): cada contenedor
    descarta su copia y vuelve a leer todo en su próxima solicitud. Devuelve la época nueva."""
    ts = datos.ahora()
    cliente.update_item(**con_nombres({
        "TableName": tabla, "Key": clave(META, ULTIMO), "UpdateExpression": "SET #epoca = :e, #ts = :ts ADD #n :uno",
        "ExpressionAttributeValues": {":e": {"S": ts}, ":ts": {"S": ts}, ":uno": {"N": "1"}}}))
    return ts


class AlmacenDynamo(datos.Almacen):
    """La copia en memoria de datos.Almacen, respaldada por la tabla de DynamoDB. Una instancia por contenedor."""

    def __init__(self, tabla=None, cliente=None, sesion=None, hilos=16, segmentos=None):
        super().__init__()
        self.tabla = tabla or os.environ["TABLE"]
        self.hilos = hilos                                   # escrituras en paralelo de guardar_lote
        self.segmentos = segmentos or int(os.environ.get("SEGMENTOS_SCAN", "4"))  # lectura inicial en paralelo
        self._cli = cliente or cliente_dynamo(sesion, max(hilos, self.segmentos) + 8)
        self._visto = None       # marcador (época, ts, n) hasta donde está al día la copia
        self._t_sinc = ""        # momento (reloj propio) de la última vez que la copia se puso al día
        self._confirmar = None   # (desde, reloj): relectura de confirmación pendiente
        self._amplia = None      # (desde, reloj) de la próxima relectura amplia
        self.lecturas = collections.Counter()  # cuántas veces se leyó de cada forma (para medir y para los tests)

    def _op(self, nombre, **kw):
        return getattr(self._cli, nombre)(TableName=self.tabla, **con_nombres(kw))

    def _directo(self):
        return not self.cargado

    def _en_paralelo(self, fn, xs):
        xs = list(xs)
        if len(xs) < 2 or self.hilos < 2:
            return [datos._intentar(fn, x) for x in xs]
        with ThreadPoolExecutor(max_workers=min(self.hilos, len(xs))) as ex:
            return list(ex.map(lambda x: datos._intentar(fn, x), xs))

    # ---------- lectura ----------
    def _leer_marcador(self):
        self.lecturas["marcador"] += 1
        m = de_dynamo(self._op("get_item", Key=clave(META, ULTIMO), ConsistentRead=True).get("Item") or {})
        return m.get("epoca") or "", m.get("ts") or "", int(m.get("n") or 0)

    def _paginas(self, operacion, **kw):
        items = []
        while True:
            r = self._op(operacion, **kw)
            items += [de_dynamo(i) for i in r.get("Items", [])]
            if "LastEvaluatedKey" not in r:
                return items
            kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]

    def _scan(self, segmento):
        kw = {"ConsistentRead": True}
        if self.segmentos > 1:
            kw.update(Segment=segmento, TotalSegments=self.segmentos)
        return self._paginas("scan", **kw)

    def _cargar_todo(self):
        """Lee la tabla completa una vez. El marcador se lee ANTES: lo que se escriba mientras dura la lectura queda
        después de ese marcador y lo trae la sincronización que sigue."""
        t0 = datos.ahora()
        marcador = self._leer_marcador()
        with ThreadPoolExecutor(max_workers=self.segmentos) as ex:
            partes = list(ex.map(self._scan, range(self.segmentos)))
        self.lecturas["scan"] += 1
        self._vaciar()
        self._mezclar(it for parte in partes for it in parte)
        self.cargado, self._visto, self._t_sinc, self._confirmar = True, marcador, t0, None
        self._amplia = (_restar(t0, TRASLAPE_S), time.monotonic())
        self._max_ts = max(self._max_ts, marcador[1])  # la carga completa ya incluye todo lo que el marcador anunciaba
        self._al_dia()
        self._sincronizar(recargar=False)

    def _leer_desde(self, desde):
        """Trae por el índice PorDia lo escrito después de `desde` y lo mezcla en la copia."""
        self.lecturas["por_dia"] += 1
        d0 = date.fromisoformat(desde[:10])
        d1 = max(date.fromisoformat(datos.ahora()[:10]), d0)
        items = []
        for k in range((d1 - d0).days + 1):
            items += self._paginas("query", IndexName=INDICE, KeyConditionExpression="#dia = :d AND #ts > :t",
                                   ExpressionAttributeValues={":d": {"S": (d0 + timedelta(days=k)).isoformat()}, ":t": {"S": desde}})
        return self._mezclar(items)

    def _sincronizar(self, recargar=True):
        t, reloj = datos.ahora(), time.monotonic()
        marcador = self._leer_marcador()
        # Época distinta: se borró o se cargó por fuera y la copia ya no vale. Copia abandonada por días: releer todo
        # cuesta menos que consultar día por día.
        if marcador[0] != self._visto[0] or (date.fromisoformat(t[:10]) - date.fromisoformat(self._amplia[0][:10])).days > MAX_DIAS:
            if recargar:
                self._cargar_todo()
            return
        if reloj - self._amplia[1] >= AMPLIA_S:
            # Red de seguridad: una escritura que tardó más que el traslape en anunciarse (reintentos de red) o cuyo
            # anuncio falló no la habría visto este contenedor. Cada 5 min se relee todo lo escrito desde la vez anterior.
            desde, self._amplia = self._amplia[0], (_restar(t, TRASLAPE_S), reloj)
            self._leer_desde(desde)
        if marcador == self._visto:
            # Nada nuevo. Si hace poco hubo cambios, una relectura de confirmación: lo que escribió otro contenedor casi
            # al mismo tiempo pudo no estar aún en el índice cuando se leyó (el índice es de consistencia eventual).
            if self._confirmar and reloj - self._confirmar[1] >= CONFIRMAR_S:
                desde, self._confirmar = self._confirmar[0], None
                self._leer_desde(desde)
            self._t_sinc = t
            return
        # Desde el último ts visto, con traslape. Si el marcador es antiguo (nadie escribía hace rato), no hace falta ir
        # tan atrás: basta un minuto antes de la última sincronización (cubre lo que estaba a medio escribir entonces).
        desde = _restar(max(self._visto[1], _restar(self._t_sinc, MARGEN_S)), TRASLAPE_S)
        for _ in range(REINTENTOS):
            self._leer_desde(desde)
            if self._max_ts >= marcador[1]:  # ya se ve lo último que anunció el marcador
                break
            time.sleep(ESPERA_S)
        self._visto, self._t_sinc, self._confirmar = marcador, t, (desde, reloj)

    def _r_item(self, pk, sk):
        self.lecturas["get"] += 1
        it = self._op("get_item", Key=clave(pk, sk), ConsistentRead=True).get("Item")
        return de_dynamo(it) if it else None

    def _r_particion(self, pk, prefijo=""):
        """Ítems de una partición, sin la copia: una consulta consistente (para procesos que no necesitan la lista)."""
        self.lecturas["particion"] += 1
        kw = {"KeyConditionExpression": "#pk = :pk", "ExpressionAttributeValues": {":pk": {"S": pk}}, "ConsistentRead": True}
        if prefijo:
            kw["KeyConditionExpression"] += " AND begins_with(#sk, :s)"
            kw["ExpressionAttributeValues"][":s"] = {"S": prefijo}
        return self._paginas("query", **kw)

    # ---------- escritura ----------
    def _r_poner(self, it, si_no_existe):
        kw = {"Item": a_dynamo(it)}
        if si_no_existe:  # un ítem con TTL vencido que DynamoDB aún no borra no cuenta como existente
            kw.update(ConditionExpression="attribute_not_exists(#sk) OR (attribute_exists(#expira) AND #expira < :ahora)",
                      ExpressionAttributeValues={":ahora": {"N": str(int(time.time()))}}, ReturnValuesOnConditionCheckFailure="ALL_OLD")
        try:
            self._op("put_item", **kw)
            return True, None
        except ClientError as e:
            if e.response["Error"]["Code"] != YA_EXISTE:
                raise
            existente = e.response.get("Item")
            return False, de_dynamo(existente) if existente else None

    def _condicion_rev(self, kw, rev_vista):
        cond = "#rev = :vista" if rev_vista else "(attribute_not_exists(#rev) OR #rev = :vista)"
        kw["ConditionExpression"] = f'{kw["ConditionExpression"]} AND {cond}' if kw.get("ConditionExpression") else cond
        kw["ExpressionAttributeValues"][":vista"] = {"N": str(rev_vista)}

    def _conflicto(self, pid, rev_vista):
        """Alguien escribió antes: deja la copia al día (la app va a recargar) y avisa con el rev que rige."""
        actual = self._r_item(pid, PERFIL) or {}
        if self.cargado:
            self._mezclar([actual] if actual else [])  # el contador que rige, aunque quien escribió aún no lo anuncie
            try:
                self._sincronizar()
            except Exception as e:
                print(f"almacén: no se pudo sincronizar tras el conflicto: {type(e).__name__}: {e}")
        raise datos.Conflicto(pid, rev_vista, int(actual.get("rev") or 0))

    def _r_perfil(self, it, si_no_existe, rev_vista):
        """El ítem perfil siempre se escribe con UpdateItem: así el contador rev no se pierde aunque cambie el contenido."""
        pk = it["id_paciente"]
        sets = ["#perfil = :p", "#ts = :ts", "#dia = :dia"]
        kw = {"Key": clave(pk, PERFIL), "ReturnValues": "ALL_NEW",
              "ExpressionAttributeValues": {":p": {"S": it["perfil"]}, ":ts": {"S": it["ts"]}, ":dia": {"S": it["dia"]}, ":uno": {"N": "1"}}}
        if it.get("especialidad"):
            sets.append("#esp = :e")
            kw["ExpressionAttributeValues"][":e"] = {"S": it["especialidad"]}
        if it.get("origen"):  # de dónde vino el paciente no cambia aunque después se actualice por otro canal
            sets.append("#origen = if_not_exists(#origen, :o)")
            kw["ExpressionAttributeValues"][":o"] = {"S": it["origen"]}
        if si_no_existe:
            kw.update(ConditionExpression="attribute_not_exists(#perfil)", ReturnValuesOnConditionCheckFailure="ALL_OLD")
        else:
            ant = self._item_de(pk, PERFIL) or {}
            if "perfil" in ant and ant["perfil"] == it["perfil"] and ant.get("especialidad") == it.get("especialidad", ant.get("especialidad")):
                return False, ant  # nada que cambiar
            if ant.get("origen") == REGISTRO_BASE and "perfil" in ant and "perfil_base" not in ant:
                # el original del registro no se pierde: perfiles() y la limpieza de la demo lo usan
                sets.append("#base = if_not_exists(#base, :orig)")
                kw["ExpressionAttributeValues"][":orig"] = {"S": ant["perfil"]}
        if rev_vista is not None:
            self._condicion_rev(kw, rev_vista)
        kw["UpdateExpression"] = "SET " + ", ".join(sets) + " ADD #rev :uno"
        try:
            return True, de_dynamo(self._op("update_item", **kw)["Attributes"])
        except ClientError as e:
            if e.response["Error"]["Code"] != YA_EXISTE:
                raise
            existente = e.response.get("Item")
        if si_no_existe:
            actual = de_dynamo(existente) if existente else (self._r_item(pk, PERFIL) or {})
            if "perfil" in actual:
                return False, actual
        self._conflicto(pk, rev_vista)

    def _r_subir_rev(self, pid, ts, rev_vista=None):
        """Sube el contador del paciente y deja su ítem perfil con el ts de esta escritura (así los otros contenedores
        reciben el rev nuevo por el índice PorDia, junto con lo que se escribió)."""
        kw = {"Key": clave(pid, PERFIL), "UpdateExpression": "SET #ts = :ts, #dia = :dia ADD #rev :uno", "ReturnValues": "ALL_NEW",
              "ExpressionAttributeValues": {":ts": {"S": ts}, ":dia": {"S": ts[:10]}, ":uno": {"N": "1"}}}
        if rev_vista is not None:
            self._condicion_rev(kw, rev_vista)
        try:
            return de_dynamo(self._op("update_item", **kw)["Attributes"])
        except ClientError as e:
            if e.response["Error"]["Code"] != YA_EXISTE:
                raise
        self._conflicto(pid, rev_vista)

    def _r_marcar(self, ts):
        """Marcador de frescura: ts = lo más reciente que se escribió (nunca retrocede) y n = cuántas escrituras van
        (siempre cambia, aunque dos escrituras tengan el mismo ts)."""
        marcador, uno = clave(META, ULTIMO), {":uno": {"N": "1"}}
        try:
            try:
                r = self._op("update_item", Key=marcador, UpdateExpression="SET #ts = :ts ADD #n :uno", ReturnValues="ALL_OLD",
                             ConditionExpression="attribute_not_exists(#ts) OR #ts < :ts", ExpressionAttributeValues={":ts": {"S": ts}, **uno})
            except ClientError as e:
                if e.response["Error"]["Code"] != YA_EXISTE:
                    raise
                r = self._op("update_item", Key=marcador, UpdateExpression="ADD #n :uno", ReturnValues="ALL_OLD", ExpressionAttributeValues=uno)
        except Exception as e:
            # Lo escrito ya quedó guardado: fallar aquí haría que el usuario lo repita. Los otros contenedores lo verán
            # con la próxima escritura o, a más tardar, con su relectura amplia.
            print(f"almacén: no se pudo actualizar el marcador: {type(e).__name__}: {e}")
            return
        viejo = de_dynamo(r.get("Attributes") or {})
        antes = (viejo.get("epoca") or "", viejo.get("ts") or "", int(viejo.get("n") or 0))
        if self._visto is not None and antes == self._visto:
            # nadie más escribió desde la última sincronización: la copia sigue al día y no hace falta releer
            self._visto = (antes[0], max(antes[1], ts), antes[2] + 1)

    def cambiar_epoca(self):
        return cambiar_epoca(self._cli, self.tabla)
