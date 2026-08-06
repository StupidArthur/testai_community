@echo off
REM Test wrapper: force daily push
setlocal
cd /d "%~dp0.."
set "TM_PUSH_KIND=daily"
set "TM_PUSH_FORCE=1"
set "PYTHONWARNINGS=ignore"
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=venv\Scripts\python.exe"
if not exist "%PY%" (
  echo FAIL no venv python>> "scripts\logs\wecom_test_daily.err.log"
  exit /b 1
)
if not exist "scripts\logs" mkdir "scripts\logs"
echo %DATE% %TIME% START daily FORCE>> "scripts\logs\wecom_test_daily.log"
"%PY%" "scripts\wecom_scheduled_push.py" >> "scripts\logs\wecom_test_daily.log" 2>&1
echo %DATE% %TIME% EXIT %ERRORLEVEL%>> "scripts\logs\wecom_test_daily.log"
exit /b %ERRORLEVEL%
