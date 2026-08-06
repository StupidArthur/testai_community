@echo off
REM ============================================================
REM TestAI prod backend installer (CMD). Starts backend HIDDEN.
REM Closing PowerShell/CMD after PASS must NOT kill the site.
REM
REM Admin CMD or PowerShell:
REM   cd /d D:\deploy\testai_community_prod\backend\scripts
REM   .\install_prod_backend.cmd
REM ============================================================
setlocal EnableExtensions
cd /d "%~dp0"

set "BACKEND=%~dp0.."
set "PY=%BACKEND%\.venv\Scripts\python.exe"
set "APP=%BACKEND%\run_prod.py"
set "KEEP=%~dp0run_prod_keepalive.cmd"
set "HIDDEN=%~dp0run_prod_keepalive_hidden.vbs"
set "TASK=TestAI-Backend"
set "PORT=48011"
set "LOGDIR=%~dp0logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

echo.
echo [1/6] Check files
if not exist "%PY%" (
  echo FAIL: missing %PY%
  exit /b 1
)
if not exist "%APP%" (
  echo FAIL: missing %APP%
  exit /b 1
)
if not exist "%KEEP%" (
  echo FAIL: missing %KEEP%
  exit /b 1
)
if not exist "%HIDDEN%" (
  echo FAIL: missing %HIDDEN%
  exit /b 1
)
echo OK python=%PY%
"%PY%" -c "import uvicorn; print('uvicorn', uvicorn.__version__)"
if errorlevel 1 (
  echo FAIL: venv cannot import uvicorn
  exit /b 1
)

echo.
echo [2/6] Stop old task / free port %PORT%
schtasks /End /TN "%TASK%" >nul 2>&1
schtasks /Delete /TN "%TASK%" /F >nul 2>&1
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT% " ^| findstr LISTENING') do (
  echo Kill PID %%P
  taskkill /PID %%P /F >nul 2>&1
)
timeout /t 2 /nobreak >nul

echo.
echo [3/6] Register scheduled task %TASK% ^(hidden via VBS^)
REM Use wscript + VBS so no black CMD window appears (closing a visible CMD used to kill the site)
schtasks /Create /TN "%TASK%" /TR "wscript.exe \"%HIDDEN%\"" /SC ONLOGON /RL HIGHEST /F
if errorlevel 1 (
  echo FAIL: schtasks create failed
  exit /b 1
)

echo.
echo [4/6] Start task now
schtasks /Run /TN "%TASK%"
if errorlevel 1 (
  echo FAIL: schtasks run failed
  exit /b 1
)

echo.
echo [5/6] Wait for health http://127.0.0.1:%PORT%/api/health
set /a N=0
:wait_health
set /a N+=1
curl.exe --max-time 3 -s "http://127.0.0.1:%PORT%/api/health" | findstr /i "ok" >nul
if not errorlevel 1 goto health_ok
if %N% GEQ 30 goto health_fail
timeout /t 2 /nobreak >nul
goto wait_health

:health_fail
echo FAIL: health not OK after ~60s
echo ---- last log lines ----
if exist "%LOGDIR%\backend_keepalive.log" (
  powershell -NoProfile -Command "Get-Content -LiteralPath '%LOGDIR%\backend_keepalive.log' -Tail 40"
) else (
  echo (no log yet) %LOGDIR%\backend_keepalive.log
)
exit /b 1

:health_ok
echo.
echo [6/6] PASS
curl.exe --max-time 3 -s "http://127.0.0.1:%PORT%/api/health"
echo.
echo Task: %TASK%  ^(runs HIDDEN - you should NOT see a black CMD for the server^)
schtasks /Query /TN "%TASK%" /FO LIST | findstr /i "Status TaskName"
echo Log:  %LOGDIR%\backend_keepalive.log
echo.
echo NEXT:
echo   1. Close ALL PowerShell / CMD windows  ^(site must stay up^)
echo   2. Open http://10.30.144.64:%PORT% from another PC
echo   3. If a black CMD appears for the server, something is wrong - re-run this installer
echo.
echo Stop:  .\stop_prod_backend.cmd
exit /b 0
