#!/usr/bin/env python3
"""Despliega el Ambulatorio Dinámico HLF en AWS: backend (stack de CloudFormation/SAM), datos sintéticos y página.

Es el único lugar donde está la lógica del despliegue. `scripts/desplegar.sh` (Linux, macOS, CloudShell, Git Bash) y
`scripts\\deploy_aws.ps1` (PowerShell) solo buscan Python y llaman a este archivo, para que no existan dos versiones
que se desalineen. Usa `aws`, `sam` y `npm` del PATH: no tiene rutas, perfiles ni cuentas fijas.

Pasos (cualquiera que falle detiene el despliegue):
  1. Identidad      muestra la cuenta y la región donde se va a desplegar; prod pide confirmación
  2. Verificación   tests (pytest) y validación de la plantilla: si fallan, no se despliega
  3. Paquete        código de lambda/ + pydantic compilado para Lambda (Linux arm64, Python 3.12)
  4. Stack          sam deploy con los valores del ambiente en samconfig.toml
  5. Datos          solo en prueba: carga el registro sintético si la tabla está vacía
  6. Comprobación   /health responde; /pacientes entrega la lista (sin login) o exige token (con login)
  7. Página         compila el front apuntando a la API y lo publica en Amplify; nunca publica un sitio vacío

Uso:
  python scripts/desplegar.py prueba
  python scripts/desplegar.py prod --parametros "CorreoAlertas=ti@hospital.cl PresupuestoMensualUSD=150"
  python scripts/desplegar.py prueba --solo-front
  python scripts/desplegar.py --solo-paquete        # no usa AWS: sirve para probar que el paquete se arma

Requiere Python 3.11+, `pip install -r requirements-dev.txt`, AWS CLI v2, AWS SAM CLI y Node.js. Detalle en DEPLOY.md.
"""
import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

if sys.version_info < (3, 11):
    sys.exit(f"ERROR: se necesita Python 3.11 o superior (este es {sys.version.split()[0]}). "
             "Instale Python 3.12 (el mismo de la Lambda) y vuelva a correr; en CloudShell: sudo dnf install -y python3.12")
import tomllib  # noqa: E402  (existe desde Python 3.11)

RAIZ = Path(__file__).resolve().parent.parent
SAMCONFIG = RAIZ / "samconfig.toml"
RAMA = "main"  # rama de Amplify donde se publica (la crea la plantilla: AppWebRama)
# Con el intérprete exacto: en un computador con varios Python, "python -m pip" puede instalar en otro.
INSTALAR = f'"{sys.executable}" -m pip install -r requirements-dev.txt'
# Wheels para el runtime de la Lambda (python3.12, arm64). Si cambia el Runtime o la arquitectura en template.yaml, cambiar aquí.
PIP_LAMBDA = ["--platform", "manylinux2014_aarch64", "--python-version", "3.12", "--implementation", "cp", "--only-binary=:all:",
              "--no-compile"]  # sin .pyc: los compilaría el Python de esta máquina, que no es el de la Lambda
NO_VAN_EN_LA_LAMBDA = shutil.ignore_patterns("local_server.py", "requirements.txt", "__pycache__", "*.pyc", ".pytest_cache")
AYUDA_HERRAMIENTA = {
    "aws": "AWS CLI v2: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html",
    "sam": "AWS SAM CLI: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html",
    "npm": "Node.js 20.19 o superior (trae npm): https://nodejs.org",
}


class Alto(Exception):
    """Error esperable: se muestra el mensaje, sin traza, y el despliegue se detiene."""


def paso(numero, titulo):
    print(f"\n=== {numero}. {titulo} ===", flush=True)


# ---------------------------------------------------------------------------------------------------------------------
# Ejecutar herramientas
# ---------------------------------------------------------------------------------------------------------------------
def exigir_herramientas(nombres):
    faltan = [n for n in nombres if not shutil.which(n)]
    if faltan:
        raise Alto("no encuentro en el PATH: " + ", ".join(faltan) + ". Instale y vuelva a correr:\n"
                   + "\n".join(f"  - {AYUDA_HERRAMIENTA[n]}" for n in faltan))


def correr(cmd, *, capturar=False, cwd=None, env=None, mostrar=True):
    """Corre una herramienta del PATH. Devuelve (código, salida, errores); los dos textos solo si capturar=True.
    En Windows `sam` y `npm` son archivos .cmd: se lanzan a través de cmd.exe con la línea completa entre comillas,
    que es la forma que no rompe las rutas con espacios (C:\\Program Files\\...)."""
    ejecutable = shutil.which(str(cmd[0]))
    if not ejecutable:
        raise Alto(f"no encuentro '{cmd[0]}' en el PATH. {AYUDA_HERRAMIENTA.get(cmd[0], '')}")
    if mostrar:
        print("  $ " + " ".join(shlex.quote(str(c)) for c in cmd), flush=True)
    args = [ejecutable, *map(str, cmd[1:])]
    por_cmd = os.name == "nt" and ejecutable.lower().endswith((".cmd", ".bat"))
    r = subprocess.run(subprocess.list2cmdline(args) if por_cmd else args, shell=por_cmd, cwd=cwd, env=env,
                       capture_output=capturar, text=True, encoding="utf-8", errors="replace")
    return r.returncode, r.stdout or "", r.stderr or ""


def aws(*args, region=None):
    """Llama a AWS CLI y devuelve su salida JSON ya leída. Lanza Alto con el mensaje de AWS si falla."""
    cmd = ["aws", *args, "--output", "json"] + (["--region", region] if region else [])
    codigo, salida, errores = correr(cmd, capturar=True, mostrar=False)
    if codigo != 0:
        raise Alto(f"falló: {' '.join(cmd)}\n{(errores or salida).strip()}")
    return json.loads(salida) if salida.strip() else None


def pedir(url, *, metodo="GET", cabeceras=None, datos=None, espera=30):
    """Solicitud HTTP sin librerías externas. Devuelve (estado, cabeceras, cuerpo); estado 0 si no hubo respuesta."""
    solicitud = urllib.request.Request(url, data=datos, method=metodo, headers=cabeceras or {})
    try:
        with urllib.request.urlopen(solicitud, timeout=espera) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, {}, str(e).encode()


# ---------------------------------------------------------------------------------------------------------------------
# Configuración: samconfig.toml es la única fuente de verdad
# ---------------------------------------------------------------------------------------------------------------------
def pares(texto):
    """'Clave=Valor Clave2="otro valor" Clave3=' -> {'Clave': 'Valor', ...}"""
    salida = {}
    for trozo in shlex.split(texto or ""):
        if "=" not in trozo:
            raise Alto(f"parámetro mal escrito: '{trozo}' (se espera Clave=Valor, separados por espacio)")
        clave, valor = trozo.split("=", 1)
        salida[clave] = valor
    return salida


def leer_config(ambiente, extras, region=None):
    """Valores del ambiente en samconfig.toml, con los parámetros de --parametros / PARAMETROS_EXTRA encima."""
    if not SAMCONFIG.exists():
        raise Alto(f"no existe {SAMCONFIG}")
    todo = tomllib.loads(SAMCONFIG.read_text(encoding="utf-8"))
    if ambiente not in todo or "deploy" not in todo[ambiente]:
        raise Alto(f"samconfig.toml no define el ambiente '{ambiente}' ([{ambiente}.deploy.parameters])")
    comunes = dict(todo[ambiente].get("global", {}).get("parameters", {}))
    despliegue = dict(todo[ambiente]["deploy"]["parameters"])
    crudo = despliegue.get("parameter_overrides", "")
    parametros = {**pares(crudo if isinstance(crudo, str) else " ".join(crudo)), **extras}
    if parametros.get("Ambiente", ambiente) != ambiente:
        raise Alto(f"el ambiente '{ambiente}' declara Ambiente={parametros['Ambiente']}: deben coincidir")
    parametros["Ambiente"] = ambiente
    for clave, valor in parametros.items():
        if not valor.isascii() or '"' in valor or "\\" in valor:
            raise Alto(f"el valor de {clave} trae tildes, comillas o barras invertidas: SAM CLI no los lee bien desde su archivo de configuración")
    if region:  # --region manda sobre el archivo, esté definida donde esté
        comunes["region"] = region
        despliegue.pop("region", None)
    for clave in ("stack_name", "region"):
        if not (despliegue.get(clave) or comunes.get(clave)):
            raise Alto(f"samconfig.toml no define {clave} para '{ambiente}'")
    return {"ambiente": ambiente, "comunes": comunes, "despliegue": despliegue, "parametros": parametros,
            "stack": despliegue.get("stack_name") or comunes["stack_name"], "region": despliegue.get("region") or comunes["region"]}


def escribir_config(cfg, destino):
    """Escribe un samconfig.toml temporal con los parámetros ya combinados. Así `sam deploy` recibe los valores desde un
    archivo y no por la línea de comandos (donde las comillas y los valores vacíos se rompen en Windows)."""
    def toml(valor):
        if isinstance(valor, bool):
            return "true" if valor else "false"
        if isinstance(valor, (int, float)):
            return str(valor)
        if isinstance(valor, list):
            return "[" + ", ".join(toml(v) for v in valor) + "]"
        return json.dumps(str(valor))  # las cadenas de JSON son cadenas válidas de TOML (y quedan en ASCII)
    amb = cfg["ambiente"]
    despliegue = {k: v for k, v in cfg["despliegue"].items() if k != "parameter_overrides"}
    despliegue["parameter_overrides"] = " ".join(f"{k}={json.dumps(v)}" for k, v in cfg["parametros"].items())
    lineas = ["version = 0.1", "", f"[{amb}.global.parameters]"]
    lineas += [f"{k} = {toml(v)}" for k, v in cfg["comunes"].items()]
    lineas += ["", f"[{amb}.deploy.parameters]"] + [f"{k} = {toml(v)}" for k, v in despliegue.items()]
    texto = "\n".join(lineas) + "\n"
    if tomllib.loads(texto)[amb]["deploy"]["parameters"]["parameter_overrides"] != despliegue["parameter_overrides"]:
        raise Alto("no pude escribir la configuración combinada para sam (error interno de desplegar.py)")
    destino.write_text(texto, encoding="utf-8")  # json.dumps ya dejó todo en ASCII
    return destino


# ---------------------------------------------------------------------------------------------------------------------
# Pasos
# ---------------------------------------------------------------------------------------------------------------------
def identidad(cfg, confirmar):
    try:
        quien = aws("sts", "get-caller-identity")
    except Alto as e:
        raise Alto("no hay credenciales de AWS vigentes. Inicie sesión (por ejemplo `aws sso login`, o exporte las "
                   f"credenciales temporales) y, si usa un perfil, pase --perfil NOMBRE.\n{e}") from None
    print(f"  Cuenta   {quien['Account']}\n  Entra como {quien['Arn']}\n  Región   {cfg['region']}\n"
          f"  Stack    {cfg['stack']}   (ambiente {cfg['ambiente']})")
    if cfg["ambiente"] == "prod" and confirmar:
        try:  # isatty no basta: en Windows la entrada vacía (NUL) también dice ser una consola
            respuesta = input("  Va a desplegar PRODUCCIÓN en esa cuenta. Escriba prod para continuar: ") if sys.stdin.isatty() else None
        except EOFError:
            respuesta = None
        if respuesta is None:
            raise Alto("prod pide confirmación y no hay consola para preguntar. En un pipeline con aprobación, agregue --si.")
        if respuesta.strip() != "prod":
            raise Alto("despliegue cancelado")
    return quien["Account"]


def dataset():
    return Path(os.environ.get("DATA_DIR") or RAIZ / "data") / "perfiles.json"


def verificar_codigo(sin_tests):
    if correr([sys.executable, str(RAIZ / "scripts" / "validar_plantilla.py")])[0] != 0:
        raise Alto(f"la plantilla o samconfig.toml no pasan la validación (detalle arriba): no se despliega. "
                   f"(Si lo que falta es una librería: {INSTALAR})")
    if sin_tests:
        print("  AVISO: se saltan los tests (--sin-tests). Úselo solo para volver a una versión que ya se probó.")
        return
    datos = dataset()
    if not datos.exists():
        raise Alto(f"no está el dataset sintético ({datos}): los tests lo necesitan y no va en git.\n"
                   "  - Cópielo a data/perfiles.json (o apunte DATA_DIR a su carpeta) y vuelva a correr; o\n"
                   "  - para volver atrás a una versión ya probada, agregue --sin-tests.")
    entorno = {**os.environ, "DATA_DIR": str(datos.parent)}
    if correr([sys.executable, "-X", "utf8", "-m", "pytest", "-q", str(RAIZ / "tests")], cwd=RAIZ, env=entorno)[0] != 0:
        raise Alto(f"los tests fallan: no se despliega. (Si lo que falta es pytest: {INSTALAR})")


def empaquetar():
    """Arma, en una carpeta temporal nueva, lo mismo que hay en el repo pero con lambda/ lista para Lambda:
    template.yaml + lambda/ (código + dependencias para Linux arm64). `CodeUri: lambda/` se resuelve junto a la plantilla."""
    destino = Path(tempfile.mkdtemp(prefix="hlf_paquete_"))
    paquete = destino / "lambda"
    shutil.copytree(RAIZ / "lambda", paquete, ignore=NO_VAN_EN_LA_LAMBDA)
    shutil.copy2(RAIZ / "template.yaml", destino / "template.yaml")
    codigo, salida, errores = correr([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                                      "-r", str(RAIZ / "lambda" / "requirements.txt"), *PIP_LAMBDA, "--target", str(paquete)], capturar=True)
    if codigo != 0:
        raise Alto("pip no pudo bajar las dependencias para Lambda (¿hay internet?, ¿existe el paquete para arm64?):\n"
                   + (errores or salida).strip())
    # Un binario de otra plataforma (por ejemplo el de Windows) haría fallar la Lambda recién al ejecutarla.
    binarios = [p for p in paquete.rglob("*") if p.suffix in (".so", ".pyd", ".dll", ".dylib")]
    ajenos = [p.name for p in binarios if not ("aarch64-linux-gnu" in p.name and ("cpython-312" in p.name or "abi3" in p.name))]
    if ajenos:
        raise Alto("el paquete trae binarios que no son de Linux arm64 / Python 3.12: " + ", ".join(ajenos[:5]))
    if not (paquete / "app.py").exists():
        raise Alto("el paquete no trae app.py: revise la carpeta lambda/")
    megas = sum(p.stat().st_size for p in paquete.rglob("*") if p.is_file()) / 1e6
    print(f"  Paquete listo en {destino} ({megas:.1f} MB sin comprimir, {len(binarios)} binario(s) de Linux arm64)")
    return destino


def desplegar_stack(cfg, paquete, confirmar):
    config = escribir_config(cfg, paquete / "samconfig.toml")
    cmd = ["sam", "deploy", "--template-file", paquete / "template.yaml", "--config-file", config,
           "--config-env", cfg["ambiente"], "--no-fail-on-empty-changeset"]
    if not confirmar or not sys.stdin.isatty():
        cmd.append("--no-confirm-changeset")
    visibles = ("Autenticacion", "OrigenPermitido", "LlavePropia", "Algoritmo", "ModelId", "BarridoActivo")
    print("  Modo: " + ", ".join(f"{k}={cfg['parametros'].get(k, '(por defecto)')}" for k in visibles))
    if correr(cmd, cwd=RAIZ)[0] != 0:
        raise Alto("sam deploy falló: CloudFormation deja el stack como estaba antes (el detalle está arriba y en la "
                   "consola de CloudFormation, pestaña Eventos)")


def salidas_del_stack(cfg):
    stacks = aws("cloudformation", "describe-stacks", "--stack-name", cfg["stack"], region=cfg["region"])
    return {s["OutputKey"]: s["OutputValue"] for s in stacks["Stacks"][0].get("Outputs", [])}


def salud(api, intentos=1):
    """Consulta /health. Devuelve el JSON, o None si no responde bien (reintenta: una Lambda nueva tarda en estar lista)."""
    for i in range(intentos):
        estado, _, cuerpo = pedir(f"{api}/health")
        if estado == 200:
            try:
                datos = json.loads(cuerpo)
                if datos.get("ok"):
                    return datos
            except ValueError:
                pass
        if i + 1 < intentos:
            time.sleep(5)
    return None


def cargar_datos(cfg, salidas, recargar):
    if cfg["ambiente"] == "prod":
        print("  En prod no se carga el registro sintético: los datos reales entran por los canales de ingesta (DEPLOY.md).")
        return
    ya = (salud(salidas["ApiUrl"], intentos=6) or {}).get("pacientes", 0)
    if ya and not recargar:
        print(f"  La tabla ya tiene {ya} pacientes: no se vuelve a cargar (use --recargar-datos para forzarlo).")
        return
    cargador, datos = RAIZ / "scripts" / "cargar_registro.py", dataset()
    for ruta in (cargador, datos):
        if not ruta.exists():
            raise Alto(f"no existe {ruta}: no se puede cargar el registro sintético (o agregue --sin-datos)")
    # La app ya no lee perfiles.json de S3: sin esta carga la lista sale vacía. --perfil "" = credenciales por defecto
    # (las que ya validó el paso 1, incluido AWS_PROFILE si se pasó --perfil); el valor por defecto del cargador es
    # un perfil fijo del hackatón que en otro computador no existe.
    if correr([sys.executable, "-X", "utf8", str(cargador), "--archivo", str(datos),
               "--tabla", salidas["TableName"], "--region", cfg["region"], "--perfil", ""], cwd=RAIZ)[0] != 0:
        raise Alto("falló la carga del registro sintético")


def comprobar_api(cfg, salidas, con_datos):
    api, con_login = salidas["ApiUrl"], salidas.get("Autenticacion") == "cognito"
    estado_salud = salud(api, intentos=12)
    if not estado_salud:
        estado, _, cuerpo = pedir(f"{api}/health")
        raise Alto(f"GET /health no responde bien (estado {estado}): {cuerpo[:300].decode(errors='replace')}")
    print(f"  /health OK: {estado_salud.get('pacientes')} pacientes, fecha {estado_salud.get('fecha_hoy')}, modo {estado_salud.get('modo')}")
    if con_datos and not estado_salud.get("pacientes"):
        # los contenedores que ya estaban arriba ven la carga cuando el cargador actualiza el marcador de la tabla
        for _ in range(12):
            time.sleep(5)
            estado_salud = salud(api) or estado_salud
            if estado_salud.get("pacientes"):
                break
        else:
            raise Alto("la API sigue sin pacientes después de cargar el registro: revise la carga y los logs de la función")
        print(f"  /health ve la carga: {estado_salud['pacientes']} pacientes")

    if con_login:
        estado, _, _ = pedir(f"{api}/pacientes")
        if estado != 401:
            raise Alto(f"con login activo, GET /pacientes sin token debe responder 401 y respondió {estado}: la API NO está protegida")
        print("  /pacientes sin token responde 401: el login protege la API")
    else:
        for intento in range(6):  # la lista lee toda la tabla: puede tardar más que /health justo después de un cambio de versión
            estado, _, cuerpo = pedir(f"{api}/pacientes", espera=60)
            if estado == 200 and b'"pacientes"' in cuerpo:
                break
            time.sleep(10)
        else:
            raise Alto(f"GET /pacientes no entrega la lista (estado {estado}): {cuerpo[:300].decode(errors='replace')}")
        print("  /pacientes entrega la lista")

    # CORS: un sitio cualquiera no debe quedar autorizado, salvo en la demo (OrigenPermitido=*).
    intruso = "https://sitio-no-autorizado.example"
    _, cabeceras, _ = pedir(f"{api}/health", cabeceras={"Origin": intruso})
    permitido = cabeceras.get("access-control-allow-origin")
    if cfg["parametros"].get("OrigenPermitido", "*") == "*":
        print("  CORS abierto a cualquier origen (OrigenPermitido=*): correcto solo para la demo con datos sintéticos")
    elif permitido in ("*", intruso):
        raise Alto(f"la API autoriza a un origen que no corresponde ({permitido}): revise OrigenPermitido")
    else:
        print("  CORS: un origen no autorizado no recibe permiso")


def publicar_pagina(cfg, salidas, app_amplify):
    app = app_amplify or salidas.get("SitioAppId")
    if not app:
        print("  Este stack no crea el sitio (SitioAmplify=no) y no se indicó --app-amplify: no se publica la página.")
        return None
    front = RAIZ / "front"
    if not (front / "node_modules").exists() or os.environ.get("CI"):
        if correr(["npm", "ci"], cwd=front)[0] != 0:
            raise Alto("npm ci falló: no se publica la página")
    # Vite deja estas variables fijas dentro de la página al compilar.
    entorno = {**os.environ, "VITE_API_URL": salidas["ApiUrl"], "VITE_AUTH": salidas.get("Autenticacion", "ninguna"),
               "VITE_COGNITO_DOMINIO": salidas.get("LoginUrl", ""), "VITE_COGNITO_CLIENTE": salidas.get("ClienteWebId", ""),
               "VITE_COGNITO_REDIRECCION": salidas.get("SitioUrl", "")}
    trabajo = Path(tempfile.mkdtemp(prefix="hlf_pagina_"))
    dist = trabajo / "dist"
    codigo = correr(["npm", "run", "build", "--", "--outDir", dist, "--emptyOutDir"], cwd=front, env=entorno)[0]
    # Nunca publicar un sitio vacío ni uno que no apunte a esta API.
    js = list(dist.rglob("*.js")) if dist.exists() else []
    indice = dist / "index.html"
    if codigo != 0 or not indice.exists() or indice.stat().st_size == 0 or not js:
        raise Alto("la compilación del front falló o quedó vacía: no se publica la página (la anterior sigue en línea)")
    if not any(salidas["ApiUrl"] in p.read_text(encoding="utf-8", errors="ignore") for p in js):
        raise Alto("la página compilada no trae la dirección de la API (VITE_API_URL): no se publica")

    paquete = trabajo / "pagina.zip"
    with zipfile.ZipFile(paquete, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(dist.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(dist).as_posix())  # rutas con "/" aunque se arme en Windows
    region = cfg["region"]
    despliegue = aws("amplify", "create-deployment", "--app-id", app, "--branch-name", RAMA, region=region)
    estado, _, cuerpo = pedir(despliegue["zipUploadUrl"], metodo="PUT", datos=paquete.read_bytes(),
                              cabeceras={"Content-Type": "application/zip"}, espera=300)
    if estado not in (200, 201):
        raise Alto(f"no se pudo subir la página a Amplify (estado {estado}): {cuerpo[:300].decode(errors='replace')}")
    aws("amplify", "start-deployment", "--app-id", app, "--branch-name", RAMA, "--job-id", despliegue["jobId"], region=region)
    resultado = "PENDING"
    for _ in range(60):
        resultado = aws("amplify", "get-job", "--app-id", app, "--branch-name", RAMA, "--job-id", despliegue["jobId"],
                        region=region)["job"]["summary"]["status"]
        if resultado in ("SUCCEED", "FAILED", "CANCELLED"):
            break
        time.sleep(5)
    if resultado != "SUCCEED":
        raise Alto(f"Amplify no terminó la publicación (estado {resultado}): revise la aplicación {app} en la consola de Amplify")
    sitio = salidas.get("SitioUrl") or f"https://{RAMA}.{aws('amplify', 'get-app', '--app-id', app, region=region)['app']['defaultDomain']}"
    for _ in range(6):
        estado, _, cuerpo = pedir(sitio)
        if estado == 200 and cuerpo.strip():
            break
        time.sleep(5)
    else:
        raise Alto(f"la página se publicó pero {sitio} no responde (estado {estado})")
    print(f"  Página publicada: {sitio}")
    return sitio


# ---------------------------------------------------------------------------------------------------------------------
def argumentos():
    p = argparse.ArgumentParser(description="Despliega el Ambulatorio Dinámico HLF en AWS (ver DEPLOY.md).")
    p.add_argument("ambiente", nargs="?", default="prueba", help="ambiente de samconfig.toml: prueba (por defecto) o prod")
    p.add_argument("--solo-front", action="store_true", help="solo compila y publica la página (usa el stack ya desplegado)")
    p.add_argument("--solo-backend", action="store_true", help="no publica la página")
    p.add_argument("--solo-paquete", action="store_true", help="solo arma el paquete de la Lambda; no usa AWS")
    p.add_argument("--sin-tests", action="store_true", help="salta los tests (solo para volver atrás a una versión ya probada)")
    p.add_argument("--sin-datos", action="store_true", help="no carga el registro sintético")
    p.add_argument("--recargar-datos", action="store_true", help="carga el registro sintético aunque la tabla ya tenga pacientes")
    p.add_argument("--parametros", default="", metavar='"Clave=Valor ..."',
                   help="parámetros de la plantilla que pisan los de samconfig.toml en este despliegue (también: variable PARAMETROS_EXTRA)")
    p.add_argument("--region", help="región de AWS (por defecto, la de samconfig.toml)")
    p.add_argument("--perfil", help="perfil de AWS CLI (por defecto, las credenciales activas)")
    p.add_argument("--app-amplify", help="aplicación de Amplify donde publicar (por defecto, la que crea el stack)")
    p.add_argument("--si", action="store_true", help="no pedir confirmación (pipeline con aprobación previa)")
    a = p.parse_args()
    if a.solo_front and a.solo_backend:
        p.error("--solo-front y --solo-backend no van juntos")
    return a


def main():
    for flujo in (sys.stdout, sys.stderr):  # tildes legibles también en Git Bash y en consolas de Windows
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8", errors="replace")
    a = argumentos()
    if a.solo_paquete:
        paso(3, "Paquete de la Lambda (sin AWS)")
        empaquetar()
        return
    if a.perfil:
        os.environ["AWS_PROFILE"] = a.perfil  # lo leen aws, sam y boto3 (cargar_registro.py)
    extras = {**pares(os.environ.get("PARAMETROS_EXTRA", "")), **pares(a.parametros)}
    cfg = leer_config(a.ambiente, extras, a.region)
    exigir_herramientas(["aws"] + ([] if a.solo_front else ["sam"]) + ([] if a.solo_backend else ["npm"]))
    print(f"Python {sys.version.split()[0]} ({sys.executable})")

    paso(1, "Identidad")
    identidad(cfg, confirmar=not a.si)
    if not a.solo_front:
        paso(2, "Verificación previa (plantilla y tests)")
        verificar_codigo(a.sin_tests)
        paso(3, "Paquete de la Lambda")
        paquete = empaquetar()
        paso(4, f"Stack {cfg['stack']}")
        desplegar_stack(cfg, paquete, confirmar=not a.si)
    salidas = salidas_del_stack(cfg)
    if not a.solo_front:
        paso(5, "Datos")
        con_datos = cfg["ambiente"] != "prod" and not a.sin_datos
        if a.sin_datos:
            print("  No se carga el registro sintético (--sin-datos).")
        else:
            cargar_datos(cfg, salidas, a.recargar_datos)
        paso(6, "Comprobación de la API")
        comprobar_api(cfg, salidas, con_datos)
    sitio = None
    if not a.solo_backend:
        paso(7, "Página")
        sitio = publicar_pagina(cfg, salidas, a.app_amplify)

    print("\n=== Listo ===")
    print(f"  API     {salidas['ApiUrl']}")
    if sitio or salidas.get("SitioUrl"):
        print(f"  Página  {sitio or salidas['SitioUrl']}")
    print(f"  Tabla   {salidas['TableName']}\n  Bucket  {salidas['BucketName']}  (zona de carga: entrada/)")
    if salidas.get("Autenticacion") == "cognito":
        print(f"  Login   {salidas.get('LoginUrl')}  -> alta de usuarios y roles: docs/operacion/RUNBOOK.md")


if __name__ == "__main__":
    try:
        main()
    except Alto as e:
        sys.exit(f"\nERROR: {e}")
    except KeyboardInterrupt:
        sys.exit("\nCancelado.")
