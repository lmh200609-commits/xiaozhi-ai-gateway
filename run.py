#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
小智 AI 语音网关 - 统一入口启动器 (Xiaozhi AI Voice Gateway Launcher)
================================================================================
本脚本为小智 AI 语音网关的主入口，兼容 Windows/Linux/macOS，自动完成环境检测、
端口冲突清理、Wi-Fi IP 同步及自动打开 Web 控制台。

常用启动方式:
  1. 根目录下直接运行:   py -3.11 run.py  或  python run.py
  2. 便携批处理双击:     start_gateway.bat
  3. 指定端口与参数:     py -3.11 run.py --port 8001 --no-browser
================================================================================
"""

import os
import sys
from pathlib import Path

# 1. Windows 控制台字符编码安全重定向 (防 GBK 乱码与 Unicode 崩溃)
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 2. 定位项目绝对根目录，并优先加入 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
os.chdir(PROJECT_ROOT)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse
import subprocess
import threading
import time
import webbrowser

def print_banner(host: str, port: int):
    print("=" * 64)
    print("   🚀 小智 AI 语音网关 & 硬件服务平台 (Xiaozhi AI Gateway v2.0)")
    print("=" * 64)
    print(f"[*] 项目根目录 : {PROJECT_ROOT}")
    print(f"[*] Python 解释器: {sys.executable}")
    print(f"[*] 监听网络地址: http://{host}:{port}")
    print(f"[*] 本地控制台  : http://localhost:{port}")
    print("=" * 64)

def check_and_heal_dependencies():
    """轻量自愈检测，若缺关键包自动快速补齐，避免新手因依赖缺失无法启动"""
    missing = []
    checks = [
        ("uvicorn", "uvicorn"),
        ("fastapi", "fastapi"),
        ("python-multipart", "multipart"),
        ("pypdf", "pypdf"),
        ("python-docx", "docx"),
        ("aiofiles", "aiofiles"),
    ]
    for pkg_name, import_name in checks:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg_name)
    
    if missing:
        print(f"[*] 检测到缺少运行时必要依赖: {', '.join(missing)}")
        print("[*] 正在自动执行快速安装 (pip install)...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", *missing], check=True)
            print("[✓] 依赖安装完成！")
        except Exception as e:
            print(f"[!] 自动补齐依赖失败: {e}，请先执行 setup_env.bat")

def cleanup_port(port: int):
    """自动释放被旧网关残留进程占用的端口"""
    try:
        from gateway.scripts.free_port import free_port
        free_port(port)
    except Exception as e:
        # 降级备用检查
        try:
            cmd = f'netstat -ano | findstr ":{port}.*LISTENING"'
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            for line in res.stdout.strip().splitlines():
                parts = line.split()
                if len(parts) >= 5:
                    pid = parts[-1]
                    print(f"[*] 释放端口 {port} 占用进程 PID={pid}")
                    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
        except Exception:
            pass

def sync_network_config():
    """检测 Wi-Fi IP 并同步到 NVS 配置"""
    try:
        import gateway.scripts.auto_sync_nvs as nvs_sync
        local_ip = nvs_sync.sync_nvs()
        return local_ip
    except Exception as e:
        return "127.0.0.1"

def open_browser_delayed(url: str, delay: float = 2.0):
    """后台延时自动打开浏览器"""
    def _open():
        time.sleep(delay)
        print(f"[*] 正在自动打开 Web 控制台: {url}")
        try:
            webbrowser.open(url)
        except Exception:
            pass
    threading.Thread(target=_open, daemon=True).start()

def main():
    parser = argparse.ArgumentParser(description="Xiaozhi AI Voice Gateway Launcher")
    parser.add_argument("--host", default="0.0.0.0", help="Binding host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8001, help="Binding port (default: 8001)")
    parser.add_argument("--reload", action="store_true", help="Enable uvicorn hot-reload")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")
    args = parser.parse_args()

    # 1. 打印横幅
    print_banner(args.host, args.port)

    # 2. 依赖自愈检测
    check_and_heal_dependencies()

    # 3. 释放被占用的端口
    cleanup_port(args.port)

    # 4. Wi-Fi IP 与固件 NVS 同步
    sync_network_config()

    # 5. 延时调起浏览器
    if not args.no_browser:
        open_browser_delayed(f"http://localhost:{args.port}", delay=2.5)

    # 6. 启动 Uvicorn 服务
    print("[*] 正在启动网关核心进程...")
    print("[*] 【重要提示】请保持此黑框窗口运行，最小化即可，不要关闭！")
    print("=" * 64)

    try:
        import uvicorn
        uvicorn.run("gateway.main:app", host=args.host, port=args.port, reload=args.reload, log_level="info")
    except KeyboardInterrupt:
        print("\n[*] 网关服务已收到中断信号，正在退出...")
    except Exception as e:
        print(f"\n[!] 网关服务异常退出: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n[!] 网关服务已停止。")

if __name__ == "__main__":
    main()
