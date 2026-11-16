# Levanta la demo local (API en localhost:3001 y pagina en localhost:5174) desde PowerShell.
#
# Este archivo solo delega en scripts\demo.py, el lanzador unico de la demo (Windows, macOS y Linux): asi no hay dos
# lanzadores distintos que mantener. Las opciones son las mismas de demo.py, escritas al estilo de PowerShell:
#
#   powershell -ExecutionPolicy Bypass -File scripts\iniciar_demo.ps1                 # IA simulada, sin AWS
#   powershell -ExecutionPolicy Bypass -File scripts\iniciar_demo.ps1 -Reglas         # solo reglas, sin IA
#   powershell -ExecutionPolicy Bypass -File scripts\iniciar_demo.ps1 -Bedrock us.anthropic.claude-sonnet-5-5
#   -Hoy  -SoloApi  -SinNavegador  -PuertoApi 3001  -PuertoWeb 5174                   # igual que en demo.py
#
# Se conservan las opciones de la version anterior de este script:
#   -ConAWS [-Modelo ID]   equivale a -Bedrock ID (por defecto us.anthropic.claude-sonnet-5-5)
#   -Perfil NOMBRE         perfil de AWS CLI (por defecto, las credenciales activas)
#   -Region REGION         region de Bedrock y Textract (por defecto la de demo.py: us-east-1)
# En Linux o macOS:  python3 scripts/demo.py
# Sin tildes a proposito: Windows PowerShell 5.1 lee mal los archivos UTF-8 sin BOM.
param(
    [switch]$Reglas,
    [string]$Bedrock = "",
    [switch]$Hoy,
    [switch]$SoloApi,
    [switch]$SinNavegador,
    [int]$PuertoApi = 0,
    [int]$PuertoWeb = 0,
    [Alias("ConBedrock")][switch]$ConAWS,
    [string]$Modelo = "us.anthropic.claude-sonnet-5-5",
    [string]$Perfil = "",
    [string]$Region = ""
)
$raiz = Split-Path -Parent $PSScriptRoot

# Existe y es 3.11+. En Windows "python3" puede ser el acceso directo a la Tienda, que no es un Python: por eso se prueba.
function Test-Python([string]$comando) {
    if (-not (Get-Command $comando -ErrorAction SilentlyContinue)) { return $false }
    try { & $comando -c "import sys; sys.exit(sys.version_info < (3, 11))" 2>$null | Out-Null } catch { return $false }
    return $LASTEXITCODE -eq 0
}

$python = $null
if ($env:PYTHON) {
    if (-not (Test-Python $env:PYTHON)) { Write-Host "ERROR: PYTHON=$($env:PYTHON) no existe o es anterior a Python 3.11." -ForegroundColor Red; exit 1 }
    $python = $env:PYTHON
} else {
    foreach ($candidato in "python", "python3", "py") { if (Test-Python $candidato) { $python = $candidato; break } }
}
if (-not $python) {
    Write-Host "ERROR: no encuentro Python 3.11 o superior en el PATH." -ForegroundColor Red
    Write-Host "  Instale Python 3.12 desde https://www.python.org/downloads/ y abra una terminal nueva."
    exit 1
}

if ($ConAWS -and -not $Bedrock) { $Bedrock = $Modelo }
if ($Perfil) { $env:AWS_PROFILE = $Perfil }
if ($Region) { $env:BEDROCK_REGION = $Region }

$argumentos = @((Join-Path $raiz "scripts\demo.py"))
if ($Reglas) { $argumentos += "--reglas" }
if ($Bedrock) { $argumentos += @("--bedrock", $Bedrock) }
if ($Hoy) { $argumentos += "--hoy" }
if ($SoloApi) { $argumentos += "--solo-api" }
if ($SinNavegador) { $argumentos += "--sin-navegador" }
if ($PuertoApi) { $argumentos += @("--puerto-api", $PuertoApi) }
if ($PuertoWeb) { $argumentos += @("--puerto-web", $PuertoWeb) }

& $python @argumentos
exit $LASTEXITCODE
