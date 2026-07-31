# Prevent Modern Standby / Connected Standby so WeCom scheduled push can fire on time.
# Screen off + lock screen remain OK (does NOT force display on).
#
# Run manually (stays until closed):
#   powershell -ExecutionPolicy Bypass -File .\wecom_keep_awake.ps1
# Install logon task:
#   powershell -ExecutionPolicy Bypass -File .\install_wecom_keep_awake.ps1
#
# ASCII-only for Windows PowerShell 5.x parse safety.

$ErrorActionPreference = "Stop"

# --- tunables (module top) ---
# How often to renew the "system required" request (seconds).
$RefreshSeconds = 60
# Optional log (append). Empty string = no file log.
$LogPath = Join-Path $PSScriptRoot "logs\wecom_keep_awake.log"
# EXECUTION STATE flags (Win32): keep system awake, allow display off.
# Note: 0x80000000 must go via Int64 — PS Int32 literal is negative and cannot cast to UInt32.
$ES_CONTINUOUS = [Convert]::ToUInt32("80000000", 16)
$ES_SYSTEM_REQUIRED = [Convert]::ToUInt32("00000001", 16)
$KeepFlags = $ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED
$ClearFlags = $ES_CONTINUOUS

if (-not ("TestAI.KeepAwakeNative" -as [type])) {
    Add-Type -Namespace TestAI -Name KeepAwakeNative -MemberDefinition @"
[DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
public static extern uint SetThreadExecutionState(uint esFlags);
"@
}

function Write-KeepLog {
    param([string]$Message)
    $line = "{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $Message
    Write-Host $line
    if (-not $LogPath) { return }
    $dir = Split-Path -Parent $LogPath
    if ($dir -and -not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    Add-Content -Path $LogPath -Value $line -Encoding UTF8
}

Write-KeepLog "keep-awake start (refresh=${RefreshSeconds}s). Screen may turn off; Connected Standby should be blocked."

try {
    while ($true) {
        [void][TestAI.KeepAwakeNative]::SetThreadExecutionState($KeepFlags)
        Start-Sleep -Seconds $RefreshSeconds
    }
}
finally {
    [void][TestAI.KeepAwakeNative]::SetThreadExecutionState($ClearFlags)
    Write-KeepLog "keep-awake stop"
}
