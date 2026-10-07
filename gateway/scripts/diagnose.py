import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from pathlib import Path
import re
import socket
import urllib.request

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import gateway.scripts.auto_sync_nvs as sync_module
import serial.tools.list_ports

def check_port_open(host, port, timeout=1.0):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False

def main():
    print("=" * 65)
    print("       小智 AI 语音网关 - 运行环境与设备连接一键诊断报告")
    print("=" * 65)
    print()

    # 1. PC Wi-Fi IP
    pc_ip = sync_module.get_current_wlan_ip()
    print(f"[1] 电脑局域网 IP 状态:")
    print(f"    - 当前电脑 Wi-Fi IP: {pc_ip}")
    if pc_ip in ("127.0.0.1", "0.0.0.0"):
        print("    [!] 警告: 未检测到有效的局域网 Wi-Fi IP，请检查电脑是否已连上 Wi-Fi！")
    else:
        print("    [✓] 已正常获取局域网 IP。")
    print()

    # 2. Gateway Service Check
    print(f"[2] 本地网关服务运行状态 (端口 8001):")
    is_local_running = check_port_open("127.0.0.1", 8001)
    if is_local_running:
        print("    [✓] 网关服务正常运行中 (127.0.0.1:8001 响应正常)")
        # Test HTTP
        try:
            req = urllib.request.Request("http://127.0.0.1:8001/", headers={"User-Agent": "XiaozhiDiag"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                print(f"    [✓] HTTP 网页控制台测试成功 (HTTP {resp.status})")
        except Exception as e:
            print(f"    [*] HTTP 访问提示: {e}")
    else:
        print("    [✗] 警告: 8001 端口未响应！网关服务【未启动】！")
        print("    --> 请先双击运行项目根目录下的 【start_gateway.bat】 启动网关！")
    print()

    # 3. NVS Config Check
    print(f"[3] 开发板固件配置 (nvs_config.csv):")
    nvs_csv = BASE_DIR / "nvs_config.csv"
    cfg_ip = None
    cfg_ssid = None
    cfg_pwd = None
    if nvs_csv.exists():
        content = nvs_csv.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.startswith("ssid,"):
                cfg_ssid = line.split(",")[-1]
            elif line.startswith("password,"):
                cfg_pwd = line.split(",")[-1]
            elif line.startswith("url,"):
                m = re.search(r'ws://([0-9.]+):', line)
                if m:
                    cfg_ip = m.group(1)

        print(f"    - 配置的 Wi-Fi 名称 (SSID): {cfg_ssid or '(未设置)'}")
        print(f"    - 配置的 Wi-Fi 密码: {'(无密码 / 开放网络)' if not cfg_pwd else cfg_pwd}")
        print(f"    - 配置的网关 IP: {cfg_ip or '(未检测到)'}")

        if cfg_ip == pc_ip:
            print("    [✓] 固件配置中的 IP 与当前电脑 IP 一致！")
        else:
            print(f"    [!] 注意: 固件配置中的 IP ({cfg_ip}) 与当前电脑 IP ({pc_ip}) 不一致！")
            print("    --> 如果小智开发板上还是旧 IP，小智呼叫时会无法连接电脑！")
            print("    --> 请插上数据线，双击运行 【flash_board_ip.bat】 将新 IP 写入开发板。")
    else:
        print("    [!] 未找到 nvs_config.csv 配置文件。")
    print()

    # 4. USB Serial Check
    print(f"[4] USB 串口连接状态:")
    ports = list(serial.tools.list_ports.comports())
    if ports:
        print(f"    [✓] 检测到已连接的串口设备：")
        for p in ports:
            print(f"        - {p.device}: {p.description}")
    else:
        print("    [*] 当前未检测到 USB 数据线连接 (若开发板已脱机运行可忽略)。")
    print()

    # 5. Summary & Solutions
    print("=" * 65)
    print("【诊断结果与排查建议】针对呼叫小智一直显示“连接中”：")
    print("=" * 65)
    
    issues = []
    if not is_local_running:
        issues.append("【问题1: 网关未启动】请先双击运行 start_gateway.bat，保持黑窗口运行！")

    if cfg_ip != pc_ip:
        issues.append(f"【问题2: 开发板 IP 可能是旧的】开发板内记录的可能是旧 IP ({cfg_ip})，请插上数据线双击运行 flash_board_ip.bat 重新写入。")

    issues.append("【问题3: Windows 防火墙拦截（高概率）】")
    issues.append("        新 Wi-Fi（尤其是无密码 Wi-Fi）会被 Windows 设为“公用网络”，默认拦截 8001 端口。")
    issues.append("        解决办法：在当前电脑以【管理员身份】运行 CMD，粘贴执行以下命令放行：")
    issues.append("        netsh advfirewall firewall add rule name=\"Xiaozhi Gateway\" dir=in action=allow protocol=TCP localport=8001")

    issues.append("【问题4: 路由器 AP 隔离】如果这是一个公共开放 Wi-Fi（如商场/校园/公司访客 Wi-Fi），")
    issues.append("        路由器可能禁止设备间互相访问。可以用手机开启热点，电脑和板子都连手机热点测试。")

    for i, issue in enumerate(issues, 1):
        print(f"{issue}")
    print("=" * 65)
    print()

if __name__ == "__main__":
    main()
