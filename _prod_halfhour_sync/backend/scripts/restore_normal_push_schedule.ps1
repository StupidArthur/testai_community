# Restore normal Daily(17:12+20:00..04) + Weekly(1min poll) after half-hour test.
# Removes TestAI-Push-HalfHour-Test; re-runs install_wecom_scheduled_tasks.ps1.
# ASCII-only for Windows PowerShell 5.x.

$ErrorActionPreference = "Stop"
$ScriptsDir = $PSScriptRoot
$TestTaskName = "TestAI-Push-HalfHour-Test"

Get-ScheduledTask -TaskName $TestTaskName -ErrorAction SilentlyContinue |
    Unregister-ScheduledTask -Confirm:$false -ErrorAction SilentlyContinue
Write-Host ("Removed (if existed): " + $TestTaskName)

$Install = Join-Path $ScriptsDir "install_wecom_scheduled_tasks.ps1"
if (-not (Test-Path $Install)) { throw ("Missing " + $Install) }
& $Install

Write-Host ""
Write-Host "REQUIRED: set prod .env back to:"
Write-Host "  DINGTALK_PUSH_IDEMPOTENCY_ENABLED=true"
Write-Host "  DINGTALK_WEEKLY_IDEMPOTENCY_ENABLED=true"
Write-Host ""
Write-Host "Verify:"
Write-Host "  schtasks /Query /TN TestAI-WeCom-Daily /FO LIST"
Write-Host "  schtasks /Query /TN TestAI-WeCom-Weekly /FO LIST"
Write-Host "  schtasks /Query /TN TestAI-Push-HalfHour-Test /FO LIST"
