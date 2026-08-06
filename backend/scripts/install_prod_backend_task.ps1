# Install TestAI prod backend as Scheduled Task (keepalive + health gate).
# Run as Administrator:
#   cd D:\deploy\testai_community_prod\backend\scripts
#   powershell -ExecutionPolicy Bypass -File .\install_prod_backend_task.ps1
#
# Success = script prints PASS and health returns ok.
# Then close all PowerShell windows; site should stay up.

$ErrorActionPreference = "Stop"
$ScriptsDir = $PSScriptRoot
$BackendDir = Split-Path -Parent $ScriptsDir
$RepoRoot = Split-Path -Parent $BackendDir
$Py = Join-Path $BackendDir ".venv\Scripts\python.exe"
$RunProd = Join-Path $BackendDir "run_prod.py"
$Keepalive = Join-Path $ScriptsDir "run_prod_keepalive.cmd"
$LogDir = Join-Path $ScriptsDir "logs"
$TaskName = "TestAI-Backend"
$Port = 48011

$envFile = Join-Path $RepoRoot ".env"
if (Test-Path -LiteralPath $envFile) {
    $line = Get-Content -LiteralPath $envFile | Where-Object { $_ -match '^\s*BACKEND_PORT\s*=' } | Select-Object -First 1
    if ($line -match '=\s*(\d+)') {
        $Port = [int]$Matches[1]
    }
}

function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host ("==> " + $msg) -ForegroundColor Cyan
}

function Stop-PortListeners([int]$ListenPort) {
    $lines = netstat -ano | Select-String (":" + $ListenPort + "\s+.*LISTENING")
    foreach ($line in $lines) {
        $parts = ($line.ToString() -split "\s+") | Where-Object { $_ -ne "" }
        $procId = $parts[-1]
        if ($procId -match "^\d+$" -and $procId -ne "0") {
            Write-Host ("Kill PID " + $procId + " on port " + $ListenPort)
            cmd /c ("taskkill /PID " + $procId + " /F") | Out-Null
        }
    }
}

function Test-Health([int]$ListenPort, [int]$TimeoutSec) {
    $url = "http://127.0.0.1:" + $ListenPort + "/api/health"
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3
            if ($resp.StatusCode -eq 200 -and $resp.Content -match "ok") {
                return $true
            }
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    return $false
}

Write-Step "1/5 Preflight"
if (-not (Test-Path -LiteralPath $Py)) {
    throw ("Missing venv python: " + $Py)
}
if (-not (Test-Path -LiteralPath $RunProd)) {
    throw ("Missing run_prod.py: " + $RunProd)
}
if (-not (Test-Path -LiteralPath $Keepalive)) {
    throw ("Missing keepalive cmd: " + $Keepalive)
}
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Write-Host ("BackendDir = " + $BackendDir)
Write-Host ("Python     = " + $Py)
$probe = Join-Path $LogDir "probe_uvicorn.py"
Set-Content -LiteralPath $probe -Value "import uvicorn`r`nprint('uvicorn ok', uvicorn.__version__)`r`n" -Encoding ASCII
& $Py $probe
if ($LASTEXITCODE -ne 0) {
    throw "venv cannot import uvicorn; reinstall requirements.txt"
}

Write-Step "2/5 Stop old listeners / old task"
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Stop-PortListeners -ListenPort $Port
Start-Sleep -Seconds 2

Write-Step "3/5 Register scheduled task"
$arg = '/c "' + $Keepalive + '"'
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $arg -WorkingDirectory $BackendDir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "TestAI prod backend keepalive. Closing PowerShell is OK." `
    -Force | Out-Null

Write-Step "4/5 Start task and wait for health"
Start-ScheduledTask -TaskName $TaskName
$ok = Test-Health -ListenPort $Port -TimeoutSec 60
if (-not $ok) {
    $logFile = Join-Path $LogDir "backend_keepalive.log"
    Write-Host "FAIL health check. Log tail:" -ForegroundColor Red
    if (Test-Path -LiteralPath $logFile) {
        Get-Content -LiteralPath $logFile -Tail 40
    } else {
        Write-Host ("(no log yet) " + $logFile)
    }
    throw "Install failed: health not OK. Fix log errors, then re-run this script."
}

Write-Step "5/5 PASS"
$info = Get-ScheduledTaskInfo -TaskName $TaskName
$state = (Get-ScheduledTask -TaskName $TaskName).State
Write-Host ("Task   = " + $TaskName + "  State=" + $state) -ForegroundColor Green
Write-Host ("Health = http://127.0.0.1:" + $Port + "/api/health  OK") -ForegroundColor Green
Write-Host ("Log    = " + (Join-Path $LogDir "backend_keepalive.log"))
Write-Host ("LastRun= " + $info.LastRunTime + "  LastResult=" + $info.LastTaskResult)
Write-Host ""
Write-Host "NEXT:" -ForegroundColor Yellow
Write-Host "  1) Close ALL PowerShell windows"
Write-Host ("  2) Open http://10.30.144.64:" + $Port + " from another PC")
Write-Host "  3) If down, read backend_keepalive.log"
Write-Host ""
Write-Host ("Stop:  powershell -ExecutionPolicy Bypass -File .\stop_prod_backend_task.ps1")
Write-Host "WeCom: .\install_wecom_scheduled_tasks.ps1  and set WECOM_PUSH_ENABLED=false"
