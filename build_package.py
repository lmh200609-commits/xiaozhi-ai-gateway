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
        "PIL", "PIL.Image", "PIL._imaging", "pyogg", "pyogg.opus", "pyogg.library_loader",
        "tokenizers", "requests", "webview", "pythonnet", "clr", "clr_loader", "proxy_tools", "bottle",
        "jieba", "pypdf", "docx", "serial", "esptool", "esp_idf_nvs_partition_gen",
        "sqlite3", "numpy", "pydantic", "httpx", "psutil",
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
        "--windowed",
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
        "--collect-all", "pyogg",
        "--collect-all", "PIL",
        "--collect-all", "tokenizers",
        "--collect-all", "webview",
        "--collect-all", "pythonnet",
        "--collect-all", "clr_loader",
        "--collect-all", "psutil",
        "--exclude-module", "tkinter",
        "--exclude-module", "matplotlib",
        "--exclude-module", "scipy",
        "--exclude-module", "pandas",
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
    model_src = PROJECT_ROOT / "models" / "sense-voice" / "model.int8.onnx"
    if model_src.exists():
        shutil.copy(model_src, output_app_dir / "models" / "sense-voice" / "model.int8.onnx")

    # 5. One-click launcher scripts
    launcher_bat_gui = output_app_dir / "启动小智网关.bat"
    launcher_bat_gui.write_text(
        "@echo off\r\n"
        "cd /d \"%~dp0\"\r\n"
        "start XiaozhiGateway.exe\r\n",
        encoding="utf-8"
    )

    launcher_bat_console = output_app_dir / "启动小智网关(控制台模式).bat"
    launcher_bat_console.write_text(
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        "title 小智 AI 语音网关 - 控制台调试模式\r\n"
        "cd /d \"%~dp0\"\r\n"
        "echo ============================================================\r\n"
        "echo    🚀 正在以控制台调试模式启动小智 AI 语音网关\r\n"
        "echo ============================================================\r\n"
        "XiaozhiGateway.exe --no-gui\r\n"
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
        "    echo [✓] 模型下载完成！您可以直接运行 XiaozhiGateway.exe！\r\n"
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
        "       小智 AI 语音网关 - 纯净原生桌面应用程序 (v2.0-Vanilla)\n"
        "================================================================\n"
        "【快速上手说明】\n"
        "1. 直接双击运行【XiaozhiGateway.exe】或桌面图标【小智AI语音网关】。\n"
        "2. 程序将直接以原生桌面应用程序窗口启动，体验与普通电脑客户端软件完全一致！\n"
        "3. 本版本为纯净空白版，大模型 API 密钥已留空，请在系统设置中填入您自己的 API Key。\n"
        "4. 本版本已内置【专属知识库客服】角色，并支持在界面中新建或删除自定义人设。\n"
        "5. 如需在命令行查看实时调试日志，可运行【启动小智网关(控制台模式).bat】。\n"
        "6. 硬件设备 (ESP32) 连接至网关 IP 即可享受流畅语音对话！\n"
        "================================================================\n",
        encoding="utf-8"
    )

    print("[4/5] 正在创建便携发布压缩包 (XiaozhiGateway-v2.0-Vanilla.zip)...")
    zip_file = dist_dir / "XiaozhiGateway-v2.0-Vanilla.zip"
    if zip_file.exists():
        zip_file.unlink()

    with zipfile.ZipFile(zip_file, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, dirs, files in os.walk(output_app_dir):
            for f in files:
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

    print("[5/5] 正在编译原生图形化安装向导 (XiaozhiGateway-v2.0-Setup.exe)...")
    csc_path = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
    installer_exe = dist_dir / "XiaozhiGateway-v2.0-Setup.exe"
    cs_src = PROJECT_ROOT / "gateway" / "scripts" / "installer_template.cs"

    if os.path.exists(csc_path) and cs_src.exists():
        csc_cmd = [
            csc_path,
            "/nologo",
            "/optimize+",
            "/target:winexe",
            f"/out:{installer_exe}",
            f"/resource:{zip_file},payload.zip",
            "/reference:System.IO.Compression.FileSystem.dll,System.IO.Compression.dll,System.Windows.Forms.dll,System.Drawing.dll",
            str(cs_src)
        ]
        csc_res = subprocess.run(csc_cmd)
        if csc_res.returncode == 0:
            installer_size_mb = installer_exe.stat().st_size / (1024 * 1024)
            print(f"  [✓] 原生安装向导生成成功: {installer_exe.name} ({installer_size_mb:.1f} MB)")
            release_installer = release_dir / "XiaozhiGateway-v2.0-Setup.exe"
            shutil.copy(installer_exe, release_installer)
            print(f"  [✓] 已同步安装包至发布目录: {release_installer.relative_to(PROJECT_ROOT)}")
        else:
            print("[!] 编译安装向导失败！")
    else:
        print("[!] 找不到 csc.exe 或 installer_template.cs，跳过安装向导编译")

    print("=" * 64)
    print(f"🎉 纯净空白版打包已完成！")
    print(f"   便携版: {zip_file}")
    if (dist_dir / "XiaozhiGateway-v2.0-Setup.exe").exists():
        print(f"   安装包: {dist_dir / 'XiaozhiGateway-v2.0-Setup.exe'}")
    print("=" * 64)
    return True


if __name__ == "__main__":
    build()
