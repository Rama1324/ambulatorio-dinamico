"""Vocabularios cerrados del equipo clínico (contacto, decisión, ajuste, gestión) y el catálogo que usa el front."""
import puntaje
from datos import perfiles, perfiles_combinados


TIPOS_EVENTO = {"cambio_farmaco", "control_aps", "examen_alterado", "hospitalizacion", "visita_urgencia", "hallazgo_oncologico"}  # criterio_clinico: solo lo registra la IA
# Contacto = lo que hace quien llama (enfermería/administrativo). No es una decisión clínica.
RESULTADOS_CONTACTO = {
    "citado": "Contactado: citado (sobrecupo o cupo liberado)",
    "derivado_urgencia": "Contactado: derivado a urgencia",
    "contactado": "Contactado e informado: queda pendiente la decisión médica",
    "no_contesta": "No contesta: reintentar",
}
# Decisión clínica = la toma un profesional identificado; cierra la alerta de descompensación.
DECISIONES = {
    "citar_prioritario": "Citar en forma prioritaria",
    "derivar_urgencia": "Derivar a urgencia",
    "adelantar_control": "Adelantar control o teleconsulta",
    "mantener": "Se mantiene en lista con su prioridad actual",
}


AJUSTE_MANUAL = {  # mover a un paciente en la lista exige un motivo previo y explicado
    "criterio_clinico": "Criterio clínico del especialista",
    "informacion_no_registrada": "Información clínica que no está en el registro",
    "comite": "Decisión de comité o jefatura",
    "error_registro": "Corrección de un error de registro",
    "otro": "Otro motivo (explicado)",
}
MIN_EXPLICACION = 20


ESTADOS_GESTION = {
    "pendiente_revision": ("Decisión del especialista", "Ver si corresponde cambiar la prioridad"),
    "pendiente_contacto": ("Pendiente de contacto", "Volver a llamar"),
    "pendiente_cita": ("Pendiente de cita", "Buscar cupo y citar"),
    "cita_reservada": ("Cita reservada", "Confirmar asistencia"),
}
MOTIVOS_PENDIENTE = {"falta_cupo": "Falta de cupo", "contacto": "No se ha podido contactar", "antecedentes": "Faltan antecedentes o exámenes",
                     "revision": "Espera revisión del especialista", "paciente": "Decisión o disponibilidad del paciente",
                     "revision_humana": "El paciente pidió que una persona revise su prioridad (Ley 21.719, art. 8 bis)", "otro": "Otro (documentado)"}


def _cobertura(cie, textos_registro):
    """Qué criterios aplican a este diagnóstico, para mostrarlo al ingresar: equivalente del registro y qué pasa si empeora."""
    base = puntaje.cie_base(cie)
    fila, eq = puntaje.fila_descompensado(cie)
    return {"equivalente": f"{base} {textos_registro.get(base, '')}".strip() if base != cie else None,
            "criterios_clinicos": base in puntaje.criterios_registro(),
            "si_empeora": f'"{fila[0]}" → prioridad {fila[1]} (pág. {fila[2]})' + (" · equivalencia a validar" if eq else "") if fila else None}


def catalogo():
    """Diagnósticos de la lista (especialidad, sub-especialidad, CIE-10, texto), tal como vienen en el registro. Solo se
    ingresan pacientes de las especialidades y diagnósticos que tiene el registro del hospital."""
    vistos = {}
    for p in perfiles_combinados()[0].values():
        le = p["lista_espera"]
        if le["diagnostico_cie10"] in puntaje.tabla_hlf():
            continue  # paciente ingresado con una fila de la tabla: esa fila ya está abajo (no duplicar)
        vistos[le["diagnostico_cie10"]] = {"especialidad": le["especialidad"], "sub_especialidad": le["sub_especialidad"],
                                          "diagnostico_cie10": le["diagnostico_cie10"], "diagnostico_texto": le["diagnostico_texto"]}
    registro = sorted(vistos.values(), key=lambda d: (d["especialidad"], d["diagnostico_cie10"]))
    # más todos los diagnósticos y síntomas de la tabla oficial del HLF para esas mismas especialidades (código HLF-…)
    tabla = [{"especialidad": x["especialidad"], "sub_especialidad": x["especialidad"], "diagnostico_cie10": x["codigo"],
              "diagnostico_texto": x["texto"], "prioridad_tabla": x["prioridad"], "pagina": x["pagina"], "origen": "tabla_hlf"}
             for x in puntaje.tabla_hlf().values() if x["especialidad"] in {d["especialidad"] for d in registro}]
    for d in registro + tabla:
        d.update(_cobertura(d["diagnostico_cie10"], {x["diagnostico_cie10"]: x["diagnostico_texto"] for x in registro}))
    return {"diagnosticos": registro + tabla,
            "comunas": sorted({p["paciente"]["comuna"] for p in perfiles().values()}),
            "previsiones": sorted({p["paciente"]["prevision"] for p in perfiles().values()}),
            "origenes": sorted({p["lista_espera"]["origen_derivacion"] for p in perfiles().values()}),
            "charlson": [{"condicion": n, "peso": p} for n, p in puntaje.CONDICIONES_CHARLSON],
            "grupos_proteccion": sorted(puntaje.GRUPOS_PROTECCION),
            "acg": [{"nivel": k, "texto": v} for k, v in puntaje.ACG_NIVELES.items()],
            "resultados_contacto": [{"valor": k, "texto": v} for k, v in RESULTADOS_CONTACTO.items()],
            "decisiones": [{"valor": k, "texto": v} for k, v in DECISIONES.items()],
            "motivos_pendiente": [{"valor": k, "texto": v} for k, v in MOTIVOS_PENDIENTE.items()],
            "motivos_ajuste": [{"valor": k, "texto": v} for k, v in AJUSTE_MANUAL.items()], "min_explicacion": MIN_EXPLICACION}
