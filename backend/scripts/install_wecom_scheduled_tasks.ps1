# Install WeCom push scheduled tasks. ASCII-only for Windows PowerShell 5.x.
# Prefer:  .\install_wecom_tasks.cmd
# Or:      powershell -ExecutionPolicy Bypass -File .\install_wecom_scheduled_tasks.ps1
#
# Daily: 17:12 + 20:00..20:04 (idempotent; already-sent skips later ticks)
# Weekly: every 15 minutes; send time = week_end + 15 min (Python rule)
# Also installs TestAI-WeCom-KeepAwake when present.

$ErrorActionPreference = "Stop"

$ScriptsDir = $PSScriptRoot
$DailyPs1 = Join-Path $ScriptsDir "wecom_push_daily.ps1"
$WeeklyPs1 = Join-Path $ScriptsDir "wecom_push_weekly.ps1"
if (-not (Test-Path $DailyPs1)) { throw ("Missing " + $DailyPs1) }
if (-not (Test-Path $WeeklyPs1)) { throw ("Missing " + $WeeklyPs1) }

$UserId = if ($env:USERDOMAIN) { ($env:USERDOMAIN + "\" + $env:USERNAME) } else { $env:USERNAME }
$PsExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

Write-Host ("Daily  : " + $DailyPs1)
Write-Host ("Weekly : " + $WeeklyPs1)
Write-Host ("User   : " + $UserId)

function Install-Ps1Task {
    param(
        [string]$TaskName,
        [string]$Ps1Path,
        [string]$Kind
    )

    $arg = "-NoProfile -ExecutionPolicy Bypass -File `"$Ps1Path`""
    $action = New-ScheduledTaskAction -Execute $PsExe -Argument $arg

    if ($Kind -eq "daily") {
        $trigger = @(
            (New-ScheduledTaskTrigger -Daily -At "17:12"),
            (New-ScheduledTaskTrigger -Daily -At "20:00"),
            (New-ScheduledTaskTrigger -Daily -At "20:01"),
            (New-ScheduledTaskTrigger -Daily -At "20:02"),
            (New-ScheduledTaskTrigger -Daily -At "20:03"),
            (New-ScheduledTaskTrigger -Daily -At "20:04")
        )
    }
    else {
        # Duration must be finite; MaxValue is rejected by Windows Task Scheduler
        $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Days 3650)
    }

    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -WakeToRun `
        -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
        -MultipleInstances IgnoreNew

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
        Write-Host ("Retry with UserId=" + $env:USERNAME + " ...")
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

    Write-Host ("Registered " + $TaskName + " (" + $Kind + ")")
}

Install-Ps1Task -TaskName "TestAI-WeCom-Daily" -Ps1Path $DailyPs1 -Kind "daily"
Install-Ps1Task -TaskName "TestAI-WeCom-Weekly" -Ps1Path $WeeklyPs1 -Kind "weekly"

$KeepInstall = Join-Path $ScriptsDir "install_wecom_keep_awake.ps1"
if (Test-Path $KeepInstall) {
    Write-Host ""
    Write-Host "Installing keep-awake ..."
    & $KeepInstall
}

Write-Host ""
Write-Host "Done."
Write-Host "  [1] Ensure .env has WECOM_WEBHOOK_URL"
Write-Host "  [2] Set WECOM_PUSH_ENABLED=false (prod backend should not double-send)"
Write-Host "  [3] Daily 17:12 + 20:00~20:04 ; Weekly every 15min (week_end+15min rule)"
Write-Host "  [4] KeepAwake running; optional: .\configure_wecom_push_power.ps1"
Write-Host "  [5] Disable TestAI-WeCom-* on DEV machine to avoid double push"
