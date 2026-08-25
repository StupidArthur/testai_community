# ===================================================================
# 62 Task-Manager guard - zero-config, double-click version
# Just double-click the .cmd shortcuts:
#   install / start / stop / restart / status / uninstall
# install auto-detects python and port (reads the currently running
# process), so you never type anything.
# Uses NSSM (real service) if nssm.exe is present, else watchdog.
# ===================================================================
param([string]$Action = 'status')
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = $PSScriptRoot
$CfgFile = Join-Path $Root 'config.json'
$LogDir = Join-Path $Root 'logs'
$ServiceName = 'TaskManager'
$WatchdogTask = 'TaskManager-Watchdog'
$Nssm = Join-Path $Root 'nssm.exe'
$DeployDir = 'D:\deploy-task-manager\deploy'   # main.py dir on 62

function Read-Cfg {
    if (Test-Path $CfgFile) { return (Get-Content $CfgFile -Raw -Encoding UTF8 | ConvertFrom-Json) }
    return $null
}
function Write-Cfg($o) { $o | ConvertTo-Json -Compress | Set-Content $CfgFile -Encoding UTF8 }

function Find-MainProc {
    return (Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*main.py*' -and $_.Name -match 'python' } |
        Select-Object -First 1)
}
function Detect-Python {
    $p = Find-MainProc
    if ($p -and $p.PathName) { $e = $p.PathName.Trim('"'); if (Test-Path $e) { return $e } }
    $venv = Join-Path $DeployDir '.venv\Scripts\python.exe'
    if (Test-Path $venv) { return $venv }
    $c = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $c = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    return $null
}
function Detect-Port {
    $p = Find-MainProc
    if ($p -and $p.CommandLine -match '--port\s+(\d+)') { return $matches[1] }
    return '8000'
}
function Is-Listening($port) {
    return ($null -ne (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue))
}
function Start-App($cfg) {
    Start-Process -FilePath $cfg.Python -ArgumentList "main.py --port $($cfg.Port)" -WorkingDirectory $cfg.Dir -WindowStyle Hidden
}
function Stop-App {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*main.py*' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

switch ($Action) {
    'install' {
        Write-Host '====== Install 62 Task-Manager guard ======' -ForegroundColor Cyan
        $py = Detect-Python
        $port = Detect-Port
        if (-not $py) { Write-Host 'Python not found. Fix $DeployDir in daemon62.ps1, or put nssm.exe beside it.' -ForegroundColor Red; return }
        Write-Host ('Python : ' + $py) -ForegroundColor Green
        Write-Host ('Port    : ' + $port) -ForegroundColor Green
        Write-Host ('Dir     : ' + $DeployDir) -ForegroundColor Green

        $cfg = [pscustomobject]@{ Python = $py; Port = $port; Dir = $DeployDir; Mode = '' }
        New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

        if (Is-Listening $port) {
            Write-Host 'Port in use (the cmd window one), stopping old process...' -ForegroundColor Yellow
            Stop-App
            Start-Sleep -Seconds 2
        }

        if (Test-Path $Nssm) {
            $cfg.Mode = 'nssm'; Write-Cfg $cfg
            Write-Host 'Using NSSM (real Windows service)...' -ForegroundColor Cyan
            & $Nssm remove $ServiceName confirm 2>$null | Out-Null
            & $Nssm install $ServiceName $py 2>$null | Out-Null
            & $Nssm set $ServiceName AppDirectory $DeployDir 2>$null | Out-Null
            Invoke-Expression ("& '$Nssm' set '$ServiceName' AppParameters main.py --port $port") 2>$null | Out-Null
            & $Nssm set $ServiceName Start SERVICE_AUTO_START 2>$null | Out-Null
            & $Nssm set $ServiceName AppExit Default Restart 2>$null | Out-Null
            & $Nssm set $ServiceName AppRestartDelay 5000 2>$null | Out-Null
            & $Nssm set $ServiceName AppStdout "$LogDir\out.log" 2>$null | Out-Null
            & $Nssm set $ServiceName AppStderr "$LogDir\err.log" 2>$null | Out-Null
            & $Nssm start $ServiceName 2>$null | Out-Null
        } else {
            $cfg.Mode = 'watchdog'; Write-Cfg $cfg
            Write-Host 'No nssm.exe found, using watchdog (schtasks)...' -ForegroundColor Yellow

            # Create wrapper .cmd to avoid quoting issues with schtasks.exe
            $wrapper = Join-Path $Root 'watchdog-runner.cmd'
            $cmdBody = "@echo off`r`nchcp 65001 >nul`r`npowershell -NoProfile -ExecutionPolicy Bypass -File `"%~dp0daemon62.ps1`" -Action keepalive"
            [System.IO.File]::WriteAllText($wrapper, $cmdBody, (New-Object System.Text.UTF8Encoding($false)))

            # Remove old tasks
            schtasks.exe /Delete /TN $WatchdogTask /F 2>$null | Out-Null
            schtasks.exe /Delete /TN "$WatchdogTask-Boot" /F 2>$null | Out-Null

            # Create every-minute watchdog task
            $out = & schtasks.exe /Create /TN $WatchdogTask /TR $wrapper /SC MINUTE /MO 1 /RU SYSTEM /RL HIGHEST /F 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Host 'Watchdog task created (runs every 1 minute).' -ForegroundColor Green
            } else {
                Write-Host ('Watchdog task FAILED: ' + ($out -join ' ')) -ForegroundColor Red
            }
            # Create boot trigger task
            & schtasks.exe /Create /TN "$WatchdogTask-Boot" /TR $wrapper /SC ONSTART /RU SYSTEM /RL HIGHEST /F 2>$null | Out-Null

            # Run watchdog once now
            & schtasks.exe /Run /TN $WatchdogTask 2>$null | Out-Null
            Start-Sleep -Seconds 3
            if (-not (Is-Listening $port)) { Start-App $cfg }
        }

        Start-Sleep -Seconds 3
        Write-Host ''
        if (Is-Listening $port) {
            Write-Host ('Install OK! Listening on port ' + $port + '.') -ForegroundColor Green
            Write-Host ('Open: http://127.0.0.1:' + $port) -ForegroundColor Green
        } else {
            Write-Host 'Port not up yet. Check logs\err.log (usually wrong port/python).' -ForegroundColor Red
        }
        Write-Host 'Daily: use the status / restart / stop shortcuts.' -ForegroundColor DarkGray
    }

    'start' {
        $cfg = Read-Cfg
        if (-not $cfg) { Write-Host 'Not installed. Run the INSTALL shortcut first.' -ForegroundColor Yellow; return }
        if ($cfg.Mode -eq 'nssm') { & $Nssm start $ServiceName 2>$null | Out-Null }
        elseif (-not (Is-Listening $cfg.Port)) { Start-App $cfg }
        Write-Host 'Started.' -ForegroundColor Green
    }

    'stop' {
        $cfg = Read-Cfg
        if (-not $cfg) { Write-Host 'Not installed.' -ForegroundColor Yellow; return }
        if ($cfg.Mode -eq 'nssm') { & $Nssm stop $ServiceName 2>$null | Out-Null }
        Stop-App
        Write-Host 'Stopped.' -ForegroundColor Yellow
    }

    'restart' {
        $cfg = Read-Cfg
        if (-not $cfg) { Write-Host 'Not installed. Run the INSTALL shortcut first.' -ForegroundColor Yellow; return }
        if ($cfg.Mode -eq 'nssm') { & $Nssm restart $ServiceName 2>$null | Out-Null }
        else { Stop-App; Start-Sleep -Seconds 2; Start-App $cfg }
        Write-Host 'Restarted.' -ForegroundColor Green
    }

    'status' {
        $cfg = Read-Cfg
        $port = if ($cfg) { $cfg.Port } else { Detect-Port }
        $mode = if ($cfg) { $cfg.Mode } else { 'not installed' }
        $up = Is-Listening $port
        Write-Host ('Port ' + $port + '  Status: ' + $(if ($up) { 'RUNNING' } else { 'STOPPED' })) -ForegroundColor $(if ($up) { 'Green' } else { 'Red' })
        Write-Host ('Guard mode: ' + $mode) -ForegroundColor DarkGray
        if ($cfg) { Write-Host ('Python : ' + $cfg.Python) -ForegroundColor DarkGray }
        if ($up) { Write-Host ('Open: http://127.0.0.1:' + $port) -ForegroundColor Green }
    }

    'keepalive' {
        $cfg = Read-Cfg
        if (-not $cfg) { return }
        if (-not (Is-Listening $cfg.Port)) {
            try { Start-App $cfg; (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' restarted' | Out-File (Join-Path $LogDir 'watchdog.log') -Append -Encoding UTF8 } catch {}
        }
    }

    'uninstall' {
        $cfg = Read-Cfg
        if ($cfg -and $cfg.Mode -eq 'nssm') {
            & $Nssm stop $ServiceName 2>$null | Out-Null
            & $Nssm remove $ServiceName confirm 2>$null | Out-Null
        }
        schtasks.exe /End /TN $WatchdogTask 2>$null | Out-Null
        schtasks.exe /Delete /TN $WatchdogTask /F 2>$null | Out-Null
        schtasks.exe /Delete /TN "$WatchdogTask-Boot" /F 2>$null | Out-Null
        Stop-App
        Remove-Item $CfgFile -ErrorAction SilentlyContinue
        Write-Host 'Uninstalled.' -ForegroundColor Green
    }

    default { Write-Host ('Unknown action: ' + $Action + '. Use: install/start/stop/restart/status/keepalive/uninstall') -ForegroundColor Yellow }
}
