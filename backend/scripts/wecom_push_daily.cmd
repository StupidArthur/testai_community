@echo off
REM 委托给 wecom_push_daily.ps1（自动选用 backend\.venv 或本机 Python）
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0wecom_push_daily.ps1"
exit /b %ERRORLEVEL%
