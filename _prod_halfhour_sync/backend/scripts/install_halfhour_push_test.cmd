@echo off
REM Install half-hour Daily/Weekly ALTERNATING test schedule (prod).
REM Same push path as 20:00; FORCE=1; disables normal Daily/Weekly.
setlocal
cd /d "%~dp0"
echo Installing half-hour push TEST schedule ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_halfhour_push_test.ps1"
if errorlevel 1 (
  echo FAIL: install_halfhour_push_test.ps1
  exit /b 1
)
echo.
echo REMEMBER: set DINGTALK_*_IDEMPOTENCY_ENABLED=false in prod .env
echo Next tick uses wecom_push_daily.ps1 / wecom_push_weekly.ps1 (same as 20:00).
exit /b 0
