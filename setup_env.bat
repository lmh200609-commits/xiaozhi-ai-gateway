@echo off
chcp 65001 >nul
title 小智 AI 语音网关 - 一键环境部署与配置
cd /d "%~dp0"

echo =======================================================
echo          小智 AI 语音网关 - 跨电脑一键初始化向导
echo =======================================================
echo.

:: 1. 检测 Python
set "SYS_PY="
where py >nul 2>nul
if not errorlevel 1 (
    set "SYS_PY=py -3.11"
) else (
    where python >nul 2>nul
    if not errorlevel 1 (
        set "SYS_PY=python"
    )
)

if "%SYS_PY%"=="" (
    echo [错误] 系统中未找到 Python！
    echo 请先安装 Python 3.10 或 3.11 (建议从 python.org 下载 64 位版本)
    echo 安装时务必勾选 "Add python.exe to PATH"！
    echo.
    pause
    exit /b 1
)

echo [*] 检测到系统 Python: %SYS_PY%
%SYS_PY% --version
echo.

:: 2. 创建独立虚拟环境 .venv (避免与其他项目依赖冲突)
if not exist ".venv\Scripts\python.exe" (
    echo [*] 正在创建独立虚拟环境 (.venv)...
    %SYS_PY% -m venv .venv
    if errorlevel 1 (
        echo [!] 创建虚拟环境失败，将使用全局 Python 环境安装依赖。
        set "VENV_PY=%SYS_PY%"
    ) else (
        echo [*] 虚拟环境创建成功！
        set "VENV_PY=.venv\Scripts\python.exe"
    )
) else (
    echo [*] 已存在虚拟环境 (.venv)
    set "VENV_PY=.venv\Scripts\python.exe"
)

echo.
echo [*] 正在配置国内 PyPI 镜像源并升级 pip...
%VENV_PY% -m pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ >nul 2>nul
%VENV_PY% -m pip install --upgrade pip

echo.
echo [*] 正在安装网关完整依赖包 (FastAPI, Sherpa-ONNX, Edge-TTS, FastEmbed, Jieba, ESP工具等)...
%VENV_PY% -m pip install -r "gateway\requirements.txt"
if errorlevel 1 (
    echo [!] 部分依赖安装遇到警告，尝试直接安装核心库...
)

echo.
echo [*] 正在检查离线语音识别模型 (SenseVoice INT8)...
%VENV_PY% "gateway\scripts\download_models.py"

:: 3. 配置文件初始化
if not exist "gateway\config.json" (
    if exist "gateway\config.example.json" (
        copy "gateway\config.example.json" "gateway\config.json" >nul
        echo [*] 已为您生成默认网关配置文件: gateway\config.json
    )
)

if not exist "nvs_config.csv" (
    if exist "nvs_config.example.csv" (
        copy "nvs_config.example.csv" "nvs_config.csv" >nul
        echo [*] 已为您生成默认开发板配置模板: nvs_config.csv
    )
)

echo.
echo =======================================================
echo [✓] 恭喜！小智 AI 语音网关跨电脑环境已全部就绪！
echo.
echo 下一步使用建议：
echo 1. 打开 gateway\config.json，填入您的大模型 relay_api_key 与模型配置
echo 2. 双击 start_gateway.bat 即可启动网关！
echo 3. 浏览器会自动打开控制台: http://localhost:8001
echo =======================================================
echo.
pause