import os
import subprocess

python_exe = r"C:\Users\liu200609\AppData\Local\Programs\Python\Python311\python.exe"
script_py = r"d:\gemini 工作区\ai硬件工作区\gateway\scripts\run_gateway.py"
work_dir = r"d:\gemini 工作区\ai硬件工作区"
desktop = os.path.expanduser("~/Desktop")

# 1. Write Start_Gateway.bat on desktop
desktop_bat = os.path.join(desktop, "Start_Gateway.bat")
bat_content = f'''@echo off
"{python_exe}" "{script_py}"
pause
'''
with open(desktop_bat, "w", encoding="utf-8") as f:
    f.write(bat_content)
print(f"Created {desktop_bat}")

# 2. Write 启动小智AI网关.bat on desktop
desktop_cn_bat = os.path.join(desktop, "启动小智AI网关.bat")
with open(desktop_cn_bat, "w", encoding="utf-8") as f:
    f.write(bat_content)
print(f"Created {desktop_cn_bat}")

# 3. Create 启动小智AI网关.lnk directly pointing to python.exe
ps_script = f'''$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("{desktop}\\启动小智AI网关.lnk")
$Shortcut.TargetPath = "{python_exe}"
$Shortcut.Arguments = '"{script_py}"'
$Shortcut.WorkingDirectory = "{work_dir}"
$Shortcut.Description = "启动小智AI语音网关"
$Shortcut.IconLocation = "{python_exe},0"
$Shortcut.Save()
Write-Output "Shortcut created successfully!"
'''

ps_file = "create_lnk_final.ps1"
with open(ps_file, "w", encoding="utf-8-sig") as f:
    f.write(ps_script)

res = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", ps_file], capture_output=True, text=True)
print("PowerShell output:", res.stdout.strip(), res.stderr.strip())
