# Levanta el entorno de desarrollo completo en dos ventanas y abre la web:
#   - backend  FastAPI con recarga en http://127.0.0.1:8000
#   - frontend Vite con proxy en  http://localhost:5173  <- se abre sola
#
#   .\web.ps1

$root = $PSScriptRoot
$url = 'http://localhost:5173'

if (-not (Test-Path (Join-Path $root 'frontend\node_modules'))) {
    Write-Host 'Instalando dependencias del frontend...' -ForegroundColor Yellow
    Push-Location (Join-Path $root 'frontend')
    npm install
    Pop-Location
}

Write-Host 'Backend  -> http://127.0.0.1:8000' -ForegroundColor Green
Start-Process powershell -ArgumentList '-NoExit', '-Command',
    "Set-Location '$root\backend'; python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"

Write-Host "Frontend -> $url" -ForegroundColor Green
Start-Process powershell -ArgumentList '-NoExit', '-Command',
    "Set-Location '$root\frontend'; npm run dev"

# Espera a que Vite responda (hasta 60 s) y abre el navegador por defecto.
Write-Host 'Esperando a que arranque la web...' -ForegroundColor Yellow
$ready = $false
for ($i = 0; $i -lt 60 -and -not $ready; $i++) {
    try {
        Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 | Out-Null
        $ready = $true
    } catch {
        Start-Sleep -Seconds 1
    }
}

if ($ready) {
    Write-Host "Abriendo $url" -ForegroundColor Green
} else {
    Write-Host "La web no respondio a tiempo; se abre igualmente $url" -ForegroundColor Yellow
}
Start-Process $url
