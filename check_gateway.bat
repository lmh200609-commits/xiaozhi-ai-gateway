@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Xiaozhi Diagnostics Tool

echo ============================================================
echo      Xiaozhi Gateway Connection Diagnostics
echo ============================================================
echo [*] Working Directory: %~dp0
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

%PY_CMD% "gateway\scripts\diagnose.py"
pause
