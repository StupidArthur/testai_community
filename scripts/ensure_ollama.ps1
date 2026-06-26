# Ensure Ollama is running and required models are present (Windows)
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\ensure_ollama.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\ensure_ollama.ps1 -SkipPull
#
# Production: install Ollama once, enable auto-start (installer default), run this script
# in deploy checklist OR register as Scheduled Task at boot. Models pull only once.

param(
    [switch]$SkipPull,
    [int]$StartupTimeoutSec = 45
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot | Split-Path -Parent
$EnvFile = Join-Path $ProjectRoot ".env"

function Read-DotEnv {
    param([string]$Path)
    $map = @{}
    if (-not (Test-Path $Path)) { return $map }
    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if ($line -eq "" -or $line.StartsWith("#")) { return }
        if ($line -match '^\s*([^#=]+?)\s*=\s*(.*)$') {
            $map[$Matches[1].Trim()] = $Matches[2].Trim()
        }
    }
    return $map
}

function Find-OllamaExe {
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { return $cmd.Source }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"),
        "C:\Program Files\Ollama\ollama.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

function Get-OllamaBaseUrl {
    param([hashtable]$EnvVars)
    $url = $EnvVars["OLLAMA_BASE_URL"]
    if (-not $url) { $url = "http://127.0.0.1:11434" }
    return $url.TrimEnd("/")
}

function Test-OllamaApi {
    param([string]$BaseUrl)
    try {
        $resp = Invoke-WebRequest -Uri "$BaseUrl/api/tags" -UseBasicParsing -TimeoutSec 3
        return ($resp.StatusCode -eq 200)
    } catch {
        return $false
    }
}

function Get-InstalledModelNames {
    param([string]$BaseUrl)
    try {
        $json = Invoke-RestMethod -Uri "$BaseUrl/api/tags" -TimeoutSec 10
        $names = @()
        foreach ($m in $json.models) {
            if ($m.name) { $names += [string]$m.name }
        }
        return $names
    } catch {
        return @()
    }
}

function Test-ModelInstalled {
    param(
        [string[]]$Installed,
        [string]$Wanted
    )
    if (-not $Wanted) { return $true }
    $base = $Wanted.Split(":")[0]
    foreach ($n in $Installed) {
        $nb = $n.Split(":")[0]
        if ($n -eq $Wanted -or $n -eq "$base`:latest" -or $nb -eq $base) {
            return $true
        }
    }
    return $false
}

function Wait-OllamaReady {
    param(
        [string]$BaseUrl,
        [int]$TimeoutSec
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-OllamaApi -BaseUrl $BaseUrl) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Start-OllamaServe {
    param([string]$OllamaExe)
    Write-Host "  starting: ollama serve" -ForegroundColor Yellow
    Start-Process -FilePath $OllamaExe -ArgumentList "serve" -WindowStyle Hidden | Out-Null
}

# ---------- main ----------

Write-Host ""
Write-Host "=== Ollama check ===" -ForegroundColor Cyan

$envVars = Read-DotEnv -Path $EnvFile
$baseUrl = Get-OllamaBaseUrl -EnvVars $envVars
$embedModel = if ($envVars["OLLAMA_EMBED_MODEL"]) { $envVars["OLLAMA_EMBED_MODEL"].Trim() } else { "bge-m3" }
$vlModel = if ($envVars["OLLAMA_VL_MODEL"]) { $envVars["OLLAMA_VL_MODEL"].Trim() } else { "qwen2.5vl:7b" }
# 单元素数组用 += 会被 PowerShell 当成字符串拼接，必须 @() 强制保持数组
$requiredModels = @()
if ($embedModel) { $requiredModels = @($embedModel) }
if ($vlModel -and $vlModel -ne $embedModel) {
    $requiredModels = @($requiredModels) + @($vlModel)
}

Write-Host ("  API: " + $baseUrl)
Write-Host ("  embed: " + $embedModel)
Write-Host ("  vision: " + $vlModel)

$ollamaExe = Find-OllamaExe
if (-not $ollamaExe) {
    Write-Host ""
    Write-Host "Ollama not found. Install from https://ollama.com/download" -ForegroundColor Red
    Write-Host "Knowledge base vector ingest and RAG require Ollama on the same machine." -ForegroundColor Yellow
    exit 1
}
Write-Host ("  ollama: " + $ollamaExe)

if (-not (Test-OllamaApi -BaseUrl $baseUrl)) {
    Write-Host "  Ollama API not reachable, trying to start..." -ForegroundColor Yellow
    Start-OllamaServe -OllamaExe $ollamaExe
    if (-not (Wait-OllamaReady -BaseUrl $baseUrl -TimeoutSec $StartupTimeoutSec)) {
        Write-Host ""
        Write-Host "Ollama failed to start within ${StartupTimeoutSec}s." -ForegroundColor Red
        Write-Host "Try: open Ollama app from Start menu, or run: ollama serve" -ForegroundColor Yellow
        exit 1
    }
}
Write-Host "  Ollama API OK" -ForegroundColor Green

if ($SkipPull) {
    Write-Host "  SkipPull: not checking models" -ForegroundColor DarkGray
    Write-Host ""
    exit 0
}

$installed = Get-InstalledModelNames -BaseUrl $baseUrl
$missing = @()
foreach ($m in $requiredModels) {
    if (-not (Test-ModelInstalled -Installed $installed -Wanted $m)) {
        $missing += $m
    }
}

if ($missing.Count -eq 0) {
    Write-Host ("  models OK: " + ($requiredModels -join ", ")) -ForegroundColor Green
    Write-Host ""
    exit 0
}

Write-Host ""
Write-Host "Missing models, pulling (first time may take several minutes)..." -ForegroundColor Yellow
foreach ($m in $missing) {
    Write-Host ("  ollama pull " + $m) -ForegroundColor Cyan
    & $ollamaExe pull $m
    if ($LASTEXITCODE -ne 0) {
        Write-Host ("  pull failed: " + $m) -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "Ollama ready with required models." -ForegroundColor Green
Write-Host ""
