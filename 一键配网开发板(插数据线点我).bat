@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 小智开发板 - USB 一键自动配网与 IP 烧录工具

echo ============================================================
echo      小智 AI 开发板 - USB 一键自动配网与 IP 烧录工具
echo ============================================================
echo.
echo 说明：
echo 当更换电脑或网络时，只需用 Type-C 数据线将小智开发板插在电脑上，
echo 运行本工具将自动获取当前电脑局域网 IP 并写入开发板，免除手动配网烦恼！
echo.

set "PY_CMD="
if exist ".venv\Scripts\python.exe" (
    set "PY_CMD=.venv\Scripts\python.exe"
) else (
    py -3.11 -V >nul 2>nul
    if not errorlevel 1 (
        set "PY_CMD=py -3.11"
    ) else (
        set "PY_CMD=python"
    )
)

%PY_CMD% "gateway\scripts\auto_sync_nvs.py"

echo.
pause
