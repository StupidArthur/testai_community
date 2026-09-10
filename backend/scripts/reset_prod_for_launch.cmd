@echo off
chcp 65001 >nul
setlocal

echo ============================================
echo  重置生产环境数据并创建正式用户
echo ============================================
echo.

REM ==== 1. 定位后端工作目录（优先 62 新路径） ====
set "BACKEND_DIR="
if exist "D:\testai_community_prod\backend\.venv\Scripts\python.exe" set "BACKEND_DIR=D:\testai_community_prod\backend"
if not defined BACKEND_DIR if exist "D:\deploy\testai_community_prod\backend\.venv\Scripts\python.exe" set "BACKEND_DIR=D:\deploy\testai_community_prod\backend"

if not defined BACKEND_DIR (
    echo [ERROR] 找不到项目目录：
    echo         D:\testai_community_prod\backend\.venv\Scripts\python.exe
    echo         D:\deploy\testai_community_prod\backend\.venv\Scripts\python.exe
    echo 请确认代码已部署到 62。
    pause
    exit /b 1
)

echo [OK] 后端目录: %BACKEND_DIR%

REM ==== 2. 定位脚本（脚本应与本 cmd 在同一目录，或在 backend\scripts\ 下） ====
set "SCRIPT=%~dp0reset_prod_for_launch.py"
if not exist "%SCRIPT%" set "SCRIPT=%BACKEND_DIR%\scripts\reset_prod_for_launch.py"
if not exist "%SCRIPT%" (
    echo [ERROR] 找不到脚本 reset_prod_for_launch.py
    echo 请把 reset_prod_for_launch.py 和本 cmd 放到同一目录，
    echo 或放到 %BACKEND_DIR%\scripts\ 下。
    pause
    exit /b 1
)
echo [OK] 脚本路径: %SCRIPT%
echo.

REM ==== 3. 停后端（通过 guardian 端口检查，若 48011 监听则提示）===
echo [..] 检查后端服务...
netstat -ano | findstr ":48011" | findstr "LISTENING" >nul
if %errorlevel%==0 (
    echo [!!] 检测到后端正在运行（端口 48011 监听中）。
    echo      建议先通过 guardian 面板 http://127.0.0.1:9000 停止 testai-backend 服务，
    echo      再运行本脚本；脚本执行完后再启动。
    echo.
    choice /C YN /M "现在继续执行吗？(Y=继续，N=取消)"
    if errorlevel 2 (
        echo 已取消。请先停止后端再重新运行。
        pause
        exit /b 0
    )
)

echo.
echo [..] 开始执行重置脚本...
echo ============================================
"%BACKEND_DIR%\.venv\Scripts\python.exe" "%SCRIPT%"
echo ============================================
echo.

if %errorlevel% neq 0 (
    echo [ERROR] 脚本执行失败，错误码 %errorlevel%
    pause
    exit /b %errorlevel%
)

echo.
echo [提醒] 请通过 guardian 面板重启 testai-backend 服务。
echo        然后浏览器访问 http://10.30.144.62:48011/admin 验证用户列表应为 39 人。
pause
