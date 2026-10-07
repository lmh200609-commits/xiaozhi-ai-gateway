import socket
import os
import signal
import subprocess

def free_port(port=8001):
    try:
        import psutil
        for conn in psutil.net_connections(kind='inet'):
            if conn.laddr.port == port and conn.status == psutil.CONN_LISTEN:
                pid = conn.pid
                if pid and pid != os.getpid():
                    print(f"[*] Terminating process holding port {port}: PID={pid}")
                    try:
                        p = psutil.Process(pid)
                        p.terminate()
                        p.wait(timeout=2)
                    except Exception:
                        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
    except Exception as e:
        # Fallback to netstat
        cmd = f'netstat -ano | findstr ":{port}.*LISTENING"'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        for line in res.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) >= 5:
                pid = parts[-1]
                print(f"[*] Fallback kill PID={pid} on port {port}")
                subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)

if __name__ == "__main__":
    free_port(8001)
    print("[*] Port 8001 is ready.")
