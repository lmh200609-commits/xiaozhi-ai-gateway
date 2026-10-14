@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 小智 AI 语音网关 - Windows 防火墙一键放行工具

echo ============================================================
echo        小智 AI 语音网关 - 局域网防火墙端口一键放行工具
echo ============================================================
echo.
echo 说明：
echo 当外部小智开发板通过 Wi-Fi 连入电脑时，Windows 防火墙可能会拦截 8001 端口，
echo 导致开发板一直提示【检查新版本失败】。
echo.
echo 正在检查并请求管理员权限...

:: 检查是否具备管理员权限
net session >nul 2>&1
if not %errorLevel% == 0 (
    echo [*] 正在弹出系统提权提示，请在弹窗中点击【是】...
    powershell -Command "Start-Process cmd -ArgumentList '/c chcp 65001 >nul && netsh advfirewall firewall add rule name=\"Xiaozhi AI Gateway (8001)\" dir=in action=allow protocol=TCP localport=8001 profile=any && echo. && echo [成功] 已成功为小智网关放行 8001 端口！小智开发板现在可以正常连接电脑了。 && echo. && pause' -Verb RunAs"
    exit /b
)

netsh advfirewall firewall add rule name="Xiaozhi AI Gateway (8001)" dir=in action=allow protocol=TCP localport=8001 profile=any
echo.
echo [成功] 已成功为小智网关放行 8001 端口！小智开发板现在可以正常连接电脑了。
echo.
pause
