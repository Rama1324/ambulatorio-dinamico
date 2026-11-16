"""Levanta la demostración completa en este computador con un solo comando (Windows, macOS o Linux), sin AWS.

    python scripts/demo.py

Qué hace:
  1. Revisa lo necesario (Python 3.11+, pydantic, Node.js con npm) y dice qué falta y cómo instalarlo.
  2. Deja el registro sintético en data/ (lo copia desde "docs/Datasets de ejemplo" si hace falta).
  3. Instala las dependencias de la página la primera vez (npm ci).
  4. Inicia la API en http://localhost:3001 y la página en http://localhost:5174, y abre el navegador.
  5. Ctrl+C detiene todo. Lo registrado vive en memoria: al reiniciar, la demo vuelve a su estado inicial.

Opciones:
  --reglas             solo reglas, sin IA (ALGORITMO=reglas)
  --bedrock MODELO     IA real con Amazon Bedrock (necesita credenciales AWS vigentes; MODELO = id del modelo o perfil)
  --hoy                usa la fecha real de Chile en vez de la fecha del registro sintético (2026-10-13)
  --solo-api           no inicia la página
  --sin-navegador      no abre el navegador
  --puerto-api N       puerto de la API (3001)      --puerto-web N   puerto de la página (5174)

Por defecto la IA corre en modo SIMULADO (un lector determinista, sin Bedrock): sirve para mostrar el flujo completo sin
cuenta de AWS, y queda rotulado así en cada decisión.
"""
import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATOS = os.path.join(RAIZ, "data")
EJEMPLO = os.path.join(RAIZ, "docs", "Datasets de ejemplo")
FECHA_REGISTRO = "2026-10-13"


def fallar(msg):
    print(f"\n[!] {msg}\n")
    sys.exit(1)


def revisar_requisitos(con_web):
    if sys.version_info < (3, 11):
        fallar(f"Se necesita Python 3.11 o superior (este es {sys.version.split()[0]}).")
    try:
        import pydantic  # noqa: F401
    except ImportError:
        fallar("Falta la librería pydantic. Instálela con:  python -m pip install -r lambda/requirements.txt")
    if con_web and not shutil.which("npm"):
        fallar("Falta Node.js (trae npm). Instálelo desde https://nodejs.org (versión 20 o superior) y vuelva a correr este comando,\n"
               "    o use  python scripts/demo.py --solo-api  para levantar solo la API.")


def preparar_datos():
    destino = os.path.join(DATOS, "perfiles.json")
    if os.path.exists(destino):
        return
    origen = os.path.join(EJEMPLO, "perfiles.json")
    if not os.path.exists(origen):
        fallar("No encuentro el registro sintético. Copie perfiles.json (y los CSV) del hospital a la carpeta data/.\n"
               f"    Busqué en: {destino}\n    y en:      {origen}")
    os.makedirs(DATOS, exist_ok=True)
    for nombre in os.listdir(EJEMPLO):
        if nombre.endswith((".json", ".csv")):
            shutil.copy2(os.path.join(EJEMPLO, nombre), os.path.join(DATOS, nombre))
    print(f'Registro sintético copiado a data/ desde "docs/Datasets de ejemplo".')


def esperar(url, segundos, proceso):
    limite = time.time() + segundos
    while time.time() < limite:
        if proceso.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=2):
                return True
        except Exception:
            time.sleep(0.5)
    return False


def main():
    ap = argparse.ArgumentParser(description="Demostración local de Ambulatorio Dinámico HLF")
    ap.add_argument("--reglas", action="store_true")
    ap.add_argument("--bedrock", metavar="MODELO")
    ap.add_argument("--hoy", action="store_true")
    ap.add_argument("--solo-api", action="store_true")
    ap.add_argument("--sin-navegador", action="store_true")
    ap.add_argument("--puerto-api", type=int, default=3001)
    ap.add_argument("--puerto-web", type=int, default=5174)
    a = ap.parse_args()
    con_web = not a.solo_api

    revisar_requisitos(con_web)
    preparar_datos()

    env = dict(os.environ, LOCAL="1", DATA_DIR=DATOS, PYTHONUNBUFFERED="1", PYTHONUTF8="1",
               FECHA_REFERENCIA="hoy" if a.hoy else FECHA_REGISTRO, PUERTO=str(a.puerto_api))
    if a.reglas:
        env.update(ALGORITMO="reglas")
        env.pop("MODEL_ID", None)
        modo = "solo reglas (sin IA)"
    elif a.bedrock:
        env.update(ALGORITMO="rubrica", MODEL_ID=a.bedrock)
        env.setdefault("BEDROCK_REGION", "us-east-1")
        modo = f"IA con Amazon Bedrock ({a.bedrock}); usa las credenciales AWS de este computador"
    else:
        env.update(ALGORITMO="rubrica", MODEL_ID="simulado")
        modo = "IA SIMULADA (lector determinista, sin Bedrock)"

    procesos = []

    def detener(*_):
        for p in procesos:
            if p.poll() is None:
                p.terminate()
        time.sleep(0.5)
        for p in procesos:
            if p.poll() is None:
                p.kill()

    signal.signal(signal.SIGINT, lambda *_: (detener(), sys.exit(0)))
    api_url, web_url = f"http://localhost:{a.puerto_api}", f"http://localhost:{a.puerto_web}"
    try:
        print(f"Iniciando la API en {api_url} …")
        api = subprocess.Popen([sys.executable, "-X", "utf8", os.path.join(RAIZ, "lambda", "local_server.py")], cwd=RAIZ, env=env)
        procesos.append(api)
        if not esperar(api_url + "/health", 40, api):
            detener()
            fallar(f"La API no respondió. Revise el mensaje de error de arriba (¿el puerto {a.puerto_api} está ocupado?).")

        if con_web:
            front = os.path.join(RAIZ, "front")
            if not os.path.isdir(os.path.join(front, "node_modules")):
                print("Instalando las dependencias de la página (solo la primera vez, 1 a 3 minutos) …")
                if subprocess.call("npm ci --no-audit --no-fund", cwd=front, shell=True) != 0:
                    detener()
                    fallar("No se pudieron instalar las dependencias de la página (npm ci). Revise su conexión a internet.")
            print(f"Iniciando la página en {web_url} …")
            web = subprocess.Popen(f"npm run dev -- --port {a.puerto_web} --strictPort", cwd=front, shell=True,
                                   env=dict(env, VITE_API_URL=api_url))
            procesos.append(web)
            if not esperar(web_url, 60, web):
                detener()
                fallar(f"La página no respondió. Revise el mensaje de error de arriba (¿el puerto {a.puerto_web} está ocupado?).")

        print("\n" + "=" * 78)
        print("  Ambulatorio Dinámico HLF — demostración local (datos 100 % sintéticos)")
        print(f"  Página : {web_url if con_web else '(no iniciada)'}")
        print(f"  API    : {api_url}/health")
        print(f"  Modo   : {modo}")
        print(f"  Fecha  : {'hoy (hora de Chile)' if a.hoy else FECHA_REGISTRO + ' (fecha del registro sintético)'}")
        print("  Para detener: Ctrl+C. Al reiniciar, la demo vuelve a su estado inicial.")
        print("=" * 78 + "\n")
        if con_web and not a.sin_navegador:
            webbrowser.open(web_url)
        while all(p.poll() is None for p in procesos):
            time.sleep(1)
        print("Uno de los procesos terminó: se detiene la demostración.")
    finally:
        detener()


if __name__ == "__main__":
    main()
