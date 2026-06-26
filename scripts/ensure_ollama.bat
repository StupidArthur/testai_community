@echo off
cd /d "%~dp0\.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ensure_ollama.ps1" %*
if errorlevel 1 pause
