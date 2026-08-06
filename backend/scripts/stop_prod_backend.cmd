@echo off
REM Stop prod backend task and free port 48011
setlocal
set "TASK=TestAI-Backend"
set "PORT=48011"
schtasks /End /TN "%TASK%" >nul 2>&1
timeout /t 2 /nobreak >nul
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT% " ^| findstr LISTENING') do (
  echo Kill PID %%P
  taskkill /PID %%P /F >nul 2>&1
)
echo Stopped %TASK% and freed port %PORT%
exit /b 0
