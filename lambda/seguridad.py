"""Identidad y permisos de quien llama a la API. Contrato: docs/diseno/ESPECIFICACION_MVP.md §8.

Dos modos (variable AUTH):

  ninguna   Demo y local, SOLO con datos sintéticos. No hay inicio de sesión: el nombre viaja en el cuerpo (`usuario`) y el
            rol en la cabecera X-Rol. Los declara el navegador, nadie los verifica y todo está permitido.
            NO es un control de seguridad: sirve para mostrar el flujo.
  cognito   API Gateway (autorizador JWT de Amazon Cognito) valida la firma, el emisor, la audiencia y el vencimiento del
            token ANTES de invocar la Lambda, y entrega sus afirmaciones en requestContext.authorizer.jwt.claims. Aquí no
            se validan firmas ni se agregan librerías: se confía en ese bloque del evento.

IMPORTANTE: sin el autorizador JWT delante, AUTH=cognito NO es seguro. Quien pueda invocar la función sin pasar por él
(lambda:InvokeFunction, una Function URL, una ruta de API Gateway sin autorizador) arma el evento a su gusto y puede
inventar las afirmaciones. La función solo debe poder invocarla API Gateway, y todas sus rutas (menos OPTIONS y /health)
deben llevar el autorizador. Lo mismo vale para lambda/local_server.py: nunca copia nada de la solicitud a `authorizer`.

Cualquier valor de AUTH distinto de "ninguna" exige token: un error de tipeo cierra la API, no la abre.
Una ruta que no esté en REGLAS queda denegada con AUTH=cognito: toda ruta nueva necesita su regla aquí.
"""
import json
import os
import re

# Roles de las personas (grupos de Cognito), de menor a mayor: cada uno incluye lo que pueden los anteriores.
ROLES = ("gestion", "especialista", "jefatura")
# Rol de los sistemas: token de máquina (client credentials) con el permiso (scope) de ingesta. No es un grupo.
INTEGRACION = "integracion"
SCOPE_INGESTA = "ambulatorio/ingesta"

# Lo que una ruta puede exigir (además de un rol): quién lo cumple está en _cumple().
AUTENTICADO = "autenticado"   # cualquier token válido, de persona o de sistema
LECTURA = "lectura"           # cualquier persona autenticada, tenga o no un grupo (§8: "Lecturas: cualquiera autenticado")
SIN_REGLA = "sin_regla"       # la ruta no está en la tabla: no pasa nadie
NIVELES = (LECTURA, *ROLES, INTEGRACION)

ORIGENES_TOKEN = ("token", "token_maquina")
ANONIMO = {"usuario": None, "roles": [], "origen": "anonimo", "cliente": None}
AVISO_DEMO = ("Sin inicio de sesión (AUTH=ninguna): el nombre y el rol los declara el navegador; la API no los verifica ni "
              "los exige. No es un control de seguridad: solo para datos sintéticos.")

# (método, ruta, exigencia). "*" = un tramo cualquiera (un id). Fuente: tabla de ESPECIFICACION_MVP §8.
REGLAS = (
    # Libres: sin token (verificar el despliegue). OPTIONS (preflight de CORS) también es libre: ver permiso().
    ("GET", (), None),
    ("GET", ("health",), None),
    # Quién soy y qué puedo hacer: cualquier token válido.
    ("GET", ("yo",), AUTENTICADO),
    # Lecturas: cualquier persona autenticada.
    ("GET", ("pacientes",), LECTURA),
    ("GET", ("pacientes", "*"), LECTURA),
    ("GET", ("pacientes", "*", "historia"), LECTURA),
    ("GET", ("pacientes", "*", "evaluaciones"), LECTURA),
    ("GET", ("pacientes", "*", "decisiones"), LECTURA),
    ("GET", ("catalogo",), LECTURA),
    ("GET", ("estadisticas",), LECTURA),
    ("GET", ("kpis",), LECTURA),
    ("GET", ("plantillas", "*"), LECTURA),
    ("GET", ("decisiones",), LECTURA),
    ("GET", ("decisiones", "*"), LECTURA),
    ("GET", ("aprendizaje",), LECTURA),
    ("GET", ("criterios-locales",), LECTURA),
    ("GET", ("conocimiento",), LECTURA),
    ("GET", ("conocimiento", "diagnostico", "*"), LECTURA),
    ("POST", ("pacientes", "*", "explicar"), LECTURA),          # redacta la explicación de lo que ya se ve: no guarda nada
    # Gestión de la lista: contacto, gestión, ingreso, eventos manuales, informes, importar.
    ("POST", ("pacientes",), "gestion"),
    ("POST", ("importar",), "gestion"),
    ("POST", ("eventos",), "gestion"),
    ("POST", ("pacientes", "*", "contacto"), "gestion"),
    ("POST", ("pacientes", "*", "gestion"), "gestion"),
    ("POST", ("pacientes", "*", "informe"), "gestion"),
    ("POST", ("pacientes", "*", "novedad"), "gestion"),         # mismos datos que el ingreso (comorbilidad, diagnóstico, egreso)
    ("POST", ("pacientes", "*", "evaluar"), "gestion"),         # relee con IA: lo mismo que ya provoca registrar un evento
    # Decisión del especialista: veredicto, decisión clínica, orden manual, enmienda de un evento.
    ("POST", ("pacientes", "*", "revision"), "especialista"),
    ("POST", ("pacientes", "*", "decision"), "especialista"),
    ("POST", ("pacientes", "*", "orden"), "especialista"),
    ("POST", ("pacientes", "*", "eventos", "*", "enmienda"), "especialista"),
    # Jefatura: resolver criterios locales (cambia la regla para todos) y reevaluar la lista completa con IA.
    ("POST", ("criterios-locales", "*", "resolver"), "jefatura"),
    ("POST", ("algoritmo", "barrido"), "jefatura"),
    # Sistemas integrados (o una persona de gestión hacia arriba): enviar datos y ver sus lotes.
    ("POST", ("ingesta", "eventos"), INTEGRACION),
    ("GET", ("ingesta", "lotes"), INTEGRACION),
    ("GET", ("ingesta", "lotes", "*"), INTEGRACION),
)


def modo():
    """`ninguna` (demo y local: sin inicio de sesión) o `cognito` (API Gateway valida el JWT antes de llegar aquí).
    Solo "ninguna" (o la variable sin definir) deja la API abierta; cualquier otro valor exige token."""
    valor = (os.environ.get("AUTH") or "ninguna").strip().lower()
    return "ninguna" if valor == "ninguna" else "cognito"


def con_token(ident):
    """¿La identidad viene de un token que validó API Gateway (y no de lo que declara el navegador)?"""
    return (ident or {}).get("origen") in ORIGENES_TOKEN


# ---------- identidad ----------
def _dic(x):
    return x if isinstance(x, dict) else {}


def _limpio(valor, largo=120):
    """Texto para la trazabilidad: en una línea, sin caracteres de control y acotado."""
    return " ".join("".join(c if c.isprintable() else " " for c in str(valor or "")).split())[:largo]


def _lista(valor):
    """Afirmación con varios valores. API Gateway (HTTP API) entrega los arreglos como texto: "[a b]"; un evento armado a
    mano los trae como lista. Los nombres de grupo los crea un administrador y no llevan espacios."""
    if isinstance(valor, (list, tuple)):
        return [str(v).strip() for v in valor if str(v).strip()]
    texto = str(valor or "").strip()
    if texto.startswith("[") and texto.endswith("]"):
        try:
            como_json = json.loads(texto)                      # '["a", "b"]'
            if isinstance(como_json, list):
                return _lista(como_json)
        except ValueError:
            pass
        texto = texto[1:-1]
    return [t for t in re.split(r"[\s,]+", texto) if t]


def _afirmaciones(event):
    """(claims, scopes) del token que API Gateway ya validó; ({}, []) si la solicitud no trae uno."""
    jwt = _dic(_dic(_dic(_dic(event).get("requestContext")).get("authorizer")).get("jwt"))
    claims = _dic(jwt.get("claims"))
    if not claims.get("sub"):
        return {}, []
    return claims, {*_lista(jwt.get("scopes")), *str(claims.get("scope") or "").split()}


def _de_token(claims, scopes):
    """Persona (token de identidad o de acceso de un usuario) o sistema (client credentials: sin usuario, con client_id)."""
    cliente = _limpio(claims.get("client_id") or claims.get("aud")) or None
    cuenta = claims.get("cognito:username") or claims.get("username")
    if not (cuenta or claims.get("email") or claims.get("name")) and claims.get("client_id"):
        roles = [INTEGRACION] if SCOPE_INGESTA in scopes else []
        return {"usuario": f"sistema:{_limpio(claims['client_id'])}", "roles": roles, "origen": "token_maquina", "cliente": cliente,
                "sujeto": _limpio(claims["sub"])}
    grupos = {g.lower() for g in _lista(claims.get("cognito:groups"))}
    nombre = next((n for n in (_limpio(claims.get(k)) for k in ("name", "email", "cognito:username", "username", "sub")) if n), None)
    return {"usuario": nombre, "roles": [r for r in ROLES if r in grupos], "origen": "token", "cliente": cliente,
            "sujeto": _limpio(claims["sub"])}


def _cuerpo_declarado(event):
    """El cuerpo de la solicitud si es un objeto JSON; si no, {} (aquí no se reclama: eso lo hace el handler)."""
    try:
        crudo = event.get("body") or ""
        if crudo and event.get("isBase64Encoded"):
            import base64
            crudo = base64.b64decode(crudo).decode("utf-8")
        return _dic(json.loads(crudo)) if crudo else {}
    except (ValueError, TypeError):
        return {}


def identidad(event, cuerpo=None):
    """{"usuario", "roles", "origen", "cliente"} de quien llama. `origen`:
      token          persona con un JWT que validó API Gateway (lleva además `sujeto`: el identificador fijo de la cuenta)
      token_maquina  sistema con client credentials: usuario "sistema:<client_id>", rol integracion si trae el scope
      declarado      AUTH=ninguna: nombre (cuerpo) y rol (X-Rol) que dice el navegador, sin verificar
      anonimo        no dijo nada, o AUTH=cognito sin token (autorizar responde 401)
    `cuerpo`: el cuerpo ya leído (si no se pasa, se lee del evento)."""
    event = _dic(event)
    claims, scopes = _afirmaciones(event)
    if claims:
        return _de_token(claims, scopes)
    if modo() != "ninguna":
        return dict(ANONIMO)
    cuerpo = _cuerpo_declarado(event) if cuerpo is None else _dic(cuerpo)
    cabeceras = {str(k).lower(): v for k, v in _dic(event.get("headers")).items()}
    rol = str(cabeceras.get("x-rol") or "").strip().lower()
    roles = [rol] if rol in NIVELES[1:] else []
    usuario = _limpio(cuerpo.get("usuario")) if isinstance(cuerpo.get("usuario"), str) else ""
    return {"usuario": usuario or None, "roles": roles, "origen": "declarado" if usuario or roles else "anonimo", "cliente": None}


def aplicar_identidad(cuerpo, ident):
    """Con token, el nombre de quien registra sale del token: reemplaza el `usuario` que mande el navegador y completa
    `responsable` si viene vacío. Sin token (demo) el cuerpo queda como llegó. Las acciones no cambian."""
    if not con_token(ident) or not isinstance(cuerpo, dict):
        return cuerpo
    cuerpo = {**cuerpo, "usuario": ident["usuario"]}
    if not str(cuerpo.get("responsable") or "").strip():
        cuerpo["responsable"] = ident["usuario"]
    return cuerpo


# ---------- permisos ----------
def permiso(method, partes):
    """Lo que exige la ruta: None (libre), "autenticado", "lectura", un rol ("gestion" < "especialista" < "jefatura"),
    "integracion", o "sin_regla" si la ruta no está en la tabla (con AUTH=cognito queda denegada)."""
    method = str(method or "").upper()
    if method == "OPTIONS":
        return None
    partes = list(partes or [])
    for metodo, ruta, exigencia in REGLAS:
        if metodo == method and len(ruta) == len(partes) and all(r in ("*", p) for r, p in zip(ruta, partes)):
            return exigencia
    return SIN_REGLA


def _cumple(roles, persona, exigencia):
    """¿Esos roles cumplen la exigencia? `persona`: el token es de una persona y no de un sistema."""
    if exigencia is None or exigencia == AUTENTICADO:
        return True
    nivel = max((ROLES.index(r) for r in roles if r in ROLES), default=-1) if persona else -1
    if exigencia == LECTURA:
        return persona
    if exigencia in ROLES:
        return nivel >= ROLES.index(exigencia)
    if exigencia == INTEGRACION:   # un sistema con el scope de ingesta, o una persona de gestión hacia arriba
        return nivel >= 0 or (not persona and INTEGRACION in roles)
    return False                   # sin_regla, o una exigencia que este módulo no conoce: nadie


def _motivo(ident, exigencia):
    roles = ident.get("roles") or []
    if exigencia == SIN_REGLA:
        return "Acceso denegado: esta ruta no tiene una regla de acceso definida."
    if ident.get("origen") == "token_maquina":
        if INTEGRACION not in roles:
            return f"Acceso denegado: el token de este sistema no trae el permiso (scope) {SCOPE_INGESTA}."
        return "Acceso denegado: un sistema integrado solo puede enviar datos a la ingesta y consultar sus lotes."
    perfil = "tiene el rol " + ", ".join(roles) if roles else "no tiene un rol asignado"
    requiere = {"jefatura": "el rol jefatura", "especialista": "el rol especialista o jefatura",
                "gestion": "el rol gestion, especialista o jefatura",
                INTEGRACION: "el rol gestion, especialista o jefatura"}.get(exigencia, "otro perfil")
    return f"Acceso denegado: esta acción requiere {requiere} y su cuenta {perfil}."


def autorizar(ident, method, partes):
    """None si puede pasar; (status, cuerpo) si no: 401 sin token válido, 403 con token pero sin permiso.
    Con AUTH=ninguna no se exige nada (demo con datos sintéticos)."""
    exigencia = permiso(method, partes)
    if exigencia is None or modo() == "ninguna":
        return None
    if not con_token(ident):
        return 401, {"error": "No autorizado: inicie sesión para usar la aplicación.", "codigo": "no_autenticado"}
    if _cumple(ident.get("roles") or [], ident["origen"] == "token", exigencia):
        return None
    return 403, {"error": _motivo(ident, exigencia), "codigo": "ruta_sin_regla" if exigencia == SIN_REGLA else "sin_permiso",
                 "requiere": exigencia, "roles": list(ident.get("roles") or [])}


def yo(ident):
    """GET /yo: quién está conectado, con qué roles y qué puede hacer (para que la página lo muestre).
    `permisos` responde por grupo de acciones de la tabla §8. Con AUTH=ninguna nada se exige (`se_exige`: false): si el
    navegador declaró un rol, `permisos` muestra lo que ese rol podría hacer; si no declaró ninguno, todo."""
    roles = list(ident.get("roles") or [])
    if con_token(ident):
        permisos = {n: _cumple(roles, ident["origen"] == "token", n) for n in NIVELES}
    elif roles:
        permisos = {n: _cumple(roles, INTEGRACION not in roles, n) for n in NIVELES}
    else:
        permisos = {n: True for n in NIVELES}
    exige = modo() != "ninguna"
    return {"usuario": ident.get("usuario"), "roles": roles, "origen": ident.get("origen"), "cliente": ident.get("cliente"),
            "auth": modo(), "se_exige": exige, "permisos": permisos, **({} if exige else {"aviso": AVISO_DEMO})}


# ---------- cabeceras de la respuesta ----------
CABECERAS_PERMITIDAS = "content-type,authorization,idempotency-key,x-rol"
METODOS_PERMITIDOS = "GET,POST,OPTIONS"
CABECERAS_SEGURIDAD = {
    "X-Content-Type-Options": "nosniff",                                       # el navegador no adivina el tipo de contenido
    "Cache-Control": "no-store",                                               # nadie guarda copias de datos clínicos
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",   # una respuesta de la API nunca es una página
    "Strict-Transport-Security": "max-age=31536000",
}


def origenes_permitidos():
    """ORIGEN_PERMITIDO: lista separada por comas. Sin definir (demo): "*"."""
    crudo = os.environ.get("ORIGEN_PERMITIDO") or "*"
    return [o.strip().rstrip("/").lower() for o in crudo.split(",") if o.strip()] or ["*"]


def cabeceras_cors(origen):
    """CORS de la respuesta. Con "*" (demo) se permite cualquier origen. Con una lista, se devuelve el origen de la
    solicitud solo si está en ella; si no, no va ninguna cabecera y el navegador bloquea la respuesta.
    CORS no reemplaza al token: solo limita desde qué páginas un navegador puede leer la API."""
    permitidos = origenes_permitidos()
    cors = {"Access-Control-Allow-Headers": CABECERAS_PERMITIDAS, "Access-Control-Allow-Methods": METODOS_PERMITIDOS,
            "Access-Control-Max-Age": "600"}
    if "*" in permitidos:
        return {"Access-Control-Allow-Origin": "*", **cors}
    origen = str(origen or "").strip()
    if origen and origen.rstrip("/").lower() in permitidos:
        return {"Access-Control-Allow-Origin": origen, **cors, "Vary": "Origin"}
    return {"Vary": "Origin"}
