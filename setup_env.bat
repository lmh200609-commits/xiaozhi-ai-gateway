@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Xiaozhi AI Gateway Setup Wizard

:: Detect preferred Python versions
set "SYS_PY="
py -3.11 -V >nul 2>nul
if not errorlevel 1 (
    set "SYS_PY=py -3.11"
    goto :FOUND_PY
)

py -3.10 -V >nul 2>nul
if not errorlevel 1 (
    set "SYS_PY=py -3.10"
    goto :FOUND_PY
)

py -3.12 -V >nul 2>nul
if not errorlevel 1 (
    set "SYS_PY=py -3.12"
    goto :FOUND_PY
)

py -3 -V >nul 2>nul
if not errorlevel 1 (
    set "SYS_PY=py -3"
    goto :FOUND_PY
)

python -V >nul 2>nul
if not errorlevel 1 (
    set "SYS_PY=python"
    goto :FOUND_PY
)

echo [ERROR] Python not found in system!
echo Please download and install Python 3.11 (64-bit) from https://www.python.org/
echo IMPORTANT: Check the box "Add Python to PATH" during installation!
pause
exit /b 1

:FOUND_PY
echo [*] Detected Python: %SYS_PY%
%SYS_PY% "gateway\scripts\setup_environment.py"
pause