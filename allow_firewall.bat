@echo off
cd /d "%~dp0"
title Xiaozhi Firewall Configuration

echo ============================================================
echo      Xiaozhi AI Gateway - Allow Port 8001 in Firewall
echo ============================================================
echo.

:: Check Administrator privileges
net session >nul 2>&1
if not %errorLevel% == 0 (
    echo [*] Administrator rights required. Requesting UAC elevation...
    powershell -Command "Start-Process cmd -ArgumentList '/c netsh advfirewall firewall add rule name=\"Xiaozhi Gateway\" dir=in action=allow protocol=TCP localport=8001 && echo [SUCCESS] Port 8001 has been allowed through Windows Firewall! && pause' -Verb RunAs"
    exit /b
)

netsh advfirewall firewall add rule name="Xiaozhi Gateway" dir=in action=allow protocol=TCP localport=8001
echo.
echo [SUCCESS] Port 8001 has been allowed through Windows Firewall!
echo.
pause
