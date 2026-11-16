# Despliega el Ambulatorio Dinamico HLF en AWS desde PowerShell (Windows PowerShell 5.1 o PowerShell 7).
#
#   powershell -ExecutionPolicy Bypass -File scripts\deploy_aws.ps1                      # prueba: backend + datos + pagina
#   powershell -ExecutionPolicy Bypass -File scripts\deploy_aws.ps1 -Ambiente prod       # pide confirmacion
#   powershell -ExecutionPolicy Bypass -File scripts\deploy_aws.ps1 -SoloFront           # solo la pagina
#   powershell -ExecutionPolicy Bypass -File scripts\deploy_aws.ps1 -Parametros "ModelId=simulado CorreoAlertas=ti@hospital.cl"
#
# Este archivo solo busca un Python 3.11 o superior y le pasa los argumentos a scripts\desplegar.py, que es donde
# esta la logica (la misma que usa scripts/desplegar.sh). No tiene rutas ni perfiles fijos: usa aws, sam y npm del PATH
# y avisa si falta alguno. El modo de IA, el stack y la region salen de samconfig.toml.
# Sin tildes a proposito: Windows PowerShell 5.1 lee mal los archivos UTF-8 sin BOM.
param(
    [ValidateSet("prueba", "prod")][string]$Ambiente = "prueba",
    [switch]$SoloFront,       # solo compila y publica la pagina
    [switch]$SoloBackend,     # no publica la pagina
    [switch]$SinTests,        # solo para volver atras a una version ya probada
    [switch]$SinDatos,        # no carga el registro sintetico
    [switch]$RecargarDatos,   # carga el registro sintetico aunque la tabla ya tenga pacientes
    [switch]$Si,              # no pedir confirmacion (pipeline con aprobacion previa)
    [string]$Parametros = "", # "Clave=Valor Clave2=Valor2": pisan los de samconfig.toml en este despliegue
    [string]$Region = "",     # por defecto, la de samconfig.toml
    [string]$Perfil = "",     # perfil de AWS CLI; por defecto, las credenciales activas
    [string]$AppAmplify = ""  # aplicacion de Amplify donde publicar; por defecto, la que crea el stack
)
$raiz = Split-Path -Parent $PSScriptRoot

# Existe y es 3.11+. En Windows "python3" puede ser el acceso directo a la Tienda, que no es un Python: por eso se prueba.
function Test-Python([string]$comando) {
    if (-not (Get-Command $comando -ErrorAction SilentlyContinue)) { return $false }
    try { & $comando -c "import sys; sys.exit(sys.version_info < (3, 11))" 2>$null | Out-Null } catch { return $false }
    return $LASTEXITCODE -eq 0
}

# Tiene instalado requirements-dev.txt. Cuando hay varios Python en el computador se prefiere ese.
function Test-Dependencias([string]$comando) {
    try { & $comando -c "import importlib.util as u, sys; sys.exit(not all(u.find_spec(m) for m in ('yaml', 'cfnlint', 'pytest')))" 2>$null | Out-Null } catch { return $false }
    return $LASTEXITCODE -eq 0
}

$python = $null
if ($env:PYTHON) {
    if (-not (Test-Python $env:PYTHON)) { Write-Host "ERROR: PYTHON=$($env:PYTHON) no existe o es anterior a Python 3.11." -ForegroundColor Red; exit 1 }
    $python = $env:PYTHON
} else {
    $primero = $null
    foreach ($candidato in "python", "python3", "py") {
        if (-not (Test-Python $candidato)) { continue }
        if (-not $primero) { $primero = $candidato }
        if (Test-Dependencias $candidato) { $python = $candidato; break }
    }
    if (-not $python) { $python = $primero }  # ninguno tiene las dependencias: desplegar.py dira cual falta y como instalarla
}
if (-not $python) {
    Write-Host "ERROR: no encuentro Python 3.11 o superior en el PATH." -ForegroundColor Red
    Write-Host "  Instale Python 3.12 (el mismo de la Lambda) desde https://www.python.org/downloads/ y abra una terminal nueva."
    Write-Host "  Si esta instalado en otra ruta: `$env:PYTHON = 'C:\ruta\python.exe'"
    exit 1
}

$argumentos = @((Join-Path $raiz "scripts\desplegar.py"), $Ambiente)
if ($SoloFront) { $argumentos += "--solo-front" }
if ($SoloBackend) { $argumentos += "--solo-backend" }
if ($SinTests) { $argumentos += "--sin-tests" }
if ($SinDatos) { $argumentos += "--sin-datos" }
if ($RecargarDatos) { $argumentos += "--recargar-datos" }
if ($Si) { $argumentos += "--si" }
if ($Parametros) { $argumentos += @("--parametros", $Parametros) }
if ($Region) { $argumentos += @("--region", $Region) }
if ($Perfil) { $argumentos += @("--perfil", $Perfil) }
if ($AppAmplify) { $argumentos += @("--app-amplify", $AppAmplify) }

& $python @argumentos
exit $LASTEXITCODE
