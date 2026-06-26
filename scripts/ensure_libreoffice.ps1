# Ensure LibreOffice works for .doc conversion (Windows)
# Usage: powershell -ExecutionPolicy Bypass -File scripts\ensure_libreoffice.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot | Split-Path -Parent
$LoProgram = Join-Path $ProjectRoot "tools\LibreOffice\program"
$SofficeCom = Join-Path $LoProgram "soffice.com"
$SofficeExe = Join-Path $LoProgram "soffice.exe"
$ProfileDir = Join-Path $ProjectRoot "data\libreoffice_profile"
$VcRedist = Join-Path $env:TEMP "vc_redist.x64.exe"

function Get-SofficePath {
    if (Test-Path $SofficeCom) { return $SofficeCom }
    if (Test-Path $SofficeExe) { return $SofficeExe }
    $envPath = $env:LIBREOFFICE_SOFFICE_PATH
    if ($envPath -and (Test-Path $envPath)) { return $envPath }
    $system = "C:\Program Files\LibreOffice\program\soffice.com"
    if (Test-Path $system) { return $system }
    return $null
}

function Test-LibreOfficeRun {
    param([string]$SofficePath)
    if (-not $SofficePath) { return $false }
    New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null
    $profileUri = ([System.Uri]((Resolve-Path $ProfileDir).Path)).AbsoluteUri
    $progDir = Split-Path $SofficePath -Parent
    $loArgs = @("--headless", "-env:UserInstallation=$profileUri", "--version")
    $proc = Start-Process -FilePath $SofficePath -ArgumentList $loArgs -WorkingDirectory $progDir -Wait -PassThru -NoNewWindow
    return ($proc.ExitCode -eq 0)
}

Write-Host "=== LibreOffice check ===" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"

$soffice = Get-SofficePath
if (-not $soffice) {
    Write-Host "LibreOffice not found. Install to tools\LibreOffice or set LIBREOFFICE_SOFFICE_PATH." -ForegroundColor Red
    exit 1
}
Write-Host "soffice: $soffice"

if (Test-LibreOfficeRun -SofficePath $soffice) {
    Write-Host "LibreOffice OK." -ForegroundColor Green
    exit 0
}

Write-Host "LibreOffice failed to start. Installing VC++ 2015-2022 x64..." -ForegroundColor Yellow
if (-not (Test-Path $VcRedist)) {
    Invoke-WebRequest -Uri "https://aka.ms/vs/17/release/vc_redist.x64.exe" -OutFile $VcRedist -UseBasicParsing
}
Start-Process -FilePath $VcRedist -ArgumentList "/install", "/quiet", "/norestart" -Wait | Out-Null

if (Test-LibreOfficeRun -SofficePath $soffice) {
    Write-Host "LibreOffice OK after VC++ install." -ForegroundColor Green
    exit 0
}

Write-Host "LibreOffice still unavailable. Check tools\LibreOffice or set LIBREOFFICE_SOFFICE_PATH in .env" -ForegroundColor Red
exit 1
