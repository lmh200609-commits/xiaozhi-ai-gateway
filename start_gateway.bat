@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Xiaozhi AI Voice Gateway

:: 1. Check local .venv first
if exist ".venv\Scripts\python.exe" (
    set "PY_CMD=.venv\Scripts\python.exe"
    goto :LAUNCH
)

:: 2. Check py launcher with preferred stable versions
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
echo Please install Python 3.11 or 3.10 from https://www.python.org/
echo Make sure to check "Add Python to PATH" during installation.
pause
exit /b 1

:LAUNCH
echo [*] Launching Xiaozhi Gateway with %PY_CMD%...
%PY_CMD% "gateway\scripts\run_gateway.py"

if errorlevel 1 (
    echo.
    echo [NOTICE] Gateway exited with error.
    echo If this is your first time running, please run setup_env.bat first!
    pause
)