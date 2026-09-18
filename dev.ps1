# Levanta el entorno de desarrollo completo en dos ventanas:
#   - backend  FastAPI con recarga en http://127.0.0.1:8000
#   - frontend Vite con proxy en  http://localhost:5173  <- abre esta
#
#   .\dev.ps1

$root = $PSScriptRoot

if (-not (Test-Path (Join-Path $root 'frontend\node_modules'))) {
    Write-Host 'Instalando dependencias del frontend...' -ForegroundColor Yellow
    Push-Location (Join-Path $root 'frontend')
    npm install
    Pop-Location
}

Write-Host 'Backend  -> http://127.0.0.1:8000' -ForegroundColor Green
Start-Process powershell -ArgumentList '-NoExit', '-Command',
    "Set-Location '$root\backend'; python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"

Write-Host 'Frontend -> http://localhost:5173' -ForegroundColor Green
Start-Process powershell -ArgumentList '-NoExit', '-Command',
    "Set-Location '$root\frontend'; npm run dev"
