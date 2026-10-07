import os
import subprocess

desktop = os.path.expanduser('~/Desktop')
target = os.path.join(desktop, 'Start_Gateway.bat')

ps_script = f"""$sh = New-Object -ComObject WScript.Shell
$sc = $sh.CreateShortcut("$HOME\\Desktop\\启动小智AI网关.lnk")
$sc.TargetPath = "{target}"
$sc.WorkingDirectory = "d:\\gemini 工作区\\ai硬件工作区"
$sc.Description = "启动小智AI语音网关"
$sc.IconLocation = "shell32.dll,14"
$sc.Save()
"""

ps_path = r"d:\gemini 工作区\ai硬件工作区\gateway\scripts\mk_sc.ps1"
with open(ps_path, "w", encoding="utf-8-sig") as f:
    f.write(ps_script)

res = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", ps_path], capture_output=True, text=True)
print("Return code:", res.returncode)
print("Stdout:", res.stdout)
print("Stderr:", res.stderr)
