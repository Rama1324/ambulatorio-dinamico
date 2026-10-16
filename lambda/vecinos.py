"""Por qué un paciente va antes que el de abajo y después que el de arriba.

Recorre los mismos criterios del orden de la lista (Ord. MINSAL 536/2025, puntaje.clave_orden) y explica el PRIMERO en
que los dos pacientes se diferencian, con los datos de cada uno. Si el orden lo puso una persona (ajuste manual), lo dice."""
import puntaje

AGUDEZA = {3: "UCI o triage C1/ESI 1", 2: "hospitalización, triage C2/ESI 2 o descompensación grave", 1: "evento moderado", 0: "sin evento agudo"}
NIVEL_LETALIDAD = {1: "muy alta", 2: "alta", 3: "moderada", 4: "baja"}


def _letalidad(p):
    n = p.get("letalidad", 9)
    if n == 9:
        return "sin descompensación con mortalidad conocida"
    cifra = puntaje.LETALIDAD_DX.get(p.get("diagnostico_cie10"), (None, ""))[1].split(" (")[0]
    return f"letalidad {NIVEL_LETALIDAD.get(n, n)}" + (f" ({cifra})" if cifra else "")


def _prioridad(p):
    """La prioridad y de dónde sale: la regla que la subió o, si no, la que asignó el especialista en la SIC."""
    r = next((x for x in p.get("razones") or [] if x.get("factor") in ("urgencia", "combinacion", "criterio_registro", "oncologico", "tabla_oficial")
              and "→" in str(x.get("valor"))), None)
    origen = str(r["valor"]).split(" · ")[0].replace(" (no supera la actual)", "")[:140] if r else "asignada por el especialista en la interconsulta"
    return f'prioridad {p["categoria"]} ({origen})'


def _grave(p):
    f = (p.get("evaluacion") or {}).get("fecha_evento")
    return "descompensación grave" + (f" el {f[8:10]}-{f[5:7]}-{f[:4]}" if f else "")


# (pregunta, valor que ordena: menor va primero, cómo se describe en cada paciente)
CRITERIOS = [
    ("prioridad clínica", lambda p: -puntaje.ORDEN_CAT[p["categoria"]], _prioridad),
    ("urgencia: derivar hoy", lambda p: not p.get("urgencia_hoy"), lambda p: "cumple un criterio de «derivar hoy a urgencia»" if p.get("urgencia_hoy") else "sin criterio de urgencia"),
    ("descompensación grave reciente", lambda p: not p.get("riesgo_vital"), lambda p: _grave(p) if p.get("riesgo_vital") else "sin descompensación grave reciente"),
    ("mortalidad de lo que tiene", lambda p: p.get("letalidad", 9), _letalidad),
    ("gravedad del último evento", lambda p: -(p.get("agudeza") or 0), lambda p: AGUDEZA.get(p.get("agudeza") or 0, "")),
    ("enfermedad descompensada", lambda p: p.get("estado_clinico") != "descompensado", lambda p: "descompensado" if p.get("estado_clinico") == "descompensado" else "estable"),
    ("grupo de especial protección", lambda p: not p.get("grupo_proteccion"), lambda p: p.get("grupo_proteccion") or "sin grupo de protección"),
    ("más de 1 año esperando", lambda p: not p.get("antiguedad_mayor_1_anio"), lambda p: "más de 1 año esperando" if p.get("antiguedad_mayor_1_anio") else "menos de 1 año esperando"),
    ("tiempo de espera", lambda p: -p["dias_espera"], lambda p: f'{p["dias_espera"]} días esperando'),
]
CLINICOS = {c[0] for c in CRITERIOS[:6]}  # los que miden gravedad; los demás solo ordenan a pacientes igual de graves
LACE = ("índice LACE (desempate experimental)", lambda p: -((p.get("lace") or {}).get("total") or 0), lambda p: f'LACE {(p.get("lace") or {}).get("total", 0)}')


def por_que_antes(a, b, con_lace=False):
    """Explica por qué `a` va antes que `b` en la lista: {criterio, este, otro, texto}."""
    if a.get("ajuste_manual") or b.get("ajuste_manual"):
        quien = a if a.get("ajuste_manual") else b
        aj = quien["ajuste_manual"]
        return {"criterio": "ajuste manual", "texto": f'el equipo clínico ajustó la posición de {quien["nombre_fantasia"]}: '
                f'{aj.get("motivo_texto") or aj.get("motivo")} ({aj.get("usuario", "equipo clínico")})'}
    for nombre, valor, describe in (CRITERIOS[:-1] + [LACE, CRITERIOS[-1]] if con_lace else CRITERIOS):
        va, vb = valor(a), valor(b)
        if va != vb:
            if va > vb:  # el orden no lo explica este criterio (no debería pasar): no inventar una razón
                break
            return {"criterio": nombre, "este": describe(a), "otro": describe(b), "clinico": nombre in CLINICOS}
    else:
        return {"criterio": "empate", "texto": "coinciden en todos los criterios clínicos y en el tiempo de espera: desempata el orden de llegada"}
    return {"criterio": "orden del equipo", "texto": "el orden lo fijó una decisión del equipo clínico"}


def agregar(pacientes, con_lace=False):
    """Agrega a cada paciente `comparacion` = {arriba, abajo} con el vecino y la razón del orden."""
    vecino = lambda p: {"id_paciente": p["id_paciente"], "nombre_fantasia": p["nombre_fantasia"], "posicion": p["posicion"],
                        "diagnostico_texto": p["diagnostico_texto"], "especialidad": p["especialidad"], "categoria": p["categoria"]}
    for i, p in enumerate(pacientes):
        p["comparacion"] = {
            "arriba": {**vecino(pacientes[i - 1]), **por_que_antes(pacientes[i - 1], p, con_lace)} if i > 0 else None,
            "abajo": {**vecino(pacientes[i + 1]), **por_que_antes(p, pacientes[i + 1], con_lace)} if i + 1 < len(pacientes) else None,
        }
