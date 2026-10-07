import os
import subprocess

desktop = os.path.expanduser("~/Desktop")

bat_lines = [
    "@echo off",
    "chcp 65001 >nul",
    "title 🚀 智慧火车园区·小智AI网关",
    "echo ===================================================",
    "echo     智慧火车园区·导览小铁 AI 语音网关",
    "echo     Smart Railway AI Voice Gateway v2.0",
    "echo ===================================================",
    "echo.",
    r'cd /d "d:\gemini 工作区\ai硬件工作区"',
    "echo [*] 正在检测局域网 IP 与小智状态...",
    r'py -3.11 "gateway\scripts\auto_sync_nvs.py"',
    "echo.",
    "echo [*] 正在检查 8001 端口并释放旧服务...",
    r'for /f "tokens=5" %%a in (\'netstat -aon 2^>nul ^| findstr ":8001.*LISTENING"\') do (',
    "    echo [*] 关闭旧网关进程 PID=%%a ...",
    "    taskkill /F /PID %%a >nul 2>&1",
    ")",
    "timeout /t 1 >nul",
    "echo.",
    "echo [*] 正在启动网关服务: http://localhost:8001",
    "echo [*] 【注意】请保持此黑框窗口运行，不要关闭！最小化即可！",
    "echo.",
    r'start "" cmd /c "timeout /t 3 >nul && start http://localhost:8001"',
    r"py -3.11 -m uvicorn gateway.main:app --host 0.0.0.0 --port 8001",
    "echo.",
    "echo [!] 网关已退出或被手动停止。",
    "pause"
]

bat_content = "\r\n".join(bat_lines) + "\r\n"

# 1. Write d:\gemini 工作区\ai硬件工作区\start_gateway.bat
proj_bat = r"d:\gemini 工作区\ai硬件工作区\start_gateway.bat"
with open(proj_bat, "w", encoding="utf-8") as f:
    f.write(bat_content)
print(f"Written: {proj_bat}")

# 2. Write C:\Users\liu200609\Desktop\启动小智AI网关.bat
desktop_bat = os.path.join(desktop, "启动小智AI网关.bat")
with open(desktop_bat, "w", encoding="utf-8") as f:
    f.write(bat_content)
print(f"Written: {desktop_bat}")

# 3. Also write English filename on Desktop as a secondary backup
desktop_bat_en = os.path.join(desktop, "Start_Gateway.bat")
with open(desktop_bat_en, "w", encoding="utf-8") as f:
    f.write(bat_content)
print(f"Written: {desktop_bat_en}")

# 4. Create proper Windows Shortcut (.lnk) using PowerShell with UTF8-BOM script
ps1_script = f'''$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("{desktop}\\启动小智AI网关.lnk")
$Shortcut.TargetPath = "{desktop_bat}"
$Shortcut.WorkingDirectory = "d:\\gemini 工作区\\ai硬件工作区"
$Shortcut.Description = "启动小智AI网关"
$Shortcut.IconLocation = "shell32.dll,14"
$Shortcut.Save()
'''
ps1_path = r"d:\gemini 工作区\ai硬件工作区\make_lnk.ps1"
with open(ps1_path, "w", encoding="utf-8-sig") as f:
    f.write(ps1_script)

res = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", ps1_path], capture_output=True, text=True)
print("PS1 create shortcut result:", res.returncode, res.stdout, res.stderr)
