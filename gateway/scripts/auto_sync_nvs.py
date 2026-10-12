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

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
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
    all_ports = list(serial.tools.list_ports.comports())
    for p in all_ports:
        hwid = (p.hwid or "").lower()
        desc = (p.description or "").lower()
        if any(k in hwid or k in desc for k in [
            "303a", "espressif", "ch340", "ch341", "ch343", 
            "cp210", "cp2102", "cp2104", "usb-serial", "uart", 
            "serial", "串行"
        ]):
            return p.device
    if len(all_ports) == 1:
        return all_ports[0].device
    return None

DEFAULT_NVS_TEMPLATE = """key,type,encoding,value
wifi,namespace,,
ssid,data,string,YOUR_WIFI_NAME
password,data,string,YOUR_WIFI_PASSWORD
ota_url,data,string,http://{ip}:8001/ota/
websocket,namespace,,
url,data,string,ws://{ip}:8001/xiaozhi/v1/
version,data,u32,1
"""

def generate_nvs_bin_file(csv_path, bin_path):
    """编译 NVS 配置文件为二进制 bin，优先使用内存模块调用，兼容打包环境"""
    try:
        import esp_idf_nvs_partition_gen.nvs_partition_gen as nvs_gen
        args = type('Args', (), {
            'input': str(csv_path),
            'output': str(bin_path),
            'outdir': str(csv_path.parent),
            'size': '0x4000',
            'version': 2
        })()
        nvs_gen.generate(args)
        return True
    except Exception as e:
        # 备选：通过 Python 命令行调用
        try:
            cmd = [
                sys.executable, "-m", "esp_idf_nvs_partition_gen.nvs_partition_gen",
                "generate", str(csv_path), str(bin_path), "0x4000"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(BASE_DIR))
            return res.returncode == 0
        except Exception:
            return False

def flash_nvs_bin_file(port, bin_path):
    """将 bin 写入开发板 NVS 分区，优先使用内存模块调用"""
    try:
        import esptool
        esptool.main(["-p", port, "write_flash", "0x9000", str(bin_path)])
        return True
    except SystemExit as se:
        return se.code == 0
    except Exception:
        try:
            cmd = [sys.executable, "-m", "esptool", "-p", port, "write-flash", "0x9000", str(bin_path)]
            res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(BASE_DIR))
            return res.returncode == 0
        except Exception:
            return False

def sync_nvs(target_port=None, force_flash=False):
    ip = get_current_wlan_ip()
    print(f"[Auto-Sync] 当前电脑 Wi-Fi 局域网 IP: {ip}")
    
    if not NVS_CSV.exists():
        try:
            NVS_CSV.write_text(DEFAULT_NVS_TEMPLATE.format(ip=ip), encoding="utf-8")
            print("[Auto-Sync] 已根据当前 IP 自动创建 nvs_config.csv 配置文件模板。")
        except Exception as e:
            print(f"[Auto-Sync] 创建 nvs_config.csv 失败: {e}")
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

    port = target_port or find_esp32_port()

    # 1. Update CSV and recompile BIN if IP changed or BIN missing or force_flash
    if needs_update or not NVS_BIN.exists() or force_flash:
        print(f"[Auto-Sync] 正在生成固件配置 (IP: {ip})...")
        try:
            NVS_CSV.write_text(updated_content, encoding="utf-8")
        except Exception:
            pass
        
        ok = generate_nvs_bin_file(NVS_CSV, NVS_BIN)
        if ok:
            print("[Auto-Sync] 已成功生成最新固件配置 nvs_custom.bin")
        else:
            print("[Auto-Sync] 生成 NVS 二进制文件失败")
            return ip
    else:
        print(f"[Auto-Sync] 本地固件配置已与当前电脑 IP {ip} 保持一致。")

    # 2. Flash to board if port found
    if port and NVS_BIN.exists():
        print(f"[Auto-Sync] 检测到小智开发板连接在 {port}，正在一键写入新配置 (IP: {ip})...")
        if flash_nvs_bin_file(port, NVS_BIN):
            print(f"[Auto-Sync] [成功] 已自动为小智开发板更新 IP: {ip}！开发板将自动重启连接。")
        else:
            print(f"[Auto-Sync] 写入失败，请检查串口是否被其他程序占用。")
    elif not port:
        print(f"[Auto-Sync] 提示: 未检测到小智 USB 串口连接 (已更新本地文件配置)。")

    return ip

if __name__ == "__main__":
    sync_nvs()

