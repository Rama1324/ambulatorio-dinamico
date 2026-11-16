"""Servidor local para probar la API sin AWS.
Uso (desde la raíz del proyecto):  LOCAL=1 DATA_DIR=data python lambda/local_server.py
En Windows PowerShell:  $env:LOCAL="1"; $env:DATA_DIR="data"; python lambda/local_server.py
Queda en http://localhost:3001 (o el puerto de la variable PUERTO) → en front/.env.local poner VITE_API_URL=http://localhost:3001

Arma el mismo evento que API Gateway HTTP API (método, ruta, consulta, cabeceras, cuerpo). Nunca copia nada de la
solicitud a requestContext.authorizer: aquí no hay autorizador JWT, así que con AUTH=cognito todo responde 401."""
import base64, os, socket, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qsl
os.environ.setdefault("LOCAL", "1"); os.environ.setdefault("DATA_DIR", "data")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app

PUERTO = int(os.environ.get("PUERTO") or 3001)


class H(BaseHTTPRequestHandler):
    def _go(self, method):
        u = urlparse(self.path)
        n = int(self.headers.get("content-length") or 0)
        ev = {"requestContext": {"http": {"method": method}}, "rawPath": u.path,
              "queryStringParameters": dict(parse_qsl(u.query)) or None,
              "headers": {k.lower(): v for k, v in self.headers.items()},
              "body": self.rfile.read(n).decode("utf-8") if n else None}
        r = app.handler(ev)
        cuerpo = r.get("body") or ""
        cuerpo = base64.b64decode(cuerpo) if r.get("isBase64Encoded") else cuerpo.encode("utf-8")  # gzip: llega en base64
        self.send_response(r["statusCode"])
        for k, v in r["headers"].items(): self.send_header(k, v)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers(); self.wfile.write(cuerpo)
    def do_GET(self): self._go("GET")
    def do_POST(self): self._go("POST")
    def do_OPTIONS(self): self._go("OPTIONS")


class DualStack(ThreadingHTTPServer):
    """Escucha en IPv4 e IPv6: en Windows 'localhost' prueba primero ::1 y, si no responde, espera ~2 s."""
    address_family = socket.AF_INET6

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()


if __name__ == "__main__":
    print(f"API local en http://localhost:{PUERTO}")
    try:
        DualStack(("::", PUERTO), H).serve_forever()
    except OSError:
        ThreadingHTTPServer(("127.0.0.1", PUERTO), H).serve_forever()  # solo este computador
