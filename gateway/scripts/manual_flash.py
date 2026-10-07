"""
Manual / Dedicated tool to flash Gateway IP & Wi-Fi to Xiaozhi board via USB.
"""
import os
import sys

# 1. Ensure utf-8 output in Windows CMD
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from pathlib import Path

# 2. Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import re
import subprocess
import serial.tools.list_ports

NVS_CSV = BASE_DIR / "nvs_config.csv"
NVS_BIN = BASE_DIR / "nvs_custom.bin"

def main():
    print("=" * 60)
    print("       小智 AI 开发板 - USB 固件配置与 IP 烧录工具")
    print("=" * 60)

    # 1. Detect WLAN IP
    import gateway.scripts.auto_sync_nvs as sync_module
    cur_ip = sync_module.get_current_wlan_ip()
    print(f"[*] 当前电脑局域网 IP: {cur_ip}")

    # 2. Check COM ports
    ports = list(serial.tools.list_ports.comports())
    print(f"[*] 正在扫描系统中的 USB 串口设备...")
    
    if not ports:
        print("\n[!] 警告: 未在电脑上找到任何连接的串口设备 (COM口)！")
        print("-" * 60)
        print("请检查以下常见原因：")
        print("1. 【数据线问题】你使用的 Type-C 线可能是『仅充电线』(内部只有供电无数据引脚)。")
        print("   -> 请更换一根能够传输数据的手机数据线！")
        print("2. 【接口问题】部分开发板有两个 Type-C 口 (一个标 PWR 仅供电，一个标 USB/UART)。")
        print("   -> 请将数据线插到标有 USB / UART 的接口上！")
        print("3. 【驱动缺失】电脑设备管理器中是否出现黄色感叹号？")
        print("   -> 部分开发板需要 CH340 或 CP2102 驱动，可从芯片官网下载安装。")
        print("-" * 60)
        print("\n[免插线替代方案]：")
        print(f"小智连上 Wi-Fi 后报错是因为小智还在请求旧 IP！")
        print(f"你也可以长按开发板按键或重启小智，在小智的『配网页面 (192.168.4.1)』中，")
        print(f"将 OTA 网址手动修改为: http://{cur_ip}:8001/ota/ 即可！\n")
        return

    print(f"[✓] 检测到以下可用串口：")
    for i, p in enumerate(ports):
        print(f"    [{i+1}] {p.device} - {p.description}")

    target_port = ports[0].device
    print(f"\n[*] 默认选择串口: {target_port}")

    # 3. Update NVS and flash
    sync_module.sync_nvs(force_flash=True)
    print("\n" + "=" * 60)
    print("操作完成！请观察开发板屏幕是否已成功联网连接网关。")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()
