# HomeServer V2 — Windows PowerShell Startup Script
# Copyright 2026 Aswin A
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
Set-Location $ProjectDir

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  HomeServer V2 — Startup" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. Check Docker ──────────────────────────────
try {
    $null = docker info 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Docker not running" }
    Write-Host "[OK] Docker is available." -ForegroundColor Green
} catch {
    Write-Host "ERROR: Docker is not installed or not running." -ForegroundColor Red
    Write-Host "  Install Docker Desktop: https://docs.docker.com/desktop/install/windows-install/"
    exit 1
}

# ── 2. Check Docker Compose ──────────────────────
try {
    $composeVersion = docker compose version --short 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Compose not found" }
    Write-Host "[OK] Docker Compose $composeVersion detected." -ForegroundColor Green
} catch {
    Write-Host "ERROR: Docker Compose (v2) is not available." -ForegroundColor Red
    Write-Host "  Docker Desktop includes Compose. Update Docker Desktop if needed."
    exit 1
}

# ── 3. Check .env ────────────────────────────────
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host ""
    Write-Host "IMPORTANT: .env was created from .env.example." -ForegroundColor Yellow
    Write-Host "  You MUST edit .env and set secure values for:"
    Write-Host "    - SECRET_KEY          (unique random string, 32+ characters)"
    Write-Host "    - POSTGRES_PASSWORD   (unique database password)"
    Write-Host ""
    Write-Host "  Generate a secret in PowerShell:"
    Write-Host '    [Convert]::ToBase64String((1..48 | ForEach-Object { Get-Random -Max 256 }) -as [byte[]])'
    Write-Host ""
    Write-Host "  Edit .env, then re-run this script."
    exit 0
}

# Validate secrets
$envContent = Get-Content ".env" -Raw
$secretKey = ($envContent | Select-String "^SECRET_KEY=(.+)$" -AllMatches).Matches | ForEach-Object { $_.Groups[1].Value.Trim() }
$dbPassword = ($envContent | Select-String "^POSTGRES_PASSWORD=(.+)$" -AllMatches).Matches | ForEach-Object { $_.Groups[1].Value.Trim() }

if (-not $secretKey -or $secretKey -eq "replace-with-a-unique-random-secret-at-least-32-characters") {
    Write-Host "ERROR: SECRET_KEY in .env is not set or is still the placeholder." -ForegroundColor Red
    exit 1
}
if (-not $dbPassword -or $dbPassword -eq "replace-with-a-unique-database-password") {
    Write-Host "ERROR: POSTGRES_PASSWORD in .env is not set or is still the placeholder." -ForegroundColor Red
    exit 1
}

Write-Host "[OK] .env validated." -ForegroundColor Green

# ── 4. Create data directory ─────────────────────
$dataDir = if ($envContent -match "HOST_DATA_PATH=(.+)") { $Matches[1].Trim() } else { "./data" }
if (-not (Test-Path $dataDir)) { New-Item -ItemType Directory -Path $dataDir | Out-Null }
Write-Host "[OK] Data directory: $dataDir" -ForegroundColor Green

# ── 5. Build and start ───────────────────────────
Write-Host ""
Write-Host "Building and starting HomeServer V2 services..."
Write-Host "  (First run may take a few minutes to download base images and build.)"
Write-Host ""

docker compose up -d --build

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Docker Compose failed to start services." -ForegroundColor Red
    Write-Host "  Check: docker compose logs"
    exit 1
}

# ── 6. Wait for health ──────────────────────────
$frontendPort = if ($envContent -match "FRONTEND_PORT=(\d+)") { $Matches[1] } else { "8081" }
$publicUrl = if ($envContent -match "PUBLIC_BASE_URL=(.+)") { $Matches[1].Trim() } else { "http://localhost:$frontendPort" }
$healthUrl = "http://localhost:${frontendPort}/health/ready"

Write-Host "Waiting for backend to become healthy..."
$attempts = 0
$maxAttempts = 60
while ($attempts -lt $maxAttempts) {
    try {
        $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 3 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) { break }
    } catch { }
    $attempts++
    Start-Sleep -Seconds 3
    Write-Host -NoNewline "."
}

if ($attempts -ge $maxAttempts) {
    Write-Host ""
    Write-Host "WARNING: Backend did not become ready in time." -ForegroundColor Yellow
    Write-Host "  Check logs: docker compose logs homeserver-v2-backend"
    exit 1
}

Write-Host ""
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  HomeServer V2 is running!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Application:  $publicUrl"
Write-Host "  Mailpit UI:   http://localhost:$( if ($envContent -match 'MAILPIT_UI_PORT=(\d+)') { $Matches[1] } else { '8025' } )  (dev email viewer)"
Write-Host ""
Write-Host "  First time? Open the application URL and create"
Write-Host "  your administrator account on the setup page."
Write-Host ""
Write-Host "  Stop services:    docker compose down"
Write-Host "  View logs:        docker compose logs -f"
Write-Host "  Restart:          docker compose restart"
Write-Host ""
