#!/usr/bin/env bash
# Despliega el Ambulatorio Dinamico HLF en AWS desde Linux, macOS, AWS CloudShell o Git Bash.
#
#   scripts/desplegar.sh prueba                      # backend + datos sinteticos + pagina
#   scripts/desplegar.sh prod                        # pide confirmacion
#   scripts/desplegar.sh prueba --solo-front         # solo la pagina
#   scripts/desplegar.sh --help                      # todas las opciones
#
# Este archivo solo elige el Python y le pasa los argumentos a scripts/desplegar.py, que es donde esta la logica
# (la misma que usa scripts/deploy_aws.ps1 en PowerShell). Otro interprete: PYTHON=python3.12 scripts/desplegar.sh
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Existe y es 3.11 o superior (en Windows "python3" puede ser el acceso directo a la Tienda, que no es un Python).
sirve() {
  command -v "$1" >/dev/null 2>&1 && "$1" -c 'import sys; sys.exit(sys.version_info < (3, 11))' >/dev/null 2>&1
}
# Tiene instalado requirements-dev.txt. Cuando hay varios Python en el computador se prefiere ese.
con_dependencias() {
  "$1" -c 'import importlib.util as u, sys; sys.exit(not all(u.find_spec(m) for m in ("yaml", "cfnlint", "pytest")))' >/dev/null 2>&1
}

PY="${PYTHON:-}"
if [ -n "$PY" ]; then
  sirve "$PY" || { echo "ERROR: PYTHON=$PY no existe o es anterior a Python 3.11." >&2; exit 1; }
else
  primero=""
  for candidato in python python3 python3.13 python3.12 python3.11; do
    sirve "$candidato" || continue
    [ -n "$primero" ] || primero="$candidato"
    if con_dependencias "$candidato"; then PY="$candidato"; break; fi
  done
  PY="${PY:-$primero}"  # ninguno tiene las dependencias: desplegar.py dira cual falta y como instalarla
fi
if [ -z "$PY" ]; then
  echo "ERROR: no encuentro Python 3.11 o superior en el PATH." >&2
  echo "  Instale Python 3.12 (el mismo de la Lambda). En AWS CloudShell: sudo dnf install -y python3.12 python3.12-pip" >&2
  echo "  Si esta instalado con otro nombre: PYTHON=/ruta/a/python scripts/desplegar.sh ..." >&2
  exit 1
fi

exec "$PY" "$RAIZ/scripts/desplegar.py" "$@"
