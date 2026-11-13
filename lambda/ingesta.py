"""Ingesta continua: una sola tubería para todos los canales (app, archivo, API para sistemas, zona de carga S3, informes).
Contrato: docs/diseno/ESPECIFICACION_MVP.md §7.

ARCHIVO DE ARRANQUE: solo la interfaz. La implementación la reemplaza."""


def registrar(carga, *, canal, usuario=None, origen=None, archivo=None, corte=None, evaluar="ahora"):
    """Valida, deduplica y guarda lo recibido; deja el registro del lote; evalúa y registra los dictámenes."""
    raise NotImplementedError("la tubería de ingesta aún no está implementada")


def rutear(method, partes, qs, body, cabeceras=None):
    """POST /ingesta/eventos · GET /ingesta/lotes · GET /ingesta/lotes/{id_lote}. None si la ruta no es de este módulo."""
    return None


def s3_handler(event, context=None):
    """Lambda de la zona de carga: un objeto nuevo bajo entrada/ en el bucket."""
    raise NotImplementedError


def cola_handler(event, context=None):
    """Lambda trabajadora: consume la cola de evaluación (SQS) y responde con fallas parciales."""
    raise NotImplementedError
