"""
Auto-detect PC WLAN IP and sync to Xiaozhi ESP32 NVS partition.
Runs automatically on gateway startup.
"""
import os
import sys
import time
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

def robust_decode(data: bytes) -> str:
    """安全鲁棒地解码控制台/命令行字节流，兼容 UTF-8、GBK、GB18030、CP936"""
    if not data:
        return ""
    for enc in ("utf-8", "gb18030", "gbk", "cp936"):
        try:
            txt = data.decode(enc)
            if "\ufffd" not in txt:
                return txt
        except Exception:
            pass
    try:
        return data.decode("gb18030", errors="ignore")
    except Exception:
        return data.decode("utf-8", errors="ignore")

def get_current_wlan_ip():
    """
    精确提取当前连接至路由器/热点的物理网卡 IPv4 地址。
    优先通过路由表 (route print 0.0.0.0) 匹配默认网关接口，彻底排除虚拟网卡 (WSL/VMware/VirtualBox/VPN)。
    """
    # 1. 优先从无线网卡匹配（因为开发板通过 Wi-Fi 连接，电脑与开发板必须处于同一 Wi-Fi 子网）
    try:
        w_res = subprocess.run(['netsh', 'wlan', 'show', 'interfaces'], capture_output=True)
        w_txt = robust_decode(w_res.stdout)
        wlan_names = []
        for line in w_txt.splitlines():
            line_s = line.strip()
            if any(line_s.startswith(k) for k in ['名称', 'Name']) and ':' in line_s:
                wlan_names.append(line_s.split(':', 1)[1].strip())
        
        ip_out = subprocess.check_output('ipconfig', text=True, encoding='gbk', errors='ignore')
        blocks = re.split(r'\r?\n(?=\S)', ip_out)
        for b in blocks:
            is_wlan_block = any(wn in b for wn in wlan_names) or ('无线局域网' in b) or ('Wireless LAN' in b)
            if is_wlan_block and ('IPv4' in b) and ('默认网关' in b or 'Default Gateway' in b):
                m = re.search(r'IPv4.*?: ([0-9.]+)', b)
                if m:
                    ip = m.group(1).strip()
                    if not ip.startswith('127.') and not ip.startswith('169.254.'):
                        return ip
    except Exception:
        pass

    # 2. 备选：从路由表查找默认网关绑定的物理接口 IP
    try:
        out = subprocess.check_output('route print 0.0.0.0', shell=True, text=True, encoding='gbk', errors='ignore')
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[0] == '0.0.0.0' and parts[1] == '0.0.0.0':
                gw, iface = parts[2], parts[3]
                if re.match(r'^\d+\.\d+\.\d+\.\d+$', gw) and gw != '0.0.0.0' and not gw.startswith('127.'):
                    if re.match(r'^\d+\.\d+\.\d+\.\d+$', iface) and not iface.startswith('127.'):
                        return iface
    except Exception as e:
        print(f"[Auto-Sync] route print failed: {e}")

    # 3. 备选：解析 ipconfig 中带有“默认网关”且非虚拟的适配器
    try:
        out = subprocess.check_output("ipconfig", text=True, encoding="gbk", errors="ignore")
        blocks = re.split(r'\r?\n(?=\S)', out)
        for b in blocks:
            if "默认网关" in b or "Default Gateway" in b:
                if not any(v in b for v in ["VirtualBox", "VMnet", "Hyper-V", "vEthernet", "WSL", "TAP-Windows"]):
                    m = re.search(r'IPv4.*?: ([0-9.]+)', b)
                    if m:
                        ip = m.group(1).strip()
                        if not ip.startswith("127.") and not ip.startswith("169.254."):
                            return ip
    except Exception as e:
        print(f"[Auto-Sync] ipconfig failed: {e}")
    
    # 4. 终极备选：通过 socket 连接判定
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1.5)
        s.connect(('114.114.114.114', 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass

    return "127.0.0.1"

def is_genuine_esp_port(p):
    """严格判断是否为真实 ESP32 / USB 转串口芯片，坚决排除蓝牙/主板虚拟串口"""
    hwid = (p.hwid or "").lower()
    desc = (p.description or "").lower()
    # 严格排除蓝牙、主板管理、虚拟调制解调器
    if any(k in hwid or k in desc for k in [
        "bthenum", "bluetooth", "蓝牙", "intel(r) active", "sol", 
        "pnp0501", "acpi", "virtual", "modem"
    ]):
        return False
    # 匹配真正常见的 USB 转串口硬件芯片 VID:PID 与特征名
    if any(k in hwid for k in [
        "vid:pid=1a86:",  # 沁恒 WCH (CH340/CH341/CH343)
        "vid:pid=10c4:",  # 芯科 CP210x (CP2102/CP2104)
        "vid:pid=303a:",  # 乐鑫 Espressif Systems
        "vid:pid=0403:",  # FTDI
    ]):
        return True
    if any(k in desc for k in [
        "ch340", "ch341", "ch343", "cp210", "cp2102", "cp2104", 
        "espressif", "wch", "ft232", "usb-serial"
    ]):
        return True
    return False

def find_esp32_port():
    """Finds COM port for connected ESP32 board."""
    all_ports = list(serial.tools.list_ports.comports())
    for p in all_ports:
        if is_genuine_esp_port(p):
            return p.device
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

def reset_esp32_via_serial(port):
    """
    通过精确的 DTR/RTS 硬件电平时序，强制唤醒/复位 ESP32，
    使其退出黑屏/Bootloader下载模式，并强制从 Flash (SPI_FAST_FLASH_BOOT) 启动！
    """
    if not port:
        return False, "未指定串口端口"
    for attempt in range(3):
        try:
            import serial
            ser = serial.Serial(port, 115200, timeout=1)
            ser.setDTR(False)  # IO0 高电平，绝不进下载模式
            ser.setRTS(True)   # EN 低电平，复位芯片
            time.sleep(0.2)
            ser.setRTS(False)  # EN 高电平，释放复位
            time.sleep(0.1)
            ser.setDTR(False)
            ser.setRTS(False)
            ser.close()
            return True, f"已向 {port} 发送硬件唤醒开机信号，小智开发板正在启动！"
        except Exception as e:
            err_str = str(e)
            if "121" in err_str or "超时" in err_str:
                err_hint = f"串口 {port} 打开超时（可能为蓝牙虚拟端口或设备未插好），请确认串口是否选对！"
            elif "拒绝访问" in err_str or "PermissionError" in err_str:
                err_hint = f"串口 {port} 被其他程序占用，请关闭串口调试助手后重试。"
            else:
                err_hint = f"唤醒串口 {port} 失败: {err_str}"
            if attempt < 2:
                time.sleep(0.3)
            else:
                return False, err_hint
    return False, f"唤醒串口 {port} 失败"

def flash_nvs_bin_file(port, bin_path):
    """将 bin 写入开发板 NVS 分区，使用 hard-reset 并在完成后发送精准唤醒脉冲，彻底告别黑屏"""
    ok = False
    if getattr(sys, "frozen", False):
        try:
            import esptool
            esptool.main(["-p", port, "--after", "hard-reset", "write-flash", "0x9000", str(bin_path)])
            ok = True
        except SystemExit as se:
            ok = (se.code == 0)
        except Exception:
            ok = False
    else:
        # 开发模式下优先使用独立子进程执行 esptool，操作系统级确保子进程退出后完全释放 COM 句柄
        try:
            cmd = [sys.executable, "-m", "esptool", "-p", port, "--after", "hard-reset", "write-flash", "0x9000", str(bin_path)]
            res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(BASE_DIR), timeout=25)
            if res.returncode == 0:
                ok = True
        except Exception:
            pass

        # 备选：内存模块直接调用
        if not ok:
            try:
                import esptool
                esptool.main(["-p", port, "--after", "hard-reset", "write-flash", "0x9000", str(bin_path)])
                ok = True
            except SystemExit as se:
                ok = (se.code == 0)
            except Exception:
                ok = False

    # 刷写完成后，等待串口驱动释放，再次发送精准 DTR/RTS 硬件唤醒脉冲作为双保险
    if ok:
        time.sleep(0.4)
        reset_esp32_via_serial(port)

    return ok

def get_current_wifi_info():
    """获取当前 Windows 电脑实际连接的 Wi-Fi 名称、频段(2.4G/5G)与保存的密码"""
    ssid = ""
    band = "2.4 GHz"
    password = ""
    is_5g = False
    try:
        res = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True)
        txt = robust_decode(res.stdout)
        for line in txt.splitlines():
            line_str = line.strip()
            # 严格匹配 SSID 行（排除 BSSID 和 AP BSSID）
            if re.search(r'^\s*SSID\s*:', line_str):
                parts = line_str.split(":", 1)
                if len(parts) == 2 and not ssid:
                    ssid = parts[1].strip()
            if any(k in line_str for k in ["频段", "波段", "Band"]):
                if "5" in line_str:
                    is_5g = True
                    band = "5 GHz"
                elif "2.4" in line_str:
                    band = "2.4 GHz"
        
        if band and "5" in band:
            is_5g = True
        
        if ssid:
            try:
                p_res = subprocess.run(
                    ["netsh", "wlan", "show", "profile", f"name={ssid}", "key=clear"],
                    capture_output=True
                )
                p_txt = robust_decode(p_res.stdout)
                for p_line in p_txt.splitlines():
                    p_str = p_line.strip()
                    if any(k in p_str for k in ["关键内容", "Key Content", "关键"]):
                        p_parts = p_str.split(":", 1)
                        if len(p_parts) == 2 and not password:
                            password = p_parts[1].strip()
            except Exception:
                pass
    except Exception:
        pass
    
    return {
        "ssid": ssid,
        "band": band or ("5 GHz" if is_5g else "2.4 GHz"),
        "is_5g": is_5g,
        "password": password
    }

def check_firewall_rule_exists(port=8001):
    """检测 8001 端口是否在防火墙中放行"""
    try:
        res = subprocess.run(f'netsh advfirewall firewall show rule name="Xiaozhi AI Gateway ({port})"', shell=True, capture_output=True)
        return res.returncode == 0
    except Exception:
        return False

def open_firewall_port(port=8001):
    """请求放行 Windows 防火墙入站端口"""
    try:
        cmd = f'netsh advfirewall firewall add rule name="Xiaozhi AI Gateway ({port})" dir=in action=allow protocol=TCP localport={port}'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.returncode == 0:
            return True, "防火墙规则已成功添加"
        ps_cmd = f'Start-Process powershell -ArgumentList \'-Command "New-NetFirewallRule -DisplayName \\\"Xiaozhi AI Gateway ({port})\\\" -Direction Inbound -LocalPort {port} -Protocol TCP -Action Allow"\' -Verb RunAs -WindowStyle Hidden'
        subprocess.run(["powershell", "-Command", ps_cmd])
        return True, "已弹出管理员提权窗口，请在弹窗中选择【是】！"
    except Exception as e:
        return False, str(e)

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
    
    wifi_info = get_current_wifi_info()
    cur_ssid = wifi_info.get("ssid", "")
    cur_pass = wifi_info.get("password", "")

    # Check if IP or Wi-Fi needs update
    needs_update = False
    new_lines = []
    for line in content.splitlines():
        if line.startswith("ota_url,"):
            new_line = f"ota_url,data,string,http://{ip}:8001/ota/"
            if new_line != line:
                needs_update = True
            new_lines.append(new_line)
        elif line.startswith("url,"):
            new_line = f"url,data,string,ws://{ip}:8001/xiaozhi/v1/"
            if new_line != line:
                needs_update = True
            new_lines.append(new_line)
        elif line.startswith("ssid,") and cur_ssid:
            parts = line.split(",", 3)
            val = parts[3].strip() if len(parts) > 3 else ""
            if not val or val == "YOUR_WIFI_NAME":
                new_line = f"ssid,data,string,{cur_ssid}"
                needs_update = True
                new_lines.append(new_line)
            else:
                new_lines.append(line)
        elif line.startswith("password,") and cur_pass:
            parts = line.split(",", 3)
            val = parts[3].strip() if len(parts) > 3 else ""
            if not val or val == "YOUR_WIFI_PASSWORD":
                new_line = f"password,data,string,{cur_pass}"
                needs_update = True
                new_lines.append(new_line)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)
            
    updated_content = "\n".join(new_lines) + "\n"

    port = target_port
    if force_flash and not port:
        port = find_esp32_port()

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

    # 2. Flash to board ONLY when force_flash=True (never blindly overwrite on startup)
    if force_flash and port and NVS_BIN.exists():
        print(f"[Auto-Sync] 检测到小智开发板连接在 {port}，正在一键写入新配置 (IP: {ip})...")
        if flash_nvs_bin_file(port, NVS_BIN):
            print(f"[Auto-Sync] [成功] 已自动为小智开发板更新 IP: {ip}！开发板将自动重启连接。")
        else:
            print(f"[Auto-Sync] 写入失败，请检查串口是否被其他程序占用。")
    elif not port and force_flash:
        print(f"[Auto-Sync] 提示: 未检测到小智 USB 串口连接 (已更新本地文件配置)。")

    return ip

if __name__ == "__main__":
    sync_nvs(force_flash=True)

