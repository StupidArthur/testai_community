# 停止生产后端计划任务并释放端口
$ErrorActionPreference = "Continue"
$TaskName = "TestAI-Backend"
$Port = 48011
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
$lines = netstat -ano | Select-String ":$Port\s+.*LISTENING"
foreach ($line in $lines) {
    $parts = ($line.ToString() -split "\s+") | Where-Object { $_ -ne "" }
    $procId = $parts[-1]
    if ($procId -match "^\d+$" -and $procId -ne "0") {
        Write-Host "Kill PID $procId"
        taskkill /PID $procId /F 2>$null | Out-Null
    }
}
Write-Host "Stopped $TaskName and freed port $Port"
