"""Almacén (lambda/datos.py + lambda/almacen_dynamo.py): ítems normalizados por paciente, perfiles armados desde los ítems
y lectura sin Scan por solicitud. El backend de DynamoDB se prueba con moto (sin AWS ni credenciales reales)."""
import base64
import copy
import itertools
import json
import os
import sys
import time
import types
from concurrent.futures import ThreadPoolExecutor

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["LOCAL"] = "1"; os.environ.setdefault("DATA_DIR", os.path.join(RAIZ, "data")); os.environ.pop("MODEL_ID", None)
sys.path.insert(0, os.path.join(RAIZ, "lambda"))
sys.path.insert(0, os.path.join(RAIZ, "scripts"))
import app  # noqa: E402
import datos  # noqa: E402

_N = itertools.count(1)
CALLADO = lambda *_: None  # noqa: E731


def call(method, path, qs=None, body=None):
    r = app.handler({"requestContext": {"http": {"method": method}}, "rawPath": path,
                     "queryStringParameters": qs, "body": json.dumps(body) if body else None})
    return r["statusCode"], json.loads(r["body"])


def perfil(pid, eventos=2):
    """Paciente de prueba en el formato de perfiles.json."""
    return {"id_paciente": pid,
            "paciente": {"nombre_fantasia": f"Paciente {pid}", "edad": 60, "sexo": "F", "comuna": "La Florida", "prevision": "FONASA B",
                         "nivel_socioeconomico": "medio", "fallecido": False, "fecha_defuncion": None},
            "lista_espera": {"id_solicitud": "IC-" + pid, "especialidad": "Cardiología", "sub_especialidad": "Cardiología adulto",
                             "diagnostico_cie10": "I50", "diagnostico_texto": "Insuficiencia cardíaca", "prioridad_inicial": "media",
                             "fecha_ingreso_lista": "2026-01-10", "origen_derivacion": "CESFAM/APS", "estado": "en_espera"},
            "eventos_clinicos": [{"id_evento": f"EV-{pid}-{i}", "fecha_evento": f"2026-0{i + 3}-15", "tipo_evento": "control_aps",
                                  "subtipo": "control rutina", "severidad": "leve", "detalle": "control"} for i in range(eventos)],
            "mediciones": [{"fecha_medicion": "2026-03-01", "tipo_medicion": "presion_sistolica", "valor": 130, "unidad": "mmHg", "fuera_de_rango": False},
                           {"fecha_medicion": "2026-05-01", "tipo_medicion": "HbA1c", "valor": 7.5, "unidad": "%", "fuera_de_rango": True}],
            "citaciones": [{"id_cita": f"CT-{pid}", "id_box": "BOX-01", "fecha_cita": "2026-04-02", "especialidad": "Cardiología",
                            "estado_cita": "no_asistio", "minutos_atencion_real": None}]}


def armado(p):
    return {**p, "eventos_anulados": []}


def item(pid, tipo, contenido, marca=None):
    return {"id_paciente": pid, "sk": f"{tipo}#{marca or datos.ahora()}", tipo: json.dumps(contenido, ensure_ascii=False)}


def hospitalizacion(ide, fecha="2026-10-01", **extra):
    return {"id_evento": ide, "fecha_evento": fecha, "tipo_evento": "hospitalizacion", "subtipo": "ingreso hospitalario",
            "severidad": "grave", "detalle": "ingreso hospitalario", **extra}


@pytest.fixture(scope="module")
def archivo():
    with open(os.path.join(os.environ["DATA_DIR"], "perfiles.json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def aws_simulado():
    """DynamoDB simulado (moto), una vez para todo el archivo: crear el cliente de boto3 es lo lento."""
    import boto3
    from moto import mock_aws
    import almacen_dynamo
    mp = pytest.MonkeyPatch()
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        mp.setenv(k, "prueba")
    mp.setenv("AWS_DEFAULT_REGION", "us-east-1")
    mp.delenv("AWS_PROFILE", raising=False)
    with mock_aws():
        sesion = boto3.Session(region_name="us-east-1")
        yield types.SimpleNamespace(sesion=sesion, cliente=almacen_dynamo.cliente_dynamo(sesion))
    mp.undo()


@pytest.fixture
def nube(aws_simulado):
    """Una tabla nueva por test, como la que espera el almacén (claves id_paciente + sk, índice PorDia)."""
    import almacen_dynamo
    tabla = f"registros-{next(_N)}"
    almacen_dynamo.crear_tabla(aws_simulado.cliente, tabla)
    return types.SimpleNamespace(sesion=aws_simulado.sesion, cliente=aws_simulado.cliente, tabla=tabla)


def contenedor(nube, perfiles=None):
    """Una instancia nueva del backend sobre la misma tabla: como un contenedor de Lambda que recién arranca."""
    import cargar_registro
    from almacen_dynamo import AlmacenDynamo
    a = AlmacenDynamo(nube.tabla, cliente=nube.cliente)
    if perfiles is not None:
        cargar_registro.cargar(perfiles, a, avisar=CALLADO)
    return a


@pytest.fixture(params=["memoria", "dynamo"])
def alm(request):
    """El mismo comportamiento se exige a los dos backends: memoria y DynamoDB, con dos pacientes del registro base."""
    base = [perfil("PAC-A"), perfil("PAC-B", eventos=1)]
    if request.param == "memoria":
        return datos.AlmacenMemoria(base)
    nube = request.getfixturevalue("nube")
    contenedor(nube, base)
    return contenedor(nube)


# ---------- los 500 perfiles armados desde ítems equivalen a perfiles.json ----------
def test_los_500_perfiles_armados_desde_items_equivalen_a_perfiles_json(archivo):
    datos.restablecer()
    base, (al_dia, revisiones) = datos.perfiles(), datos.perfiles_combinados()
    assert len(archivo) == len(base) == len(al_dia) == 500 and revisiones == {} and datos.registros() == []
    assert list(base) == [p["id_paciente"] for p in archivo]
    for p in archivo:
        pid = p["id_paciente"]
        for armado_ in (base[pid], al_dia[pid]):
            assert armado_["paciente"] == p["paciente"] and armado_["lista_espera"] == p["lista_espera"]
            assert armado_["eventos_clinicos"] == p["eventos_clinicos"] and armado_["mediciones"] == p["mediciones"]   # mismo orden
            # las citas quedan por fecha (en el archivo, 10 pacientes las traen desordenadas): mismas citas
            assert armado_["citaciones"] == sorted(p["citaciones"], key=lambda c: c["fecha_cita"])
            assert armado_["eventos_anulados"] == []
        assert datos.rev(pid) == 1
    # un ítem por paciente, evento, medición y cita; todos del registro base y sin `registrado` dentro de los eventos
    n = {t: len(datos.registros_tipo(t)) for t in ("perfil", "evento#", "medicion#", "cita#")}
    assert n == {"perfil": 500, "evento#": sum(len(p["eventos_clinicos"]) for p in archivo),
                 "medicion#": sum(len(p["mediciones"]) for p in archivo), "cita#": sum(len(p["citaciones"]) for p in archivo)}
    eventos = datos.registros_tipo("evento#")
    assert all(i["origen"] == datos.REGISTRO_BASE and i["ts"] and i["dia"] == i["ts"][:10] for i in eventos)
    assert not any("registrado" in json.loads(i["evento"]) for i in eventos)   # de eso depende llego_al_sistema
    assert datos.datos_hasta() == max(x[k] for p in archivo for lista_, k in (("eventos_clinicos", "fecha_evento"),
                                      ("mediciones", "fecha_medicion"), ("citaciones", "fecha_cita")) for x in p[lista_])


def test_items_de_perfil_y_claves():
    p = perfil("PAC-X")
    items = datos.items_de_perfil(p, origen="registro_base")
    assert [i["sk"].split("#")[0] for i in items] == ["perfil", "evento", "evento", "medicion", "medicion", "cita"]
    assert items[0]["especialidad"] == "Cardiología" and json.loads(items[0]["perfil"]) == {"paciente": p["paciente"], "lista_espera": p["lista_espera"]}
    assert items[1]["sk"] == "evento#2026-03-15#EV-PAC-X-0" and items[5]["sk"] == "cita#2026-04-02#CT-PAC-X"
    assert all(i["origen"] == "registro_base" and i["id_paciente"] == "PAC-X" for i in items)
    # medición: hash8 de fecha + tipo + valor (130 y 130.0 son la misma; otro valor es otra medición)
    m = p["mediciones"][0]
    sk = datos.item_medicion("PAC-X", m)["sk"]
    assert sk.startswith("medicion#2026-03-01#presion_sistolica#") and len(sk.rsplit("#", 1)[1]) == 8
    assert datos.item_medicion("PAC-X", {**m, "valor": 130.0, "unidad": "otra"})["sk"] == sk
    assert datos.item_medicion("PAC-X", {**m, "valor": 131})["sk"] != sk
    # cita sin id: hash8 del contenido; evento sin id: uno determinista por contenido (reenviarlo no lo duplica)
    c = {"fecha_cita": "2026-04-02", "id_box": "BOX-01", "estado_cita": "asistio"}
    assert datos.item_cita("PAC-X", c)["sk"] == datos.item_cita("PAC-X", dict(c))["sk"] != datos.item_cita("PAC-X", {**c, "estado_cita": "cancelo"})["sk"]
    e = {"fecha_evento": "2026-10-01", "tipo_evento": "hospitalizacion", "subtipo": "ingreso UCI"}
    a, b = datos.item_evento("PAC-X", e), datos.item_evento("PAC-X", dict(e))
    assert a["sk"] == b["sk"] and json.loads(a["evento"])["id_evento"].startswith("EV-")
    # perfil parcial (lo que usa la ingesta): sin datos del paciente no sale ítem "perfil"
    assert [i["sk"] for i in datos.items_de_perfil({"id_paciente": "PAC-X", "eventos_clinicos": [hospitalizacion("EV-1")]})] == ["evento#2026-10-01#EV-1"]
    for malo in ("", "_kb"):   # las particiones que empiezan con "_" son del sistema
        with pytest.raises(datos.EntradaInvalida):
            datos.item_perfil(malo, p)


# ---------- mismo comportamiento en memoria y en DynamoDB ----------
def test_perfiles_armados_y_lecturas(alm):
    a, b = perfil("PAC-A"), perfil("PAC-B", eventos=1)
    perfs, revisiones = alm.perfiles_combinados()
    assert perfs == {"PAC-A": armado(a), "PAC-B": armado(b)} == alm.perfiles() and revisiones == {}
    assert alm.perfil_de("PAC-A") == armado(a) and alm.perfil_de("NADIE") is None
    assert alm.registros() == []                                    # lo del registro base no es "lo que registra el equipo"
    assert alm.rev("PAC-A") == 1 and alm.rev("NADIE") == 0
    de_a = alm.registros_de("PAC-A")
    assert [i["sk"] for i in de_a] == sorted(i["sk"] for i in de_a) and len(de_a) == 6
    assert all(i["origen"] == datos.REGISTRO_BASE and i["ts"] and i["dia"] == i["ts"][:10] for i in de_a)
    assert [i["sk"] for i in alm.registros_tipo("evento#", "PAC-A")] == ["evento#2026-03-15#EV-PAC-A-0", "evento#2026-04-15#EV-PAC-A-1"]
    todos = alm.registros_tipo("evento#")
    assert [(i["sk"], i["id_paciente"]) for i in todos] == sorted((i["sk"], i["id_paciente"]) for i in todos) and len(todos) == 3
    assert len(alm.registros_tipo("evento#2026-03")) == 2 and len(alm.registros_tipo("medicion#")) == 4
    assert alm.datos_hasta() == "2026-05-01"


def test_lo_que_se_escribe_se_ve_de_inmediato_y_sube_rev(alm):
    rev = {"accion": "confirmar", "usuario": "Dra. Soto", "fecha_corte": "2026-10-13", "fecha": datos.ahora()}
    assert alm.guardar(item("PAC-A", "revision", rev, rev["fecha"])) is True
    assert alm.perfiles_combinados()[1] == {"PAC-A": rev} and alm.rev("PAC-A") == 2 and alm.rev("PAC-B") == 1
    guardada, ficha = alm.registros_tipo("revision#", "PAC-A")[0], alm.registros_tipo("perfil", "PAC-A")[0]
    assert (ficha["ts"], ficha["dia"], ficha["rev"]) == (guardada["ts"], guardada["dia"], 2)   # el perfil viaja con el contador nuevo
    assert alm.guardar(datos.item_evento("PAC-A", hospitalizacion("EV-NUEVO", registrado=datos.ahora())), si_no_existe=True) is True
    al_dia = alm.perfiles_combinados()[0]["PAC-A"]
    assert [e["id_evento"] for e in al_dia["eventos_clinicos"]] == ["EV-PAC-A-0", "EV-PAC-A-1", "EV-NUEVO"] and alm.rev("PAC-A") == 3
    assert alm.perfiles()["PAC-A"] == armado(perfil("PAC-A"))        # el registro base queda tal como se cargó
    assert alm.guardar(datos.item_medicion("PAC-A", {"fecha_medicion": "2026-01-01", "tipo_medicion": "PHQ9", "valor": 12}), si_no_existe=True)
    assert alm.guardar(datos.item_cita("PAC-A", {"fecha_cita": "2026-01-05", "id_box": "BOX-02", "estado_cita": "asistio"}), si_no_existe=True)
    al_dia = alm.perfiles_combinados()[0]["PAC-A"]
    assert [m["fecha_medicion"] for m in al_dia["mediciones"]] == ["2026-01-01", "2026-03-01", "2026-05-01"]    # cada lista por fecha
    assert [c["fecha_cita"] for c in al_dia["citaciones"]] == ["2026-01-05", "2026-04-02"]
    regs = alm.registros()                                          # lo que llegó después de la carga inicial
    assert sorted(r["sk"].split("#")[0] for r in regs) == ["cita", "evento", "medicion", "revision"]
    assert all(r["ts"] and r["dia"] == r["ts"][:10] and "origen" not in r for r in regs)
    with pytest.raises(ValueError):
        alm.guardar({"id_paciente": "PAC-A", "sk": "paciente#", "perfil": "{}"})   # el perfil completo ya no existe


def test_a_igual_fecha_los_eventos_quedan_en_el_orden_en_que_llegaron(alm):
    for ide, marca in (("EV-Z-PRIMERO", "2026-10-13T10:00:00.000000+00:00"), ("EV-A-DESPUES", "2026-10-13T11:00:00.000000+00:00")):
        alm.guardar(datos.item_evento("PAC-B", hospitalizacion(ide, "2026-04-15", registrado=marca)), si_no_existe=True)
    alm.guardar(datos.item_evento("PAC-B", hospitalizacion("EV-SIN-REGISTRO", "2026-04-15")), si_no_existe=True)
    ids = [e["id_evento"] for e in alm.perfiles_combinados()[0]["PAC-B"]["eventos_clinicos"]]
    assert ids == ["EV-PAC-B-0", "EV-SIN-REGISTRO", "EV-Z-PRIMERO", "EV-A-DESPUES"]   # por fecha; el último registrado, al final


def test_si_no_existe_es_idempotente(alm):
    ev = hospitalizacion("EV-1", registrado="2026-10-13T10:00:00.000000+00:00")
    assert alm.guardar(datos.item_evento("PAC-A", ev), si_no_existe=True) is True
    rev = alm.rev("PAC-A")
    assert alm.guardar(datos.item_evento("PAC-A", {**ev, "detalle": "otro texto"}), si_no_existe=True) is False
    assert alm.rev("PAC-A") == rev                                  # no se escribió nada: el contador no se mueve
    guardado = [e for e in alm.perfiles_combinados()[0]["PAC-A"]["eventos_clinicos"] if e["id_evento"] == "EV-1"]
    assert guardado == [ev]                                          # ni se duplica ni se pisa
    # un evento del registro base tampoco se pisa (solo se agrega)
    assert alm.guardar(datos.item_evento("PAC-A", {**perfil("PAC-A")["eventos_clinicos"][0], "severidad": "grave"}), si_no_existe=True) is False
    assert alm.perfiles_combinados()[0]["PAC-A"]["eventos_clinicos"][0]["severidad"] == "leve"
    # sin si_no_existe, guardar reemplaza (como antes) y devuelve True
    marca = datos.ahora()
    assert alm.guardar(item("PAC-A", "gestion", {"nota": "uno"}, marca)) and alm.guardar(item("PAC-A", "gestion", {"nota": "dos"}, marca))
    assert [json.loads(r["gestion"]) for r in alm.registros_tipo("gestion#", "PAC-A")] == [{"nota": "dos"}]


def test_guardar_lote(alm):
    nuevos = datos.items_de_perfil({"id_paciente": "PAC-A", "eventos_clinicos": [hospitalizacion("EV-L1"), hospitalizacion("EV-L2", "2026-10-02")],
                                    "mediciones": [{"fecha_medicion": "2026-10-01", "tipo_medicion": "PHQ9", "valor": 15}]}, origen="api")
    nuevos += datos.items_de_perfil({"id_paciente": "PAC-B", "citaciones": [{"fecha_cita": "2026-10-03", "id_cita": "CT-L", "estado_cita": "asistio"}]}, origen="api")
    nuevos += datos.items_de_perfil(perfil("PAC-C", eventos=1), origen="api")          # paciente nuevo, con su perfil
    ya_estaban = datos.items_de_perfil(perfil("PAC-A"))                               # todo lo de PAC-A ya existe
    lote_ingesta = {"id_paciente": "_ingesta", "sk": "lote#2026-10-13#L1", "lote": json.dumps({"id_lote": "L1"})}
    assert alm.guardar_lote(nuevos + ya_estaban + [nuevos[0], lote_ingesta]) == len(nuevos) + 1   # repetidos dentro del lote: una vez
    assert (alm.rev("PAC-A"), alm.rev("PAC-B"), alm.rev("PAC-C")) == (2, 2, 1)        # el contador sube una vez por lote y paciente
    perfs = alm.perfiles_combinados()[0]
    assert [e["id_evento"] for e in perfs["PAC-A"]["eventos_clinicos"]][-2:] == ["EV-L1", "EV-L2"]
    assert perfs["PAC-A"]["paciente"] == perfil("PAC-A")["paciente"]                  # el perfil existente no se pisa en un lote
    assert perfs["PAC-C"] == armado(perfil("PAC-C", eventos=1)) and "PAC-C" not in alm.perfiles()
    assert [i["sk"] for i in alm.globales("_ingesta")] == ["lote#2026-10-13#L1"] and alm.globales("_ingesta", "lote#2027") == []
    assert all(r["origen"] == "api" for r in alm.registros())                         # el lote de _ingesta no es de un paciente
    assert alm.guardar_lote(nuevos + [lote_ingesta]) == 0                             # reenviar el mismo lote no duplica…
    assert (alm.rev("PAC-A"), alm.rev("PAC-B"), alm.rev("PAC-C")) == (2, 2, 1)        # …ni mueve los contadores
    assert alm.guardar_lote([]) == 0
    with pytest.raises(ValueError):                                                   # un ítem mal formado: no se escribe nada del lote
        alm.guardar_lote(datos.items_de_perfil(perfil("PAC-D")) + [{"sk": "evento#sin-paciente"}])
    assert "PAC-D" not in alm.perfiles_combinados()[0]


def test_un_lote_grande_se_escribe_por_tandas_sin_separar_a_un_paciente(alm, monkeypatch):
    monkeypatch.setattr(alm, "TANDA", 5)                                              # tandas chicas para probarlo con pocos datos
    nuevos = [perfil(f"PAC-T{i}") for i in range(7)]                                  # 6 ítems por paciente
    items = [it for p in nuevos for it in datos.items_de_perfil(p, origen="api")]
    marcas = []
    monkeypatch.setattr(alm, "_r_marcar", lambda ts, original=alm._r_marcar: (marcas.append(ts), original(ts))[1])
    assert alm.guardar_lote(items[::-1]) == 42                                        # aunque lleguen desordenados
    perfs = alm.perfiles_combinados()[0]
    assert all(perfs[p["id_paciente"]] == armado(p) and alm.rev(p["id_paciente"]) == 1 for p in nuevos)
    assert len(marcas) == 7 and marcas == sorted(set(marcas))                         # cada tanda se anuncia apenas termina
    assert alm.guardar_lote(items) == 0 and len(marcas) == 7


def test_conflicto_si_el_paciente_recibio_algo_despues(alm):
    vista = alm.rev("PAC-A")
    assert alm.guardar(item("PAC-A", "contacto", {"resultado": "no_contesta"}))       # llegó algo mientras el usuario miraba
    antes = len(alm.registros())
    with pytest.raises(datos.Conflicto) as e:
        alm.guardar(item("PAC-A", "revision", {"accion": "confirmar"}), rev_vista=vista)
    assert (e.value.id_paciente, e.value.rev_vista, e.value.rev_actual) == ("PAC-A", vista, vista + 1)
    assert len(alm.registros()) == antes and alm.rev("PAC-A") == vista + 1            # no se guardó nada
    assert alm.guardar(item("PAC-A", "revision", {"accion": "confirmar"}), rev_vista=str(vista + 1)) is True   # recargó y reintenta
    assert alm.rev("PAC-A") == vista + 2 and "PAC-A" in alm.perfiles_combinados()[1]
    assert alm.guardar(item("PAC-B", "decision", {"decision": "mantener"}), rev_vista=alm.rev("PAC-B"))        # otro paciente no se ve afectado
    with pytest.raises(datos.Conflicto):
        alm.guardar_perfil("PAC-B", {**perfil("PAC-B"), "paciente": {"edad": 99}}, rev_vista=1)
    with pytest.raises(datos.EntradaInvalida):
        alm.guardar(item("PAC-A", "revision", {}), rev_vista="siete")


def test_el_perfil_se_pisa_pero_el_original_del_registro_queda(alm):
    original = perfil("PAC-A")
    cambiado = copy.deepcopy(original)
    cambiado["paciente"].update(fallecido=True, fecha_defuncion="2026-10-12")
    cambiado["lista_espera"].update(estado="fallecido", especialidad="Neurología")
    alm.guardar_perfil("PAC-A", cambiado)
    al_dia = alm.perfiles_combinados()[0]["PAC-A"]
    assert al_dia["paciente"]["fallecido"] and al_dia["lista_espera"]["especialidad"] == "Neurología"
    assert al_dia["eventos_clinicos"] == original["eventos_clinicos"]                  # eventos, mediciones y citas no se tocan
    assert alm.perfiles()["PAC-A"] == armado(original) and alm.rev("PAC-A") == 2       # perfiles(): tal como se cargó
    it = alm.registros_de("PAC-A")[-1]
    assert it["sk"] == "perfil" and it["especialidad"] == "Neurología" and it["origen"] == datos.REGISTRO_BASE
    assert json.loads(it["perfil_base"]) == {"paciente": original["paciente"], "lista_espera": original["lista_espera"]}
    cambiado["paciente"]["edad"] = 61
    alm.guardar_perfil("PAC-A", cambiado, origen="archivo")                            # segundo cambio, por otro canal
    it = alm.registros_de("PAC-A")[-1]                                                 # el original sigue siendo el del registro…
    assert json.loads(it["perfil_base"])["paciente"]["edad"] == 60 and alm.rev("PAC-A") == 3
    assert it["origen"] == datos.REGISTRO_BASE and "PAC-A" in alm.perfiles()           # …y el paciente sigue siendo del registro
    alm.guardar_perfil("PAC-A", cambiado)                                              # sin cambios: no se escribe
    assert alm.rev("PAC-A") == 3 and alm.registros() == []
    # paciente nuevo (ingresado en la app): está al día, pero no es parte del registro base
    alm.guardar_perfil("PAC-N", perfil("PAC-N", eventos=0), origen="app")
    assert alm.perfiles_combinados()[0]["PAC-N"]["lista_espera"]["diagnostico_cie10"] == "I50" and "PAC-N" not in alm.perfiles()
    assert [(r["id_paciente"], r["sk"], r["origen"], r["rev"]) for r in alm.registros()] == [("PAC-N", "perfil", "app", 1)]


def test_paciente_sin_perfil_no_aparece_hasta_que_llega(alm):
    assert alm.guardar(datos.item_evento("PAC-FUTURO", hospitalizacion("EV-F")), si_no_existe=True)
    assert "PAC-FUTURO" not in alm.perfiles_combinados()[0] and alm.perfil_de("PAC-FUTURO") is None and alm.rev("PAC-FUTURO") == 1
    alm.guardar_perfil("PAC-FUTURO", perfil("PAC-FUTURO", eventos=0))
    assert [e["id_evento"] for e in alm.perfiles_combinados()[0]["PAC-FUTURO"]["eventos_clinicos"]] == ["EV-F"] and alm.rev("PAC-FUTURO") == 2


def test_enmiendas_anulan_o_corrigen_la_relacion_sin_borrar_el_evento(alm):
    def enmendar(ide, accion):
        marca = datos.ahora()
        alm.guardar(item("PAC-A", "enmienda", {"id_evento": ide, "accion": accion, "motivo": "evento mal registrado en otro paciente",
                                               "usuario": "Dra. Soto", "fecha": marca}, marca))
    enmendar("EV-PAC-A-0", "anular")
    p = alm.perfiles_combinados()[0]["PAC-A"]
    assert [e["id_evento"] for e in p["eventos_clinicos"]] == ["EV-PAC-A-1"]            # sale de los eventos vigentes…
    assert [(e["id_evento"], e["anulado"]["usuario"]) for e in p["eventos_anulados"]] == [("EV-PAC-A-0", "Dra. Soto")]   # …y queda aquí
    assert len(alm.registros_tipo("evento#", "PAC-A")) == 2                             # el ítem del evento no se borra
    enmendar("EV-PAC-A-1", "no_relacionado")
    assert alm.perfiles_combinados()[0]["PAC-A"]["eventos_clinicos"][0]["relacionado"] is False
    enmendar("EV-PAC-A-1", "relacionado")                                               # rige la última enmienda
    assert alm.perfiles_combinados()[0]["PAC-A"]["eventos_clinicos"][0]["relacionado"] is True
    assert alm.perfiles()["PAC-A"] == armado(perfil("PAC-A"))                           # el registro base no cambia
    assert alm.perfiles_combinados()[0]["PAC-B"] == armado(perfil("PAC-B", eventos=1))  # ni los otros pacientes


def test_vistas_por_tipo_de_registro(alm):
    for pid, resultado in (("PAC-A", "no_contesta"), ("PAC-A", "no_contesta"), ("PAC-B", "no_contesta"), ("PAC-B", "citado")):
        alm.guardar(item(pid, "contacto", {"resultado": resultado}))
    c = alm.contactos()
    assert (c["PAC-A"]["intentos_sin_respuesta"], c["PAC-B"]["intentos_sin_respuesta"], c["PAC-B"]["resultado"]) == (2, 0, "citado")
    c["PAC-A"]["resultado"] = "modificado por quien lo pidió"
    assert alm.contactos()["PAC-A"]["resultado"] == "no_contesta"                      # se entregan copias
    alm.guardar(item("PAC-A", "decision", {"decision": "mantener"}))
    alm.guardar(item("PAC-A", "decision", {"decision": "citar_prioritario"}))
    assert alm.ultimos("decision#", "decision") == {"PAC-A": {"decision": "citar_prioritario"}}
    for n in (1, 2, 3):
        alm.guardar(item("PAC-B", "evaluacion", {"n": n}))
    assert alm.evaluaciones_por_paciente() == {"PAC-B": [{"n": 3}, {"n": 2}, {"n": 1}]}   # la más reciente primero
    assert alm.ultimos("evaluacion#", "evaluacion") == {"PAC-B": {"n": 3}}
    alm.guardar({"id_paciente": "PAC-A", "sk": f"gestion#{datos.ahora()}", "gestion": "{esto no es json"})   # un registro malo no bota nada
    assert alm.ultimos("gestion#", "gestion") == {} and len(alm.registros_tipo("gestion#")) == 1


def test_claves_de_un_solo_uso_con_vencimiento(alm):
    clave = {"id_paciente": "_idem", "sk": "solicitud-123", "respuesta": json.dumps({"id_lote": "L1"})}
    assert alm.guardar({**clave, "expira": int(time.time()) + 3600}, si_no_existe=True) is True
    assert alm.guardar({**clave, "respuesta": "{}", "expira": int(time.time()) + 3600}, si_no_existe=True) is False
    assert json.loads(alm.globales("_idem", "solicitud-123")[0]["respuesta"]) == {"id_lote": "L1"}
    vencida = {"id_paciente": "_idem", "sk": "solicitud-vieja", "expira": int(time.time()) - 10}
    assert alm.guardar(vencida, si_no_existe=True) and alm.guardar({**vencida, "expira": int(time.time()) + 60}, si_no_existe=True)   # la vencida no cuenta
    assert alm.registros() == [] and alm.rev("_idem") == 0                              # no es de un paciente: sin contador


def test_un_registro_con_json_malo_no_deja_al_paciente_fuera(alm):
    alm.guardar({"id_paciente": "PAC-A", "sk": "evento#2026-10-01#EV-MALO", "evento": "{roto"})
    alm.guardar({"id_paciente": "PAC-A", "sk": "medicion#2026-10-01#x#00000000", "medicion": '"un texto, no una medición"'})
    p = alm.perfiles_combinados()[0]["PAC-A"]
    assert [e["id_evento"] for e in p["eventos_clinicos"]] == ["EV-PAC-A-0", "EV-PAC-A-1"] and len(p["mediciones"]) == 2
    assert alm.perfiles_combinados()[0]["PAC-B"] == armado(perfil("PAC-B", eventos=1))


# ---------- API pública de datos.py en modo memoria ----------
def test_escrituras_desde_varios_hilos():
    """evaluacion_ia.barrido guarda desde un ThreadPoolExecutor: nada se pierde, el contador cuenta cada escritura y de
    dos escrituras iguales simultáneas solo una es la nueva (el candado protege la copia)."""
    datos.restablecer()
    pid, antes = "PAC-HLF-00003", datos.rev("PAC-HLF-00003")
    intervalo = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)   # cambia de hilo a cada instante: sin candado, el contador pierde escrituras
    try:
        with ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(lambda i: datos.guardar({"id_paciente": pid, "sk": f"evaluacion#{i:04d}", "evaluacion": json.dumps({"n": i})}), range(400)))
            nuevas = list(ex.map(lambda i: datos.guardar({"id_paciente": pid, "sk": f"contacto#{i % 100:04d}", "contacto": "{}"}, si_no_existe=True), range(400)))
    finally:
        sys.setswitchinterval(intervalo)
    assert len(datos.registros_tipo("evaluacion#", pid)) == 400 and sum(nuevas) == 100 and datos.rev(pid) == antes + 500
    assert datos.evaluaciones()[pid] == {"n": 399} and len(datos.evaluaciones_por_paciente()[pid]) == 400


def test_restablecer_deja_el_almacen_como_recien_cargado(monkeypatch):
    datos.restablecer()
    pid = "PAC-HLF-00003"
    datos.guardar_evento(pid, hospitalizacion("EV-R", registrado=datos.ahora()))
    datos.guardar_perfil("PAC-NUEVO-R", perfil("PAC-NUEVO-R"))
    datos.guardar({"id_paciente": "_kb", "sk": "criterio_local#CL-1#x", "criterio_local": "{}"})
    assert datos.rev(pid) == 2 and len(datos.perfiles_combinados()[0]) == 501 and datos.globales("_kb")
    datos.restablecer()
    assert datos.rev(pid) == 1 and len(datos.perfiles_combinados()[0]) == 500 and datos.registros() == [] and datos.globales("_kb") == []
    assert not any(e["id_evento"] == "EV-R" for e in datos.perfiles_combinados()[0][pid]["eventos_clinicos"])
    monkeypatch.setattr(datos, "LOCAL", False)                                          # en DynamoDB la aplicación no borra
    with pytest.raises(RuntimeError, match="limpiar_demo"):
        datos.restablecer()


def test_si_el_refresco_falla_la_solicitud_sigue_con_la_copia_que_hay(monkeypatch, capsys):
    class SinRed(datos.AlmacenMemoria):
        def _sincronizar(self):
            raise ConnectionError("sin conexión con DynamoDB")
    alm = SinRed([perfil("PAC-A")])
    monkeypatch.setattr(datos, "_alm", alm)
    assert list(datos.perfiles_combinados()[0]) == ["PAC-A"]
    with pytest.raises(ConnectionError):
        alm.nueva_solicitud()                                        # el almacén avisa…
    datos.nueva_solicitud()                                          # …pero la solicitud no se cae: queda en el registro
    assert "no se pudo refrescar" in capsys.readouterr().out and call("GET", "/pacientes")[0] == 200


def test_novedad_guarda_antes_y_despues_y_no_toca_los_eventos():
    datos.restablecer()
    pid = "PAC-HLF-00003"
    s, ev = call("POST", "/eventos", body={"id_paciente": pid, "tipo_evento": "visita_urgencia", "subtipo": "triage ESI 2", "fecha_corte": "2026-10-13"})
    assert s == 200
    s, r = call("POST", f"/pacientes/{pid}/novedad", body={"tipo": "riesgo", "grupo_proteccion": "PRAIS", "acg": "G3", "usuario": "Enf. Rojas"})
    assert s == 200 and r["paciente"]["grupo_proteccion"] == "PRAIS"
    s, r = call("POST", f"/pacientes/{pid}/novedad", body={"tipo": "atendido", "fecha": "2026-10-13", "usuario": "Enf. Rojas"})
    assert s == 200 and not r["en_lista"]
    riesgo, atendido = [json.loads(n["novedad"]) for n in datos.registros_tipo("novedad#", pid)]   # dos novedades seguidas: dos registros
    assert riesgo["antes"] == {"paciente": {"grupo_proteccion": None, "acg": None}} and riesgo["usuario"] == "Enf. Rojas"
    assert riesgo["despues"] == {"paciente": {"grupo_proteccion": "PRAIS", "acg": "G3"}}
    assert atendido["antes"] == {"lista_espera": {"estado": "en_espera", "fecha_atencion": None}}
    assert atendido["despues"] == {"lista_espera": {"estado": "atendido", "fecha_atencion": "2026-10-13"}} and atendido["tipo"] == "atendido"
    al_dia = datos.perfiles_combinados()[0][pid]
    assert [e["id_evento"] for e in al_dia["eventos_clinicos"]].count(ev["evento"]["id_evento"]) == 1   # el evento sigue, una sola vez
    assert al_dia["lista_espera"]["estado"] == "atendido" and al_dia["paciente"]["acg"] == "G3"
    base = datos.perfiles()[pid]                                                         # el registro base, tal como se cargó
    assert base["lista_espera"]["estado"] == "en_espera" and "acg" not in base["paciente"] and len(base["eventos_clinicos"]) == len(al_dia["eventos_clinicos"]) - 1
    assert "paciente#" not in {r["sk"] for r in datos.registros()}


def _csv(texto):
    return base64.b64encode(texto.encode("utf-8")).decode()


def test_importar_guarda_cada_registro_por_separado_y_con_su_traza(monkeypatch):
    datos.restablecer()
    _, lista = call("GET", "/pacientes", {"fecha_corte": "2026-10-13"})
    pid = next(p["id_paciente"] for p in lista["pacientes"] if p["estado_clinico"] == "sin_cambios" and p["fecha_ingreso_lista"] < "2026-09-01"
               and p["diagnostico_cie10"] == "I50")
    assert call("POST", f"/pacientes/{pid}/revision", body={"accion": "confirmar", "usuario": "Dra. Soto", "fecha_corte": "2026-10-13"})[0] == 200
    antes = datos.perfiles_combinados()[0][pid]
    archivos = [
        {"nombre": "pacientes.csv", "contenido_base64": _csv("id_paciente;nombre;edad;sexo\nPAC-IMP-1;Ana Importada;70;F\n")},
        {"nombre": "lista_espera.csv", "contenido_base64": _csv("id_paciente;diagnostico_cie10;prioridad_inicial;fecha_ingreso_lista\nPAC-IMP-1;I50;media;2026-09-10\n")},
        {"nombre": "eventos.csv", "contenido_base64": _csv(f"id_paciente;id_evento;fecha_evento;tipo_evento;subtipo\n{pid};EV-HOSP-77;2026-10-01;hospitalizacion;ingreso hospitalario\n"
                                                             "PAC-IMP-1;;2026-10-02;visita_urgencia;triage ESI 2\n")},
        {"nombre": "mediciones.csv", "contenido_base64": _csv(f"id_paciente;fecha_medicion;tipo_medicion;valor\n{pid};2026-10-01;presion_sistolica;171\n")},
        {"nombre": "citaciones.csv", "contenido_base64": _csv(f"id_paciente;id_cita;id_box;fecha_cita;estado_cita\n{pid};CT-IMP-1;BOX-03;2026-10-02;no_asistio\n")},
    ]
    s, r = call("POST", "/importar", body={"archivos": archivos, "confirmar": True, "fecha_corte": "2026-10-13"})
    assert s == 200 and r["cargado"] and r["resumen"] == {"pacientes_nuevos": 1, "pacientes_actualizados": 1, "eventos": 2, "mediciones": 1, "citaciones": 1}, r
    regs = datos.registros()
    assert "paciente#" not in {x["sk"] for x in regs}
    importados = [x for x in regs if x.get("origen") == "archivo"]
    assert sorted(x["sk"].split("#")[0] for x in importados) == ["cita", "evento", "evento", "medicion", "perfil"]   # solo lo nuevo, ítem por ítem
    ev = json.loads(next(x["evento"] for x in importados if x["sk"] == "evento#2026-10-01#EV-HOSP-77"))
    assert ev["canal"] == "archivo" and ev["registrado"] > "2026-11"                    # momento real en que llegó, dentro del evento
    al_dia = datos.perfiles_combinados()[0]
    assert al_dia[pid]["paciente"] == antes["paciente"] and al_dia[pid]["lista_espera"] == antes["lista_espera"]   # el perfil no cambió: no se reescribe
    assert not datos.registros_tipo("novedad#", pid) and "perfil_base" not in datos.registros_tipo("perfil", pid)[0]
    assert len(al_dia[pid]["eventos_clinicos"]) == len(antes["eventos_clinicos"]) + 1 and len(al_dia[pid]["mediciones"]) == len(antes["mediciones"]) + 1
    assert al_dia["PAC-IMP-1"]["lista_espera"]["especialidad"] == "Cardiología" and len(al_dia["PAC-IMP-1"]["eventos_clinicos"]) == 1
    # el evento importado llegó DESPUÉS de la revisión: la deja sin efecto, igual que uno registrado en la app
    _, lista = call("GET", "/pacientes", {"fecha_corte": "2026-10-13"})
    fila = next(p for p in lista["pacientes"] if p["id_paciente"] == pid)
    assert fila["estado_clinico"] == "descompensado" and fila["estado_revision"] == "requiere_revision"
    # volver a cargar el mismo archivo no duplica nada (lo que ya estaba ni siquiera se intenta escribir; solo queda el
    # registro del lote en la partición reservada _ingesta: qué llegó, cuándo y que eran duplicados)
    n, intentos, alm = len(datos.registros()), [], datos.almacen()
    monkeypatch.setattr(alm, "_r_poner", lambda it, si_no_existe, real=alm._r_poner: (
        intentos.append(it["sk"]) if not it["id_paciente"].startswith("_") else None, real(it, si_no_existe))[1])
    s, r = call("POST", "/importar", body={"archivos": archivos, "confirmar": True, "fecha_corte": "2026-10-13"})
    assert s == 200 and len(datos.registros()) == n and r["resumen"]["eventos"] == 0 and intentos == []
    # un archivo que cambia datos del paciente deja la novedad con lo que cambió
    edad = antes["paciente"]["edad"]
    cambio = [{"nombre": "pacientes.csv", "contenido_base64": _csv(f"id_paciente;edad;sexo\n{pid};{edad + 1};{antes['paciente']['sexo']}\n")}]
    assert call("POST", "/importar", body={"archivos": cambio, "confirmar": True, "usuario": "Estadística HLF"})[0] == 200
    nov = json.loads(datos.registros_tipo("novedad#", pid)[0]["novedad"])
    assert (nov["tipo"], nov["usuario"], nov["antes"], nov["despues"]) == ("importacion", "Estadística HLF", {"paciente": {"edad": edad}}, {"paciente": {"edad": edad + 1}})
    assert datos.perfiles_combinados()[0][pid]["paciente"]["edad"] == edad + 1 and datos.perfiles()[pid]["paciente"]["edad"] == edad
    # un id de paciente reservado para el sistema se rechaza antes de escribir nada (ni el cambio del otro paciente)
    n = len(datos.registros())
    malo = [{"nombre": "pacientes.csv", "contenido_base64": _csv(f"id_paciente;edad;sexo\n{pid};{edad + 2};F\n_kb;50;F\n")},
            {"nombre": "lista_espera.csv", "contenido_base64": _csv("id_paciente;diagnostico_cie10;prioridad_inicial;fecha_ingreso_lista\n_kb;I50;media;2026-09-10\n")}]
    s, r = call("POST", "/importar", body={"archivos": malo, "confirmar": True})
    assert s == 400 and "_kb" in r["error"] and len(datos.registros()) == n and datos.perfiles_combinados()[0][pid]["paciente"]["edad"] == edad + 1


# ---------- DynamoDB: lectura sin Scan por solicitud ----------
def test_dynamo_registros_de_usa_una_consulta_y_no_carga_la_tabla(nube):
    contenedor(nube, [perfil("PAC-A"), perfil("PAC-B")])
    trabajador = contenedor(nube)                                    # p. ej. el trabajador de la cola: un solo paciente
    de_a = trabajador.registros_de("PAC-A")
    assert [i["sk"].split("#")[0] for i in de_a] == ["cita", "evento", "evento", "medicion", "medicion", "perfil"]
    assert trabajador.perfil_de("PAC-A") == armado(perfil("PAC-A")) and trabajador.rev("PAC-A") == 1
    assert len(trabajador.registros_tipo("evento#", "PAC-A")) == 2
    assert trabajador.guardar(item("PAC-A", "dictamen", {"id_dictamen": "DIC-1"})) and trabajador.rev("PAC-A") == 2
    trabajador.nueva_solicitud()
    assert not trabajador.cargado and trabajador.lecturas["scan"] == 0 and trabajador.lecturas["particion"] == 3
    otro = contenedor(nube)                                          # y lo que escribió lo ve cualquier otro contenedor
    assert [json.loads(r["dictamen"]) for r in otro.registros()] == [{"id_dictamen": "DIC-1"}] and otro.rev("PAC-A") == 2


def test_dynamo_refresco_incremental_entre_dos_contenedores(nube, monkeypatch):
    import almacen_dynamo
    contenedor(nube, [perfil("PAC-A"), perfil("PAC-B")])
    a, b = contenedor(nube), contenedor(nube)
    assert a.perfiles_combinados()[0] == b.perfiles_combinados()[0] and (a.lecturas["scan"], b.lecturas["scan"]) == (1, 1)
    # sin holguras: lo nuevo tiene que llegar por sí mismo (en la práctica el traslape releería la carga recién hecha)
    monkeypatch.setattr(almacen_dynamo, "TRASLAPE_S", 0)
    monkeypatch.setattr(almacen_dynamo, "MARGEN_S", 0)
    b.nueva_solicitud()
    assert b.lecturas["por_dia"] == 0                                # el marcador no cambió: no se lee nada más
    ev = hospitalizacion("EV-NUBE", registrado=datos.ahora())
    a.guardar(datos.item_evento("PAC-A", ev), si_no_existe=True)     # un contenedor escribe…
    a.guardar(item("PAC-A", "revision", {"accion": "confirmar"}))
    assert "EV-NUBE" not in [e["id_evento"] for e in b.perfiles_combinados()[0]["PAC-A"]["eventos_clinicos"]]   # …el otro aún no refresca
    marcadores = b.lecturas["marcador"]
    b.nueva_solicitud()                                              # …y lo ve en su siguiente solicitud
    perfs, revisiones = b.perfiles_combinados()
    assert perfs["PAC-A"]["eventos_clinicos"][-1] == ev and revisiones == {"PAC-A": {"accion": "confirmar"}} and b.rev("PAC-A") == 3
    assert perfs["PAC-B"] == armado(perfil("PAC-B")) and len(b.registros()) == 2
    assert (b.lecturas["scan"], b.lecturas["por_dia"], b.lecturas["marcador"]) == (1, 1, marcadores + 1)   # sin recargar todo
    b.nueva_solicitud()
    assert b.lecturas["por_dia"] == 1                                # nada nuevo: solo el marcador
    a.nueva_solicitud()                                              # quien escribió ya lo tenía: tampoco relee
    assert (a.lecturas["scan"], a.lecturas["por_dia"]) == (1, 0) and a.rev("PAC-A") == 3
    b.guardar_lote(datos.items_de_perfil(perfil("PAC-C", eventos=1), origen="api"))   # y en el otro sentido, un paciente nuevo
    a.nueva_solicitud()
    assert a.perfiles_combinados()[0]["PAC-C"] == armado(perfil("PAC-C", eventos=1)) and (a.lecturas["scan"], a.lecturas["por_dia"]) == (1, 1)
    # control de edición entre contenedores: el rev que el usuario vio en uno ya no rige si el otro escribió
    with pytest.raises(datos.Conflicto) as e:
        b.guardar(item("PAC-A", "decision", {"decision": "mantener"}), rev_vista=2)
    assert e.value.rev_actual == 3 and a.guardar(item("PAC-A", "decision", {"decision": "mantener"}), rev_vista=3)
    with pytest.raises(datos.Conflicto):                             # b todavía cree que va en 3: DynamoDB decide, no la copia
        b.guardar(item("PAC-A", "orden", {"posicion": 1}), rev_vista=3)
    assert b.rev("PAC-A") == 4 and len(b.registros_tipo("decision#", "PAC-A")) == 1   # tras el conflicto quedó al día


def test_dynamo_relectura_de_confirmacion(nube, monkeypatch):
    """El índice PorDia es de consistencia eventual: tras un cambio se relee una vez más el mismo tramo."""
    import almacen_dynamo
    contenedor(nube, [perfil("PAC-A")])
    a, b = contenedor(nube), contenedor(nube)
    a.perfiles_combinados(), b.perfiles_combinados()
    a.guardar(item("PAC-A", "contacto", {"resultado": "citado"}))
    b.nueva_solicitud()
    assert b.lecturas["por_dia"] == 1
    b.nueva_solicitud()
    assert b.lecturas["por_dia"] == 1                                # todavía no pasan los 2 s
    monkeypatch.setattr(almacen_dynamo, "CONFIRMAR_S", 0)
    b.nueva_solicitud()
    assert b.lecturas["por_dia"] == 2
    b.nueva_solicitud()
    assert b.lecturas["por_dia"] == 2 and b.lecturas["scan"] == 1    # una sola vez


def test_dynamo_red_de_seguridad_si_una_escritura_no_se_anuncio(nube, monkeypatch):
    """Si el anuncio de una escritura falla (o tarda más que el traslape), los otros contenedores igual llegan a verla:
    cada cierto tiempo releen todo lo escrito desde su relectura amplia anterior."""
    import almacen_dynamo
    contenedor(nube, [perfil("PAC-A")])
    a, b = contenedor(nube), contenedor(nube)
    a.perfiles_combinados(), b.perfiles_combinados()
    monkeypatch.setattr(a, "_r_marcar", lambda ts: None)             # la escritura queda guardada; el marcador no se entera
    a.guardar(item("PAC-A", "contacto", {"resultado": "citado"}))
    b.nueva_solicitud()
    assert b.contactos() == {} and b.lecturas["por_dia"] == 0        # el marcador no cambió: b no tiene cómo saberlo…
    monkeypatch.setattr(almacen_dynamo, "AMPLIA_S", 0)
    b.nueva_solicitud()                                              # …hasta su relectura amplia
    assert b.contactos()["PAC-A"]["resultado"] == "citado" and b.rev("PAC-A") == 2 and b.lecturas["scan"] == 1


class ClienteQueFalla:
    """Cliente de DynamoDB que falla una vez en la operación indicada (como una caída de red tras los reintentos)."""

    def __init__(self, real):
        self._real, self.fallar = real, set()

    def __getattr__(self, nombre):
        def llamar(**kw):
            if nombre in self.fallar:
                from botocore.exceptions import ClientError
                self.fallar.discard(nombre)
                raise ClientError({"Error": {"Code": "InternalServerError", "Message": "falla simulada"}}, nombre)
            return getattr(self._real, nombre)(**kw)
        return llamar


def test_dynamo_una_escritura_que_falla_a_medias_no_duplica_ni_queda_escondida(nube):
    from almacen_dynamo import AlmacenDynamo
    from botocore.exceptions import ClientError
    contenedor(nube, [perfil("PAC-A")])
    a, b = AlmacenDynamo(nube.tabla, cliente=ClienteQueFalla(nube.cliente)), contenedor(nube)
    a.perfiles_combinados(), b.perfiles_combinados()
    # registro del equipo (no idempotente): falle el contador o falle el ítem, no queda escrito y repetir la acción deja uno solo
    for operacion in ("update_item", "put_item"):
        a._cli.fallar = {operacion}
        with pytest.raises(ClientError):
            a.guardar(item("PAC-A", "revision", {"accion": "confirmar"}))
        assert a.registros() == [] and contenedor(nube).registros() == []
    assert a.guardar(item("PAC-A", "revision", {"accion": "confirmar"})) and len(contenedor(nube).registros_tipo("revision#")) == 1
    b.nueva_solicitud()                                              # b queda al día: lo que vea después es porque se anunció
    # evento (idempotente): si falla al subir el contador, el evento igual quedó guardado, se anuncia y reintentar no lo duplica
    ev = datos.item_evento("PAC-A", hospitalizacion("EV-FALLA"))
    a._cli.fallar = {"update_item"}
    with pytest.raises(ClientError):
        a.guardar(ev, si_no_existe=True)
    b.nueva_solicitud()
    assert [e["id_evento"] for e in b.perfiles_combinados()[0]["PAC-A"]["eventos_clinicos"]][-1] == "EV-FALLA" and b.lecturas["scan"] == 1
    assert a.guardar(ev, si_no_existe=True) is False and len(a.registros_tipo("evento#", "PAC-A")) == 3
    # lote: lo que alcanzó a escribirse queda y se anuncia; al reenviarlo solo entra lo que faltaba
    lote = datos.items_de_perfil({"id_paciente": "PAC-A", "eventos_clinicos": [hospitalizacion(f"EV-LOTE-{i}") for i in range(4)]}, origen="api")
    a._cli.fallar = {"put_item"}
    with pytest.raises(ClientError):
        a.guardar_lote(lote)
    b.nueva_solicitud()
    assert sum("EV-LOTE" in r["sk"] for r in b.registros()) == 3
    assert a.guardar_lote(lote) == 1 and sum("EV-LOTE" in r["sk"] for r in a.registros()) == 4
    assert contenedor(nube).perfiles_combinados()[0] == a.perfiles_combinados()[0]      # la copia coincide con la tabla


def test_cargar_registro_es_idempotente_y_equivale_al_archivo(nube, archivo):
    import cargar_registro
    sub = archivo[:24]
    a = contenedor(nube)
    r = cargar_registro.cargar(sub, a, pacientes_por_lote=10, avisar=CALLADO)
    total = sum(1 + len(p["eventos_clinicos"]) + len(p["mediciones"]) + len(p["citaciones"]) for p in sub)
    assert r == {"pacientes": 24, "items": total, "nuevos": total}
    b = contenedor(nube)
    perfs, _ = b.perfiles_combinados()
    assert list(perfs) == [p["id_paciente"] for p in sub] and perfs == b.perfiles() and b.registros() == []
    for p in sub:
        assert perfs[p["id_paciente"]] == armado({**p, "citaciones": sorted(p["citaciones"], key=lambda c: c["fecha_cita"])})
        assert b.rev(p["id_paciente"]) == 1
    b.guardar(item("PAC-HLF-00002", "revision", {"accion": "confirmar"}))               # lo que registra el equipo…
    epoca = b._leer_marcador()[0]
    assert cargar_registro.cargar(sub, contenedor(nube), avisar=CALLADO)["nuevos"] == 0   # …no se toca al repetir la carga
    c = contenedor(nube)
    assert c.perfiles_combinados()[0] == perfs and c.rev("PAC-HLF-00002") == 2 and len(c.registros()) == 1
    assert c._leer_marcador()[0] == epoca                                               # nada nuevo: los contenedores no recargan
    assert cargar_registro.cargar(archivo[:26], contenedor(nube), avisar=CALLADO)["nuevos"] > 0   # dos pacientes más
    b.nueva_solicitud()                                                                 # carga masiva → cambia la época → recarga completa
    assert len(b.perfiles()) == 26 and b.lecturas["scan"] == 2


def test_los_scripts_corren_desde_la_linea_de_comandos(nube, tmp_path, capsys):
    import cargar_registro
    import limpiar_demo
    archivo_ = tmp_path / "perfiles.json"
    archivo_.write_text(json.dumps([perfil("PAC-A"), perfil("PAC-B")], ensure_ascii=False), encoding="utf-8")
    args = ["--tabla", nube.tabla, "--region", "us-east-1", "--perfil", ""]
    assert cargar_registro.main(["--archivo", str(archivo_), *args]) == {"pacientes": 2, "items": 12, "nuevos": 12}
    assert cargar_registro.main(["--archivo", str(archivo_), *args])["nuevos"] == 0 and "ya estaban" in capsys.readouterr().out
    a = contenedor(nube)
    a.guardar(item("PAC-A", "revision", {"accion": "confirmar"}))
    assert limpiar_demo.main(args)["borrados"] == 0 and len(contenedor(nube).registros()) == 1    # sin --borrar solo muestra
    assert limpiar_demo.main([*args, "--borrar", "--conservar", "_kb, _ingesta"])["borrados"] == 1
    assert contenedor(nube).registros() == [] and len(contenedor(nube).perfiles()) == 2


def test_limpiar_demo_borra_lo_registrado_restaura_perfiles_y_cambia_la_epoca(nube):
    import limpiar_demo
    original = [perfil("PAC-A"), perfil("PAC-B")]
    contenedor(nube, original)
    a, b = contenedor(nube), contenedor(nube)
    fallecida = copy.deepcopy(original[0])
    fallecida["paciente"].update(fallecido=True, fecha_defuncion="2026-10-12")
    fallecida["lista_espera"]["estado"] = "fallecido"
    a.guardar_perfil("PAC-A", fallecida)
    a.guardar(datos.item_evento("PAC-B", hospitalizacion("EV-DEMO-1", registrado=datos.ahora())), si_no_existe=True)
    a.guardar(item("PAC-B", "revision", {"accion": "confirmar"}))
    a.guardar(item("PAC-B", "evaluacion", {"categoria_final": "alta"}))
    a.guardar_perfil("PAC-NUEVO-1", perfil("PAC-NUEVO-1", eventos=0))
    a.guardar(item("PAC-NUEVO-1", "evaluacion", {"categoria_final": "media"}))
    a.guardar({"id_paciente": "_kb", "sk": "criterio_local#CL-0001#x", "criterio_local": "{}"})
    a.guardar({"id_paciente": "_ingesta", "sk": "lote#x", "lote": "{}"})
    b.nueva_solicitud()
    assert len(b.perfiles_combinados()[0]) == 3 and b.perfiles_combinados()[0]["PAC-A"]["paciente"]["fallecido"]
    r = limpiar_demo.limpiar(nube.sesion, nube.tabla, avisar=CALLADO)                               # sin --borrar solo informa
    assert r == {"borrados": 0, "restaurados": 0, "evaluaciones": 1, "epoca": None} and len(contenedor(nube).registros()) == 5
    r = limpiar_demo.limpiar(nube.sesion, nube.tabla, borrar=True, conservar=("_kb",), avisar=CALLADO)
    assert (r["borrados"], r["restaurados"], r["evaluaciones"]) == (5, 1, 1) and r["epoca"]
    b.nueva_solicitud()                                                                 # cambió la época: recarga completa
    perfs, revisiones = b.perfiles_combinados()
    assert b.lecturas["scan"] == 2 and perfs == {p["id_paciente"]: armado(p) for p in original} == b.perfiles() and revisiones == {}
    assert [r["sk"].split("#")[0] for r in b.registros()] == ["evaluacion"]             # la evaluación del paciente del registro se conserva
    assert "perfil_base" not in b.registros_de("PAC-A")[-1] and b.registros_de("PAC-NUEVO-1") == []
    assert len(b.globales("_kb")) == 1 and b.globales("_ingesta") == []
    assert limpiar_demo.limpiar(nube.sesion, nube.tabla, borrar=True, todo=True, avisar=CALLADO)["borrados"] == 2   # --todo: evaluación y _kb
    assert contenedor(nube).registros() == [] and contenedor(nube).globales("_kb") == []
    assert contenedor(nube).perfiles_combinados()[0] == perfs


def test_la_api_completa_funciona_igual_sobre_dynamodb(nube, archivo, monkeypatch):
    """Mismas respuestas con el almacén en memoria y con DynamoDB, y las acciones del equipo pasan por el mismo camino."""
    sub = archivo[:60]
    q = {"fecha_corte": "2026-10-13"}
    monkeypatch.setattr(datos, "_alm", datos.AlmacenMemoria(sub))
    en_memoria = [call("GET", ruta, q) for ruta in ("/pacientes", "/kpis", "/catalogo", "/pacientes/PAC-HLF-00002", "/health")]
    contenedor(nube, sub)
    monkeypatch.setattr(datos, "_alm", contenedor(nube))
    assert [call("GET", ruta, q) for ruta in ("/pacientes", "/kpis", "/catalogo", "/pacientes/PAC-HLF-00002", "/health")] == en_memoria
    s, r = call("POST", "/eventos", body={"id_paciente": "PAC-HLF-00020", "tipo_evento": "hospitalizacion", "subtipo": "ingreso UCI", **q})
    assert s == 200 and r["posicion_despues"] < r["posicion_antes"] and r["paciente"]["categoria"] == "alta"
    s, r = call("POST", "/pacientes/PAC-HLF-00020/revision", body={"accion": "confirmar", "usuario": "Dra. Soto", **q})
    assert s == 200
    s, r = call("POST", "/pacientes/PAC-HLF-00003/novedad", body={"tipo": "fallecimiento", "fecha": "2026-10-12", **q})
    assert s == 200 and not r["en_lista"]
    s, r = call("POST", "/pacientes", body={"nombre": "Nueva Dynamo", "edad": 70, "sexo": "F", "diagnostico_cie10": "I50", "prioridad_inicial": "media",
                                            "fecha_ingreso_lista": "2026-09-01", **q})
    assert s == 200 and r["paciente"]["especialidad"] == "Cardiología"
    nuevo = r["id_paciente"]
    csv_ev = _csv(f"id_paciente;fecha_evento;tipo_evento;subtipo\n{nuevo};2026-10-01;hospitalizacion;ingreso hospitalario\n")
    s, r = call("POST", "/importar", body={"archivos": [{"nombre": "eventos.csv", "contenido_base64": csv_ev}], "confirmar": True, **q})
    assert s == 200 and r["cargado"] and r["resumen"]["eventos"] == 1
    s, lista = call("GET", "/pacientes", q)
    filas = {p["id_paciente"]: p for p in lista["pacientes"]}
    assert filas["PAC-HLF-00020"]["estado_revision"] == "confirmado" and filas[nuevo]["riesgo_vital"] and "PAC-HLF-00003" not in filas
    assert "PAC-HLF-00003" in [e["id_paciente"] for e in lista["excluidos"]] and call("GET", "/kpis", q)[0] == 200
    assert datos.almacen().lecturas["scan"] == 1                     # todas las solicitudes con una sola lectura de la tabla
    monkeypatch.setattr(datos, "_alm", contenedor(nube))             # otro contenedor, recién arrancado, ve lo mismo
    assert call("GET", "/pacientes", q) == (s, lista)
    assert datos.perfiles()["PAC-HLF-00003"]["paciente"]["fallecido"] is False          # y el registro base, tal como se cargó
