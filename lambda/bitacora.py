"""Bitácora de decisiones: un dictamen por cada vez que el sistema evalúa a un paciente por un disparador
(evento, ingreso, novedad, informe, carga, criterio local…). Contrato: docs/diseno/ESPECIFICACION_MVP.md §5.

ARCHIVO DE ARRANQUE: solo la interfaz, para que los demás módulos puedan llamarla. La implementación la reemplaza."""


def fotos(pids, corte):
    """Estado de cada paciente en la lista ANTES del cambio: {id_paciente: fila | None}. Una lista por especialidad."""
    return {}


def registrar_lote(disparadores, corte, antes, *, canal="app", usuario=None, id_lote=None, evaluaciones=None):
    """Arma y guarda un dictamen por paciente. disparadores: {id_paciente: {tipo, id_evento?, descripcion}}.
    antes: lo que devolvió fotos(). evaluaciones: {id_paciente: evaluación de la IA de este disparador}. Devuelve los dictámenes."""
    return []


def registrar(pid, corte, disparador, antes, **kw):
    """Atajo de un paciente (antes = su fila previa o None)."""
    evaluacion = kw.pop("evaluacion", None)
    if evaluacion is not None:
        kw["evaluaciones"] = {pid: evaluacion}
    hechos = registrar_lote({pid: disparador}, corte, {pid: antes}, **kw)
    return hechos[0] if hechos else None


def de_paciente(pid):
    """Dictámenes del paciente, el más reciente primero, cada uno con su revisión (veredicto) unida."""
    return []


def buscar(especialidad=None, estado="pendiente", limite=50, desde=None):
    """Dictámenes de la cola de revisión: estado = pendiente | revisada | todas."""
    return []


def rutear(method, partes, qs, body):
    """GET /decisiones · GET /decisiones/{id_dictamen} · GET /pacientes/{id}/decisiones. None si la ruta no es de este módulo."""
    return None
