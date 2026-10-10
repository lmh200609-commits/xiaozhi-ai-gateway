import socket
import os
import time
import subprocess

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) == 0

def free_port(port=8001):
    current_pid = str(os.getpid())
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
    except Exception:
        pass

    # Fallback to netstat & taskkill
    try:
        cmd = f'netstat -ano | findstr ":{port}.*LISTENING"'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        for line in res.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) >= 5:
                pid = parts[-1]
                if pid != current_pid and pid.isdigit() and int(pid) > 0:
                    print(f"[*] Releasing port {port} from PID={pid}")
                    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
    except Exception:
        pass

    # Wait up to 3 seconds for port to fully release
    for _ in range(30):
        if not is_port_in_use(port):
            break
        time.sleep(0.1)

if __name__ == "__main__":
    free_port(8001)
    print(f"[*] Port 8001 ready (in_use={is_port_in_use(8001)})")

