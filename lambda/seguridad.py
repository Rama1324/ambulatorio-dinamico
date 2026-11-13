"""Identidad y permisos de quien llama a la API. Contrato: docs/diseno/ESPECIFICACION_MVP.md §8.

ARCHIVO DE ARRANQUE: solo la interfaz, con el comportamiento de la demo (todo permitido). La implementación la reemplaza."""
import os


def modo():
    """`ninguna` (demo y local: sin inicio de sesión) o `cognito` (API Gateway valida el JWT antes de llegar aquí)."""
    return os.environ.get("AUTH", "ninguna")


def identidad(event):
    """{"usuario", "roles", "origen", "cliente"} de quien llama."""
    return {"usuario": None, "roles": [], "origen": "anonimo", "cliente": None}


def permiso(method, partes):
    """Rol mínimo que exige la ruta, o None si es libre."""
    return None


def autorizar(ident, method, partes):
    """None si puede pasar; (status, cuerpo) con 401 o 403 si no."""
    return None
