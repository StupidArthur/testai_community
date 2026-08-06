@echo off
REM One-shot TEST today: weekly + daily at 17:06 (local).
REM On PROD Admin PowerShell:
REM   cd /d D:\deploy\testai_community_prod\backend\scripts
REM   .\install_wecom_test_1706.cmd
setlocal EnableExtensions
cd /d "%~dp0"

set "TASK_W=TestAI-WeCom-Test-Weekly-1706"
set "TASK_D=TestAI-WeCom-Test-Daily-1706"
set "CMD_W=%~dp0wecom_push_test_weekly.cmd"
set "CMD_D=%~dp0wecom_push_test_daily.cmd"

REM Today local date for schtasks (yyyy/MM/dd). Override if needed:
set "SD=%DATE:~0,4%/%DATE:~5,2%/%DATE:~8,2%"
REM Fallback fixed if locale weird:
if not exist "%CMD_W%" (
  echo FAIL missing %CMD_W%
  exit /b 1
)
if not exist "%CMD_D%" (
  echo FAIL missing %CMD_D%
  exit /b 1
)

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyy/MM/dd"') do set "SD=%%I"
set "ST=17:06"

echo Remove old test tasks ...
schtasks /Delete /TN "TestAI-WeCom-Test-Weekly-1410" /F >nul 2>&1
schtasks /Delete /TN "TestAI-WeCom-Test-Daily-1415" /F >nul 2>&1
schtasks /Delete /TN "%TASK_W%" /F >nul 2>&1
schtasks /Delete /TN "%TASK_D%" /F >nul 2>&1

echo Create %TASK_W%  %SD% %ST%
schtasks /Create /TN "%TASK_W%" /TR "cmd /c \"\"%CMD_W%\"\"" /SC ONCE /SD %SD% /ST %ST% /RL HIGHEST /F /IT
if errorlevel 1 (
  echo FAIL weekly task
  exit /b 1
)

echo Create %TASK_D%  %SD% %ST%
schtasks /Create /TN "%TASK_D%" /TR "cmd /c \"\"%CMD_D%\"\"" /SC ONCE /SD %SD% /ST %ST% /RL HIGHEST /F /IT
if errorlevel 1 (
  echo FAIL daily task
  exit /b 1
)

echo.
echo Registered ONE-SHOT tests:
echo   Weekly: %SD% %ST%  (%TASK_W%)
echo   Daily : %SD% %ST%  (%TASK_D%)
schtasks /Query /TN "%TASK_W%" /FO LIST | findstr /i "TaskName Next Run Status"
echo.
schtasks /Query /TN "%TASK_D%" /FO LIST | findstr /i "TaskName Next Run Status"
echo.
echo After 17:06 check WeCom group + logs:
echo   scripts\logs\wecom_test_weekly.log
echo   scripts\logs\wecom_test_daily.log
echo PASS
exit /b 0
