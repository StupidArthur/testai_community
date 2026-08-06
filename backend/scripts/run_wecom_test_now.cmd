@echo off
REM Run WeCom TEST push RIGHT NOW (no waiting for clock).
REM Usage on prod:
REM   cd /d D:\deploy\testai_community_prod\backend\scripts
REM   .\run_wecom_test_now.cmd weekly
REM   .\run_wecom_test_now.cmd daily
setlocal
cd /d "%~dp0"
set "KIND=%~1"
if "%KIND%"=="" set "KIND=weekly"
if /I "%KIND%"=="weekly" (
  call "%~dp0wecom_push_test_weekly.cmd"
  echo.
  echo Log: %~dp0logs\wecom_test_weekly.log
  type "%~dp0logs\wecom_test_weekly.log" 2>nul
  exit /b %ERRORLEVEL%
)
if /I "%KIND%"=="daily" (
  call "%~dp0wecom_push_test_daily.cmd"
  echo.
  echo Log: %~dp0logs\wecom_test_daily.log
  type "%~dp0logs\wecom_test_daily.log" 2>nul
  exit /b %ERRORLEVEL%
)
echo Usage: run_wecom_test_now.cmd weekly^|daily
exit /b 1
