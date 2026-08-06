# TestAI 服务器一键启动（Windows）
# 用法：在服务器管理员 PowerShell 中执行
#   cd D:\deploy\testai_community_prod\backend\scripts
#   powershell -ExecutionPolicy Bypass -File .\start_prod_server.ps1
#
# 作用：释放 48011 → 用 .venv + run_prod.py 启动（h11/asyncio）

$ErrorActionPreference = "Stop"
$BackendDir = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $BackendDir "run_prod.py"))) {
    $BackendDir = Split-Path -Parent $BackendDir
    $BackendDir = Join-Path $BackendDir "backend"
}

$Port = 48011
$VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
$RunProd = Join-Path $BackendDir "run_prod.py"

Write-Host "BackendDir = $BackendDir"
if (-not (Test-Path $VenvPython)) { throw "Missing venv python: $VenvPython" }
if (-not (Test-Path $RunProd)) { throw "Missing run_prod.py: $RunProd . Copy from dev machine first." }

# 杀掉占用端口的进程
$lines = netstat -ano | Select-String ":$Port\s+.*LISTENING"
foreach ($line in $lines) {
    $parts = ($line.ToString() -split "\s+") | Where-Object { $_ -ne "" }
    $procId = $parts[-1]
    if ($procId -match "^\d+$" -and $procId -ne "0") {
        Write-Host "Kill PID $procId on port $Port"
        taskkill /PID $procId /F | Out-Null
    }
}

Start-Sleep -Seconds 1
Set-Location -LiteralPath $BackendDir
Write-Host "Starting: $VenvPython $RunProd"
Write-Host "After start, OPEN ANOTHER window and run:"
Write-Host "  curl.exe --max-time 5 http://127.0.0.1:$Port/api/health"
Write-Host "Others access: http://10.30.144.64:$Port"
Write-Host ""

& $VenvPython $RunProd
