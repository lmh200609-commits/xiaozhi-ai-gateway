@echo off
chcp 65001 >nul
title Xiaozhi AI Voice Gateway
cd /d "%~dp0"

echo =======================================================
echo          小智 AI 语音网关 - 跨电脑便携启动器
echo =======================================================

:: 1. 优先检测当前目录的独立虚拟环境 .venv
set "PY_CMD="
if exist ".venv\Scripts\python.exe" (
    set "PY_CMD=.venv\Scripts\python.exe"
    echo [*] 正在使用本地虚拟环境 (.venv)
)

:: 2. 若无虚拟环境，检测系统 py 或 python
if "%PY_CMD%"=="" (
    where py >nul 2>nul
    if not errorlevel 1 (
        set "PY_CMD=py -3.11"
        echo [*] 正在使用系统 Python Launcher (py -3.11)
    )
)

if "%PY_CMD%"=="" (
    where python >nul 2>nul
    if not errorlevel 1 (
        set "PY_CMD=python"
        echo [*] 正在使用系统 python
    )
)

if "%PY_CMD%"=="" (
    echo.
    echo [错误] 未在系统中检测到可用 Python 环境！
    echo 请先安装 Python 3.10 或 3.11，并确保勾选 'Add Python to PATH'。
    echo 或先运行 setup_env.bat 自动配置环境。
    echo.
    pause
    exit /b 1
)

echo [*] 工作根目录: %~dp0
echo [*] 正在启动网关服务...
echo.

%PY_CMD% "gateway\scripts\run_gateway.py"

if errorlevel 1 (
    echo.
    echo [提示] 网关异常退出。如果是首次在新电脑运行，请先双击 setup_env.bat 安装依赖。
    pause
)