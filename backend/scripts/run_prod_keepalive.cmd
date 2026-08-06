@echo off
REM Prod backend keepalive: auto-restart 5s after crash. Log = scripts\logs\
REM Started by Scheduled Task TestAI-Backend. Do NOT run prod in an open PowerShell.
setlocal
cd /d "%~dp0.."
if not exist "scripts\logs" mkdir "scripts\logs"
set "LOG=scripts\logs\backend_keepalive.log"
set "PY=.venv\Scripts\python.exe"
set "APP=run_prod.py"

echo ========== %DATE% %TIME% keepalive start ==========>> "%LOG%"
if not exist "%PY%" (
  echo FAIL missing %CD%\%PY%>> "%LOG%"
  exit /b 1
)
if not exist "%APP%" (
  echo FAIL missing %CD%\%APP%>> "%LOG%"
  exit /b 1
)

:loop
echo ---------- %DATE% %TIME% starting %PY% %APP% ---------->> "%LOG%"
"%PY%" "%APP%" >> "%LOG%" 2>&1
set EC=%ERRORLEVEL%
echo ---------- %DATE% %TIME% exited code=%EC% ; restart in 5s ---------->> "%LOG%"
timeout /t 5 /nobreak >nul
goto loop
