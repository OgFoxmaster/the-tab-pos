$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $root 'the-tab-pos\backend'
$webDir = Join-Path $root 'the-tab-pos\web'

Write-Host 'Installing backend dependencies...'
& "$env:USERPROFILE\New folder (2)\.venv\Scripts\python.exe" -m pip install -r (Join-Path $backendDir 'requirements.txt')

Write-Host 'Installing web dependencies...'
Set-Location $webDir
npm install

Write-Host 'Setup complete.'
