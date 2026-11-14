"""Ingesta continua: una sola tubería para todos los canales (app, archivo, API para sistemas, zona de carga S3, informes).
Contrato: docs/diseno/ESPECIFICACION_MVP.md §7.

    validar → resolver el paciente (id o RUT) → deduplicar → foto de antes → guardar ítems → registro del lote
           → evaluar (en línea o por la cola SQS) → dictámenes → resumen

- Lo recibido queda guardado ANTES de responder; la cola solo desacopla la evaluación con IA. Las reglas rigen de
  inmediato porque se calculan al leer.
- Solo se agrega (datos.guardar_lote escribe lo que no existe): reenviar lo mismo no duplica y se informa en `duplicados`.
- Un evento de alguien que no está en la lista no es un error (urgencia manda a todo el hospital): se cuenta en
  `fuera_de_lista` y no se guarda nada de esa persona (minimización de datos).
- La severidad sale del subtipo (modelos.SUBTIPOS vía importar.normalizar_evento), nunca del remitente.
"""
import base64
import hashlib
import json
import os
import time
import uuid
from datetime import date
from urllib.parse import unquote_plus

import bitacora
import datos
import importar
from evaluacion_ia import algoritmo_activo, evaluar_y_guardar

LOTES, IDEM = "_ingesta", "_idem"      # particiones reservadas: registro de lotes y claves de idempotencia
MAX_FILAS = 2000                        # filas por solicitud a POST /ingesta/eventos (≈0,5 MB; cabe holgado en 10 MB y 30 s)
MAX_EN_LINEA = 25                       # más pacientes afectados que esto (con cola definida) → la evaluación va a la cola
IDEM_HORAS = 24
TABLAS = ("pacientes", "lista_espera", "eventos", "mediciones", "citaciones")
DE_IMPORTAR = {"eventos": "eventos_clinicos"}   # nombre de la tabla en importar.py
EGRESO = {"atendido", "egresado", "fallecido"}
# Los sistemas del hospital mandan a todo el hospital: para ellos, quien ya egresó de la lista tampoco está en ella.
# En la app, un archivo o un informe, la persona eligió al paciente: basta con que exista.
CANALES_EXTERNOS = {"api", "s3"}
DISPARADOR = {"app": "evento", "api": "evento", "archivo": "importacion", "s3": "importacion", "informe": "informe"}
SEVERIDAD = {"grave": 3, "moderada": 2, "leve": 1}
NO_VIAJAN = {"nombre_fantasia", "nombre", "rut"}   # la foto que viaja en el mensaje de la cola no lleva identificación


class CuerpoInvalido(ValueError):
    """El cuerpo no tiene la forma esperada (400). Las filas inválidas no lo son: van en `rechazados`."""


# ---------- la tubería ----------
def registrar(carga, *, canal, usuario=None, origen=None, archivo=None, corte=None, evaluar="ahora",
              rechazados=None, antes=None, detalle=False):
    """Valida, deduplica y guarda lo recibido; deja el registro del lote; evalúa y registra los dictámenes.
    carga: {"pacientes", "lista_espera", "eventos" (o "eventos_clinicos"), "mediciones", "citaciones"} con filas ya
    normalizadas (importar.procesar o importar.filas_de_json). Opcional "_filas" (de importar.procesar): archivo y fila
    de cada registro. rechazados: filas que ya se rechazaron al leerlas ({tabla, indice, motivo}). antes: foto previa
    si quien llama ya la tomó. detalle: agrega "_detalle" (eventos guardados, evaluaciones y dictámenes completos)."""
    t0 = time.perf_counter()
    corte = date.fromisoformat(corte) if isinstance(corte, str) else (corte or datos.hoy())
    origen = origen or canal
    marca = datos.ahora()
    id_lote = "LOT-" + marca[:19].replace("-", "").replace(":", "") + "-" + uuid.uuid4().hex[:4].upper()
    filas = {t: list(carga.get(t) or carga.get(DE_IMPORTAR.get(t, t)) or []) for t in TABLAS}
    ubic = carga.get("_filas") or {}
    cuenta = {t: {"recibidos": 0, "registrados": 0, "duplicados": 0, "rechazados": 0, "fuera_de_lista": 0} for t in TABLAS}
    rech = []

    def rechazar(tabla, pos, motivo):
        rech.append({"tabla": tabla, **pos, "motivo": motivo})
        cuenta[tabla]["rechazados"] += 1

    for r in rechazados or []:
        cuenta[r["tabla"]]["recibidos"] += 1
        rechazar(r["tabla"], {k: v for k, v in r.items() if k not in ("tabla", "motivo")}, r["motivo"])

    def donde(tabla, i, r):
        """Cómo ubicar la fila en lo que mandó el remitente: índice en el JSON, o archivo y fila del Excel/CSV."""
        if r.get("_indice") is not None:
            return {"indice": r["_indice"]}
        lst = ubic.get(DE_IMPORTAR.get(tabla, tabla)) or []
        if i < len(lst):
            return {"indice": lst[i][1], "archivo": lst[i][0]}
        return {"indice": i}

    perfs, _ = datos.perfiles_combinados()

    # 1) Pacientes e interconsultas (solo archivos): mismas reglas que la carga de la app (importar.combinar)
    nuevos_perf, cambios, items = {}, [], []
    if filas["pacientes"] or filas["lista_espera"]:
        from catalogo import catalogo
        cat = {d["diagnostico_cie10"]: d for d in catalogo()["diagnosticos"]}
        solo = {"pacientes": filas["pacientes"], "lista_espera": filas["lista_espera"], "eventos_clinicos": [], "mediciones": [], "citaciones": []}
        tocados, _, avisos = importar.combinar(solo, perfs, cat)
        for pid, p in tocados.items():
            if pid not in perfs:
                nuevos_perf[pid] = p
                # se arma todo antes de escribir nada: un id inválido (p. ej. reservado) corta aquí con EntradaInvalida
                items += datos.items_de_perfil({**p, "eventos_clinicos": [], "mediciones": [], "citaciones": []}, origen=canal)
            else:
                a, d = datos.cambios_perfil(perfs[pid], p)
                if a or d:
                    cambios.append((pid, p, a, d))
        cambiados = {c[0] for c in cambios}
        for tabla in ("pacientes", "lista_espera"):
            for i, r in enumerate(filas[tabla]):
                pid = r.get("id_paciente")
                cuenta[tabla]["recibidos"] += 1
                if pid in nuevos_perf or pid in cambiados:
                    cuenta[tabla]["registrados"] += 1
                elif pid in tocados:
                    cuenta[tabla]["duplicados"] += 1
                else:
                    motivo = next((a.split(": ", 1)[1] for a in avisos if a.startswith(f"{pid}: ")), "no se pudo ingresar a la lista")
                    rechazar(tabla, donde(tabla, i, r), motivo)

    # 2) A quién corresponde cada fila: id del registro o RUT (los sistemas del hospital conocen el RUT, no nuestro id)
    por_rut = {}

    def en_lista(pid):
        if pid in nuevos_perf:
            return True
        p = perfs.get(pid)
        if p is None:
            return False
        if canal in CANALES_EXTERNOS:
            return not (p["lista_espera"].get("estado") in EGRESO or p["paciente"].get("fallecido"))
        return True

    def resolver(r):
        v = str(r.get("id_paciente") or r.get("rut") or "").strip()
        if v in perfs or v in nuevos_perf:
            pids = [v]
        else:
            from ingreso import normalizar_rut
            rut = normalizar_rut(v)
            if rut and "_listo" not in por_rut:  # el índice por RUT se arma una vez por lote, solo si llega algún RUT
                por_rut["_listo"] = []
                for pid, p in list(perfs.items()) + list(nuevos_perf.items()):
                    if p["paciente"].get("rut"):
                        por_rut.setdefault(p["paciente"]["rut"], []).append(pid)
            # una persona puede esperar por más de una interconsulta: el evento es de la persona y vale para todas
            pids = por_rut.get(rut, []) if rut else []
        return [pid for pid in pids if en_lista(pid)]

    # 3) Deduplicar contra lo que ya está guardado (y dentro del mismo lote)
    ya = {}

    def existentes(pid):
        if pid not in ya:
            p = perfs.get(pid) or {}
            ya[pid] = ({i["sk"] for i in datos.registros_de(pid)} if pid in perfs else set(),
                       {_clave(e) for e in p.get("eventos_clinicos", []) + p.get("eventos_anulados", [])})
        return ya[pid]

    nuevos_ev, nuevas_med, con_citas = {}, {}, set()
    for i, r in enumerate(filas["eventos"]):
        cuenta["eventos"]["recibidos"] += 1
        ev, motivo = (importar.normalizar_evento(r) if r.get("fecha_evento") and r.get("tipo_evento")
                      else (None, "falta fecha_evento o tipo_evento"))
        if ev:
            _, motivo = datos.fecha_valida(ev["fecha_evento"], corte, "fecha del evento")
        if motivo:
            rechazar("eventos", donde("eventos", i, r), motivo)
            continue
        pids = resolver(r)
        if not pids:
            cuenta["eventos"]["fuera_de_lista"] += 1
            continue
        id_origen = str(r.get("id_evento") or "").strip()
        extras = {k: v for k, v in r.items() if k not in ("id_paciente", "rut", "_indice", "id_evento") and v is not None}
        for pid in pids:
            e = {**extras, **ev, **({"id_evento": id_origen} if id_origen else {})}
            sk = datos.item_evento(pid, e)["sk"]           # sin id del origen: uno determinista por contenido
            e["id_evento"] = sk.split("#", 2)[2]
            sks, claves = existentes(pid)
            if sk in sks or (not id_origen and _clave(e) in claves):
                cuenta["eventos"]["duplicados"] += 1
                continue
            sks.add(sk)
            claves.add(_clave(e))
            e.update(registrado=marca, canal=canal, origen=r.get("origen") or origen, id_lote=id_lote)
            if usuario and not e.get("usuario"):
                e["usuario"] = usuario
            items.append(datos.item_evento(pid, e, origen=canal))
            nuevos_ev.setdefault(pid, []).append(e)
            cuenta["eventos"]["registrados"] += 1

    for tabla, normalizar, item_de in (("mediciones", lambda r, pid: importar.normalizar_medicion(r), datos.item_medicion),
                                       ("citaciones", lambda r, pid: importar.normalizar_cita(r, _especialidad(pid, perfs, nuevos_perf)),
                                        datos.item_cita)):
        campo_fecha = "fecha_medicion" if tabla == "mediciones" else "fecha_cita"
        for i, r in enumerate(filas[tabla]):
            cuenta[tabla]["recibidos"] += 1
            try:
                if not r.get(campo_fecha):
                    raise ValueError(f"falta {campo_fecha}")
                if tabla == "mediciones":  # una cita puede ser futura; una medición no
                    _, err = datos.fecha_valida(r[campo_fecha], corte, "fecha de la medición")
                    if err:
                        raise ValueError(err)
                pids = resolver(r)
                x = [(pid, normalizar(r, pid)) for pid in pids]
            except (KeyError, TypeError, ValueError) as e:
                rechazar(tabla, donde(tabla, i, r), str(e) or type(e).__name__)
                continue
            if not pids:
                cuenta[tabla]["fuera_de_lista"] += 1
                continue
            for pid, m in x:
                it = item_de(pid, m, origen=canal)
                sks, _ = existentes(pid)
                if it["sk"] in sks:
                    cuenta[tabla]["duplicados"] += 1
                    continue
                sks.add(it["sk"])
                items.append(it)
                cuenta[tabla]["registrados"] += 1
                if tabla == "mediciones":
                    nuevas_med.setdefault(pid, []).append(m)
                else:
                    con_citas.add(pid)

    # 4) Foto de antes (solo de quienes traen información clínica nueva), y recién entonces se escribe
    clinicos = sorted(set(nuevos_ev) | set(nuevas_med))
    errores = []
    if antes is None:
        try:
            antes = bitacora.fotos(clinicos, corte) if clinicos else {}
        except Exception as e:  # sin foto, el dictamen queda sin "antes"; lo recibido no se pierde
            errores.append({"etapa": "foto", "error": f"{type(e).__name__}: {e}"})
            antes = {}
    for pid, p, a, d in cambios:  # el perfil es el único ítem que se pisa: lo que cambió queda en una novedad
        datos.guardar({"id_paciente": pid, "sk": f"novedad#{marca}", "novedad": json.dumps(
            {"tipo": "importacion", "detalle": f"datos del paciente actualizados desde {_que(canal)}",
             "usuario": usuario or "equipo clínico", "fecha": marca, "id_lote": id_lote, "antes": a, "despues": d},
            ensure_ascii=False, default=str)})
        datos.guardar_perfil(pid, p)
    escritos = datos.guardar_lote(items) if items else 0
    esperados = len(items)
    if escritos != esperados:  # otro proceso guardó lo mismo entre la revisión y la escritura: queda como duplicado
        print(f"ingesta {id_lote}: {esperados - escritos} ítem(s) ya existían al escribir")

    afectados = sorted(set(clinicos) | con_citas | set(nuevos_perf) | {c[0] for c in cambios})
    total = {k: sum(c[k] for c in cuenta.values()) for k in ("recibidos", "registrados", "duplicados", "fuera_de_lista")}
    lote = {"id_lote": id_lote, "canal": canal, "origen": origen, "archivo": archivo, "usuario": usuario, "fecha": marca,
            "fecha_corte": corte.isoformat(), **total, "n_rechazados": len(rech), "por_tabla": cuenta,
            "rechazados": rech[:200], "pacientes_afectados": afectados, "con_informacion_clinica": clinicos, "estado": "recibido"}
    datos.guardar({"id_paciente": LOTES, "sk": f"lote#{marca}#{id_lote}", "lote": _json(lote)}, si_no_existe=True)

    # 5) Evaluación (IA si ALGORITMO=rubrica) y dictámenes: una vez por paciente aunque traiga varios eventos
    disparadores = {pid: _disparador(canal, id_lote, nuevos_ev.get(pid, []), nuevas_med.get(pid, [])) for pid in clinicos}
    url = os.environ.get("COLA_EVALUACION_URL", "").strip()
    a_cola = clinicos if (url and clinicos and (evaluar == "cola" or len(clinicos) > MAX_EN_LINEA)) else []
    fallidos = _encolar(url, [_mensaje(pid, id_lote, canal, usuario, corte, disparadores[pid], antes.get(pid)) for pid in a_cola]) if a_cola else []
    if fallidos:
        errores.append({"etapa": "cola", "error": f"{len(fallidos)} paciente(s) no se pudieron encolar: se evaluaron en línea"})
    en_linea = [pid for pid in clinicos if pid not in a_cola or pid in fallidos]
    evaluaciones, dictamenes = _evaluar(en_linea, corte, disparadores, antes, canal, usuario, id_lote, errores)
    en_cola = len(a_cola) - len(fallidos)

    cierre = {"id_lote": id_lote, "fecha": datos.ahora(), "evaluacion": "en_cola" if en_cola else "sincrona",
              "en_cola": en_cola, "evaluados_en_linea": len(en_linea), "dictamenes": [d.get("id_dictamen") for d in dictamenes],
              "errores": errores, "estado": "con_errores" if errores else ("en_cola" if en_cola else "procesado"),
              "procesado_en_ms": round((time.perf_counter() - t0) * 1000)}
    datos.guardar({"id_paciente": LOTES, "sk": f"cierre#{id_lote}", "cierre": _json(cierre)}, si_no_existe=True)
    out = {"id_lote": id_lote, "canal": canal, "origen": origen, **total, "rechazados": rech,
           "pacientes_afectados": len(afectados), "por_tabla": cuenta, "dictamenes": [_resumen_dictamen(d) for d in dictamenes],
           "evaluacion": cierre["evaluacion"], "en_cola": en_cola, "errores": errores, "estado": cierre["estado"],
           "procesado_en_ms": cierre["procesado_en_ms"]}
    if detalle:
        out["_detalle"] = {"eventos": nuevos_ev, "evaluaciones": evaluaciones, "dictamenes": dictamenes}
    return out


def _evaluar(pids, corte, disparadores, antes, canal, usuario, id_lote, errores):
    """Evalúa en línea y registra los dictámenes. Un fallo con un paciente queda anotado y el resto sigue."""
    evaluaciones = {}
    if pids and algoritmo_activo() == "rubrica":
        for pid in pids:
            try:
                reg = evaluar_y_guardar(pid, corte)
                if reg:
                    evaluaciones[pid] = reg
            except Exception as e:  # si la IA falla rigen las reglas: el lote no se cae
                errores.append({"etapa": "evaluacion", "id_paciente": pid, "error": f"{type(e).__name__}: {e}"})
    if not pids:
        return evaluaciones, []

    def lote_de(grupo):
        return bitacora.registrar_lote({p: disparadores[p] for p in grupo}, corte, {p: antes.get(p) for p in grupo},
                                       canal=canal, usuario=usuario, id_lote=id_lote,
                                       evaluaciones={p: evaluaciones[p] for p in grupo if p in evaluaciones} or None) or []
    try:
        return evaluaciones, list(lote_de(pids))
    except Exception:  # se reintenta paciente por paciente para aislar al que falla
        dictamenes = []
        for pid in pids:
            try:
                dictamenes += lote_de([pid])
            except Exception as e:
                errores.append({"etapa": "dictamen", "id_paciente": pid, "error": f"{type(e).__name__}: {e}"})
        return evaluaciones, dictamenes


def _clave(e):
    """Contenido que identifica un evento sin id del origen (mismo día, tipo, subtipo y motivo = el mismo evento)."""
    return (e.get("fecha_evento"), e.get("tipo_evento"), e.get("subtipo"), e.get("motivo") or "")


def _especialidad(pid, perfs, nuevos):
    return ((perfs.get(pid) or nuevos.get(pid) or {}).get("lista_espera") or {}).get("especialidad", "")


def _que(canal):
    return {"archivo": "un archivo", "s3": "la zona de carga", "api": "un sistema del hospital"}.get(canal, canal)


def _json(x):
    return json.dumps(x, ensure_ascii=False, default=str)


def _disparador(canal, id_lote, eventos, mediciones):
    """Qué gatilló la evaluación: el evento más grave (y más reciente) del lote, o la medición si no trae eventos."""
    d = {"tipo": DISPARADOR.get(canal, "evento"), "canal": canal, "id_lote": id_lote}
    if eventos:
        e = max(eventos, key=lambda x: (SEVERIDAD.get(x.get("severidad"), 0), x.get("fecha_evento") or ""))
        d.update(id_evento=e["id_evento"], eventos=[x["id_evento"] for x in eventos],
                 descripcion=f'{e["tipo_evento"]} · {e["subtipo"]} ({e["severidad"]})' +
                 (f" y {len(eventos) - 1} evento(s) más" if len(eventos) > 1 else ""))
    else:
        d["id_evento"] = None
    if mediciones:
        m = mediciones[-1]
        texto = f'medición {m["tipo_medicion"]} {m["valor"]}{" (fuera de rango)" if m.get("fuera_de_rango") else ""}'
        d["descripcion"] = d.get("descripcion") + f" · {len(mediciones)} medición(es)" if eventos else (
            texto + (f" y {len(mediciones) - 1} más" if len(mediciones) > 1 else ""))
    return d


def _resumen_dictamen(d):
    res = d.get("resultado") or {}
    return {"id_dictamen": d.get("id_dictamen"), "id_paciente": d.get("id_paciente"), "motor": d.get("motor"),
            **{k: res.get(k) for k in ("cambio", "categoria_antes", "categoria", "posicion_antes", "posicion")}}


# ---------- cola de evaluación (SQS) ----------
def _cliente(servicio):
    import boto3
    return boto3.client(servicio)


def _resumir_fila(fila):
    """La foto de antes viaja en el mensaje (el trabajador ya no puede reconstruirla): solo los campos simples y sin
    identificación (un mensaje SQS admite hasta 1 MiB; así queda en ~1 KB)."""
    if not fila:
        return None
    return {k: v for k, v in fila.items() if k not in NO_VIAJAN and (v is None or isinstance(v, (str, int, float, bool)))}


def _mensaje(pid, id_lote, canal, usuario, corte, disparador, antes):
    return {"id_paciente": pid, "id_lote": id_lote, "canal": canal, "usuario": usuario, "fecha_corte": corte.isoformat(),
            "disparador": disparador, "antes": _resumir_fila(antes)}


def _encolar(url, mensajes):
    """Envía de a 10 (máximo de SQS por llamada). Devuelve los pacientes que no se pudieron encolar."""
    sqs, fallidos = _cliente("sqs"), []
    for i in range(0, len(mensajes), 10):
        tanda = mensajes[i:i + 10]
        try:
            r = sqs.send_message_batch(QueueUrl=url, Entries=[{"Id": str(j), "MessageBody": _json(m)} for j, m in enumerate(tanda)])
            fallidos += [tanda[int(f["Id"])]["id_paciente"] for f in r.get("Failed", [])]
        except Exception as e:
            print(f"ingesta: no se pudo encolar: {type(e).__name__}: {e}")
            fallidos += [m["id_paciente"] for m in tanda]
    return fallidos


def cola_handler(event, context=None):
    """Lambda trabajadora: consume la cola de evaluación (SQS) y responde con fallas parciales: solo se reintentan los
    mensajes que fallaron (y tras varios intentos van a la cola de mensajes fallidos)."""
    datos.nueva_solicitud()
    fallas = []
    for rec in (event or {}).get("Records", []):
        try:
            evaluar_mensaje(json.loads(rec["body"]))
        except Exception as e:
            print(f"cola: mensaje {rec.get('messageId')}: {type(e).__name__}: {e}")
            fallas.append({"itemIdentifier": rec.get("messageId")})
    return {"batchItemFailures": fallas}


def evaluar_mensaje(m):
    """Evalúa a un paciente y registra su dictamen. Idempotente: si el lote ya dejó constancia de este paciente, no repite."""
    pid, id_lote = m["id_paciente"], m["id_lote"]
    sk = f"evaluado#{id_lote}#{pid}"
    if any(i["sk"] == sk for i in datos.globales(LOTES, sk)):
        return None
    corte = date.fromisoformat(m["fecha_corte"])
    evaluacion = None
    if algoritmo_activo() == "rubrica":
        perfil = datos.perfil_de(pid)  # el trabajador no necesita la lista entera: lee solo la partición del paciente
        if perfil is None:
            raise ValueError(f"paciente {pid} no existe")
        evaluacion = evaluar_y_guardar(pid, corte, perfs={pid: perfil})
    hechos = bitacora.registrar_lote({pid: m["disparador"]}, corte, {pid: m.get("antes")}, canal=m.get("canal"),
                                     usuario=m.get("usuario"), id_lote=id_lote,
                                     evaluaciones={pid: evaluacion} if evaluacion else None) or []
    datos.guardar({"id_paciente": LOTES, "sk": sk, "evaluado": _json(
        {"id_lote": id_lote, "id_paciente": pid, "fecha": datos.ahora(), "evaluacion": bool(evaluacion),
         "id_dictamen": hechos[0].get("id_dictamen") if hechos else None})}, si_no_existe=True)
    return hechos


# ---------- zona de carga S3 ----------
def s3_handler(event, context=None):
    """Lambda de la zona de carga: por cada objeto nuevo bajo PREFIJO_ENTRADA lo lee (importar.procesar), lo registra con
    canal "s3" y deja procesados/<nombre>.resultado.json (o errores/<nombre>.error.json si no se pudo leer)."""
    datos.nueva_solicitud()
    prefijo = os.environ.get("PREFIJO_ENTRADA", "entrada/")
    s3, hechos = _cliente("s3"), []
    for rec in (event or {}).get("Records", []):
        bucket, key = rec["s3"]["bucket"]["name"], unquote_plus(rec["s3"]["object"]["key"])
        if key.startswith(prefijo) and not key.endswith("/"):
            hechos.append(_procesar_objeto(s3, bucket, key, prefijo))
    return {"procesados": hechos}


class ArchivoIlegible(ValueError):
    pass


def _procesar_objeto(s3, bucket, key, prefijo):
    rel = key[len(prefijo):]
    nombre = rel.rsplit("/", 1)[-1]
    origen = rel.split("/", 1)[0] if "/" in rel else "zona_de_carga"   # entrada/<sistema>/archivo.csv → origen = sistema
    contenido = s3.get_object(Bucket=bucket, Key=key)["Body"].read()  # si S3 falla, la Lambda se reintenta sola
    try:
        informe, tablas = importar.procesar([{"nombre": nombre, "contenido_base64": base64.b64encode(contenido).decode()}])
        if not any(i.get("tabla") for i in informe):
            raise ArchivoIlegible("; ".join(i.get("error") or "" for i in informe) or "el archivo no trae filas")
        r = registrar(tablas, canal="s3", usuario="zona de carga", origen=origen, archivo=key, evaluar="cola",
                      rechazados=rechazos_de_informe(informe))
    except (ArchivoIlegible, datos.EntradaInvalida) as e:
        # Errores del archivo (no del sistema): no sirve reintentar. Queda la constancia y el aviso.
        err = {"archivo": key, "fecha": datos.ahora(), "error": str(e)}
        s3.put_object(Bucket=bucket, Key=f"errores/{rel}.error.json", Body=_json(err).encode("utf-8"), ContentType="application/json")
        _avisar(key, {"error": "no se pudo leer el archivo"})
        return {"archivo": key, "estado": "error", "resultado": f"errores/{rel}.error.json"}
    resultado = {**{k: v for k, v in r.items() if not k.startswith("_")}, "archivo": key, "informe": informe}
    s3.put_object(Bucket=bucket, Key=f"procesados/{rel}.resultado.json", Body=_json(resultado).encode("utf-8"),
                  ContentType="application/json")
    if r["rechazados"] or r["errores"]:
        _avisar(key, {k: r[k] for k in ("id_lote", "recibidos", "registrados", "duplicados", "fuera_de_lista")} |
                {"rechazados": len(r["rechazados"]), "errores": len(r["errores"])})
    return {"archivo": key, "estado": "procesado", "id_lote": r["id_lote"], "resultado": f"procesados/{rel}.resultado.json"}


def _avisar(archivo, conteos):
    """Aviso al equipo (SNS) sin datos de pacientes: solo el archivo y los conteos."""
    tema = os.environ.get("TEMA_ALERTAS_ARN", "").strip()
    if not tema:
        return
    try:
        _cliente("sns").publish(TopicArn=tema, Subject="Ingesta: archivo con problemas",
                                Message=_json({"archivo": archivo, **conteos}))
    except Exception as e:  # el aviso no puede botar la carga
        print(f"ingesta: no se pudo avisar: {type(e).__name__}: {e}")


def rechazos_de_informe(informe):
    """Filas que importar.procesar no pudo convertir, en el formato de `rechazados` (las primeras 15 por hoja traen
    su motivo; el resto se cuenta)."""
    out = []
    for h in informe:
        tabla = {"eventos_clinicos": "eventos"}.get(h.get("tabla"), h.get("tabla"))
        if tabla not in TABLAS:
            continue
        for e in h.get("errores", []):
            out.append({"tabla": tabla, "indice": e["fila"], "archivo": h["archivo"], "motivo": e["motivo"]})
        for _ in range((h.get("n_errores") or 0) - len(h.get("errores", []))):
            out.append({"tabla": tabla, "indice": None, "archivo": h["archivo"], "motivo": "fila inválida (ver el informe del archivo)"})
    return out


# ---------- API ----------
def rutear(method, partes, qs, body, cabeceras=None):
    """POST /ingesta/eventos · GET /ingesta/lotes · GET /ingesta/lotes/{id_lote}. None si la ruta no es de este módulo."""
    if not partes or partes[0] != "ingesta":
        return None
    if method == "POST" and partes == ["ingesta", "eventos"]:
        return post_eventos(body, cabeceras or {})
    if method == "GET" and partes == ["ingesta", "lotes"]:
        try:
            limite = max(1, min(200, int((qs or {}).get("limite") or 20)))
        except ValueError:
            raise datos.EntradaInvalida("limite debe ser un número")
        return 200, {"lotes": lotes(limite)}
    if method == "GET" and len(partes) == 3 and partes[:2] == ["ingesta", "lotes"]:
        lt = lote(partes[2])
        return (200, lt) if lt else (404, {"error": "lote no existe"})
    return None


def post_eventos(body, cabeceras):
    """API para sistemas del hospital: {origen, eventos[], mediciones[]?, citaciones[]?} + cabecera Idempotency-Key opcional.
    200 procesado · 202 evaluación en cola · 400 cuerpo sin la forma esperada (las filas inválidas van en `rechazados`)."""
    clave = str(cabeceras.get("idempotency-key") or "").strip()
    huella = hashlib.sha256(_json(body).encode("utf-8")).hexdigest()[:16] if clave else None
    if clave:
        if len(clave) > 200:
            return 400, {"error": "Idempotency-Key admite hasta 200 caracteres"}
        previo = _idem(clave)
        if previo:
            if previo["huella"] != huella:
                return 409, {"error": "esa Idempotency-Key ya se usó con otro contenido", "codigo": "idempotencia"}
            return previo["status"], previo["respuesta"]
    try:
        status, out = _procesar_api(body)
    except CuerpoInvalido as e:
        return 400, {"error": str(e)}
    if clave:
        guardada = out if len(_json(out)) < 300_000 else {**out, "rechazados": out["rechazados"][:200], "rechazados_recortados": True}
        datos.guardar({"id_paciente": IDEM, "sk": "ingesta#" + clave, "expira": int(time.time()) + IDEM_HORAS * 3600,
                       "idem": _json({"huella": huella, "status": status, "respuesta": guardada})}, si_no_existe=True)
    return status, out


def _idem(clave):
    sk = "ingesta#" + clave
    for it in datos.globales(IDEM, sk):
        try:
            vigente = it.get("expira") is None or float(it["expira"]) >= time.time()
        except (TypeError, ValueError):
            vigente = False
        if it["sk"] == sk and vigente:
            return json.loads(it["idem"])
    return None


def _procesar_api(body):
    if not isinstance(body, dict):
        raise CuerpoInvalido("el cuerpo debe ser un objeto JSON {origen, eventos, mediciones?, citaciones?}")
    origen = str(body.get("origen") or "").strip()
    if not origen:
        raise CuerpoInvalido("falta 'origen': el sistema que envía (p. ej. 'urgencia-hlf')")
    listas = {t: body.get(t) for t in ("eventos", "mediciones", "citaciones")}
    if any(v is not None and not isinstance(v, list) for v in listas.values()):
        raise CuerpoInvalido("eventos, mediciones y citaciones deben ser listas")
    n = sum(len(v or []) for v in listas.values())
    if not n:
        raise CuerpoInvalido("no trae eventos, mediciones ni citaciones")
    if n > MAX_FILAS:
        raise CuerpoInvalido(f"máximo {MAX_FILAS} filas por solicitud (llegaron {n}): divídalas en varias solicitudes")
    corte = datos.fecha_de(body)
    carga, rech = {}, []
    for t in listas:
        filas = [{**r, "id_paciente": r["rut"]} if isinstance(r, dict) and not r.get("id_paciente") and r.get("rut") else r
                 for r in listas[t] or []]
        validas, malas = importar.filas_de_json(filas, DE_IMPORTAR.get(t, t))
        carga[t] = [{**reg, "_indice": i} for i, reg in validas]
        rech += [{"tabla": t, "indice": i, "motivo": m} for i, m in malas]
    r = registrar(carga, canal="api", usuario=str(body.get("usuario") or origen), origen=origen, corte=corte,
                  rechazados=rech, evaluar="cola" if body.get("evaluar") == "cola" else "ahora")
    return (202 if r["evaluacion"] == "en_cola" else 200), r


# ---------- lotes ----------
def _cierres():
    out = {}
    for it in datos.globales(LOTES, "cierre#"):
        c = json.loads(it["cierre"])
        out[c["id_lote"]] = c
    return out


def lotes(limite=20):
    """Los últimos lotes (más reciente primero), sin el detalle de filas ni pacientes."""
    cierres = _cierres()
    out = []
    for it in reversed(datos.globales(LOTES, "lote#")):
        lt = json.loads(it["lote"])
        c = cierres.get(lt["id_lote"]) or {}
        out.append({**{k: v for k, v in lt.items() if k not in ("rechazados", "pacientes_afectados", "con_informacion_clinica", "por_tabla")},
                    "pacientes_afectados": len(lt.get("pacientes_afectados") or []),
                    "estado": c.get("estado", lt.get("estado")), "evaluacion": c.get("evaluacion"),
                    "dictamenes": len(c.get("dictamenes") or []), "errores": len(c.get("errores") or [])})
        if len(out) >= limite:
            break
    return out


def lote(id_lote):
    it = next((i for i in datos.globales(LOTES, "lote#") if i["sk"].endswith("#" + id_lote)), None)
    if not it:
        return None
    lt = json.loads(it["lote"])
    c = _cierres().get(id_lote) or {}
    evaluados = [json.loads(i["evaluado"]) for i in datos.globales(LOTES, f"evaluado#{id_lote}#")]
    return {**lt, "estado": c.get("estado", lt.get("estado")), "cierre": c or None, "evaluados_por_la_cola": evaluados}
