@echo off
REM Restore normal WeCom/DingTalk push schedule after half-hour test.
setlocal
cd /d "%~dp0"
echo Restoring normal push schedule ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0restore_normal_push_schedule.ps1"
if errorlevel 1 (
  echo FAIL: restore_normal_push_schedule.ps1
  exit /b 1
)
echo.
echo REMEMBER: set DINGTALK_*_IDEMPOTENCY_ENABLED=true in prod .env
exit /b 0
