param(
    [switch]$ExeOnly,
    [switch]$SkipClean
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path $PSScriptRoot -Parent
$RecorderDir = Join-Path $ProjectRoot "feature_recorder"
$ReleaseDir = Join-Path (Join-Path $RecorderDir "release") "recorder"
$ZipPath = Join-Path (Join-Path $RecorderDir "release") "feature-recorder-win64.zip"

if (-not (Test-Path $RecorderDir)) {
    Write-Host "feature_recorder directory not found" -ForegroundColor Red
    exit 1
}

Set-Location $RecorderDir

if (-not (Test-Path "node_modules")) {
    Write-Host "[deps] npm install..." -ForegroundColor Cyan
    npm install
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

$buildArgs = @()
if ($ExeOnly) { $buildArgs += "-SkipChromium" }
if ($SkipClean) { $buildArgs += "-SkipClean" }

Write-Host "[build] build:trial $(($buildArgs -join ' '))..." -ForegroundColor Cyan
if ($buildArgs.Count -gt 0) {
    powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path (Join-Path $RecorderDir "scripts") "build-trial.ps1") @buildArgs
} else {
    npm run build:trial
}
if ($LASTEXITCODE -ne 0) { exit 1 }

$exePath = Join-Path $ReleaseDir "feature-recorder.cmd"
$nodeExe = Join-Path (Join-Path $ReleaseDir "node") "node.exe"
if (-not (Test-Path $exePath) -or -not (Test-Path $nodeExe)) {
    Write-Host "Launcher not found. Expected:" -ForegroundColor Red
    Write-Host "  $exePath"
    Write-Host "  $nodeExe"
    exit 1
}

if ($ExeOnly) {
    Write-Host ""
    Write-Host "ExeOnly: zip skipped. Full package: .\scripts\build_feature_recorder.ps1" -ForegroundColor Yellow
    Write-Host "  launcher: $exePath"
    exit 0
}

Write-Host "[zip] create feature-recorder-win64.zip ..." -ForegroundColor Cyan
$zipParent = Split-Path $ZipPath -Parent
if (-not (Test-Path $zipParent)) {
    New-Item -ItemType Directory -Path $zipParent -Force | Out-Null
}
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path (Join-Path $ReleaseDir "*") -DestinationPath $ZipPath -Force

Write-Host "[test] smoke-test zip API ..." -ForegroundColor Cyan
powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path (Join-Path $RecorderDir "scripts") "smoke-test-zip-api.ps1")
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host ""
Write-Host "Done" -ForegroundColor Green
Write-Host "  launcher: $exePath"
Write-Host "  ZIP: $ZipPath"
Write-Host "Restart backend to sync zip to tool hub."
