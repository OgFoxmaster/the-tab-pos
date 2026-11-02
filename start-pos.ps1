$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $root 'the-tab-pos\backend'
$webDir = Join-Path $root 'the-tab-pos\web'

Write-Host 'Starting The Tab POS backend...'
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$backendDir'; & '$env:USERPROFILE\New folder (2)\.venv\Scripts\python.exe' -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

Write-Host 'Starting The Tab POS web dashboard...'
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$webDir'; npm run dev -- --host 0.0.0.0 --port 5173"

Write-Host 'The Tab POS is starting.'
Write-Host 'API: http://localhost:8000/docs'
Write-Host 'Web: http://localhost:5173'
