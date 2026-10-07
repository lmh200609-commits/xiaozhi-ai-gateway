"""
Cross-platform environment setup wizard for Xiaozhi AI Gateway.
Handles venv creation, pip dependency installation, model download, and config initialization.
"""
import os
import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
GATEWAY_DIR = BASE_DIR / "gateway"
REQUIREMENTS_FILE = GATEWAY_DIR / "requirements.txt"
CONFIG_EXAMPLE = GATEWAY_DIR / "config.example.json"
CONFIG_FILE = GATEWAY_DIR / "config.json"
NVS_EXAMPLE = BASE_DIR / "nvs_config.example.csv"
NVS_FILE = BASE_DIR / "nvs_config.csv"

def print_banner():
    print("=" * 60)
    print("       小智 AI 语音网关 - 跨电脑一键初始化向导")
    print("=" * 60)
    print(f"[*] 项目根目录: {BASE_DIR}")
    print(f"[*] 当前 Python: {sys.executable} ({sys.version.split()[0]})")
    
    major, minor = sys.version_info.major, sys.version_info.minor
    if major == 3 and minor >= 13:
        print("\n[!] 提示: 检测到当前使用的是较新的 Python 3.13+ 版本。")
        print("    由于 sherpa-onnx / numpy / miniaudio 等音频与机器学习底层库在 Python 3.10 / 3.11 下生态最稳定，")
        print("    若后续安装依赖遇到编译器报错，请前往 python.org 安装 Python 3.11 即可完美解决！\n")

def setup_venv() -> Path:
    venv_dir = BASE_DIR / ".venv"
    venv_py = venv_dir / "Scripts" / "python.exe"

    if venv_py.exists():
        print(f"[*] 检测到已存在虚拟环境: {venv_dir}")
        return venv_py

    print(f"[*] 正在为本项目创建独立的 Python 虚拟环境 (.venv)...")
    try:
        res = subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], capture_output=True, text=True)
        if res.returncode == 0 and venv_py.exists():
            print("[*] 独立虚拟环境创建成功！")
            return venv_py
        else:
            print(f"[!] 创建虚拟环境遇到问题: {res.stderr}，将直接使用系统 Python 安装。")
            return Path(sys.executable)
    except Exception as e:
        print(f"[!] 创建虚拟环境跳过: {e}，使用系统 Python。")
        return Path(sys.executable)

def install_dependencies(py_exe: Path):
    print("\n[*] 正在配置国内 PyPI 镜像源 (阿里云镜像)...")
    subprocess.run([str(py_exe), "-m", "pip", "config", "set", "global.index-url", "https://mirrors.aliyun.com/pypi/simple/"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("[*] 正在升级 pip 工具...")
    subprocess.run([str(py_exe), "-m", "pip", "install", "--upgrade", "pip"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("[*] 正在安装网关完整依赖包 (FastAPI, Sherpa-ONNX, Edge-TTS, FastEmbed, Jieba, ESP工具等)...")
    print("    这可能需要 1-3 分钟，请稍候...")
    cmd = [str(py_exe), "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)]
    res = subprocess.run(cmd)
    if res.returncode == 0:
        print("[*] 依赖库全部安装成功！")
    else:
        print("\n[!] 部分依赖安装可能有警告，如果后续运行报错，请检查终端输出。")

def check_models(py_exe: Path):
    print("\n[*] 正在检查离线语音识别模型 (SenseVoice INT8 ONNX)...")
    try:
        from gateway.scripts.download_models import check_and_download_models
        check_and_download_models()
    except Exception as e:
        print(f"[!] 模型检查脚本报错: {e}")
        # Fallback to subprocess
        script = GATEWAY_DIR / "scripts" / "download_models.py"
        subprocess.run([str(py_exe), str(script)])

def init_configs():
    print("\n[*] 正在检查配置文件...")
    if not CONFIG_FILE.exists() and CONFIG_EXAMPLE.exists():
        shutil.copy(CONFIG_EXAMPLE, CONFIG_FILE)
        print(f"[*] 已生成默认网关配置: {CONFIG_FILE.name}")
    else:
        print(f"[*] 网关配置已就绪: {CONFIG_FILE.name}")

    if not NVS_FILE.exists() and NVS_EXAMPLE.exists():
        shutil.copy(NVS_EXAMPLE, NVS_FILE)
        print(f"[*] 已生成固件配置模板: {NVS_FILE.name}")
    else:
        print(f"[*] 固件配置模板已就绪: {NVS_FILE.name}")

def main():
    print_banner()
    py_exe = setup_venv()
    install_dependencies(py_exe)
    check_models(py_exe)
    init_configs()

    print("\n" + "=" * 60)
    print(" [✓] 恭喜！小智 AI 语音网关跨电脑环境已全部配置就绪！")
    print("=" * 60)
    print("下一步使用方法：")
    print("1. 用记事本打开 gateway/config.json，填入您的 relay_api_key 大模型密钥")
    print("2. 双击 start_gateway.bat 即可一键启动网关！")
    print("3. 浏览器会自动打开控制台: http://localhost:8001")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()
