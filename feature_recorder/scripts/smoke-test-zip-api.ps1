# Dashboard ZIP API smoke test (run after build)
# Usage: powershell -File scripts/smoke-test-zip-api.ps1

$ErrorActionPreference = "Stop"

$RecorderRoot = Split-Path $PSScriptRoot -Parent
$ReleaseDir = Join-Path (Join-Path $RecorderRoot "release") "recorder"
$NodeExe = Join-Path (Join-Path $ReleaseDir "node") "node.exe"
$Bundle = Join-Path (Join-Path $ReleaseDir "app") "app.bundle.cjs"
$OutputDir = Join-Path $ReleaseDir "output"
$Port = 3000
$TestRunId = "run_smoke_test"
$TestRunDir = Join-Path $OutputDir $TestRunId
$TestZip = Join-Path $OutputDir "$TestRunId.zip"

function Stop-PortListener {
    param([int]$ListenPort)
    $lines = netstat -ano | Select-String ":$ListenPort\s" | Select-String "LISTENING"
    foreach ($line in $lines) {
        $procId = ($line.ToString().Trim() -split '\s+')[-1]
        if ($procId -match '^\d+$' -and $procId -ne '0') {
            taskkill /PID $procId /F | Out-Null
        }
    }
    Start-Sleep -Milliseconds 800
}

function Invoke-Api {
    param(
        [string]$Method,
        [string]$Path,
        [byte[]]$Body = $null
    )
    $req = [System.Net.WebRequest]::Create("http://127.0.0.1:$Port$Path")
    $req.Method = $Method
    $req.Timeout = 30000
    if ($Body -ne $null) {
        $req.ContentType = "application/json"
        $req.ContentLength = $Body.Length
        $stream = $req.GetRequestStream()
        $stream.Write($Body, 0, $Body.Length)
        $stream.Close()
    }
    try {
        $resp = $req.GetResponse()
        $reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
        $text = $reader.ReadToEnd()
        return [int]$resp.StatusCode, $text
    } catch [System.Net.WebException] {
        $resp = $_.Exception.Response
        if ($resp -eq $null) { throw }
        $reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
        $text = $reader.ReadToEnd()
        return [int]$resp.StatusCode, $text
    }
}

if (-not (Test-Path $NodeExe)) { throw "node.exe not found: $NodeExe" }
if (-not (Test-Path $Bundle)) { throw "bundle not found: $Bundle" }

Write-Host "[smoke] prepare test run dir..." -ForegroundColor Cyan
if (Test-Path $TestZip) { Remove-Item $TestZip -Force }
if (Test-Path $TestRunDir) { Remove-Item $TestRunDir -Recurse -Force }
New-Item -ItemType Directory -Path $TestRunDir -Force | Out-Null
$meta = @{
    version = "1.0"
    targetUrl = "https://example.com"
    recordStartTime = (Get-Date).ToUniversalTime().ToString("o")
    recordEndTime = (Get-Date).ToUniversalTime().ToString("o")
    totalActions = 0
    actions = @()
} | ConvertTo-Json -Depth 4
Set-Content -Path (Join-Path $TestRunDir "meta.json") -Value $meta -Encoding UTF8

Write-Host "[smoke] start dashboard..." -ForegroundColor Cyan
Stop-PortListener -ListenPort $Port
$env:APP_MODE = "dashboard"
$proc = Start-Process -FilePath $NodeExe -ArgumentList "`"$Bundle`"" -WorkingDirectory $ReleaseDir -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 3

try {
    $statusCode, $statusBody = Invoke-Api -Method "GET" -Path "/api/status"
    if ($statusCode -ne 200) { throw "status failed: $statusCode $statusBody" }
    if ($statusBody -notmatch 'runZipApi') {
        throw "bundle missing runZipApi flag in /api/status: $statusBody"
    }
    Write-Host "  /api/status OK (runZipApi=true)" -ForegroundColor Green

    $zipCode, $zipBody = Invoke-Api -Method "POST" -Path "/api/runs/$TestRunId/zip" -Body ([byte[]]@())
    if ($zipCode -ne 200) { throw "zip create failed: $zipCode $zipBody" }
    if (-not (Test-Path $TestZip)) { throw "zip file missing: $TestZip" }
    $zipSize = (Get-Item $TestZip).Length
    if ($zipSize -lt 100) { throw "zip too small: $zipSize bytes" }
    Write-Host "  POST /api/runs/:id/zip OK ($zipSize bytes)" -ForegroundColor Green

    $dlCode, $dlBody = Invoke-Api -Method "GET" -Path "/api/runs/$TestRunId/download"
    if ($dlCode -ne 200) { throw "zip download failed: $dlCode" }
    Write-Host "  GET /api/runs/:id/download OK" -ForegroundColor Green

    Write-Host "[smoke] PASS" -ForegroundColor Green
}
finally {
    if ($proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
    Stop-PortListener -ListenPort $Port
    if (Test-Path $TestZip) { Remove-Item $TestZip -Force }
    if (Test-Path $TestRunDir) { Remove-Item $TestRunDir -Recurse -Force }
}
