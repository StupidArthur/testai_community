@echo off
chcp 65001 >nul
rem ============================================================
rem  Build deploy-task-manager.exe with PyInstaller
rem  Run this on the development machine, not on 62.
rem  Output: dist\deploy-task-manager.exe
rem
rem  After building, copy these to 62 server alongside the exe:
rem    - frontend\dist\   (web UI)
rem    - tasks\            (task scripts)
rem    - .env              (config)
rem ============================================================

echo ====== Building deploy-task-manager.exe ======

rem --- Check Python ---
python --version 2>nul
if errorlevel 1 (
    echo Python not found in PATH. Install Python 3.11+ first.
    pause
    exit /b 1
)

rem --- Install deps from local wheels ---
echo Installing dependencies from local packages...
python -m pip install --no-index --find-links=packages -r requirements.txt -q 2>nul
if errorlevel 1 (
    echo Local install failed, trying online...
    python -m pip install -r requirements.txt -q
)

rem --- Install PyInstaller ---
python -m pip install pyinstaller -q 2>nul

rem --- Clean previous build ---
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist deploy-task-manager.spec del deploy-task-manager.spec

rem --- Build ---
echo Building exe (this takes ~60s)...
pyinstaller --onefile --name deploy-task-manager --noconsole --clean ^
    --hidden-import uvicorn.logging ^
    --hidden-import uvicorn.protocols ^
    --hidden-import uvicorn.protocols.http ^
    --hidden-import uvicorn.protocols.http.auto ^
    --hidden-import uvicorn.protocols.websockets ^
    --hidden-import uvicorn.protocols.websockets.auto ^
    --hidden-import uvicorn.lifespan ^
    --hidden-import uvicorn.lifespan.on ^
    --hidden-import apscheduler.schedulers.background ^
    --hidden-import apscheduler.triggers.cron ^
    --hidden-import apscheduler.jobstores.memory ^
    --hidden-import apscheduler.executors.pool ^
    --hidden-import psutil ^
    --hidden-import httptools ^
    --hidden-import watchfiles ^
    --hidden-import websockets ^
    main.py

if exist "dist\deploy-task-manager.exe" (
    echo.
    echo ====== Build OK! ======
    echo Output: dist\deploy-task-manager.exe
    echo.
    echo Copy these to 62 server alongside the exe:
    echo   - frontend\dist\
    echo   - tasks\
    echo   - .env
) else (
    echo.
    echo ====== Build FAILED ======
    echo Check the error messages above.
)

pause
