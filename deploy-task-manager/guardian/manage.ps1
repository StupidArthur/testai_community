# ===================================================================
# Guardian manager - install / uninstall / status / start / stop / restart
# Double-click the .cmd shortcuts, no typing needed.
# Uses schtasks.exe (universally reliable on Windows).
# ===================================================================
param([string]$Action = 'status')
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = $PSScriptRoot
$WatchdogTask = 'Guardian-Watchdog'
$BootTask = 'Guardian-Boot'
$GuardianExe = Join-Path $Root 'guardian.exe'
$GuardianScript = Join-Path $Root 'guardian.py'
$ConfigFile = Join-Path $Root 'services.json'
$Port = 9000

# Read port from config
if (Test-Path $ConfigFile) {
    try {
        $cfg = Get-Content $ConfigFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($cfg.guardian_port) { $Port = $cfg.guardian_port }
    } catch {}
}

# Determine how to run guardian
function Get-RunCmd {
    if (Test-Path $GuardianExe) {
        return @{ Exe = $GuardianExe; Args = ''; ProcessName = 'guardian.exe'; MatchCmd = $null }
    }
    # Try to find python
    $py = $null
    $tryPaths = @(
        'D:\Python311\python.exe',
        'D:\Python312\python.exe',
        'C:\Python311\python.exe',
        'C:\Python312\python.exe'
    )
    foreach ($p in $tryPaths) { if (Test-Path $p) { $py = $p; break } }
    if (-not $py) {
        $c = Get-Command python.exe -ErrorAction SilentlyContinue
        if ($c) { $py = $c.Source }
    }
    if (-not $py) {
        $c = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($c) { $py = @($c.Source, '-3') -join ' ' }
    }
    if ($py -and (Test-Path $GuardianScript)) {
        return @{ Exe = $py; Args = "`"$GuardianScript`""; ProcessName = 'python.exe'; MatchCmd = 'guardian.py' }
    }
    return $null
}

function Is-GuardianRunning {
    $rc = Get-RunCmd
    if (-not $rc) { return $false }
    $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq $rc.ProcessName }
    if ($rc.MatchCmd) {
        $procs = $procs | Where-Object { $_.CommandLine -like "*$($rc.MatchCmd)*" }
    }
    return ($null -ne $procs)
}

function Is-PortListening($port) {
    return ($null -ne (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue))
}

function Start-Guardian {
    $rc = Get-RunCmd
    if (-not $rc) { Write-Host 'Cannot find guardian.exe or guardian.py + python!' -ForegroundColor Red; return $false }
    if (Is-GuardianRunning) { Write-Host 'Guardian already running.' -ForegroundColor Yellow; return $true }
    $cmd = "`"$($rc.Exe)`""
    if ($rc.Args) { $cmd += " $($rc.Args)" }
    Start-Process -FilePath $rc.Exe -ArgumentList $rc.Args -WorkingDirectory $Root -WindowStyle Hidden
    Start-Sleep -Seconds 3
    return (Is-PortListening $Port)
}

function Stop-Guardian {
    $rc = Get-RunCmd
    if (-not $rc) { return }
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq $rc.ProcessName -and ($rc.MatchCmd -eq $null -or $_.CommandLine -like "*$($rc.MatchCmd)*") } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

switch ($Action) {
    'install' {
        Write-Host '====== Install Guardian ======' -ForegroundColor Cyan
        $rc = Get-RunCmd
        if (-not $rc) {
            Write-Host 'Cannot find guardian.exe or guardian.py + python!' -ForegroundColor Red
            Write-Host 'Put guardian.exe (or guardian.py + python) in this folder.' -ForegroundColor Yellow
            return
        }
        Write-Host ('Mode   : ' + $(if (Test-Path $GuardianExe) { 'guardian.exe' } else { 'python + guardian.py' })) -ForegroundColor Green
        Write-Host ('Port   : ' + $Port) -ForegroundColor Green
        Write-Host ('Config : ' + $ConfigFile) -ForegroundColor Green

        # Create watchdog wrapper
        $wrapper = Join-Path $Root 'guardian-watchdog.cmd'
        if (Test-Path $GuardianExe) {
            $cmdBody = "@echo off`r`nchcp 65001 >nul`r`ntasklist /FI `"IMAGENAME eq guardian.exe`" 2>nul | find `"guardian.exe`" >nul`r`nif errorlevel 1 start `"`" /B `"$GuardianExe`""
        } else {
            $pyPath = $rc.Exe
            $cmdBody = "@echo off`r`nchcp 65001 >nul`r`npowershell -NoProfile -ExecutionPolicy Bypass -Command `"$p = Get-CimInstance Win32_Process -Filter \\"Name='python.exe'\\" | Where-Object { `$_.CommandLine -like '*guardian.py*' }; if (-not `$p) { Start-Process -FilePath '$pyPath' -ArgumentList '\"$GuardianScript\"' -WorkingDirectory '$Root' -WindowStyle Hidden }`""
        }
        [System.IO.File]::WriteAllText($wrapper, $cmdBody, (New-Object System.Text.UTF8Encoding($false)))
        Write-Host 'Watchdog wrapper created.' -ForegroundColor Green

        # Remove old tasks
        schtasks.exe /Delete /TN $WatchdogTask /F 2>$null | Out-Null
        schtasks.exe /Delete /TN $BootTask /F 2>$null | Out-Null

        # Create every-minute watchdog
        $out = & schtasks.exe /Create /TN $WatchdogTask /TR $wrapper /SC MINUTE /MO 1 /RU SYSTEM /RL HIGHEST /F 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host 'Watchdog task created (runs every 1 minute).' -ForegroundColor Green
        } else {
            Write-Host ('Watchdog task FAILED: ' + ($out -join ' ')) -ForegroundColor Red
        }
        # Create boot trigger
        & schtasks.exe /Create /TN $BootTask /TR $wrapper /SC ONSTART /RU SYSTEM /RL HIGHEST /F 2>$null | Out-Null

        # Start guardian now
        Start-Guardian | Out-Null
        Start-Sleep -Seconds 3

        Write-Host ''
        if (Is-PortListening $Port) {
            Write-Host "Install OK! Guardian running on port $Port." -ForegroundColor Green
            Write-Host "Dashboard: http://127.0.0.1:$Port" -ForegroundColor Green
        } else {
            Write-Host 'Guardian not responding yet. Check guardian.log' -ForegroundColor Red
        }
    }

    'uninstall' {
        schtasks.exe /End /TN $WatchdogTask 2>$null | Out-Null
        schtasks.exe /Delete /TN $WatchdogTask /F 2>$null | Out-Null
        schtasks.exe /Delete /TN $BootTask /F 2>$null | Out-Null
        Stop-Guardian
        Write-Host 'Guardian uninstalled.' -ForegroundColor Green
    }

    'start' {
        if (Start-Guardian) {
            Write-Host "Guardian started on port $Port." -ForegroundColor Green
        } else {
            Write-Host 'Failed to start. Check guardian.log' -ForegroundColor Red
        }
    }

    'stop' {
        Stop-Guardian
        Write-Host 'Guardian stopped.' -ForegroundColor Yellow
    }

    'restart' {
        Stop-Guardian
        Start-Sleep -Seconds 2
        if (Start-Guardian) {
            Write-Host "Guardian restarted on port $Port." -ForegroundColor Green
        } else {
            Write-Host 'Failed to restart.' -ForegroundColor Red
        }
    }

    'status' {
        $running = Is-GuardianRunning
        $portUp = Is-PortListening $Port
        $rc = Get-RunCmd
        Write-Host ("Guardian  Status: " + $(if ($running -and $portUp) { 'RUNNING' } elseif ($running) { 'STARTING' } else { 'STOPPED' })) -ForegroundColor $(if ($running -and $portUp) { 'Green' } else { 'Red' })
        Write-Host ("Port     : $Port") -ForegroundColor DarkGray
        Write-Host ("Dashboard: http://127.0.0.1:$Port") -ForegroundColor DarkGray
        if ($rc) { Write-Host ("Mode     : " + $(if (Test-Path $GuardianExe) { 'guardian.exe' } else { 'python + guardian.py' })) -ForegroundColor DarkGray }

        # Show watched services
        if (Is-PortListening $Port) {
            try {
                $resp = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/services" -TimeoutSec 5
                Write-Host ''
                Write-Host 'Watched services:' -ForegroundColor Cyan
                foreach ($s in $resp.services) {
                    $status = if ($s.running) { 'RUNNING' } else { 'STOPPED' }
                    $color = if ($s.running) { 'Green' } else { 'Red' }
                    $portInfo = if ($s.port) { " port:$($s.port)" } else { '' }
                    Write-Host ("  {0,-25} {1,-8}{2}  restarts:{3}" -f $s.name, $status, $portInfo, $s.restart_count) -ForegroundColor $color
                }
            } catch {}
        }
    }

    default { Write-Host "Usage: manage.ps1 -Action install|uninstall|start|stop|restart|status" -ForegroundColor Yellow }
}
