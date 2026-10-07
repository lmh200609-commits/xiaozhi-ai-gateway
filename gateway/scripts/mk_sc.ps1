$sh = New-Object -ComObject WScript.Shell
$sc = $sh.CreateShortcut("$HOME\Desktop\启动小智AI网关.lnk")
$sc.TargetPath = "C:\Users\liu200609/Desktop\Start_Gateway.bat"
$sc.WorkingDirectory = "d:\gemini 工作区\ai硬件工作区"
$sc.Description = "启动小智AI语音网关"
$sc.IconLocation = "shell32.dll,14"
$sc.Save()
