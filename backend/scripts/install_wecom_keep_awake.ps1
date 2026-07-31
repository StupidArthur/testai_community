# Register logon task: TestAI-WeCom-KeepAwake (blocks Connected Standby).
# ASCII-only. Run:
#   powershell -ExecutionPolicy Bypass -File .\install_wecom_keep_awake.ps1
#
# Also called from install_wecom_scheduled_tasks.ps1.

$ErrorActionPreference = "Stop"

$ScriptsDir = $PSScriptRoot
$KeepPs1 = Join-Path $ScriptsDir "wecom_keep_awake.ps1"
if (-not (Test-Path $KeepPs1)) { throw "Missing $KeepPs1" }

$TaskName = "TestAI-WeCom-KeepAwake"
$UserId = if ($env:USERDOMAIN) { "$env:USERDOMAIN\$env:USERNAME" } else { $env:USERNAME }
$PsExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

# Hidden window; run until logoff / task stop.
$arg = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$KeepPs1`""
$action = New-ScheduledTaskAction -Execute $PsExe -Argument $arg
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $UserId

# Unlimited run time; restart if process dies.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew `
    -Hidden

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
        -Principal $principal `
        -Description "Keep PC out of Modern Standby so TestAI WeCom push tasks fire on time. Screen off / lock OK." |
        Out-Null
}
catch {
    Write-Host "Retry with UserId=$env:USERNAME ..."
    $trigger2 = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $principal2 = New-ScheduledTaskPrincipal `
        -UserId $env:USERNAME `
        -LogonType Interactive `
        -RunLevel Limited
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger2 `
        -Settings $settings `
        -Principal $principal2 `
        -Description "Keep PC out of Modern Standby so TestAI WeCom push tasks fire on time." |
        Out-Null
}

# Start now (do not wait until next logon).
Start-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
$info = Get-ScheduledTaskInfo -TaskName $TaskName
$state = (Get-ScheduledTask -TaskName $TaskName).State

Write-Host "Registered $TaskName"
Write-Host "  User  : $UserId"
Write-Host "  State : $state"
Write-Host "  Last  : $($info.LastRunTime) result=$($info.LastTaskResult)"
Write-Host "  Log   : $(Join-Path $ScriptsDir 'logs\wecom_keep_awake.log')"
Write-Host "Done. Lock / screen-off OK; do not end this task if you need on-time WeCom push."
