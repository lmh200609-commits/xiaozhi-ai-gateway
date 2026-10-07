@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Xiaozhi AI Voice Gateway

echo ============================================================
echo      Xiaozhi AI Voice Gateway - Portable Launcher
echo ============================================================
echo [*] Working Directory: %~dp0
echo.

:: 1. Check local .venv first
if exist ".venv\Scripts\python.exe" (
    set "PY_CMD=.venv\Scripts\python.exe"
    echo [*] Found local project virtual environment (.venv)
    goto :LAUNCH
)

:: 2. Check py launcher with preferred stable versions
echo [*] Detecting system Python...
py -3.11 -V >nul 2>nul
if not errorlevel 1 (
    set "PY_CMD=py -3.11"
    goto :LAUNCH
)

py -3.10 -V >nul 2>nul
if not errorlevel 1 (
    set "PY_CMD=py -3.10"
    goto :LAUNCH
)

py -3.12 -V >nul 2>nul
if not errorlevel 1 (
    set "PY_CMD=py -3.12"
    goto :LAUNCH
)

py -3.14 -V >nul 2>nul
if not errorlevel 1 (
    set "PY_CMD=py -3.14"
    goto :LAUNCH
)

py -3 -V >nul 2>nul
if not errorlevel 1 (
    set "PY_CMD=py -3"
    goto :LAUNCH
)

python -V >nul 2>nul
if not errorlevel 1 (
    set "PY_CMD=python"
    goto :LAUNCH
)

echo [ERROR] No suitable Python installation found!
echo Please install Python 3.11 from https://www.python.org/
echo Make sure to check "Add Python to PATH" during installation.
echo.
pause
exit /b 1

:LAUNCH
echo [*] Starting gateway with: %PY_CMD%
echo.
%PY_CMD% "gateway\scripts\run_gateway.py"

if errorlevel 1 (
    echo.
    echo [ERROR] Gateway exited unexpectedly.
    echo [TIP] If this is your first time running, please double-click setup_env.bat first!
    echo.
    pause
)