$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("C:\Users\liu200609/Desktop\启动小智AI网关.lnk")
$Shortcut.TargetPath = "C:\Users\liu200609/Desktop\启动小智AI网关.bat"
$Shortcut.WorkingDirectory = "d:\gemini 工作区\ai硬件工作区"
$Shortcut.Description = "启动小智AI网关"
$Shortcut.IconLocation = "shell32.dll,14"
$Shortcut.Save()
