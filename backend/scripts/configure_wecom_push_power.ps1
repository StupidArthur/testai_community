# Desktop + Win+L/Ctrl+L lock: keep awake for WeCom push; no sleep/hibernate; no fast startup.
# Run elevated if registry write fails:
#   powershell -ExecutionPolicy Bypass -File .\configure_wecom_push_power.ps1

$ErrorActionPreference = "Continue"

Write-Host "=== Before ==="
powercfg /a
Write-Host ""

# Never sleep / hibernate (AC+DC)
powercfg /change standby-timeout-ac 0
powercfg /change standby-timeout-dc 0
powercfg /change hibernate-timeout-ac 0
powercfg /change hibernate-timeout-dc 0
powercfg /setacvalueindex SCHEME_CURRENT SUB_SLEEP STANDBYIDLE 0
powercfg /setdcvalueindex SCHEME_CURRENT SUB_SLEEP STANDBYIDLE 0
powercfg /setacvalueindex SCHEME_CURRENT SUB_SLEEP HIBERNATEIDLE 0
powercfg /setdcvalueindex SCHEME_CURRENT SUB_SLEEP HIBERNATEIDLE 0
powercfg /setacvalueindex SCHEME_CURRENT SUB_SLEEP HYBRIDSLEEP 0
powercfg /setdcvalueindex SCHEME_CURRENT SUB_SLEEP HYBRIDSLEEP 0

# Power button = shutdown is OK; do not sleep on "sleep button" if present
# Try set sleep button to Do nothing (0) when available
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS SBUTTONACTION 0 2>$null
powercfg /setdcvalueindex SCHEME_CURRENT SUB_BUTTONS SBUTTONACTION 0 2>$null

powercfg /setactive SCHEME_CURRENT

# Disable Fast Startup (makes unlock sometimes look like boot)
$hiberbootKey = "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power"
try {
    Set-ItemProperty -Path $hiberbootKey -Name HiberbootEnabled -Value 0 -Type DWord -Force -ErrorAction Stop
    Write-Host "HiberbootEnabled set to 0 (Fast Startup OFF)"
} catch {
    Write-Host "NEED ADMIN to disable Fast Startup."
    Write-Host "Run elevated PowerShell:"
    Write-Host '  reg add "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power" /v HiberbootEnabled /t REG_DWORD /d 0 /f'
}

Write-Host ""
Write-Host "=== After ==="
reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power" /v HiberbootEnabled
powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE | Select-String "Current AC Power Setting Index|Current DC Power Setting Index"
powercfg /query SCHEME_CURRENT SUB_SLEEP HIBERNATEIDLE | Select-String "Current AC Power Setting Index|Current DC Power Setting Index"
Write-Host "KeepAwake:" (Get-ScheduledTask -TaskName "TestAI-WeCom-KeepAwake").State
Write-Host ""
Write-Host "Desktop OK: Win+L / lock screen = session stays, push can run."
Write-Host "Do NOT: Shutdown / Restart / Hibernate / Sleep."
