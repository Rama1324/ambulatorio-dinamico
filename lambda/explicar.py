"""Explicación de la prioridad con Amazon Bedrock (Converse API).

El LLM NO decide la prioridad: solo redacta, en lenguaje clínico claro, las 'razones'
que ya calculó puntaje.py. Si Bedrock falla, devuelve una explicación por plantilla
para que el demo nunca se caiga.
Variables de entorno: MODEL_ID (obligatoria para usar Bedrock), BEDROCK_REGION (opcional).
"""
import json
import os

PROMPT_SISTEMA = """Eres un asistente de gestión de listas de espera de un hospital público chileno.
Redactas para un gestor de salud y el equipo clínico.

Reglas estrictas:
- Usa SOLO los datos entregados. No inventes síntomas, exámenes, fechas ni diagnósticos.
- No decides la prioridad ni recomiendas tratamientos: explicas por qué el sistema propone esa categoría.
- Máximo 3 frases cortas, en español de Chile, sin markdown ni viñetas.
- Menciona el evento que cambió la categoría (con su fecha) y la fuente oficial que se aplicó, si las hay.
- Termina siempre con: "Propuesta sujeta a validación clínica."
"""


def _datos(p):
    return {
        "edad": p.get("edad"),
        "especialidad": p.get("especialidad"),
        "diagnostico": f'{p.get("diagnostico_cie10")} {p.get("diagnostico_texto")}',
        "prioridad_inicial": p.get("prioridad_inicial"),
        "categoria": p.get("categoria"),
        "estado_clinico": p.get("estado_clinico"),
        "posicion_actual": p.get("posicion"),
        "posicion_hace_14_dias": p.get("posicion_anterior"),
        "riesgo_inasistencia": p.get("riesgo_inasistencia"),
        "evaluacion_descompensacion": p.get("evaluacion"),
        "razones": p.get("razones"),
    }


def plantilla(p):
    rz = {r["factor"]: r for r in p.get("razones", [])}
    partes = [f'Prioridad {p.get("categoria")} para {p.get("diagnostico_texto")} '
              f'(inicial {p.get("prioridad_inicial")}).']
    if "evento" in rz:
        partes.append(f'Evento posterior a la interconsulta: {rz["evento"]["valor"]}.')
    if "tabla_oficial" in rz:
        partes.append(f'Según {rz["tabla_oficial"]["fuente"]}: {rz["tabla_oficial"]["valor"]}.')
    if "riesgo_vital" in rz:
        partes.append(f'{rz["riesgo_vital"]["valor"]}.')
    if p.get("antiguedad_mayor_1_anio"):
        partes.append("Lleva más de 1 año en lista (criterio MINSAL).")
    if "ges" in rz and (p.get("ges") or {}).get("vencida"):
        partes.append(f'{rz["ges"]["valor"]}.')
    if p.get("riesgo_inasistencia"):
        partes.append("Tiene 2 inasistencias consecutivas: confirmar asistencia por teléfono.")
    return " ".join(partes) + " Propuesta sujeta a validación clínica."


def explicar(paciente):
    """Devuelve (texto, fuente) donde fuente es 'bedrock' o 'plantilla'."""
    model_id = os.environ.get("MODEL_ID")
    if not model_id:
        return plantilla(paciente), "plantilla"
    try:
        import boto3
        kw = {"region_name": os.environ["BEDROCK_REGION"]} if os.environ.get("BEDROCK_REGION") else {}
        from aws_config import CORTA
        client = boto3.client("bedrock-runtime", config=CORTA, **kw)
        r = client.converse(
            modelId=model_id,
            system=[{"text": PROMPT_SISTEMA}],
            messages=[{"role": "user", "content": [{"text": "Datos del paciente:\n" + json.dumps(_datos(paciente), ensure_ascii=False)}]}],
            inferenceConfig={"maxTokens": 1200},  # holgado: el razonamiento también gasta tokens. Sin 'temperature' (no la aceptan)
        )
        texto = "".join(b.get("text", "") for b in r["output"]["message"]["content"]).strip()  # puede venir un bloque de razonamiento antes
        if r.get("stopReason") == "max_tokens" and "." in texto:
            texto = texto[:texto.rindex(".") + 1]  # cortado: dejar solo oraciones completas
        if "validación clínica" not in texto:
            texto += " Propuesta sujeta a validación clínica."
        return texto, "bedrock"
    except Exception as e:
        print(f"Bedrock falló, uso plantilla: {e}")
        return plantilla(paciente), "plantilla"


# ---------------------------------------------------------------------------------------------------------------------
# Resumen para el equipo: distinto del "por qué está en el N°" (que ya muestra la ficha). Cuenta la historia del paciente
# en lenguaje simple y dice qué hacer. La IA solo redacta con los datos entregados; si falla, se arma con una plantilla.
MEDICION = {"presion_sistolica": "presión sistólica", "PHQ9": "PHQ-9 (cuestionario de depresión)",
            "HbA1c": "HbA1c (azúcar promedio de 3 meses)", "saturacion_o2": "saturación de oxígeno", "peso": "peso"}
TIPO = {"visita_urgencia": "consulta en urgencia", "hospitalizacion": "hospitalización", "examen_alterado": "examen alterado",
        "cambio_farmaco": "cambio de fármaco", "control_aps": "control en APS", "hallazgo_oncologico": "hallazgo oncológico",
        "criterio_clinico": "criterio clínico en un informe", "combinacion_riesgo": "combinación de riesgo en un informe"}

PROMPT_RESUMEN = """Eres un asistente de un hospital público chileno. Escribes un resumen de un paciente en lista de espera
para el equipo que gestiona la lista (enfermería, secretaría, médicos). Debe entenderlo alguien sin formación médica.

Reglas estrictas:
- Usa SOLO los datos entregados. No inventes síntomas, exámenes, fechas, diagnósticos ni cifras.
- No decides la prioridad ni indicas tratamientos. No repitas la lista de reglas: explica la historia y qué hacer.
- Español de Chile, frases cortas, sin siglas sin explicar (si usas una, explícala entre paréntesis la primera vez).
- Fechas en formato DD-MM-AAAA. No menciones nombre, RUT, comuna ni previsión.
- Responde SOLO un objeto JSON con estas claves:
  "en_pocas_palabras": 1 o 2 frases: quién es (edad, qué espera y desde cuándo) y cómo está hoy.
  "mientras_esperaba": lista de 1 a 5 frases, en orden de fecha, con lo que le pasó mientras esperaba, en palabras simples.
  "por_que_importa": 1 o 2 frases con qué le puede pasar si sigue esperando, usando SOLO el campo "riesgo" de las razones (con su cifra y fuente). Si no hay riesgo en los datos, dilo.
  "que_hacer": lista de 1 a 4 acciones concretas para el equipo, sacadas de los datos (próxima acción, contactar hoy, plazo, GES, inasistencias, revisión del especialista).
  "que_falta": lista de 0 a 3 datos que faltan o están por confirmar.
"""


def _datos_resumen(d, corte):
    p, dp = d["paciente"], d.get("datos_paciente") or {}
    evs = sorted(d.get("eventos_clinicos", []), key=lambda e: e["fecha_evento"])[-10:]
    meds = sorted(d.get("mediciones", []), key=lambda m: m["fecha_medicion"])[-6:]
    citas = d.get("citaciones", [])
    return {  # sin nombre, RUT, comuna ni previsión (Ley 21.719: minimización; y no son criterios clínicos)
        "fecha_de_hoy": corte.isoformat(), "edad": p.get("edad"), "sexo": p.get("sexo"), "especialidad": p.get("especialidad"),
        "diagnostico": p.get("diagnostico_texto"), "fecha_ingreso_lista": p.get("fecha_ingreso_lista"), "dias_esperando": p.get("dias_espera"),
        "prioridad_inicial": p.get("prioridad_inicial"), "prioridad_actual": p.get("categoria"),
        "puesto": p.get("posicion"), "estado_clinico": p.get("estado_clinico"),
        "plazo_referencia_dias": p.get("plazo_dias"), "plazo_superado": p.get("plazo_vencido"),
        "contactar_hoy": p.get("contactar_hoy"), "derivar_hoy_a_urgencia": p.get("urgencia_hoy"),
        "inasistencias_consecutivas": p.get("riesgo_inasistencia"), "ges": p.get("ges"),
        "comorbilidades": p.get("comorbilidades") or dp.get("comorbilidades"),
        "gestion": {k: (p.get("gestion") or {}).get(k) for k in ("texto", "proxima_accion", "responsable", "motivo_texto")},
        "revision_especialista": p.get("estado_revision"), "aviso_descompensacion": p.get("evaluacion"),
        "eventos": [{"fecha": e["fecha_evento"], "tipo": TIPO.get(e["tipo_evento"], e["tipo_evento"]), "detalle": e.get("subtipo"),
                     "gravedad": e.get("severidad"), "motivo": e.get("motivo"), "relacionado_con_su_diagnostico": e.get("relacionado")} for e in evs],
        "mediciones": [{"fecha": m["fecha_medicion"], "tipo": m["tipo_medicion"], "valor": m.get("valor"), "unidad": m.get("unidad"),
                        "fuera_de_rango": m.get("fuera_de_rango")} for m in meds],
        "citas": {"asistio": sum(c.get("estado_cita") == "asistio" for c in citas), "no_asistio": sum(c.get("estado_cita") == "no_asistio" for c in citas)},
        "razones": [{"factor": r.get("factor"), "valor": r.get("valor"), "riesgo": r.get("riesgo"), "fuente": r.get("fuente")}
                    for r in p.get("razones", []) if r.get("factor") != "lace"],
    }


def _f(iso):
    return "-".join(reversed(iso[:10].split("-"))) if iso else ""


def resumen_plantilla(d, corte):
    """El mismo resumen sin IA (si Bedrock falla o no está configurado)."""
    p = d["paciente"]
    rz = {r["factor"]: r for r in p.get("razones", [])}
    sube = p["categoria"] != p["prioridad_inicial"]
    pocas = (f'{p.get("edad")} años, espera consulta de {p["especialidad"]} por {p["diagnostico_texto"].lower()} desde el '
             f'{_f(p["fecha_ingreso_lista"])} ({p["dias_espera"]} días). Hoy tiene prioridad {p["categoria"]}'
             + (f' (entró como {p["prioridad_inicial"]})' if sube else "")
             + (" y su enfermedad está descompensada." if p.get("estado_clinico") == "descompensado" else "."))
    hechos = []  # (fecha, frase), en orden de fecha: eventos y mediciones fuera de rango desde que entró a la lista
    for e in d.get("eventos_clinicos", []):
        if e["fecha_evento"] >= p["fecha_ingreso_lista"]:
            grav = f', gravedad {e["severidad"]}' if e.get("severidad") else ""
            hechos.append((e["fecha_evento"], f'{_f(e["fecha_evento"])}: {TIPO.get(e["tipo_evento"], e["tipo_evento"])} ({e.get("subtipo")}{grav})'
                           + (f', por {e["motivo"]}' if e.get("motivo") else "") + "."))
    for m in [m for m in d.get("mediciones", []) if m.get("fuera_de_rango") and m["fecha_medicion"] >= p["fecha_ingreso_lista"]][-2:]:
        nombre = MEDICION.get(m["tipo_medicion"], m["tipo_medicion"].replace("_", " "))
        hechos.append((m["fecha_medicion"], f'{_f(m["fecha_medicion"])}: {nombre} {m.get("valor")} {m.get("unidad") or ""}'.rstrip() + " (fuera de rango)."))
    hechos = [t for _, t in sorted(hechos)][-5:]
    if p.get("riesgo_inasistencia"):
        hechos.append("Faltó a 2 citas seguidas.")
    if not hechos:
        hechos.append("No hay eventos registrados desde que entró a la lista.")
    # el riesgo de su enfermedad primero; el de esperar más del plazo, solo en su primera frase (la general)
    riesgos = list(dict.fromkeys(r["riesgo"] if r.get("factor") != "plazo" else
                                 "Esperar más que el plazo de referencia se asocia a más muertes en lista de espera (OR 1,66; Sobolev 2006, PMID 16799363)."
                                 for r in p.get("razones", []) if r.get("riesgo")))[:2]
    importa = " ".join(riesgos) if riesgos else "No hay registrado un evento que aumente su riesgo mientras espera."
    hacer = []
    if p.get("urgencia_hoy"):
        hacer.append("Derivar hoy a urgencia: cumple un criterio que no permite esperar una cita.")
    elif p.get("contactar_hoy"):
        hacer.append("Llamarlo hoy y ofrecerle una hora con prioridad.")
    if (p.get("gestion") or {}).get("accion_asignada"):  # la que anotó el equipo (no la sugerida por el sistema)
        hacer.append(f'Próxima acción anotada por el equipo: {p["gestion"]["proxima_accion"]}.')
    if p.get("plazo_vencido"):
        hacer.append(f'Ya superó el plazo de referencia de su prioridad ({p.get("plazo_dias")} días): buscar cupo.')
    if (p.get("ges") or {}).get("vencida"):
        hacer.append("Verificar el plazo de la garantía GES con la fecha real de derivación.")
    if p.get("riesgo_inasistencia"):
        hacer.append("Confirmar por teléfono que podrá asistir antes de asignar la hora.")
    falta = []
    if p.get("estado_clinico") == "descompensado":
        falta.append("No hay registro de estabilización después del evento.")
    if p.get("riesgo_vital") and (p.get("evaluacion") or {}).get("estado") == "pendiente":
        falta.append("El especialista aún no revisa la prioridad después del evento.")
    if "tabla_oficial" in rz and rz["tabla_oficial"].get("sin_regla"):
        falta.append("La tabla del hospital no define qué prioridad corresponde a esta enfermedad descompensada.")
    return {"en_pocas_palabras": pocas, "mientras_esperaba": hechos, "por_que_importa": importa,
            "que_hacer": hacer[:4] or ["Citar según su turno en la lista."], "que_falta": falta[:3]}


def _limpia(r):
    """Valida la respuesta de la IA: claves conocidas, textos y listas cortas."""
    lista = lambda v, n: [str(x)[:400] for x in (v if isinstance(v, list) else [v] if v else [])][:n]
    out = {"en_pocas_palabras": str(r.get("en_pocas_palabras") or "")[:500], "mientras_esperaba": lista(r.get("mientras_esperaba"), 5),
           "por_que_importa": str(r.get("por_que_importa") or "")[:600], "que_hacer": lista(r.get("que_hacer"), 4),
           "que_falta": lista(r.get("que_falta"), 3)}
    if not out["en_pocas_palabras"] or not out["que_hacer"]:
        raise ValueError("respuesta incompleta")
    return out


def resumen_equipo(d, corte):
    """Devuelve (secciones, fuente). fuente: 'bedrock' o 'plantilla'."""
    model_id = os.environ.get("MODEL_ID")
    if not model_id:
        return resumen_plantilla(d, corte), "plantilla"
    try:
        import boto3
        from botocore.config import Config
        kw = {"region_name": os.environ["BEDROCK_REGION"]} if os.environ.get("BEDROCK_REGION") else {}
        # ~10 s sin razonamiento extendido (con razonamiento eran ~20 s); 20 s de margen bajo los 29 s de API Gateway
        cfg = Config(connect_timeout=3, read_timeout=20, retries={"max_attempts": 1})
        r = boto3.client("bedrock-runtime", config=cfg, **kw).converse(
            modelId=model_id, system=[{"text": PROMPT_RESUMEN}],
            messages=[{"role": "user", "content": [{"text": "Datos del paciente:\n" + json.dumps(_datos_resumen(d, corte), ensure_ascii=False, default=str)}]}],
            inferenceConfig={"maxTokens": 1500}, additionalModelRequestFields={"thinking": {"type": "disabled"}})
        crudo = "".join(b.get("text", "") for b in r["output"]["message"]["content"])
        return _limpia(json.loads(crudo[crudo.find("{"): crudo.rfind("}") + 1])), "bedrock"
    except Exception as e:
        print(f"Bedrock falló en el resumen, uso plantilla: {e}")
        return resumen_plantilla(d, corte), "plantilla"
