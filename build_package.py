import os
import sys
import shutil
import zipfile
import subprocess
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent

def build():
    print("=" * 64)
    print("   🔨 打包小智 AI 语音网关 - 纯净空白版 EXE")
    print("=" * 64)

    # 1. First ensure data is clean vanilla edition
    print("[1/5] 确保知识库与角色为纯净空白版...")
    subprocess.run([sys.executable, str(PROJECT_ROOT / "gateway" / "scripts" / "make_vanilla.py")], check=True)

    # 2. Prepare PyInstaller command
    dist_dir = PROJECT_ROOT / "dist"
    build_dir = PROJECT_ROOT / "build"
    output_app_dir = dist_dir / "XiaozhiGateway"

    pyinstaller_exe = PROJECT_ROOT / ".venv" / "Scripts" / "pyinstaller.exe"
    if not pyinstaller_exe.exists():
        pyinstaller_exe = Path(sys.executable).parent / "pyinstaller.exe"

    hidden_imports = [
        "uvicorn", "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
        "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan", "uvicorn.lifespan.on",
        "fastapi", "starlette", "multipart", "aiofiles", "websockets",
        "sherpa_onnx", "onnxruntime", "miniaudio", "edge_tts", "fastembed",
        "jieba", "pypdf", "docx", "serial", "esptool", "esp_idf_nvs_partition_gen",
        "sqlite3", "numpy", "pydantic", "httpx",
        "gateway.main", "gateway.config", "gateway.audio.opus_codec", "gateway.audio.vad",
        "gateway.asr.sense_voice", "gateway.tts.edge_tts_streamer", "gateway.llm.relay_client",
        "gateway.rag.knowledge_store", "gateway.rag.fts_engine", "gateway.rag.embedding",
        "gateway.rag.entity_graph", "gateway.rag.document_parser", "gateway.rag.knowledge_structurer",
        "gateway.rag.zone_manager", "gateway.rag.video_manager", "gateway.roles.role_manager",
        "gateway.roles.skill_manager", "gateway.agent.pc_tools", "gateway.scripts.auto_sync_nvs",
        "gateway.scripts.free_port", "gateway.scripts.download_models"
    ]

    cmd = [
        str(pyinstaller_exe),
        "--noconfirm",
        "--clean",
        "--onedir",
        "--console",
        "--name", "XiaozhiGateway",
        "--distpath", str(dist_dir),
        "--workpath", str(build_dir),
        "--add-data", f"{PROJECT_ROOT / 'gateway' / 'web'};gateway/web",
        "--add-data", f"{PROJECT_ROOT / 'gateway' / 'data' / 'skills'};gateway/data/skills",
        "--paths", str(PROJECT_ROOT),
        "--collect-all", "gateway",
        "--collect-all", "sherpa_onnx",
        "--collect-all", "fastembed",
        "--collect-all", "miniaudio",
        "--exclude-module", "tkinter",
        "--exclude-module", "matplotlib",
        "--exclude-module", "scipy",
        "--exclude-module", "pandas",
        "--exclude-module", "PIL",
        "--exclude-module", "hf_xet",
        "--exclude-module", "unittest",
        "--exclude-module", "pytest",
        "--exclude-module", "IPython",
    ]
    for hi in hidden_imports:
        cmd.extend(["--hidden-import", hi])
    cmd.append(str(PROJECT_ROOT / "run.py"))

    print("[2/5] 正在执行 PyInstaller 编译打包...")
    print(f"    命令: {' '.join(cmd[:6])} ...")
    res = subprocess.run(cmd)
    if res.returncode != 0:
        print("[!] PyInstaller 打包失败！")
        return False

    print("[3/5] 编译完成，正在组装纯净空白版发布包结构...")
    # 1. Copy clean config.json to both app root and gateway/
    clean_config_src = PROJECT_ROOT / "gateway" / "config.example.json"
    if clean_config_src.exists():
        shutil.copy(clean_config_src, output_app_dir / "config.json")
        (output_app_dir / "gateway").mkdir(parents=True, exist_ok=True)
        shutil.copy(clean_config_src, output_app_dir / "gateway" / "config.json")

    # 2. Copy clean gateway/data
    dst_data = output_app_dir / "gateway" / "data"
    dst_data.mkdir(parents=True, exist_ok=True)
    src_data = PROJECT_ROOT / "gateway" / "data"
    for item in ["roles.json", "zones.json", "knowledge.db"]:
        s = src_data / item
        if s.exists():
            shutil.copy(s, dst_data / item)
    (dst_data / "documents").mkdir(parents=True, exist_ok=True)
    
    # Copy skills
    dst_skills = dst_data / "skills"
    dst_skills.mkdir(parents=True, exist_ok=True)
    src_skills = src_data / "skills"
    if src_skills.exists():
        for sk in src_skills.glob("*.skill.md"):
            shutil.copy(sk, dst_skills / sk.name)

    # Empty video manifest
    dst_videos = dst_data / "videos"
    dst_videos.mkdir(parents=True, exist_ok=True)
    (dst_videos / "videos_manifest.json").write_text("[]", encoding="utf-8")

    # 3. Copy web directory
    dst_web = output_app_dir / "gateway" / "web"
    if not dst_web.exists():
        shutil.copytree(PROJECT_ROOT / "gateway" / "web", dst_web)

    # 4. Copy model structure & tokens.txt
    (output_app_dir / "models" / "sense-voice").mkdir(parents=True, exist_ok=True)
    tokens_src = PROJECT_ROOT / "models" / "sense-voice" / "tokens.txt"
    if tokens_src.exists():
        shutil.copy(tokens_src, output_app_dir / "models" / "sense-voice" / "tokens.txt")

    # 5. One-click launcher script
    launcher_bat = output_app_dir / "启动小智网关.bat"
    launcher_bat.write_text(
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        "title 小智 AI 语音网关 (Xiaozhi AI Gateway)\r\n"
        "cd /d \"%~dp0\"\r\n"
        "echo ============================================================\r\n"
        "echo    🚀 正在启动小智 AI 语音网关 (独立免安装运行版)\r\n"
        "echo ============================================================\r\n"
        "echo [*] 本窗口请保持运行，最小化即可，不要关闭！\r\n"
        "echo [*] 正在拉起服务...\r\n"
        "XiaozhiGateway.exe\r\n"
        "pause\r\n",
        encoding="utf-8"
    )

    # 6. Offline Model Downloader bat for users with slow initial launch
    model_dl_bat = output_app_dir / "一键下载离线语音识别模型.bat"
    model_dl_bat.write_text(
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        "title 离线语音识别模型下载\r\n"
        "cd /d \"%~dp0\"\r\n"
        "echo ============================================================\r\n"
        "echo    SenseVoice 离线语音识别模型 (INT8 ONNX) 极速下载\r\n"
        "echo ============================================================\r\n"
        "echo 正在从 ModelScope 国内高速镜像拉取模型文件 (~239MB)...\r\n"
        "powershell -Command \"[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('https://modelscope.cn/models/poloniumrock/SenseVoiceSmallOnnx/resolve/master/model.int8.onnx', 'models/sense-voice/model.int8.onnx')\"\r\n"
        "if exist models\\sense-voice\\model.int8.onnx (\r\n"
        "    echo [✓] 模型下载完成！您可以直接双击 [启动小智网关.bat] 运行！\r\n"
        ") else (\r\n"
        "    echo [!] 下载遇到问题，请检查网络连接！\r\n"
        ")\r\n"
        "pause\r\n",
        encoding="utf-8"
    )

    # 7. Readme user guide
    readme = output_app_dir / "README_使用说明.txt"
    readme.write_text(
        "================================================================\n"
        "       小智 AI 语音网关 - 纯净便携免安装版 (v2.0-Vanilla)\n"
        "================================================================\n"
        "【快速上手说明】\n"
        "1. 双击运行【启动小智网关.bat】或【XiaozhiGateway.exe】。\n"
        "2. 初次运行时，系统会自动补全离线语音识别模型 (如已包含则直接秒启)。\n"
        "3. 启动成功后，会自动在浏览器中打开控制台：http://localhost:8001\n"
        "4. 本版本为纯净空白版，已内置【专属知识库客服】角色。\n"
        "5. 您可以在 Web 控制台的【知识库管理】中上传您自己的 Word、PDF、Markdown 资料。\n"
        "6. 硬件设备 (ESP32) 连接至网关 IP 即可享受流畅语音对话！\n"
        "================================================================\n",
        encoding="utf-8"
    )

    print("[4/5] 正在创建便携发布压缩包 (XiaozhiGateway-v2.0-Vanilla.zip)...")
    zip_file = dist_dir / "XiaozhiGateway-v2.0-Vanilla.zip"
    if zip_file.exists():
        zip_file.unlink()

    with zipfile.ZipFile(zip_file, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for root, dirs, files in os.walk(output_app_dir):
            for f in files:
                # Exclude the 239MB onnx model from portable zip to stay within GitHub 100MB limit
                if f.endswith(".onnx"):
                    continue
                full_path = Path(root) / f
                arc_name = full_path.relative_to(dist_dir)
                zf.write(full_path, arc_name)

    zip_size_mb = zip_file.stat().st_size / (1024 * 1024)
    print(f"  [✓] 便携发布压缩包打包成功: {zip_file.name} ({zip_size_mb:.1f} MB)")

    # Copy to repo release directory for GitHub direct download
    release_dir = PROJECT_ROOT / "release"
    release_dir.mkdir(parents=True, exist_ok=True)
    release_zip = release_dir / "XiaozhiGateway-v2.0-Vanilla.zip"
    shutil.copy(zip_file, release_zip)
    print(f"  [✓] 已将免安装包同步至仓库发布目录: {release_zip.relative_to(PROJECT_ROOT)} ({zip_size_mb:.1f} MB)")

    print("[5/5] 打包校验与就绪！")
    print("=" * 64)
    print(f"🎉 纯净空白版打包已完成！发布路径: {zip_file}")
    print("=" * 64)
    return True

if __name__ == "__main__":
    build()
