# ====================================================================
# svc.ps1  —— 通用服务守护器（多服务统一管理）
#
# 两种后端，自动选择：
#   - 若同目录存在 nssm.exe  -> NSSM 模式（注册为真正的 Windows 服务，
#                                 开机自启 + 崩溃重启 + services.msc 可见）
#   - 否                      -> watchdog 模式（零依赖，靠计划任务每分钟
#                                 检测进程，不在就隐藏窗口拉起）
#
# 两种后端用同一套命令，互不冲突。建议优先 NSSM 模式。
#
# 用法示例：
#   svc add TaskManager -Exe "D:\deploy-task-manager\deploy\.venv\Scripts\python.exe" -Arguments "main.py --port 8000" -Dir "D:\deploy-task-manager\deploy"
#   svc start TaskManager
#   svc stop TaskManager
#   svc restart TaskManager
#   svc status TaskManager
#   svc list
#   svc remove TaskManager
#   svc install-watchdog      # watchdog 模式必装；NSSM 模式可装可不装
#   svc uninstall-watchdog
# ====================================================================
param(
    [Parameter(Position = 0)][string]$Action = 'help',
    [Parameter(Position = 1)][string]$Name = '',
    [string]$Exe = '',
    [string]$Arguments = '',
    [string]$Dir = ''
)
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$OutputEncoding = [System.Text.Encoding]::UTF8

$Root = $PSScriptRoot
$Nssm = Join-Path $Root 'nssm.exe'
$UseNssm = Test-Path $Nssm
$Csv = Join-Path $Root 'services.csv'
$LogDir = Join-Path $Root 'logs'

function Load-List {
    if (Test-Path $Csv) { @(Import-Csv $Csv) } else { @() }
}
function Save-List($list) {
    $list | Export-Csv $Csv -NoTypeInformation -Encoding UTF8
}
function Find-Svc($n) {
    (Load-List) | Where-Object { $_.Name -eq $n } | Select-Object -First 1
}
function ExeName($p) { [IO.Path]::GetFileName($p) }
function Is-Running($svc) {
    $procs = Get-CimInstance Win32_Process -Filter "Name='$(ExeName $svc.Exe)'" -ErrorAction SilentlyContinue
    if ([string]::IsNullOrWhiteSpace($svc.Arguments)) {
        return ($null -ne $procs)
    }
    foreach ($p in $procs) {
        if ($p.CommandLine -and ($p.CommandLine -like "*$($svc.Arguments)*")) { return $true }
    }
    return $false
}
function Nssm-Set($n, $param, $val) {
    # 路径/日志值走普通 & 调用
    & $Nssm set $n $param $val 2>$null | Out-Null
}
function Kill-Proc($svc) {
    Get-CimInstance Win32_Process -Filter "Name='$(ExeName $svc.Exe)'" -ErrorAction SilentlyContinue |
        Where-Object { [string]::IsNullOrWhiteSpace($svc.Arguments) -or ($_.CommandLine -like "*$($svc.Arguments)*") } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

Write-Host ('后端：' + $(if ($UseNssm) { 'NSSM（真 Windows 服务）' } else { 'watchdog（零依赖进程守护）' })) -ForegroundColor DarkGray

switch ($Action) {
    'help' {
        Write-Host @'

通用服务守护器 用法：
  svc add    <名> -Exe <python.exe全路径> -Arguments "<启动参数>" -Dir <工作目录>
  svc remove <名>
  svc start  <名>
  svc stop   <名>
  svc restart<名>
  svc status <名>
  svc list
  svc install-watchdog     （watchdog 模式必须装一次；NSSM 模式可选）
  svc uninstall-watchdog

示例（注册当前定时任务平台）：
  svc add TaskManager -Exe "D:\deploy-task-manager\deploy\.venv\Scripts\python.exe" -Arguments "main.py --port 8000" -Dir "D:\deploy-task-manager\deploy"

'@
    }

    'add' {
        if (-not $Name -or -not $Exe) { throw 'add 需要：Name、-Exe（必填）；-Arguments、-Dir 可选' }
        if (-not (Test-Path $Exe)) { throw "Exe 不存在：$Exe" }
        $list = @(Load-List | Where-Object { $_.Name -ne $Name })
        $list += [pscustomobject]@{ Name = $Name; Exe = $Exe; Arguments = $Arguments; Dir = $Dir }
        $list | Export-Csv $Csv -NoTypeInformation -Encoding UTF8
        New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

        if ($UseNssm) {
            Write-Host "[NSSM] 注册服务 $Name ..." -ForegroundColor Cyan
            & $Nssm remove $Name confirm 2>$null | Out-Null
            & $Nssm install $Name $Exe 2>$null | Out-Null
            if ($Dir) { & $Nssm set $Name AppDirectory $Dir 2>$null | Out-Null }
            if ($Arguments) {
                # 用 Invoke 避免 PowerShell 给整段参数加外层引号导致 nssm 当成单参
                Invoke-Expression "& '$Nssm' set '$Name' AppParameters $Arguments" 2>$null | Out-Null
            }
            & $Nssm set $Name Start SERVICE_AUTO_START 2>$null | Out-Null
            & $Nssm set $Name AppExit Default Restart 2>$null | Out-Null
            & $Nssm set $Name AppRestartDelay 5000 2>$null | Out-Null
            & $Nssm set $Name AppStdout "$LogDir\$Name.out.log" 2>$null | Out-Null
            & $Nssm set $Name AppStderr "$LogDir\$Name.err.log" 2>$null | Out-Null
            & $Nssm set $Name AppRotateFiles 1 2>$null | Out-Null
            & $Nssm set $Name AppRotateBytes 10485760 2>$null | Out-Null
            & $Nssm start $Name 2>$null | Out-Null
            Write-Host "  已注册并启动。日志：$LogDir\$Name.*.log" -ForegroundColor Green
        } else {
            Write-Host "[watchdog] 已记录 $Name。请确保已运行：svc install-watchdog" -ForegroundColor Yellow
            Write-Host '  watchdog 会在 1 分钟内自动拉起该服务（开机也会自动拉起）。' -ForegroundColor DarkGray
        }
    }

    'remove' {
        $svc = Find-Svc $Name
        if (-not $svc) { Write-Host "未找到服务：$Name" -ForegroundColor Yellow; return }
        if ($UseNssm) {
            & $Nssm stop $Name 2>$null | Out-Null
            & $Nssm remove $Name confirm 2>$null | Out-Null
            Write-Host "[NSSM] 已卸载服务 $Name" -ForegroundColor Green
        } else {
            Kill-Proc $svc
            Write-Host "[watchdog] 已停止进程 $Name（已从清单移除）" -ForegroundColor Green
        }
        Save-List @(Load-List | Where-Object { $_.Name -ne $Name })
    }

    'start' {
        $svc = Find-Svc $Name
        if (-not $svc) { throw "未找到服务：$Name（先 svc add）" }
        if ($UseNssm) { & $Nssm start $Name 2>$null | Out-Null; Write-Host "已启动 $Name" -ForegroundColor Green }
        else {
            Start-Process -FilePath $svc.Exe -ArgumentList $svc.Arguments -WorkingDirectory $svc.Dir -WindowStyle Hidden
            Write-Host "已拉起 $Name" -ForegroundColor Green
        }
    }

    'stop' {
        $svc = Find-Svc $Name
        if (-not $svc) { throw "未找到服务：$Name" }
        if ($UseNssm) { & $Nssm stop $Name 2>$null | Out-Null; Write-Host "已停止 $Name" -ForegroundColor Yellow }
        else { Kill-Proc $svc; Write-Host "已停止 $Name 进程" -ForegroundColor Yellow }
    }

    'restart' {
        $svc = Find-Svc $Name
        if (-not $svc) { throw "未找到服务：$Name" }
        if ($UseNssm) { & $Nssm restart $Name 2>$null | Out-Null }
        else { Kill-Proc $svc; Start-Sleep -Seconds 2; Start-Process -FilePath $svc.Exe -ArgumentList $svc.Arguments -WorkingDirectory $svc.Dir -WindowStyle Hidden }
        Write-Host "已重启 $Name" -ForegroundColor Green
    }

    'status' {
        $svc = Find-Svc $Name
        if (-not $svc) { Write-Host "未找到服务：$Name" -ForegroundColor Yellow; return }
        if ($UseNssm) {
            $st = (& $Nssm status $Name 2>$null)
            Write-Host ("{0,-20} {1}" -f $Name, $st) -ForegroundColor Cyan
        } else {
            $r = Is-Running $svc
            Write-Host ("{0,-20} {1}" -f $Name, $(if ($r) { 'RUNNING' } else { 'STOPPED' })) -ForegroundColor $(if ($r) { 'Green' } else { 'Red' })
        }
    }

    'list' {
        $list = Load-List
        if (-not $list) { Write-Host '清单为空（services.csv 不存在）。先 svc add 添加服务。' -ForegroundColor Yellow; return }
        Write-Host '受管服务清单：' -ForegroundColor Cyan
        foreach ($s in $list) {
            if ($UseNssm) {
                $st = (& $Nssm status $s.Name 2>$null)
            } else {
                $st = if (Is-Running $s) { 'RUNNING' } else { 'STOPPED' }
            }
            $color = if ($st -eq 'RUNNING') { 'Green' } else { 'Red' }
            Write-Host ("  {0,-20} [{1}]  {2} {3}" -f $s.Name, $st, $s.Exe, $s.Arguments) -ForegroundColor $color
        }
        Write-Host ''
        Write-Host ('后端：' + $(if ($UseNssm) { 'NSSM —— services.msc 也能看到这些服务' } else { 'watchdog —— 计划任务 Gateway-Watchdog 守护' })) -ForegroundColor DarkGray
    }

    'install-watchdog' {
        $task = 'Gateway-Watchdog'
        Stop-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue
        $action = New-ScheduledTaskAction -Execute 'powershell.exe' `
            -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Root\watchdog.ps1`""
        $t1 = New-ScheduledTaskTrigger -AtStartup
        $t2 = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
            -RepetitionInterval (New-TimeSpan -Minutes 1) `
            -RepetitionDuration ([TimeSpan]::FromDays(3650))
        $principal = New-ScheduledTaskPrincipal -UserId 'NT AUTHORITY\SYSTEM' -LogonType ServiceAccount -RunLevel Highest
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable
        Register-ScheduledTask -TaskName $task -Action $action -Trigger @($t1, $t2) -Principal $principal -Settings $settings -Force | Out-Null
        Write-Host "已注册 $task：开机自启 + 每 1 分钟检测拉起" -ForegroundColor Green
        Start-ScheduledTask -TaskName $task
    }

    'uninstall-watchdog' {
        $task = 'Gateway-Watchdog'
        Stop-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue
        Write-Host "已卸载 $task" -ForegroundColor Green
    }

    default { Write-Host "未知动作：$Action。用 svc help 查看用法。" -ForegroundColor Yellow }
}
