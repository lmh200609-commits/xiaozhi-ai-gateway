$Desktop = [Environment]::GetFolderPath('Desktop')
$ProjDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BatPath = Join-Path $ProjDir "start_gateway.bat"
$LnkPath = Join-Path $Desktop "启动小智AI网关.lnk"

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($LnkPath)
$Shortcut.TargetPath = $BatPath
$Shortcut.WorkingDirectory = $ProjDir
$Shortcut.Description = "启动小智AI语音网关"
$Shortcut.IconLocation = "shell32.dll,14"
$Shortcut.Save()
Write-Host "[✓] 桌面快捷方式已成功创建: $LnkPath"
