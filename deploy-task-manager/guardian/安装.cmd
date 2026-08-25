@echo off
chcp 65001 >nul
rem Guardian install - requires admin
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"%~dp0manage.ps1\" -Action install' -Verb RunAs -Wait"
pause
