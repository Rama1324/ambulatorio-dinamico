"""Datos: fecha de trabajo y almacén (docs/diseno/ESPECIFICACION_MVP.md §3).

El almacén es la única fuente de verdad y guarda ítems normalizados por paciente (pk = id_paciente, sk):
  perfil                                    perfil = {"paciente": {...}, "lista_espera": {...}} + especialidad + rev
  evento#<fecha_evento>#<id_evento>         evento
  medicion#<fecha_medicion>#<tipo>#<hash8>  medicion
  cita#<fecha_cita>#<id_cita o hash8>       cita
  revision# · contacto# · decision# · gestion# · orden# · novedad# · evaluacion# · dictamen# · enmienda# + marca de tiempo
Particiones reservadas (su pk empieza con "_"): _kb, _ingesta, _idem y _meta (marcador de frescura).
Todo ítem lleva ts (momento UTC en que se escribió) y dia; los de la carga inicial, origen = "registro_base". Un ítem
puede llevar expira (segundos epoch, TTL): pasado ese momento ya no cuenta como existente.
Solo se agrega: nada se pisa ni se borra, salvo el ítem perfil (lleva el contador rev y conserva el original del
registro en perfil_base).

Cada proceso trabaja con una copia en memoria (ítems + perfiles armados) con índices por paciente y por tipo de sk:
  LOCAL=1 → AlmacenMemoria: se inicializa convirtiendo DATA_DIR/perfiles.json a esos mismos ítems (un solo camino de código).
  AWS     → almacen_dynamo.AlmacenDynamo: carga la tabla una vez y después lee solo lo nuevo (marcador + índice PorDia).
"""
import json
import os
import threading
import time
import zlib
from datetime import date, datetime, timedelta, timezone

LOCAL = os.environ.get("LOCAL") == "1"
# Fecha de trabajo. FECHA_REFERENCIA=hoy → fecha real de Chile (versión publicada); AAAA-MM-DD → simulación
# (el dataset sintético llega al 2026-10-13).
_FR = os.environ.get("FECHA_REFERENCIA", "2026-10-13")
TIEMPO_REAL = _FR == "hoy"
# Fecha en que se extrajo el registro del hospital que se cargó (el dataset sintético es al 2026-10-13)
REGISTRO_AL = os.environ.get("REGISTRO_AL", "2026-10-13")

REGISTRO_BASE = "registro_base"  # origen de los ítems de la carga inicial: la "foto" del hospital
PERFIL = "perfil"
META, ULTIMO = "_meta", "ultimo"  # marcador de frescura (lo usa el almacén de DynamoDB)
ARMAN = ("evento", "medicion", "cita", "enmienda")  # tipos de ítem que, junto al perfil, forman el perfil armado


def hoy():
    if not TIEMPO_REAL:
        return date.fromisoformat(_FR)
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Santiago")).date()
    except Exception:  # sin base de zonas horarias: Chile continental en horario de verano (UTC-3)
        return (datetime.now(timezone.utc) - timedelta(hours=3)).date()


def ahora():
    """Marca de tiempo UTC con microsegundos: ordena los registros y dice qué se registró después de qué."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


class EntradaInvalida(ValueError):
    """Dato mal formado en la solicitud: el handler responde 400, no 500."""


class Conflicto(Exception):
    """El paciente recibió algo después de lo que el usuario tenía a la vista (rev distinto): el handler responde 409
    y la app recarga."""

    def __init__(self, id_paciente, rev_vista, rev_actual=None):
        self.id_paciente, self.rev_vista, self.rev_actual = id_paciente, rev_vista, rev_actual
        super().__init__(f"El paciente {id_paciente} recibió información nueva mientras lo tenía abierto "
                         f"(tenía la versión {rev_vista}; va en la {rev_actual}). Recargue y vuelva a intentar.")


def fecha_de(qs):
    """Fecha de corte de la consulta o del cuerpo de la solicitud; si no viene, hoy."""
    f = (qs or {}).get("fecha_corte")
    try:
        return date.fromisoformat(f) if f else hoy()
    except (TypeError, ValueError):
        raise EntradaInvalida(f"fecha_corte inválida: {f!r} (formato AAAA-MM-DD)")


def fecha_valida(valor, corte, campo="fecha"):
    """Fecha ISO real, no posterior a la fecha de corte ni anterior al año 2000. Devuelve (fecha_iso, error)."""
    try:
        f = date.fromisoformat(str(valor))
    except (TypeError, ValueError):
        return None, f"{campo} inválida: '{valor}' (formato AAAA-MM-DD)"
    if f > corte:
        return None, f"{campo} {f} es posterior a la fecha de hoy ({corte})"
    if f.year < 2000:
        return None, f"{campo} {f} no es plausible"
    return f.isoformat(), None


def posterior(s, desde_corte, desde_ts):
    """¿La señal ocurrió o se registró después de la revisión? (fecha clínica > corte revisado, o registro posterior)."""
    return s["fecha"] > desde_corte or bool(s.get("registrado") and s["registrado"] > desde_ts)


# ---------- ítems normalizados ----------
_json = json.JSONEncoder(ensure_ascii=False, default=str).encode  # un solo codificador: la carga inicial escribe miles de ítems


def _hash8(*partes):
    """8 caracteres estables para distinguir registros del mismo paciente y fecha (CRC-32: rápido y sin dependencias)."""
    return f'{zlib.crc32("|".join(map(str, partes)).encode("utf-8")):08x}'


def _valor(v):
    """Valor de una medición en forma canónica: 112 y 112.0 son la misma medición."""
    try:
        return repr(float(v))
    except (TypeError, ValueError):
        return str(v)


def _item(pid, sk, campo, contenido, origen):
    pid = str(pid or "").strip()
    if not pid or pid.startswith("_"):  # las particiones que empiezan con "_" son del sistema (_kb, _ingesta, _idem, _meta)
        raise EntradaInvalida(f"id de paciente no válido: {pid!r}")
    it = {"id_paciente": pid, "sk": sk, campo: _json(contenido)}
    if origen:
        it["origen"] = origen
    return it


def item_perfil(pid, perfil, origen=None):
    """Ítem "perfil": solo los datos del paciente y de su interconsulta (eventos, mediciones y citas van aparte)."""
    le = perfil.get("lista_espera") or {}
    it = _item(pid, PERFIL, "perfil", {"paciente": perfil.get("paciente") or {}, "lista_espera": le}, origen)
    if le.get("especialidad"):
        it["especialidad"] = le["especialidad"]
    return it


def item_evento(pid, ev, origen=None):
    if not ev.get("fecha_evento"):
        raise EntradaInvalida("evento sin fecha_evento")
    if not ev.get("id_evento"):  # sin id del sistema de origen: uno determinista por contenido (reenviarlo no lo duplica)
        ev = {**ev, "id_evento": "EV-" + _hash8(pid, ev["fecha_evento"], ev.get("tipo_evento"), ev.get("subtipo"), ev.get("motivo") or "").upper()}
    return _item(pid, f'evento#{ev["fecha_evento"]}#{ev["id_evento"]}', "evento", ev, origen)


def item_medicion(pid, m, origen=None):
    f, t = m.get("fecha_medicion"), m.get("tipo_medicion")
    if not f or not t:
        raise EntradaInvalida("medición sin fecha_medicion o tipo_medicion")
    return _item(pid, f"medicion#{f}#{t}#{_hash8(f, t, _valor(m.get('valor')))}", "medicion", m, origen)


def item_cita(pid, c, origen=None):
    f = c.get("fecha_cita")
    if not f:
        raise EntradaInvalida("cita sin fecha_cita")
    return _item(pid, f'cita#{f}#{c.get("id_cita") or _hash8(f, c.get("id_box") or "", c.get("estado_cita") or "")}', "cita", c, origen)


def items_de_perfil(perfil, origen=None):
    """Convierte un perfil completo (formato perfiles.json) en ítems. Sirve también con un perfil parcial: sin "paciente"
    ni "lista_espera" no sale el ítem "perfil" (solo los eventos, mediciones y citas que traiga)."""
    pid = perfil["id_paciente"]
    items = [item_perfil(pid, perfil, origen)] if perfil.get("paciente") is not None and perfil.get("lista_espera") is not None else []
    items += [item_evento(pid, e, origen) for e in perfil.get("eventos_clinicos") or []]
    items += [item_medicion(pid, m, origen) for m in perfil.get("mediciones") or []]
    items += [item_cita(pid, c, origen) for c in perfil.get("citaciones") or []]
    return items


def cambios_perfil(antes, despues):
    """Solo los campos de "paciente" y "lista_espera" que cambian entre dos perfiles: (antes, después). Es lo que guarda
    cada novedad# para que la modificación del ítem perfil (el único que se pisa) quede trazable."""
    a, d = {}, {}
    for parte in ("paciente", "lista_espera"):
        x, y = antes.get(parte) or {}, despues.get(parte) or {}
        for k in list(x) + [k for k in y if k not in x]:
            if x.get(k) != y.get(k):
                a.setdefault(parte, {})[k] = x.get(k)
                d.setdefault(parte, {})[k] = y.get(k)
    return a, d


def _leer_uno_a_uno(textos, pid):
    out = []
    for t in textos:
        try:
            out.append(json.loads(t))
        except ValueError:
            print(f"almacén: {pid}: se omite un registro con JSON inválido")
    return out


def _armar(pid, particion, solo_base=False):
    """(perfil armado | None, puro) desde los ítems de un paciente ({sk: ítem}).
    Perfil armado = ítem perfil + sus eventos (sin los anulados; con `relacionado` corregido por la última enmienda)
    + mediciones + citas, cada lista ordenada por fecha. Los eventos anulados quedan en "eventos_anulados".
    `solo_base`: solo lo que vino en la carga inicial, tal como se cargó (sin lo que se agregó o modificó después).
    `puro`: todo lo que lo forma es del registro base y nadie lo ha modificado."""
    perfil, puro, partes = None, True, {t: [] for t in ARMAN}
    for sk in sorted(particion):  # por sk: dentro de cada tipo quedan por fecha y, a igual fecha, por id (orden estable)
        it = particion[sk]
        tipo = sk.split("#", 1)[0]
        base = it.get("origen") == REGISTRO_BASE
        if sk == PERFIL:
            if "perfil" in it and (base or not solo_base):
                perfil = (it.get("perfil_base") or it["perfil"]) if solo_base else it["perfil"]
                puro = puro and base and "perfil_base" not in it
        elif tipo in partes and tipo in it and (base or not solo_base):
            partes[tipo].append(it[tipo])
            puro = puro and base
    if perfil is None:  # hay registros pero no datos del paciente: todavía no existe para la lista
        return None, False
    try:  # una sola lectura de JSON por paciente (más rápido y comparte los nombres de campo en memoria)
        d = json.loads('{"perfil":%s,"evento":[%s],"medicion":[%s],"cita":[%s],"enmienda":[%s]}'
                       % (perfil, *(",".join(partes[t]) for t in ARMAN)))
    except ValueError:  # un registro mal guardado no puede dejar al paciente fuera: se lee uno a uno y se omite el malo
        d = {t: _leer_uno_a_uno(partes[t], pid) for t in ARMAN}
        d["perfil"] = (_leer_uno_a_uno([perfil], pid) or [None])[0]
    c = d["perfil"]
    if not isinstance(c, dict) or not isinstance(c.get("paciente"), dict) or not isinstance(c.get("lista_espera"), dict):
        return None, False
    eventos, mediciones, citas, enmiendas = ([x for x in d[t] if isinstance(x, dict)] for t in ARMAN)
    # a igual fecha, primero lo del registro y después lo que fue llegando (por su momento de registro)
    eventos.sort(key=lambda e: (str(e.get("fecha_evento") or ""), str(e.get("registrado") or "")))
    anular, relacion = {}, {}
    for x in enmiendas:  # en el orden en que se registraron: para `relacionado` rige la última de cada evento
        if x.get("accion") == "anular":
            anular[x.get("id_evento")] = x
        elif x.get("accion") in ("no_relacionado", "relacionado"):
            relacion[x.get("id_evento")] = x["accion"] == "relacionado"
    vigentes, anulados = [], []
    for e in eventos:
        ide = e.get("id_evento")
        if ide in relacion:
            e["relacionado"] = relacion[ide]
        if ide in anular:
            anulados.append({**e, "anulado": {k: anular[ide].get(k) for k in ("motivo", "usuario", "fecha")}})
        else:
            vigentes.append(e)
    return {"id_paciente": pid, "paciente": c["paciente"], "lista_espera": c["lista_espera"], "eventos_clinicos": vigentes,
            "mediciones": sorted(mediciones, key=lambda m: str(m.get("fecha_medicion") or "")),
            "citaciones": sorted(citas, key=lambda x: str(x.get("fecha_cita") or "")),
            "eventos_anulados": anulados}, puro


def armar(pid, items, solo_base=False):
    """Perfil armado de un paciente a partir de sus ítems (None si no tiene ítem perfil)."""
    return _armar(pid, {i["sk"]: i for i in items}, solo_base)[0]


def _entero(v, campo="rev_vista"):
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        raise EntradaInvalida(f"{campo} inválido: {v!r} (debe ser un número)")


def _vencido(it):
    """Ítem con fecha de expiración (TTL) ya cumplida: DynamoDB puede tardar en borrarlo, pero ya no cuenta."""
    try:
        return it.get("expira") is not None and float(it["expira"]) < time.time()
    except (TypeError, ValueError):
        return False


def _intentar(fn, x):
    try:
        return fn(x)
    except Exception as e:  # se devuelve para no perder lo que sí se escribió; quien llama la vuelve a lanzar
        return e


def _original(it):
    """Contenido del ítem perfil tal como vino en el registro base (False si el paciente no es del registro)."""
    return it.get("origen") == REGISTRO_BASE and (it.get("perfil_base") or it.get("perfil"))


# ---------- almacén: copia en memoria + índices + perfiles armados (igual para memoria y DynamoDB) ----------
class Almacen:
    """Copia en memoria de los ítems, con índices por paciente y por tipo de sk, y los perfiles armados.
    Las subclases dicen de dónde se carga y dónde se escribe (métodos _r_*): memoria o DynamoDB.
    Un candado protege la copia: evaluacion_ia.barrido escribe desde varios hilos."""

    def __init__(self):
        self._candado = threading.RLock()
        self._ultimo_ts = ""
        self._vaciar()

    def _vaciar(self):
        self.cargado = False
        self._por_pk = {}        # pk → {sk: ítem}
        self._por_tipo = {}      # tipo de sk (lo que va antes del primer "#") → {(pk, sk): ítem}
        self._no_base = {}       # (pk, sk) → ítem: lo que registra el equipo y lo que llega después de la carga inicial
        self._perfs = {}         # pid → perfil armado, al día
        self._sucios = set()     # pacientes que recibieron algo: su perfil se vuelve a armar al pedirlo
        self._base = {}          # pid → perfil armado solo con el registro base (si nadie lo tocó, el mismo objeto de _perfs)
        self._base_dict = None   # lo que devuelve perfiles()
        self._datos_hasta = None
        self._vistas = {}        # (tipo, nombre) → vista derivada; se bota cuando llega un ítem de ese tipo
        self._contenidos = {}    # (pk, sk) → contenido ya leído del JSON (cada ítem se lee una sola vez)
        self._max_ts = ""        # mayor ts que ha visto la copia

    # --- lo que cambia según dónde se guarda (lo redefinen las subclases) ---
    def _directo(self):
        """¿Hay que leer directo del respaldo, sin la copia? Solo DynamoDB antes de cargar: así un proceso que trabaja
        con un solo paciente (trabajador de la cola) no lee toda la tabla."""
        return False

    def _cargar_todo(self):
        raise NotImplementedError

    def _sincronizar(self):
        """Trae a la copia lo que otros procesos escribieron (en memoria no hay otros)."""

    def _r_marcar(self, ts):
        """Avisa a los otros procesos que hay algo nuevo (en memoria no hay a quién)."""

    def _en_paralelo(self, fn, xs):
        return [_intentar(fn, x) for x in xs]

    # --- copia ---
    def _asegurar(self):
        if not self.cargado:
            self._cargar_todo()

    def _ts(self):
        """Momento de escritura, siempre creciente dentro del proceso (ordena lo escrito en la misma solicitud)."""
        t = ahora()
        if t <= self._ultimo_ts:
            t = (datetime.fromisoformat(self._ultimo_ts) + timedelta(microseconds=1)).isoformat(timespec="microseconds")
        self._ultimo_ts = t
        return t

    @staticmethod
    def _validar(item):
        if not isinstance(item, dict) or not all(isinstance(item.get(k), str) and item[k] for k in ("id_paciente", "sk")):
            raise ValueError("todo ítem lleva id_paciente y sk (textos no vacíos)")
        if item["sk"] == "paciente#":
            raise ValueError('sk "paciente#" ya no existe: use guardar_perfil y guarde eventos, mediciones y citas por separado')
        if item["sk"] == PERFIL and not item["id_paciente"].startswith("_") and not isinstance(item.get("perfil"), str):
            raise ValueError('el ítem "perfil" lleva el atributo perfil (JSON en texto): use guardar_perfil o item_perfil')
        return item

    def _sellar(self, item, ts=None):
        """Copia del ítem con el momento en que se escribe (ts y dia son del almacén, no de quien llama)."""
        ts = ts or self._ts()
        return {**{k: v for k, v in self._validar(item).items() if v is not None}, "ts": ts, "dia": ts[:10]}

    def _olvidar_base(self, pk):
        self._base.pop(pk, None)
        self._base_dict = self._datos_hasta = None

    def _mezclar(self, items):
        """Deja los ítems en la copia (idempotente por (pk, sk)). Devuelve cuántos eran nuevos o distintos."""
        cambios = 0
        for it in items:
            pk, sk = it["id_paciente"], it["sk"]
            if pk == META:
                continue
            parte = self._por_pk.setdefault(pk, {})
            ant = parte.get(sk)
            if ant == it:
                continue
            cambios += 1
            tipo = sk.split("#", 1)[0]
            base, reservada = it.get("origen") == REGISTRO_BASE, pk.startswith("_")
            parte[sk] = it
            self._por_tipo.setdefault(tipo, {})[(pk, sk)] = it
            if not base and not reservada:
                self._no_base[(pk, sk)] = it
            else:
                self._no_base.pop((pk, sk), None)
            if self._contenidos:
                self._contenidos.pop((pk, sk), None)
            if self._vistas:  # lo derivado de ese tipo de registro se vuelve a calcular cuando se pida
                for k in [k for k in self._vistas if k[0] == tipo]:
                    del self._vistas[k]
            if it.get("ts", "") > self._max_ts:
                self._max_ts = it["ts"]
            if reservada:
                continue
            if tipo == PERFIL:  # subir el contador rev no cambia el perfil armado: solo se rearma si cambió el contenido
                if (ant or {}).get("perfil") != it.get("perfil"):
                    self._sucios.add(pk)
                if _original(ant or {}) != _original(it):
                    self._olvidar_base(pk)
            elif tipo in ARMAN:
                self._sucios.add(pk)
                if base:
                    self._olvidar_base(pk)
        return cambios

    def _anotar(self, items):
        """Lo recién escrito se ve de inmediato en este proceso (si aún no cargó la copia, lo verá al cargar)."""
        if self.cargado:
            self._mezclar([i for i in items if i])

    def _al_dia(self):
        """Vuelve a armar solo a los pacientes que recibieron algo."""
        for pid in sorted(self._sucios):
            try:
                p, puro = _armar(pid, self._por_pk.get(pid, {}))
            except Exception as e:  # un paciente con datos malos no puede botar la lista de todos
                print(f"almacén: no se pudo armar {pid}: {type(e).__name__}: {e}")
                p, puro = None, False
            if p is None:
                self._perfs.pop(pid, None)
                continue
            self._perfs[pid] = p
            if puro:
                self._base[pid] = p
        self._sucios.clear()

    def _item_de(self, pk, sk):
        if self._directo():
            return self._r_item(pk, sk)
        self._asegurar()
        return self._por_pk.get(pk, {}).get(sk)

    def _particion(self, pk, prefijo=""):
        if self._directo():
            return self._r_particion(pk, prefijo)
        self._asegurar()
        return sorted((i for sk, i in self._por_pk.get(pk, {}).items() if sk.startswith(prefijo)), key=lambda i: i["sk"])

    def _ordenados(self, prefijo):
        """Ítems cuyo sk empieza con prefijo, ordenados por sk (se guarda hasta que llegue algo de ese tipo)."""
        self._asegurar()
        por_sk = lambda i: (i["sk"], i["id_paciente"])
        tipo = prefijo.split("#", 1)[0]
        if "#" not in prefijo:  # prefijo de varios tipos posibles ("ev" → evento y evaluacion): no vale la pena guardarlo
            return sorted((i for t, g in self._por_tipo.items() if t.startswith(prefijo) for i in g.values()
                           if i["sk"].startswith(prefijo)), key=por_sk)
        clave = (tipo, "sk:" + prefijo)
        if clave not in self._vistas:
            self._vistas[clave] = sorted((i for i in self._por_tipo.get(tipo, {}).values() if i["sk"].startswith(prefijo)), key=por_sk)
        return self._vistas[clave]

    def _contenido(self, it, campo):
        k = (it["id_paciente"], it["sk"])
        if k not in self._contenidos:
            try:
                self._contenidos[k] = json.loads(it[campo])
            except (KeyError, TypeError, ValueError):  # un registro mal guardado se omite: no puede botar la lista
                print(f"almacén: {k[0]} {k[1]}: sin contenido '{campo}' legible")
                self._contenidos[k] = None
        return self._contenidos[k]

    def _vista(self, prefijo, nombre, armar_vista):
        self._asegurar()
        clave = (prefijo.split("#", 1)[0], nombre)
        if clave not in self._vistas:
            self._vistas[clave] = armar_vista()
        return self._vistas[clave]

    def _ultimos(self, prefijo, campo):
        """Último registro de ese tipo por paciente (copias: quien lo recibe puede modificarlas sin tocar la copia)."""
        def armar_vista():
            out = {}
            for it in self._ordenados(prefijo):
                c = self._contenido(it, campo)
                if c is not None:
                    out[it["id_paciente"]] = c
            return out
        return {pid: dict(c) for pid, c in self._vista(prefijo, f"ultimos:{prefijo}:{campo}", armar_vista).items()}

    # --- lectura ---
    def nueva_solicitud(self):
        """Punto donde se refresca la copia: una vez por solicitud. Dentro de la solicitud, lo escrito se ve de inmediato."""
        with self._candado:
            if self.cargado:
                self._sincronizar()

    def perfiles(self):
        """Perfiles del registro base tal como se cargaron (sin lo que se registró o modificó después)."""
        with self._candado:
            self._asegurar()
            if self._base_dict is None:
                self._al_dia()
                out = {}
                for pid in sorted(self._por_pk):
                    it = self._por_pk[pid].get(PERFIL)
                    if not it or it.get("origen") != REGISTRO_BASE or "perfil" not in it:
                        continue
                    if pid not in self._base:
                        self._base[pid] = _armar(pid, self._por_pk[pid], solo_base=True)[0]
                    if self._base[pid] is not None:
                        out[pid] = self._base[pid]
                self._base_dict = out
            return self._base_dict

    def perfiles_combinados(self):
        """(perfiles armados al día por paciente, última revisión por paciente)."""
        with self._candado:
            self._asegurar()
            self._al_dia()
            return dict(self._perfs), self._ultimos("revision#", "revision")

    def perfil_de(self, pid):
        """Perfil armado de un paciente. Antes de cargar la copia (DynamoDB) sale de una consulta a su partición."""
        with self._candado:
            if self._directo():
                return armar(pid, self._r_particion(pid, ""))
            self._asegurar()
            self._al_dia()
            return self._perfs.get(pid)

    def datos_hasta(self):
        """Fecha del último dato del registro cargado (eventos, mediciones o citas): hasta dónde llega la información."""
        with self._candado:
            if self._datos_hasta is None:
                fechas = [x.get(k) for p in self.perfiles().values() for lista_, k in (("eventos_clinicos", "fecha_evento"),
                          ("mediciones", "fecha_medicion"), ("citaciones", "fecha_cita")) for x in p.get(lista_, [])]
                fechas = [f for f in fechas if f]
                if not fechas:
                    return hoy().isoformat()
                self._datos_hasta = max(fechas)
            return self._datos_hasta

    def registros(self):
        with self._candado:
            self._asegurar()
            return [dict(i) for i in self._no_base.values()]

    def registros_de(self, pid):
        with self._candado:
            return [dict(i) for i in self._particion(pid)]

    def registros_tipo(self, prefijo, pid=None):
        with self._candado:
            return [dict(i) for i in (self._particion(pid, prefijo) if pid is not None else self._ordenados(prefijo))]

    def globales(self, pk, prefijo=""):
        with self._candado:
            return [dict(i) for i in self._particion(pk, prefijo)]

    def rev(self, pid):
        with self._candado:
            return int((self._item_de(pid, PERFIL) or {}).get("rev") or 0)

    def contactos(self):
        def armar_vista():
            out, intentos = {}, {}
            for it in self._ordenados("contacto#"):
                c = self._contenido(it, "contacto")
                if c is None:
                    continue
                pid = it["id_paciente"]
                intentos[pid] = intentos.get(pid, 0) + 1 if c.get("resultado") == "no_contesta" else 0
                out[pid] = {**c, "intentos_sin_respuesta": intentos[pid]}
            return out
        with self._candado:
            return {pid: dict(c) for pid, c in self._vista("contacto#", "contactos", armar_vista).items()}

    def ultimos(self, prefijo, campo):
        with self._candado:
            return self._ultimos(prefijo, campo)

    def evaluaciones_por_paciente(self):
        def armar_vista():
            out = {}
            for it in reversed(self._ordenados("evaluacion#")):
                c = self._contenido(it, "evaluacion")
                if c is not None:
                    out.setdefault(it["id_paciente"], []).append(c)
            return out
        with self._candado:  # las evaluaciones son grandes: se entregan las ya leídas (son de solo lectura)
            return {pid: list(evs) for pid, evs in self._vista("evaluacion#", "por_paciente", armar_vista).items()}

    # --- escritura ---
    def guardar(self, item, *, si_no_existe=False, rev_vista=None):
        with self._candado:
            if not self._directo():
                self._asegurar()
            rev_vista = _entero(rev_vista)
            it = self._sellar(item)
            pk, ts = it["id_paciente"], it["ts"]
            if pk.startswith("_"):  # particiones del sistema: no son de un paciente, no hay contador que subir
                creado, existente = self._r_poner(it, si_no_existe)
                self._anotar([it if creado else existente])
                if creado:
                    self._r_marcar(ts)
                return creado
            if it["sk"] == PERFIL:
                creado, como_quedo = self._r_perfil(it, si_no_existe, rev_vista)
                self._anotar([como_quedo])
                if creado:
                    self._r_marcar(ts)
                return creado
            if rev_vista is not None or not si_no_existe:
                # Primero el contador (con rev_vista, condicional y atómico: si alguien escribió antes, Conflicto). Si
                # algo falla después, no quedó nada escrito a medias y repetir la acción no duplica el registro.
                self._anotar([self._r_subir_rev(pk, ts, rev_vista)])
                creado, existente = self._r_poner(it, si_no_existe)
                self._anotar([it if creado else existente])
                self._r_marcar(ts)
                return creado
            # Escritura idempotente (evento, medición, cita): primero el ítem, y el contador solo si era nuevo, para que
            # reenviar algo que ya estaba no mueva el contador de nadie.
            creado, existente = self._r_poner(it, True)
            self._anotar([it if creado else existente])
            if creado:
                try:
                    self._anotar([self._r_subir_rev(pk, ts)])
                finally:
                    self._r_marcar(ts)  # lo escrito se anuncia aunque el contador falle
            return creado

    TANDA = 400  # un lote grande se escribe por tandas: cada una se anuncia a los otros procesos apenas termina

    def guardar_lote(self, items):
        """Escribe varios ítems, cada uno solo si no existe (reenviar el mismo lote no duplica). Devuelve cuántos eran
        nuevos. El contador rev de cada paciente sube una vez por lote, no una por ítem."""
        with self._candado:
            if not self._directo():
                self._asegurar()
            por_paciente = {}
            for item in items:  # se valida todo antes de escribir nada; repetidos dentro del lote: vale el primero
                self._validar(item)
                por_paciente.setdefault(item["id_paciente"], {}).setdefault(item["sk"], item)
            n, tanda = 0, []
            for grupo in por_paciente.values():  # los ítems de un paciente van juntos en la misma tanda
                tanda += grupo.values()
                if len(tanda) >= self.TANDA:
                    n, tanda = n + self._guardar_tanda(tanda), []
            return n + self._guardar_tanda(tanda) if tanda else n

    def _guardar_tanda(self, items):
        ts = self._ts()
        items = [self._sellar(i, ts) for i in items]
        es_perfil = lambda it: it["sk"] == PERFIL and not it["id_paciente"].startswith("_")
        perfiles, otros = [it for it in items if es_perfil(it)], [it for it in items if not es_perfil(it)]
        r_perfiles = self._en_paralelo(lambda it: self._r_perfil(it, True, None), perfiles)
        r_otros = self._en_paralelo(lambda it: self._r_poner(it, True)[0], otros)
        escritos = [it for it, ok in zip(otros, r_otros) if ok is True]
        con_perfil = [r[1] for r in r_perfiles if not isinstance(r, Exception) and r[0]]
        subir = sorted({it["id_paciente"] for it in escritos if not it["id_paciente"].startswith("_")}
                       - {it["id_paciente"] for it in con_perfil})
        r_rev = self._en_paralelo(lambda pid: self._r_subir_rev(pid, ts), subir)
        self._anotar(con_perfil + escritos + [r for r in r_rev if not isinstance(r, Exception)])
        if con_perfil or escritos:
            self._r_marcar(ts)
        errores = [r for r in r_perfiles + r_otros + r_rev if isinstance(r, Exception)]
        if errores:  # lo que alcanzó a escribirse queda; como cada ítem es idempotente, se puede reenviar el lote
            raise errores[0]
        return len(con_perfil) + len(escritos)

    def guardar_perfil(self, pid, perfil, *, origen=None, rev_vista=None):
        return self.guardar(item_perfil(pid, perfil, origen), rev_vista=rev_vista)


class AlmacenMemoria(Almacen):
    """Todo vive en el proceso (LOCAL=1 y tests): la copia es el almacén. Se inicializa con el registro base
    (DATA_DIR/perfiles.json, o los perfiles que se le pasen) convertido a ítems."""

    def __init__(self, perfiles=None):
        super().__init__()
        self._iniciales = perfiles

    def _cargar_todo(self):
        perfs = self._iniciales
        if perfs is None:
            with open(os.path.join(os.environ.get("DATA_DIR", "data"), "perfiles.json"), encoding="utf-8") as f:
                perfs = json.load(f)
        ts = self._ts()
        items = []
        for p in perfs:
            for it in items_de_perfil(p, origen=REGISTRO_BASE):
                it["ts"], it["dia"] = ts, ts[:10]
                if it["sk"] == PERFIL:
                    it["rev"] = 1
                items.append(it)
        self._mezclar(items)
        self.cargado = True
        self._al_dia()

    def _r_poner(self, it, si_no_existe):
        ant = self._por_pk.get(it["id_paciente"], {}).get(it["sk"])
        if si_no_existe and ant is not None and not _vencido(ant):
            return False, ant
        return True, None

    def _r_perfil(self, it, si_no_existe, rev_vista):
        pk = it["id_paciente"]
        ant = self._por_pk.get(pk, {}).get(PERFIL) or {}
        if "perfil" in ant and (si_no_existe or (ant["perfil"] == it["perfil"] and ant.get("especialidad") == it.get("especialidad", ant.get("especialidad")))):
            return False, ant  # ya existe, o no hay nada que cambiar
        rev = int(ant.get("rev") or 0)
        if rev_vista is not None and rev != rev_vista:
            raise Conflicto(pk, rev_vista, rev)
        nuevo = {**ant, "id_paciente": pk, "sk": PERFIL, "perfil": it["perfil"], "rev": rev + 1, "ts": it["ts"], "dia": it["dia"]}
        if it.get("especialidad"):
            nuevo["especialidad"] = it["especialidad"]
        if it.get("origen") and not ant.get("origen"):
            nuevo["origen"] = it["origen"]
        if ant.get("origen") == REGISTRO_BASE and "perfil" in ant and "perfil_base" not in ant:
            nuevo["perfil_base"] = ant["perfil"]  # el original del registro no se pierde: perfiles() y la limpieza lo usan
        return True, nuevo

    def _r_subir_rev(self, pid, ts, rev_vista=None):
        ant = self._por_pk.get(pid, {}).get(PERFIL) or {"id_paciente": pid, "sk": PERFIL}
        rev = int(ant.get("rev") or 0)
        if rev_vista is not None and rev != rev_vista:
            raise Conflicto(pid, rev_vista, rev)
        return {**ant, "rev": rev + 1, "ts": ts, "dia": ts[:10]}


# ---------- API pública (el almacén del proceso) ----------
_alm = None
_candado_alm = threading.Lock()


def almacen():
    """El almacén del proceso: en memoria si LOCAL=1; DynamoDB (tabla TABLE) si no."""
    global _alm
    if _alm is None:
        with _candado_alm:
            if _alm is None:
                if LOCAL:
                    _alm = AlmacenMemoria()
                else:
                    from almacen_dynamo import AlmacenDynamo
                    _alm = AlmacenDynamo()
    return _alm


def restablecer():
    """Solo en modo memoria (LOCAL=1; lo usan los tests): deja el almacén como recién cargado desde perfiles.json
    (se descarta todo lo que no sea del registro base y se reinician contadores rev, índices y cachés)."""
    global _alm
    if not LOCAL:
        raise RuntimeError("restablecer() solo existe en modo memoria (LOCAL=1). En DynamoDB la aplicación no borra: "
                           "para volver al estado inicial use scripts/limpiar_demo.py")
    with _candado_alm:
        _alm = None  # el próximo acceso lo vuelve a cargar desde DATA_DIR/perfiles.json


def nueva_solicitud():
    """Cada solicitud refresca la copia una vez: lee el marcador y, solo si cambió, lo nuevo."""
    if _alm is None:  # un proceso que aún no ha leído nada no tiene qué refrescar
        return
    try:
        _alm.nueva_solicitud()
    except Exception as e:
        # Si el refresco falla (red, límite de DynamoDB), la solicitud sigue con la copia que hay: es mejor una lista
        # con segundos de atraso que ninguna. La próxima solicitud lo intenta de nuevo.
        print(f"almacén: no se pudo refrescar la copia: {type(e).__name__}: {e}")


def perfiles():
    """Perfiles del registro base tal como se cargaron (la "foto" del hospital), por id de paciente."""
    return almacen().perfiles()


def perfiles_combinados():
    """Todo al día: (perfil armado por paciente, última revisión por paciente)."""
    return almacen().perfiles_combinados()


def perfil_de(pid):
    """Perfil armado de un paciente (None si no existe). No obliga a cargar toda la tabla."""
    return almacen().perfil_de(pid)


def datos_hasta():
    """Fecha del último dato del registro cargado (eventos, mediciones o citas): hasta dónde llega la información."""
    return almacen().datos_hasta()


def registros():
    """Lo que registra el equipo y lo que llega después de la carga inicial (no los ítems del registro base)."""
    return almacen().registros()


def registros_de(pid):
    """Todos los ítems de un paciente, ordenados por sk (en DynamoDB, antes de cargar la copia, es una consulta a su partición)."""
    return almacen().registros_de(pid)


def registros_tipo(prefijo, pid=None):
    """Ítems cuyo sk empieza con `prefijo` (incluye los del registro base), ordenados por sk; de un paciente o de todos."""
    return almacen().registros_tipo(prefijo, pid)


def globales(pk, prefijo=""):
    """Ítems de una partición reservada (_kb, _ingesta, _idem), ordenados por sk."""
    return almacen().globales(pk, prefijo)


def rev(pid):
    """Contador de escrituras del paciente: sube con cada cosa que se le registra (0 si no existe)."""
    return almacen().rev(pid)


def guardar(item, *, si_no_existe=False, rev_vista=None):
    """Guarda un ítem. `si_no_existe`: no pisa uno igual (devuelve False si ya existía). `rev_vista`: el rev que el
    usuario tenía a la vista; si el paciente recibió algo después, lanza Conflicto (el handler responde 409)."""
    return almacen().guardar(item, si_no_existe=si_no_existe, rev_vista=rev_vista)


def guardar_lote(items):
    """Escritura por lotes: cada ítem solo si no existe. Devuelve cuántos eran nuevos."""
    return almacen().guardar_lote(items)


def guardar_perfil(pid, perfil, *, origen=None, rev_vista=None):
    """Guarda el ítem "perfil" (solo paciente + lista_espera). Es el único ítem que se pisa: sube rev y, si el paciente
    venía del registro base, el original queda guardado. Quien lo modifica deja además su novedad# (ver cambios_perfil)."""
    almacen().guardar_perfil(pid, perfil, origen=origen, rev_vista=rev_vista)


def guardar_evento(pid, ev, *, origen=None):
    """Guarda un evento (solo se agrega: uno con la misma fecha e id no se pisa). True si era nuevo."""
    return guardar(item_evento(pid, ev, origen), si_no_existe=True)


def guardar_medicion(pid, m, *, origen=None):
    """Idempotente: la misma medición (fecha, tipo y valor) no se duplica. True si era nueva."""
    return guardar(item_medicion(pid, m, origen), si_no_existe=True)


def guardar_cita(pid, c, *, origen=None):
    """Idempotente: la misma cita no se duplica. True si era nueva."""
    return guardar(item_cita(pid, c, origen), si_no_existe=True)


def contactos():
    """Último contacto por paciente, con el número de intentos sin respuesta desde el último contacto efectivo."""
    return almacen().contactos()


def decisiones():
    """Última decisión clínica por paciente."""
    return almacen().ultimos("decision#", "decision")


def gestiones():
    return almacen().ultimos("gestion#", "gestion")


def ajustes_orden():
    """Último ajuste manual de posición por paciente (un registro con 'quitar' lo deshace)."""
    return {pid: a for pid, a in almacen().ultimos("orden#", "orden").items() if not a.get("quitar")}


def evaluaciones():
    return almacen().ultimos("evaluacion#", "evaluacion")


def evaluaciones_por_paciente():
    """Todas las evaluaciones de cada paciente, la más reciente primero (cada fecha de corte usa la vigente)."""
    return almacen().evaluaciones_por_paciente()
