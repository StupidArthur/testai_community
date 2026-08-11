# Install half-hour DingTalk push TEST schedule on THIS machine (prod).
# ASCII-only for Windows PowerShell 5.x.
#
# Behavior:
#   10:00,11:00,...,21:00 -> daily  (same wecom_push_daily.ps1 as 20:00)
#   10:30,11:30,...,20:30 -> weekly (same wecom_push_weekly.ps1)
#   TM_PUSH_FORCE=1 always
# Disables: TestAI-WeCom-Daily / TestAI-WeCom-Weekly during test.
# Does NOT change KeepAwake.
#
# Before/after: set prod .env idempotency false/true (see Write-Host at end).

$ErrorActionPreference = "Stop"

$ScriptsDir = $PSScriptRoot
$TestPs1 = Join-Path $ScriptsDir "wecom_push_halfhour_test.ps1"
if (-not (Test-Path $TestPs1)) { throw ("Missing " + $TestPs1) }

$DailyPs1 = Join-Path $ScriptsDir "wecom_push_daily.ps1"
$WeeklyPs1 = Join-Path $ScriptsDir "wecom_push_weekly.ps1"
if (-not (Test-Path $DailyPs1)) { throw ("Missing " + $DailyPs1) }
if (-not (Test-Path $WeeklyPs1)) { throw ("Missing " + $WeeklyPs1) }

$UserId = if ($env:USERDOMAIN) { ($env:USERDOMAIN + "\" + $env:USERNAME) } else { $env:USERNAME }
$PsExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$TestTaskName = "TestAI-Push-HalfHour-Test"
$DailyTaskName = "TestAI-WeCom-Daily"
$WeeklyTaskName = "TestAI-WeCom-Weekly"

Write-Host ("Test script : " + $TestPs1)
Write-Host ("User        : " + $UserId)

# Disable normal Daily / Weekly (keep registered for easy restore)
foreach ($tn in @($DailyTaskName, $WeeklyTaskName)) {
    $t = Get-ScheduledTask -TaskName $tn -ErrorAction SilentlyContinue
    if ($t) {
        Disable-ScheduledTask -TaskName $tn | Out-Null
        Write-Host ("Disabled: " + $tn)
    } else {
        Write-Host ("WARN missing task (skip disable): " + $tn)
    }
}

$arg = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $TestPs1 + '"'
$action = New-ScheduledTaskAction -Execute $PsExe -Argument $arg

# 10:00 .. 21:00 every 30 minutes -> 23 triggers
$triggers = @()
for ($h = 10; $h -le 21; $h++) {
    $triggers += (New-ScheduledTaskTrigger -Daily -At ("{0:D2}:00" -f $h))
    if ($h -lt 21) {
        $triggers += (New-ScheduledTaskTrigger -Daily -At ("{0:D2}:30" -f $h))
    }
}

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew `
    -Hidden

$principal = New-ScheduledTaskPrincipal `
    -UserId $UserId `
    -LogonType Interactive `
    -RunLevel Limited

Get-ScheduledTask -TaskName $TestTaskName -ErrorAction SilentlyContinue |
    Unregister-ScheduledTask -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask `
    -TaskName $TestTaskName `
    -Action $action `
    -Trigger $triggers `
    -Settings $settings `
    -Principal $principal `
    -Force | Out-Null

Write-Host ("Registered: " + $TestTaskName + " triggers=" + $triggers.Count)
Write-Host ""
Write-Host "REQUIRED: edit prod .env (then restart backend NOT required for scheduled push scripts):"
Write-Host "  DINGTALK_PUSH_IDEMPOTENCY_ENABLED=false"
Write-Host "  DINGTALK_WEEKLY_IDEMPOTENCY_ENABLED=false"
Write-Host ""
Write-Host "Manual smoke (same path as task):"
Write-Host ("  powershell -NoProfile -ExecutionPolicy Bypass -File """ + $TestPs1 + """")
Write-Host ""
Write-Host "Restore later:"
Write-Host "  .\restore_normal_push_schedule.ps1"
Write-Host "  then set both IDEMPOTENCY flags back to true"
