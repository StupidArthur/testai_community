@echo off
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"%~dp0manage.ps1\" -Action start' -Verb RunAs -Wait"
pause
