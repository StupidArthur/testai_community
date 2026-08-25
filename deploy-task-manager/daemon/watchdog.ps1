# ====================================================================
# watchdog.ps1  —— 进程守护核心（由计划任务 Gateway-Watchdog 每分钟调用）
# 遍历 services.csv，对每个服务检测存活：进程不在就隐藏窗口拉起。
# 仅在没有 nssm.exe 时走这套；有 nssm.exe 时各服务已是真服务，无需它。
# ====================================================================
$Root = $PSScriptRoot
$Csv = Join-Path $Root 'services.csv'
$LogDir = Join-Path $Root 'logs'
$Log = Join-Path $LogDir 'watchdog.log'

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
if (-not (Test-Path $Csv)) { return }

$services = @(Import-Csv $Csv)
$ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

foreach ($s in $services) {
    if (-not $s.Exe) { continue }
    $exeName = [IO.Path]::GetFileName($s.Exe)
    $running = $false
    $procs = Get-CimInstance Win32_Process -Filter "Name='$exeName'" -ErrorAction SilentlyContinue
    if ([string]::IsNullOrWhiteSpace($s.Arguments)) {
        $running = ($null -ne $procs)
    } else {
        foreach ($p in $procs) {
            if ($p.CommandLine -and ($p.CommandLine -like "*$($s.Arguments)*")) { $running = $true; break }
        }
    }
    if (-not $running) {
        try {
            $sp = @{ FilePath = $s.Exe; WindowStyle = 'Hidden' }
            if ($s.Arguments) { $sp['ArgumentList'] = $s.Arguments }
            if ($s.Dir) { $sp['WorkingDirectory'] = $s.Dir }
            Start-Process @sp
            "$ts  拉起 $($s.Name)" | Out-File $Log -Append -Encoding UTF8
        } catch {
            "$ts  拉起失败 $($s.Name): $_" | Out-File $Log -Append -Encoding UTF8
        }
    }
}
