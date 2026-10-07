"""
Auto-detect PC WLAN IP and sync to Xiaozhi ESP32 NVS partition.
Runs automatically on gateway startup.
"""
import os
import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import re
import socket
import subprocess
from pathlib import Path
import serial.tools.list_ports

BASE_DIR = Path(__file__).resolve().parent.parent.parent
NVS_CSV = BASE_DIR / "nvs_config.csv"
NVS_BIN = BASE_DIR / "nvs_custom.bin"

def get_current_wlan_ip():
    """Extracts the IPv4 address of the WLAN / Wi-Fi adapter with default gateway."""
    try:
        out = subprocess.check_output("ipconfig", text=True, encoding="gbk", errors="ignore")
        blocks = re.split(r'\r?\n(?=\S)', out)
        for b in blocks:
            if any(k in b for k in ["WLAN", "Wi-Fi", "无线", "Wireless"]):
                m = re.search(r'IPv4.*?: ([0-9.]+)', b)
                if m:
                    return m.group(1).strip()
    except Exception as e:
        print(f"[Auto-Sync] Warning parsing ipconfig: {e}")
    
    # Fallback to general socket determination
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('114.114.114.114', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def find_esp32_port():
    """Finds COM port for connected ESP32 board."""
    for p in serial.tools.list_ports.comports():
        hwid = (p.hwid or "").lower()
        desc = (p.description or "").lower()
        if any(k in hwid or k in desc for k in ["303a:1001", "espressif", "ch340", "ch341", "ch343", "cp210", "usb-serial", "uart"]):
            return p.device
    return None

def sync_nvs(force_flash=False):
    ip = get_current_wlan_ip()
    print(f"[Auto-Sync] 当前电脑 Wi-Fi 局域网 IP: {ip}")
    
    if not NVS_CSV.exists():
        print("[Auto-Sync] 未找到 nvs_config.csv，跳过同步。")
        return ip

    content = NVS_CSV.read_text(encoding="utf-8")
    
    # Check if IP has changed
    needs_update = False
    new_lines = []
    for line in content.splitlines():
        if "ota_url" in line or "ws://" in line or "http://" in line:
            new_line = re.sub(r'https?://[0-9.]+(:[0-9]+)?', f'http://{ip}\\1', line)
            new_line = re.sub(r'wss?://[0-9.]+(:[0-9]+)?', f'ws://{ip}\\1', new_line)
            if new_line != line:
                needs_update = True
            new_lines.append(new_line)
        else:
            new_lines.append(line)
            
    updated_content = "\n".join(new_lines) + "\n"

    port = find_esp32_port()

    # 1. Update CSV and recompile BIN if IP changed or BIN missing
    if needs_update or not NVS_BIN.exists():
        print(f"[Auto-Sync] IP 发生变化 (或新生成): 更新为 {ip}，正在生成固件配置...")
        NVS_CSV.write_text(updated_content, encoding="utf-8")
        
        # Compile NVS binary
        cmd_gen = [
            sys.executable, "-m", "esp_idf_nvs_partition_gen.nvs_partition_gen",
            "generate", str(NVS_CSV), str(NVS_BIN), "0x4000"
        ]
        res = subprocess.run(cmd_gen, capture_output=True, text=True, cwd=str(BASE_DIR))
        if res.returncode != 0:
            print(f"[Auto-Sync] 生成 NVS 二进制文件失败: {res.stderr}")
            return ip
            
        print("[Auto-Sync] 已成功生成最新固件配置 nvs_custom.bin")
    else:
        print(f"[Auto-Sync] 本地固件配置已与当前电脑 IP {ip} 保持一致。")

    # 2. Flash to board if port found
    if port and NVS_BIN.exists():
        print(f"[Auto-Sync] 检测到小智开发板连接在 {port}，正在一键写入新配置 (IP: {ip})...")
        cmd_flash = [
            sys.executable, "-m", "esptool",
            "-p", port, "write-flash", "0x9000", str(NVS_BIN)
        ]
        res_flash = subprocess.run(cmd_flash, capture_output=True, text=True, cwd=str(BASE_DIR))
        if res_flash.returncode == 0:
            print(f"[Auto-Sync] [成功] 已自动为小智开发板更新 IP: {ip}！开发板将自动重启连接。")
        else:
            print(f"[Auto-Sync] 写入失败: {res_flash.stderr}")
    elif not port:
        print(f"[Auto-Sync] 提示: 未检测到小智 USB 串口连接 (已更新本地文件配置)。")

    return ip

if __name__ == "__main__":
    sync_nvs()
