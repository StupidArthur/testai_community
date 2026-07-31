# Install WeCom push scheduled tasks. ASCII-only messages for PS 5.x parse safety.
# Run: powershell -ExecutionPolicy Bypass -File .\install_wecom_scheduled_tasks.ps1
#
# Reliability (required on Modern Standby laptops):
#   1) Sleep = Never (AC): .\configure_wecom_push_power.ps1
#   2) Keep-awake at logon: .\install_wecom_keep_awake.ps1
#      (Settings "Sleep=Never" alone often cannot block Connected Standby after screen-off.)
#   3) Push tasks: Interactive + WakeToRun + StartWhenAvailable.

$ErrorActionPreference = "Stop"

$ScriptsDir = $PSScriptRoot
$DailyPs1 = Join-Path $ScriptsDir "wecom_push_daily.ps1"
$WeeklyPs1 = Join-Path $ScriptsDir "wecom_push_weekly.ps1"
if (-not (Test-Path $DailyPs1)) { throw "Missing $DailyPs1" }
if (-not (Test-Path $WeeklyPs1)) { throw "Missing $WeeklyPs1" }

$UserId = if ($env:USERDOMAIN) { "$env:USERDOMAIN\$env:USERNAME" } else { $env:USERNAME }
$PsExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

Write-Host "Daily  : $DailyPs1"
Write-Host "Weekly : $WeeklyPs1"
Write-Host "User   : $UserId"

function Install-Ps1Task {
    param(
        [string]$TaskName,
        [string]$Ps1Path,
        [string]$Kind
    )

    $arg = "-NoProfile -ExecutionPolicy Bypass -File `"$Ps1Path`""
    $action = New-ScheduledTaskAction -Execute $PsExe -Argument $arg

    if ($Kind -eq "daily") {
        # 20:00 主发 + 20:15 备份（已成功则幂等跳过）
        $trigger = @(
            (New-ScheduledTaskTrigger -Daily -At "20:00"),
            (New-ScheduledTaskTrigger -Daily -At "20:15")
        )
    }
    else {
        # 周三 17:30 主发 + 17:45 备份
        $trigger = @(
            (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Wednesday -At "17:30"),
            (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Wednesday -At "17:45")
        )
    }

    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -WakeToRun `
        -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
        -MultipleInstances IgnoreNew

    # Interactive: no password prompt; requires user session + PC not in Connected Standby.
    # Prefer configure_wecom_push_power.ps1 (Sleep=Never) over Password logon type.
    $principal = New-ScheduledTaskPrincipal `
        -UserId $UserId `
        -LogonType Interactive `
        -RunLevel Limited

    Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue |
        Unregister-ScheduledTask -Confirm:$false -ErrorAction SilentlyContinue

    try {
        Register-ScheduledTask `
            -TaskName $TaskName `
            -Action $action `
            -Trigger $trigger `
            -Settings $settings `
            -Principal $principal | Out-Null
    }
    catch {
        # Fallback: current user without domain prefix
        Write-Host "Retry with UserId=$env:USERNAME ..."
        $principal2 = New-ScheduledTaskPrincipal `
            -UserId $env:USERNAME `
            -LogonType Interactive `
            -RunLevel Limited
        Register-ScheduledTask `
            -TaskName $TaskName `
            -Action $action `
            -Trigger $trigger `
            -Settings $settings `
            -Principal $principal2 | Out-Null
    }

    Write-Host "Registered $TaskName ($Kind)"
}

Install-Ps1Task -TaskName "TestAI-WeCom-Daily" -Ps1Path $DailyPs1 -Kind "daily"
Install-Ps1Task -TaskName "TestAI-WeCom-Weekly" -Ps1Path $WeeklyPs1 -Kind "weekly"

# Keep-awake: required on Modern Standby when Sleep=Never still allows Connected Standby.
$KeepInstall = Join-Path $ScriptsDir "install_wecom_keep_awake.ps1"
if (Test-Path $KeepInstall) {
    Write-Host ""
    Write-Host "Installing keep-awake ..."
    & $KeepInstall
}

Write-Host ""
Write-Host "Done."
Write-Host "  [1] Ensure .env has WECOM_WEBHOOK_URL"
Write-Host "  [2] Set WECOM_PUSH_ENABLED=false if run.py scheduler is on"
Write-Host "  [3] Daily 20:00+20:15 backup; Weekly Wed 17:30+17:45 backup"
Write-Host "  [4] Sleep=Never + TestAI-WeCom-KeepAwake (lock / screen-off OK)"
Write-Host "  [5] Optional: .\configure_wecom_push_power.ps1"
