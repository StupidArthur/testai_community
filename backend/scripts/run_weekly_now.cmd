@echo off
REM Prod: force send WEEKLY right now + print log. Copy latest wecom_scheduled_push.py first.
setlocal
cd /d "%~dp0"
echo === force weekly now ===
call "%~dp0wecom_push_test_weekly.cmd"
echo.
echo === log tail ===
if exist "%~dp0logs\wecom_test_weekly.log" (
  powershell -NoProfile -Command "Get-Content -LiteralPath '%~dp0logs\wecom_test_weekly.log' -Tail 30"
) else (
  echo NO LOG - script may not have run. Check .venv and wecom_scheduled_push.py
)
exit /b 0
