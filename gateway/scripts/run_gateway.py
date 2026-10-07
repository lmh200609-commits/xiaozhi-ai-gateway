import os
import sys

# 1. Protect against Windows GBK encoding crashes
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import time
import subprocess
import threading
import webbrowser

# 2. Set cwd to project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(PROJECT_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

print("=======================================================")
print("   [Xiaozhi AI Voice Gateway v2.0]")
print("   小智 AI 语音网关 & 电脑智能管家")
print("=======================================================")
print(f"[*] 工作目录: {PROJECT_ROOT}")

# 3. Clean port 8001
try:
    from gateway.scripts.free_port import free_port
    free_port(8001)
except Exception as e:
    print(f"[*] free_port notice: {e}")

# 4. Check Wi-Fi IP and sync NVS configuration
try:
    import gateway.scripts.auto_sync_nvs as nvs_sync
    local_ip = nvs_sync.sync_nvs()
except Exception as e:
    print(f"[*] auto_sync notice: {e}")

# 5. Open Web Console in browser after 2.5s
def open_browser():
    time.sleep(2.5)
    print("[*] 正在打开网页控制台: http://localhost:8001")
    try:
        webbrowser.open("http://localhost:8001")
    except Exception:
        pass

threading.Thread(target=open_browser, daemon=True).start()

# 6. Launch Uvicorn Gateway
print("[*] 正在启动网关服务 (0.0.0.0:8001)...")
print("[*] 【重要提示】请保持此黑框控制台运行，最小化即可，不要关闭！")
print("=======================================================")

try:
    import uvicorn
    uvicorn.run("gateway.main:app", host="0.0.0.0", port=8001, log_level="info")
except Exception as e:
    print(f"\n[!] 网关发生异常: {e}")
    import traceback
    traceback.print_exc()
finally:
    print("\n[!] 网关已停止。")
    try:
        input("按 Enter 回车键关闭窗口...")
    except Exception:
        pass
