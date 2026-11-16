# Single-command production runner for Windows (PowerShell)
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir

Write-Host "==> Preparing BuildSprint Production Deployment..." -ForegroundColor Cyan

# 1. Frontend Build
Set-Location "$rootDir\frontend"
if (-not (Test-Path "node_modules")) {
    Write-Host "==> Installing frontend dependencies..." -ForegroundColor Yellow
    npm install
}
Write-Host "==> Building frontend assets for single-origin distribution..." -ForegroundColor Yellow
npm run build

# 2. Python Environment & Server
Set-Location $rootDir
$py = "python"
if (Test-Path "$rootDir\.venv\Scripts\python.exe") {
    $py = "$rootDir\.venv\Scripts\python.exe"
}

if (-not $env:APP_ENV) { $env:APP_ENV = "production" }
if (-not $env:HOST) { $env:HOST = "0.0.0.0" }
if (-not $env:PORT) { $env:PORT = "8000" }

Write-Host "==> Starting single-origin server on http://$($env:HOST):$($env:PORT) [APP_ENV=$($env:APP_ENV)]..." -ForegroundColor Green

& $py -m uvicorn app.main:app --app-dir backend --host $env:HOST --port $env:PORT
