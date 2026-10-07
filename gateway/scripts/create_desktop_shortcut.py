import os
import subprocess

desktop = os.path.expanduser('~/Desktop')

bat_content = """@echo off
chcp 65001 >nul
title 🚀 智慧火车园区·小智AI网关
echo.
echo ===================================================
echo     智慧火车园区·导览小铁 AI 语音网关
echo     Smart Railway AI Voice Gateway v2.0
echo ===================================================
echo.

cd /d "d:\\gemini 工作区\\ai硬件工作区"

echo [*] 正在检测 Wi-Fi IP 与小智硬件状态...
py -3.11 "gateway\\scripts\\auto_sync_nvs.py"

echo.
echo [*] 正在检查端口 8001...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8001.*LISTENING"') do (
    echo [*] 正在释放旧网关进程 PID=%%a ...
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 1 >nul

echo.
echo [*] 正在启动网关服务: http://localhost:8001
echo [*] 请勿关闭此黑框窗口，关闭则服务停止。
echo.

start "" cmd /c "timeout /t 3 >nul & start http://localhost:8001"

py -3.11 -m uvicorn gateway.main:app --host 0.0.0.0 --port 8001

echo.
echo [!] 网关服务已停止。
pause
"""

# 1. Write start_gateway.bat
local_bat = r"d:\gemini 工作区\ai硬件工作区\start_gateway.bat"
with open(local_bat, "w", encoding="utf-8") as f:
    f.write(bat_content)

# 2. Write desktop bat (for direct execution without shortcut failure)
desktop_bat = os.path.join(desktop, "启动小智AI网关.bat")
with open(desktop_bat, "w", encoding="utf-8") as f:
    f.write(bat_content)
print(f"Created {desktop_bat}")

# 3. Create Desktop .lnk pointing to local_bat via VBS
vbs_content = f'''
Set WshShell = CreateObject("WScript.Shell")
Set Shortcut = WshShell.CreateShortcut("{desktop}\\启动小智AI网关.lnk")
Shortcut.TargetPath = "{local_bat}"
Shortcut.WorkingDirectory = "d:\\gemini 工作区\\ai硬件工作区"
Shortcut.WindowStyle = 1
Shortcut.Description = "启动小智AI网关"
Shortcut.IconLocation = "shell32.dll,14"
Shortcut.Save
'''
vbs_path = r"d:\gemini 工作区\ai硬件工作区\make_shortcut.vbs"
with open(vbs_path, "w", encoding="ansi") as f:
    f.write(vbs_content)

res = subprocess.run(["cscript", "//nologo", vbs_path], capture_output=True, text=True)
print("VBS output:", res.stdout, res.stderr)
print("Created Desktop shortcut successfully!")
