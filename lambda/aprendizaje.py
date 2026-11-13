"""Aprendizaje con la retroalimentación del especialista: precedentes por patrón y criterios locales
(propuesto → vigente | rechazado → retirado). Contrato: docs/diseno/ESPECIFICACION_MVP.md §6.

ARCHIVO DE ARRANQUE: solo la interfaz. La implementación la reemplaza."""


def rutear(method, partes, qs, body):
    """GET /aprendizaje · GET /criterios-locales · POST /criterios-locales/{id}/resolver ·
    POST /pacientes/{id}/eventos/{id_evento}/enmienda. None si la ruta no es de este módulo."""
    return None
