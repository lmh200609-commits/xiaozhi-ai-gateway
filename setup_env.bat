@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Xiaozhi AI Gateway Setup Wizard

echo ============================================================
echo      Xiaozhi AI Voice Gateway - Setup Wizard
echo ============================================================
echo [*] Working Directory: %~dp0
echo [*] Searching for Python runtime...
echo.

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

py -3.14 -V >nul 2>nul
if not errorlevel 1 (
    set "SYS_PY=py -3.14"
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

echo [ERROR] No Python installation found on this system!
echo.
echo Please install Python 3.11 from https://www.python.org/
echo IMPORTANT: During installation, make sure to check "Add Python to PATH"!
echo.
pause
exit /b 1

:FOUND_PY
echo [*] Using Python interpreter: %SYS_PY%
%SYS_PY% -V
echo.
echo [*] Launching automated environment setup...
echo.
%SYS_PY% "gateway\scripts\setup_environment.py"

if errorlevel 1 (
    echo.
    echo [ERROR] Setup script exited with an error. Please check the logs above.
) else (
    echo.
    echo [SUCCESS] Setup completed successfully!
)

echo.
echo Press any key to close this window.
pause >nul