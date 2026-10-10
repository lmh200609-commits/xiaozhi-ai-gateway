"""
Automatically download SenseVoice ASR model files if missing.
Useful when cloning repository to a new computer.
"""
import os
import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from pathlib import Path
import urllib.request

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
MODEL_DIR = BASE_DIR / "models" / "sense-voice"
MODEL_FILE = MODEL_DIR / "model.int8.onnx"
TOKENS_FILE = MODEL_DIR / "tokens.txt"

# ModelScope direct download URLs (Fast in China)
URL_MODEL = "https://modelscope.cn/models/poloniumrock/SenseVoiceSmallOnnx/resolve/master/model.int8.onnx"
URL_TOKENS = "https://modelscope.cn/models/poloniumrock/SenseVoiceSmallOnnx/resolve/master/tokens.txt"

def download_with_progress(url: str, dest_path: Path):
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest_path.with_suffix(".tmp")
    print(f"[*] 正在下载: {dest_path.name}")
    print(f"    来源: {url}")

    def report(block_num, block_size, total_size):
        downloaded = block_num * block_size
        if total_size > 0:
            percent = min(100.0, downloaded * 100 / total_size)
            mb_cur = downloaded / (1024 * 1024)
            mb_tot = total_size / (1024 * 1024)
            sys.stdout.write(f"\r    进度: {percent:5.1f}% [{mb_cur:6.1f}MB / {mb_tot:6.1f}MB]")
        else:
            mb_cur = downloaded / (1024 * 1024)
            sys.stdout.write(f"\r    已下载: {mb_cur:6.1f}MB")
        sys.stdout.flush()

    try:
        opener = urllib.request.build_opener()
        opener.addheaders = [('User-Agent', 'Mozilla/5.0')]
        urllib.request.install_opener(opener)
        urllib.request.urlretrieve(url, str(temp_path), reporthook=report)
        print()
        if temp_path.exists():
            if dest_path.exists():
                dest_path.unlink()
            temp_path.rename(dest_path)
            print(f"[*] {dest_path.name} 下载完成！")
            return True
    except Exception as e:
        print(f"\n[!] 下载失败: {e}")
        if temp_path.exists():
            temp_path.unlink()
        return False

def check_and_download_models():
    print("=======================================================")
    print("      SenseVoice 离线语音识别模型检测与补全")
    print("=======================================================")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Check tokens.txt
    if not TOKENS_FILE.exists() or TOKENS_FILE.stat().st_size < 1000:
        print("[*] 未检测到 tokens.txt，开始从 ModelScope 下载...")
        success = download_with_progress(URL_TOKENS, TOKENS_FILE)
        if not success:
            print("[!] tokens.txt 下载失败，请检查网络！")
            return False
    else:
        print(f"[*] tokens.txt 已存在 ({TOKENS_FILE.stat().st_size / 1024:.1f} KB)")

    # 2. Check model.int8.onnx (~239MB)
    if not MODEL_FILE.exists() or MODEL_FILE.stat().st_size < 200 * 1024 * 1024:
        print("[*] 未检测到 SenseVoice 模型权重 (model.int8.onnx)，开始下载...")
        success = download_with_progress(URL_MODEL, MODEL_FILE)
        if not success:
            print("[!] 模型权重下载失败！您也可以从 ModelScope 手动下载并放入 models/sense-voice 目录：")
            print(f"    {URL_MODEL}")
            return False
    else:
        print(f"[*] model.int8.onnx 已存在 ({MODEL_FILE.stat().st_size / (1024*1024):.1f} MB)")

    print("[*] 语音识别模型环境检查完毕，全部正常就绪！\n")
    return True

if __name__ == "__main__":
    check_and_download_models()
