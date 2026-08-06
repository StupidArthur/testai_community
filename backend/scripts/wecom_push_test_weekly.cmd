@echo off
REM Test wrapper: force weekly push now (bypass week_end+15 gate)
setlocal
cd /d "%~dp0.."
set "TM_PUSH_KIND=weekly"
set "TM_PUSH_FORCE=1"
set "PYTHONWARNINGS=ignore"
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=venv\Scripts\python.exe"
if not exist "%PY%" (
  echo FAIL no venv python>> "scripts\logs\wecom_test_weekly.err.log"
  exit /b 1
)
if not exist "scripts\logs" mkdir "scripts\logs"
echo %DATE% %TIME% START weekly FORCE>> "scripts\logs\wecom_test_weekly.log"
"%PY%" "scripts\wecom_scheduled_push.py" >> "scripts\logs\wecom_test_weekly.log" 2>&1
echo %DATE% %TIME% EXIT %ERRORLEVEL%>> "scripts\logs\wecom_test_weekly.log"
exit /b %ERRORLEVEL%
