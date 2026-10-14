# HomeServer V2 — Windows Shutdown Script
# Copyright 2026 Aswin A — Licensed under Apache 2.0
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
Set-Location $ProjectDir

Write-Host "Stopping HomeServer V2 services..."
docker compose down
Write-Host "All HomeServer V2 services have been stopped." -ForegroundColor Green
Write-Host "  Your data and database are preserved."
Write-Host "  Run scripts\start.ps1 to restart."
