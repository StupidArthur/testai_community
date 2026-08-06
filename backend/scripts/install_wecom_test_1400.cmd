@echo off
REM One-shot TEST: weekly 14:10, daily 14:15 on 2026-08-05 (local time).
REM Does NOT replace normal 20:00 daily / week_end+15 weekly tasks.
REM On PROD (Admin):
REM   cd /d D:\deploy\testai_community_prod\backend\scripts
REM   .\install_wecom_test_1400.cmd
setlocal EnableExtensions
cd /d "%~dp0"

set "TASK_W=TestAI-WeCom-Test-Weekly-1410"
set "TASK_D=TestAI-WeCom-Test-Daily-1415"
set "CMD_W=%~dp0wecom_push_test_weekly.cmd"
set "CMD_D=%~dp0wecom_push_test_daily.cmd"
set "SD=2026/08/05"
set "ST_W=14:10"
set "ST_D=14:15"

if not exist "%CMD_W%" (
  echo FAIL missing %CMD_W%
  exit /b 1
)
if not exist "%CMD_D%" (
  echo FAIL missing %CMD_D%
  exit /b 1
)

echo Remove old test tasks if any ...
schtasks /Delete /TN "TestAI-WeCom-Test-Weekly-1400" /F >nul 2>&1
schtasks /Delete /TN "TestAI-WeCom-Test-Daily-1405" /F >nul 2>&1
schtasks /Delete /TN "%TASK_W%" /F >nul 2>&1
schtasks /Delete /TN "%TASK_D%" /F >nul 2>&1

echo Create %TASK_W%  %SD% %ST_W%
REM /TR via cmd /c is more reliable than quoting .cmd path alone
schtasks /Create /TN "%TASK_W%" /TR "cmd /c \"\"%CMD_W%\"\"" /SC ONCE /SD %SD% /ST %ST_W% /RL HIGHEST /F /IT
if errorlevel 1 (
  echo FAIL create weekly test task. Try date format for your locale, e.g. 05/08/2026
  exit /b 1
)

echo Create %TASK_D%  %SD% %ST_D%
schtasks /Create /TN "%TASK_D%" /TR "cmd /c \"\"%CMD_D%\"\"" /SC ONCE /SD %SD% /ST %ST_D% /RL HIGHEST /F /IT
if errorlevel 1 (
  echo FAIL create daily test task
  exit /b 1
)

echo.
echo Registered:
schtasks /Query /TN "%TASK_W%" /FO LIST | findstr /i "TaskName Next Run Status"
echo.
schtasks /Query /TN "%TASK_D%" /FO LIST | findstr /i "TaskName Next Run Status"
echo.
echo Weekly test: 2026-08-05 14:10
echo Daily  test: 2026-08-05 14:15
echo Copy latest wecom_scheduled_push.py + these cmd files first.
echo After test:
echo   schtasks /Delete /TN %TASK_W% /F
echo   schtasks /Delete /TN %TASK_D% /F
echo.
echo PASS: test tasks created.
exit /b 0
