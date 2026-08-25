# ===================================================================
# imgagent-server guard - zero-config, double-click version
# Just double-click the .cmd shortcuts (same as the 62 guard).
# Uses NSSM (real service) if nssm.exe is present, else watchdog.
# Survival check = process name (no port needed).
# ===================================================================
param([string]$Action = 'status')
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = $PSScriptRoot
$CfgFile = Join-Path $Root 'config.json'
$LogDir = Join-Path $Root 'logs'
$ServiceName = 'ImgAgentServer'
$WatchdogTask = 'ImgAgent-Watchdog'
$Nssm = Join-Path $Root 'nssm.exe'
$ExePath = 'D:\deploy\imgagent-server.exe'     # exe full path on 62
$WorkDir = 'D:\deploy'                         # exe working dir (has dist/data.db)
$ExeName = [IO.Path]::GetFileName($ExePath)    # imgagent-server.exe

function Read-Cfg {
    if (Test-Path $CfgFile) { return (Get-Content $CfgFile -Raw -Encoding UTF8 | ConvertFrom-Json) }
    return $null
}
function Write-Cfg($o) { $o | ConvertTo-Json -Compress | Set-Content $CfgFile -Encoding UTF8 }

function Is-Running {
    return ($null -ne (Get-CimInstance Win32_Process -Filter "Name='$ExeName'" -ErrorAction SilentlyContinue))
}
function Start-App { Start-Process -FilePath $ExePath -WorkingDirectory $WorkDir -WindowStyle Hidden }
function Stop-App {
    Get-CimInstance Win32_Process -Filter "Name='$ExeName'" -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

switch ($Action) {
    'install' {
        Write-Host '====== Install imgagent-server guard ======' -ForegroundColor Cyan
        if (-not (Test-Path $ExePath)) { Write-Host ('Exe not found: ' + $ExePath) -ForegroundColor Red; return }
        Write-Host ('Exe : ' + $ExePath) -ForegroundColor Green
        Write-Host ('Dir : ' + $WorkDir) -ForegroundColor Green
        New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

        if (Is-Running) {
            Write-Host 'Already running, stopping old one to avoid conflict...' -ForegroundColor Yellow
            Stop-App
            Start-Sleep -Seconds 2
        }

        if (Test-Path $Nssm) {
            Write-Cfg ([pscustomobject]@{ Mode = 'nssm' })
            Write-Host 'Using NSSM (real Windows service)...' -ForegroundColor Cyan
            & $Nssm remove $ServiceName confirm 2>$null | Out-Null
            & $Nssm install $ServiceName $ExePath 2>$null | Out-Null
            & $Nssm set $ServiceName AppDirectory $WorkDir 2>$null | Out-Null
            & $Nssm set $ServiceName Start SERVICE_AUTO_START 2>$null | Out-Null
            & $Nssm set $ServiceName AppExit Default Restart 2>$null | Out-Null
            & $Nssm set $ServiceName AppRestartDelay 5000 2>$null | Out-Null
            & $Nssm set $ServiceName AppStdout "$LogDir\out.log" 2>$null | Out-Null
            & $Nssm set $ServiceName AppStderr "$LogDir\err.log" 2>$null | Out-Null
            & $Nssm start $ServiceName 2>$null | Out-Null
        } else {
            Write-Cfg ([pscustomobject]@{ Mode = 'watchdog' })
            Write-Host 'No nssm.exe found, using watchdog (schtasks)...' -ForegroundColor Yellow

            # Create wrapper .cmd to avoid quoting issues with schtasks.exe
            $wrapper = Join-Path $Root 'watchdog-runner.cmd'
            $cmdBody = "@echo off`r`nchcp 65001 >nul`r`npowershell -NoProfile -ExecutionPolicy Bypass -File `"%~dp0daemon-imgagent.ps1`" -Action keepalive"
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
            if (-not (Is-Running)) { Start-App }
        }

        Start-Sleep -Seconds 3
        Write-Host ''
        if (Is-Running) {
            Write-Host 'Install OK! imgagent-server is running.' -ForegroundColor Green
        } else {
            Write-Host 'Not running yet. Check logs\err.log.' -ForegroundColor Red
        }
        Write-Host 'Daily: use the status / restart / stop shortcuts.' -ForegroundColor DarkGray
    }

    'start' {
        if (Test-Path $Nssm) { & $Nssm start $ServiceName 2>$null | Out-Null }
        elseif (-not (Is-Running)) { Start-App }
        Write-Host 'Started.' -ForegroundColor Green
    }

    'stop' {
        if (Test-Path $Nssm) { & $Nssm stop $ServiceName 2>$null | Out-Null }
        Stop-App
        Write-Host 'Stopped.' -ForegroundColor Yellow
    }

    'restart' {
        if (Test-Path $Nssm) { & $Nssm restart $ServiceName 2>$null | Out-Null }
        else { Stop-App; Start-Sleep -Seconds 2; Start-App }
        Write-Host 'Restarted.' -ForegroundColor Green
    }

    'status' {
        $cfg = Read-Cfg
        $mode = if ($cfg) { $cfg.Mode } else { 'not installed' }
        $up = Is-Running
        Write-Host ('imgagent-server  Status: ' + $(if ($up) { 'RUNNING' } else { 'STOPPED' })) -ForegroundColor $(if ($up) { 'Green' } else { 'Red' })
        Write-Host ('Guard mode: ' + $mode) -ForegroundColor DarkGray
    }

    'keepalive' {
        if (-not (Is-Running)) {
            try { Start-App; (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' restarted' | Out-File (Join-Path $LogDir 'watchdog.log') -Append -Encoding UTF8 } catch {}
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
