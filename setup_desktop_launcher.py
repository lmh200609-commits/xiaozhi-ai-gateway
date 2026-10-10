#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小智 AI 语音网关 - 桌面快捷方式一键生成器 (Portable Desktop Launcher Setup)
========================================================================
适用于任何 Windows 电脑，克隆/下载代码后运行此脚本即可在当前用户的桌面上
自动生成【启动小智AI网关.lnk】与便携批处理启动器，支持自动定位虚拟环境与项目目录。
"""

import os
import sys
import subprocess
from pathlib import Path

# 1. 确保 Windows 控制台字符编码为 UTF-8
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent

def get_desktop_dir() -> Path:
    """获取 Windows 当前用户的真实桌面路径 (兼容 OneDrive 桌面重定向与中文路径)"""
    # 优先查询注册表
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        )
        desktop_val, _ = winreg.QueryValueEx(key, "Desktop")
        winreg.CloseKey(key)
        resolved = Path(os.path.expandvars(desktop_val))
        if resolved.exists():
            return resolved
    except Exception:
        pass

    # 其次查询 PowerShell 环境变量
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
            capture_output=True, text=True, timeout=3
        )
        p = Path(res.stdout.strip())
        if p.exists():
            return p
    except Exception:
        pass

    # 降级默认路径
    default_p = Path.home() / "Desktop"
    if default_p.exists():
        return default_p
    return Path.home()

def main():
    desktop = get_desktop_dir()
    print("=" * 60)
    print("  小智 AI 语音网关 - 桌面快捷启动器生成向导")
    print("=" * 60)
    print(f"[*] 项目根目录 : {PROJECT_ROOT}")
    print(f"[*] 用户桌面路径: {desktop}")

    # 1. 生成桌面批处理启动器 (委托给项目自身的 start_gateway.bat，自动处理环境与端口)
    bat_content = f"""@echo off
chcp 65001 >nul
cd /d "{PROJECT_ROOT}"
call start_gateway.bat
"""
    cn_bat = desktop / "启动小智AI网关.bat"
    en_bat = desktop / "Start_Gateway.bat"

    try:
        cn_bat.write_text(bat_content, encoding="utf-8")
        print(f"[✓] 已创建桌面批处理: {cn_bat.name}")
        en_bat.write_text(bat_content, encoding="utf-8")
        print(f"[✓] 已创建英文备用批处理: {en_bat.name}")
    except Exception as e:
        print(f"[!] 写入桌面批处理文件异常: {e}")

    # 2. 检查 Python 运行程序与启动目标
    venv_py = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    target_py = venv_py if venv_py.exists() else Path(sys.executable)
    start_bat = PROJECT_ROOT / "start_gateway.bat"
    run_py = PROJECT_ROOT / "run.py"

    # 3. 通过 PowerShell 生成 Windows 桌面快捷方式 (.lnk)
    # 使用 cmd.exe 包装调用 start_gateway.bat，保证窗口属性正常且双击即启动
    lnk_path = desktop / "启动小智AI网关.lnk"
    
    ps_content = f'''$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("{lnk_path}")
$Shortcut.TargetPath = "{start_bat}"
$Shortcut.WorkingDirectory = "{PROJECT_ROOT}"
$Shortcut.Description = "小智 AI 语音网关 & 硬件服务平台"
if (Test-Path "{target_py}") {{
    $Shortcut.IconLocation = "{target_py},0"
}} else {{
    $Shortcut.IconLocation = "shell32.dll,14"
}}
$Shortcut.Save()
Write-Output "[✓] Windows 快捷方式 (.lnk) 已成功创建！"
'''

    temp_ps1 = PROJECT_ROOT / ".temp_make_lnk.ps1"
    try:
        temp_ps1.write_text(ps_content, encoding="utf-8-sig")
        res = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(temp_ps1)],
            capture_output=True, text=True
        )
        if res.returncode == 0:
            print(f"[✓] 已成功生成桌面快捷方式: {lnk_path.name}")
        else:
            print(f"[!] PowerShell 生成快捷方式返回: {res.stderr}")
    except Exception as e:
        print(f"[!] 创建桌面快捷方式出错: {e}")
    finally:
        if temp_ps1.exists():
            try:
                temp_ps1.unlink()
            except Exception:
                pass

    print("=" * 60)
    print("现在您可以直接在桌面双击【启动小智AI网关】图标快速启动！")
    print("=" * 60)

if __name__ == "__main__":
    main()
