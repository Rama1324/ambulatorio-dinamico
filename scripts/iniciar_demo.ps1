# Levanta la demo en local: API (localhost:3001) y front (localhost:5174), cada uno en su ventana.
# Uso, desde la raíz del repo:
#   powershell -ExecutionPolicy Bypass -File scripts\iniciar_demo.ps1              # sin IA (plantilla y palabras clave)
#   powershell -ExecutionPolicy Bypass -File scripts\iniciar_demo.ps1 -ConBedrock  # con Bedrock (perfil AWS "hack")
param([switch]$ConBedrock, [string]$Modelo = "us.anthropic.claude-sonnet-5", [string]$Perfil = "hack")

$raiz = Split-Path -Parent $PSScriptRoot
$ia = ""
if ($ConBedrock) {
    $ia = "`$env:AWS_PROFILE='$Perfil'; `$env:MODEL_ID='$Modelo'; `$env:BEDROCK_REGION='us-east-1'; "
    & "C:\Program Files\Amazon\AWSCLIV2\aws.exe" sts get-caller-identity --profile $Perfil --query Account --output text 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Las credenciales del perfil '$Perfil' vencieron o no existen. Saca nuevas del portal del evento" -ForegroundColor Yellow
        Write-Host "(Access keys > 'Add a profile to your AWS credentials file') y pégalas en $env:USERPROFILE\.aws\credentials como [$Perfil]." -ForegroundColor Yellow
        exit 1
    }
}
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$raiz'; `$env:PYTHONUNBUFFERED='1'; `$env:LOCAL='1'; `$env:DATA_DIR='data'; $ia python -X utf8 lambda/local_server.py"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$raiz\front'; npm run dev -- --port 5174"
Start-Sleep 6
Start-Process "http://localhost:5174"
Write-Host ("Demo iniciada " + ($(if ($ConBedrock) { "CON Bedrock ($Modelo)" } else { "sin Bedrock" })))
