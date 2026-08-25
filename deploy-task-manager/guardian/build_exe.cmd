@echo off
chcp 65001 >nul
rem ============================================================
rem  Build guardian.exe with PyInstaller
rem  Run this on the development machine, not on 62.
rem  Output: dist\guardian.exe
rem ============================================================

echo ====== Building guardian.exe ======

rem --- Check Python ---
python --version 2>nul
if errorlevel 1 (
    echo Python not found in PATH. Install Python 3.11+ first.
    pause
    exit /b 1
)

rem --- Install deps ---
echo Installing dependencies...
python -m pip install -r requirements.txt -q

rem --- Build ---
echo Building exe (this takes ~30s)...
python -m PyInstaller --onefile --name guardian --noconsole --clean ^
    --hidden-import uvicorn.logging ^
    --hidden-import uvicorn.protocols ^
    --hidden-import uvicorn.protocols.http ^
    --hidden-import uvicorn.protocols.http.auto ^
    --hidden-import uvicorn.protocols.websockets ^
    --hidden-import uvicorn.protocols.websockets.auto ^
    --hidden-import uvicorn.lifespan ^
    --hidden-import uvicorn.lifespan.on ^
    --hidden-import psutil ^
    guardian.py

if exist "dist\guardian.exe" (
    echo.
    echo ====== Build OK! ======
    echo Output: dist\guardian.exe
    echo Copy guardian.exe + services.json to 62 server.
) else (
    echo.
    echo ====== Build FAILED ======
    echo Check the error messages above.
)

pause
