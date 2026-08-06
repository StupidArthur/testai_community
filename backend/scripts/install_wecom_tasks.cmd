@echo off
REM Install WeCom Daily/Weekly/KeepAwake scheduled tasks on THIS machine (prod).
REM Run from: D:\deploy\testai_community_prod\backend\scripts
REM   .\install_wecom_tasks.cmd
setlocal
cd /d "%~dp0"

echo Installing WeCom scheduled tasks ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_wecom_scheduled_tasks.ps1"
if errorlevel 1 (
  echo FAIL: install_wecom_scheduled_tasks.ps1
  exit /b 1
)

echo.
echo Verify tasks:
schtasks /Query /TN "TestAI-WeCom-Daily" /FO LIST | findstr /i "TaskName Status"
schtasks /Query /TN "TestAI-WeCom-Weekly" /FO LIST | findstr /i "TaskName Status"
schtasks /Query /TN "TestAI-WeCom-KeepAwake" /FO LIST 2>nul | findstr /i "TaskName Status"

echo.
echo Manual dry-run test (optional, no real send if webhook empty):
echo   cd /d "%~dp0.."
echo   .\.venv\Scripts\python.exe scripts\wecom_scheduled_push.py
echo   (set TM_PUSH_KIND=daily or weekly in env first)
echo.
echo PASS if Daily + Weekly listed above.
exit /b 0
