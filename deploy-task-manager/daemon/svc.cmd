@echo off
chcp 65001 >nul
rem ====================================================================
rem  svc.cmd - Universal service daemon wrapper (run as Administrator)
rem  Examples:
rem    svc add TaskManager -Exe "D:\path\python.exe" -Arguments "main.py --port 8000" -Dir "D:\deploy-task-manager\deploy"
rem    svc list
rem    svc status TaskManager
rem    svc start TaskManager
rem    svc stop TaskManager
rem    svc restart TaskManager
rem    svc remove TaskManager
rem    svc install-watchdog
rem    svc uninstall-watchdog
rem ====================================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0svc.ps1" %*
