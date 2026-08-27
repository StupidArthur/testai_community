@echo off
chcp 65001 >nul
rem ============================================================
rem  Build deploy-task-manager.exe with PyInstaller
rem  Run this on the development machine, not on 62.
rem  Output: dist\deploy-task-manager.exe
rem
rem  必须用仓库里维护的 deploy-task-manager.spec，不要 --onefile 现场生成 spec：
rem  现场生成会丢掉 alg_monitor 所需的 httpx/boto3/dotenv，62 上任务会 0s 失败。
rem  main.py 已 import packaging_deps，分析器也会从入口扫到这些库。
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

if not exist deploy-task-manager.spec (
    echo Missing deploy-task-manager.spec in current directory.
    echo Run this script from the deploy\ folder.
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

rem --- Clean previous build artifacts only; keep the checked-in spec ---
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

rem --- Build from maintained spec (hiddenimports + packaging_deps via main.py) ---
echo Building exe from deploy-task-manager.spec (this takes ~60s)...
python -m PyInstaller --noconfirm --clean deploy-task-manager.spec

if exist "dist\deploy-task-manager.exe" (
    echo.
    echo ====== Build OK! ======
    echo Output: dist\deploy-task-manager.exe
    echo.
    echo Copy these to 62 server alongside the exe:
    echo   - frontend\dist\
    echo   - tasks\
    echo   - .env
    echo Then restart deploy-task-manager in guardian and manually run alg_monitor.
) else (
    echo.
    echo ====== Build FAILED ======
    echo Check the error messages above.
)

pause
