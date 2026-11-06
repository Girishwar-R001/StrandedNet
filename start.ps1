# One-command launcher for Windows: installs what's missing, builds the UI, serves everything
# on http://127.0.0.1:8000. Run from the project root:  powershell -ExecutionPolicy Bypass -File start.ps1
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

$python = Join-Path $root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    Write-Host 'Creating Python environment...'
    python -m venv (Join-Path $root 'backend\.venv')
    & $python -m pip install -q -r (Join-Path $root 'backend\requirements.txt')
}

Push-Location (Join-Path $root 'frontend')
if (-not (Test-Path 'node_modules')) {
    Write-Host 'Installing frontend packages...'
    npm install --silent
}
if (-not (Test-Path 'dist\index.html')) {
    Write-Host 'Building frontend...'
    npm run build --silent
}
Pop-Location

Write-Host ''
Write-Host 'The Stranded Network is starting: http://127.0.0.1:8000'
Write-Host 'Press Ctrl+C to stop.'
Push-Location (Join-Path $root 'backend')
try {
    & $python -m uvicorn app.main:app --port 8000
} finally {
    Pop-Location
}
