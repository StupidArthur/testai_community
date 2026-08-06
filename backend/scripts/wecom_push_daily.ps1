# Windows 计划任务入口：日报。日志落在 scripts/logs/
$ErrorActionPreference = "Continue"
$ScriptsDir = $PSScriptRoot
$BackendDir = Split-Path -Parent $ScriptsDir
$LogDir = Join-Path $ScriptsDir "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir ("wecom_daily_{0}.log" -f $stamp)
$OutFile = Join-Path $LogDir ("wecom_daily_{0}.out.log" -f $stamp)
$ErrFile = Join-Path $LogDir ("wecom_daily_{0}.err.log" -f $stamp)

function Write-Log([string]$msg) {
    $line = "{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $msg
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
    Write-Host $line
}

Write-Log "START daily BackendDir=$BackendDir"
$env:TM_PUSH_KIND = "daily"
# 0 = respect idempotency (20:01~20:04 backups skip if already sent)
$env:TM_PUSH_FORCE = "0"
$env:PYTHONWARNINGS = "ignore"
Set-Location -LiteralPath $BackendDir

# Prefer backend\.venv (prod); then common install locations for the task user
$candidates = @(
    (Join-Path $BackendDir ".venv\Scripts\python.exe"),
    (Join-Path $BackendDir "venv\Scripts\python.exe"),
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe",
    "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe",
    "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe",
    "C:\Python311\python.exe",
    "C:\Python312\python.exe"
)
$Python = $null
foreach ($c in $candidates) {
    if ($c -and (Test-Path -LiteralPath $c)) { $Python = $c; break }
}
if (-not $Python) {
    Write-Log "FAIL no python"
    foreach ($c in $candidates) { Write-Log ("  tried: " + $c) }
    exit 1
}
Write-Log "Python=$Python"

$script = Join-Path $ScriptsDir "wecom_scheduled_push.py"
$p = Start-Process -FilePath $Python -ArgumentList "`"$script`"" `
    -WorkingDirectory $BackendDir -Wait -PassThru -NoNewWindow `
    -RedirectStandardOutput $OutFile -RedirectStandardError $ErrFile
$code = $p.ExitCode
Write-Log "EXIT code=$code"
if (Test-Path -LiteralPath $OutFile) {
    Get-Content -LiteralPath $OutFile -ErrorAction SilentlyContinue | ForEach-Object { Write-Log $_ }
}
if (Test-Path -LiteralPath $ErrFile) {
    Get-Content -LiteralPath $ErrFile -ErrorAction SilentlyContinue | ForEach-Object { Write-Log "ERR $_" }
}
exit $code
