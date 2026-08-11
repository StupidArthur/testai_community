# Half-hour push test: same path as 20:00 Daily / Weekly tasks.
# :00 -> wecom_push_daily.ps1 ; :30 -> wecom_push_weekly.ps1
# Always TM_PUSH_FORCE=1 (bypass week_end gate + allow re-send when idempotency off).
$ErrorActionPreference = "Continue"
$ScriptsDir = $PSScriptRoot
$now = Get-Date
$minute = $now.Minute
$hour = $now.Hour

# Window guard: 10:00 .. 21:00 inclusive (21:00 is daily; no 21:30)
if ($hour -lt 10 -or $hour -gt 21 -or ($hour -eq 21 -and $minute -ge 30)) {
    Write-Host ("SKIP outside 10:00-21:00 window now={0:HH:mm}" -f $now)
    exit 0
}

# Odd half-hour -> weekly; on-the-hour -> daily (21:00 daily)
$env:TM_PUSH_FORCE = "1"
if ($minute -ge 15 -and $minute -lt 45) {
    $kind = "weekly"
    $target = Join-Path $ScriptsDir "wecom_push_weekly.ps1"
} else {
    $kind = "daily"
    $target = Join-Path $ScriptsDir "wecom_push_daily.ps1"
}

Write-Host ("{0:yyyy-MM-dd HH:mm:ss} halfhour-test kind={1} force=1 script={2}" -f $now, $kind, $target)
& $target
exit $LASTEXITCODE
