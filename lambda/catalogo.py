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
                     "revision": "Espera revisión del especialista", "paciente": "Decisión o disponibilidad del paciente", "otro": "Otro (documentado)"}


def catalogo():
    """Diagnósticos de la lista (especialidad, sub-especialidad, CIE-10, texto), tal como vienen en el registro."""
    import criterios
    vistos = {d["diagnostico_cie10"]: d for d in criterios.catalogo()}
    for p in perfiles_combinados()[0].values():
        le = p["lista_espera"]
        vistos[le["diagnostico_cie10"]] = {"especialidad": le["especialidad"], "sub_especialidad": le["sub_especialidad"],
                                          "diagnostico_cie10": le["diagnostico_cie10"], "diagnostico_texto": le["diagnostico_texto"]}
    return {"diagnosticos": sorted(vistos.values(), key=lambda d: (d["especialidad"], d["diagnostico_cie10"])),
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
