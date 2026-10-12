import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import os
import json
import urllib.request
import urllib.parse
import subprocess
from pathlib import Path

def get_github_token():
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    try:
        proc = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n",
            capture_output=True,
            text=True,
            check=True
        )
        for line in proc.stdout.splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""

REPO = "lmh200609-commits/xiaozhi-ai-gateway"
TAG = "v2.1.0"
RELEASE_NAME = "Xiaozhi AI Gateway v2.1.0 (硬件自愈配网与OTA全链路修复版)"

RELEASE_BODY = """## 🚀 小智 AI 语音网关 v2.1.0 (硬件自愈配网与OTA全链路修复版)

本项目是基于 ESP32 硬件与自建 Python 后端网关的小智 AI 语音助手全套工作区，支持离线语音识别 (SenseVoice)、在线流式语音合成 (Edge-TTS)、大模型对话中转、知识库 RAG 检索、设备端 MCP 工具调用及电脑端展厅展映控制。

### 🌟 v2.1.0 重大更新与修复（解决“检查新版本失败”）
1. **全面修复小智开发板“检查新版本失败”报错**：
   - 全面兼容小智官方 ESP32 固件的全部 OTA 路由别名（`/ota/`、`/xiaozhi/ota/`、`/api/ota/`）；
   - 返回标准固件版本结构体与 `Asia/Shanghai` 时区，彻底解决换电脑或跨局域网连接超时问题。
2. **内置网络自愈与一键工具**：
   - **`放行防火墙(遇到连接失败点我).bat`**：随包内置，双击自动申请 UAC 权限一键放行 Windows 防火墙 8001 端口；
   - **`一键配网开发板(插数据线点我).bat`**：通过 Type-C 数据线插电脑后双击，自动检测当前电脑 Wi-Fi IP 并一秒烧录进开发板。
3. **客户端界面优化**：
   - 首页顶部直接展示当前电脑真实的 Wi-Fi 局域网 IP；
   - 提供小智 WebSocket 长连接与 OTA 地址的**一键复制**按钮，手机 AP 配网更简单。
4. **真正的原生桌面应用程序体验**：
   - 双击桌面图标直接启动原生桌面 GUI 窗口，无需打开浏览器；
   - 纯净空白原配，大模型 API Key 彻底清空留白，新增**自定义人设删除功能**。

---

### 📥 下载与安装指南 (Assets 说明)

| 文件名 | 类型 | 说明 |
| :--- | :--- | :--- |
| **`XiaozhiGateway-v2.1-Setup.exe`** | **原生安装程序 (推荐)** | 下载后直接双击运行，自动安装并创建桌面快捷方式，秒级开启桌面原生应用！ |
| **`XiaozhiGateway-v2.1-Vanilla.zip`** | **绿色便携免安装版** | 解压到任意目录，直接双击运行 `XiaozhiGateway.exe` 即可启动原生应用。 |

---

### 💡 快速上手流程
1. 下载并运行 `XiaozhiGateway-v2.1-Setup.exe`；
2. 安装完成后启动桌面图标，直接开启原生桌面应用程序；
3. 在系统设置中填入您可用的大模型 API Key（支持 DeepSeek、智谱 GLM、SiliconFlow、OpenAI 等）；
4. 进入【知识库管理】上传您自己的 Word、PDF、Markdown 文件即可使用！
"""

def publish():
    print("=" * 64)
    print("   🚀 正在自动发布 GitHub Release 并上传 Assets...")
    print("=" * 64)

    token = get_github_token()
    headers = {
        "Authorization": f"token {token}",
        "User-Agent": "XiaozhiDeployer",
        "Accept": "application/vnd.github.v3+json"
    }

    # 1. Check if release already exists
    list_url = f"https://api.github.com/repos/{REPO}/releases"
    req = urllib.request.Request(list_url, headers=headers)
    release_obj = None
    try:
        with urllib.request.urlopen(req) as resp:
            releases = json.loads(resp.read().decode())
            for r in releases:
                if r.get("tag_name") == TAG:
                    release_obj = r
                    print(f"[*] 发现已有 Release (ID={r['id']})，将更新或复用...")
                    break
    except Exception as e:
        print(f"[*] 获取已存在 Release 提示: {e}")

    # 2. Create Release if not exist
    if not release_obj:
        print(f"[*] 正在创建新 Release: {TAG} - {RELEASE_NAME}...")
        create_url = f"https://api.github.com/repos/{REPO}/releases"
        payload = json.dumps({
            "tag_name": TAG,
            "target_commitish": "main",
            "name": RELEASE_NAME,
            "body": RELEASE_BODY,
            "draft": False,
            "prerelease": False
        }).encode("utf-8")

        req = urllib.request.Request(create_url, data=payload, headers=headers)
        with urllib.request.urlopen(req) as resp:
            release_obj = json.loads(resp.read().decode())
            print(f"[✓] Release 创建成功！ID={release_obj['id']}, HTML_URL={release_obj['html_url']}")

    release_id = release_obj["id"]
    upload_url_template = release_obj["upload_url"].split("{")[0]

    # 3. Check existing assets
    assets_url = f"https://api.github.com/repos/{REPO}/releases/{release_id}/assets"
    existing_asset_names = {}
    try:
        req = urllib.request.Request(assets_url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            existing_assets = json.loads(resp.read().decode())
            for a in existing_assets:
                existing_asset_names[a["name"]] = a["id"]
    except Exception as e:
        print(f"[*] 读取资产提示: {e}")

    # 4. Files to upload
    base_dir = Path(__file__).resolve().parent.parent.parent
    files_to_upload = [
        (base_dir / "dist" / "XiaozhiGateway-v2.1-Setup.exe", "XiaozhiGateway-v2.1-Setup.exe", "application/octet-stream"),
        (base_dir / "dist" / "XiaozhiGateway-v2.1-Vanilla.zip", "XiaozhiGateway-v2.1-Vanilla.zip", "application/zip")
    ]

    for file_path, asset_name, content_type in files_to_upload:
        if not file_path.exists():
            print(f"[!] 找不到待上传文件: {file_path}")
            continue

        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        print(f"\n[*] 准备上传资产: {asset_name} ({file_size_mb:.1f} MB)...")

        # Delete old asset if exists
        if asset_name in existing_asset_names:
            old_id = existing_asset_names[asset_name]
            print(f"    检测到已有旧资产 ID={old_id}，正在先删除旧资产...")
            del_url = f"https://api.github.com/repos/{REPO}/releases/assets/{old_id}"
            del_req = urllib.request.Request(del_url, headers=headers, method="DELETE")
            try:
                with urllib.request.urlopen(del_req) as del_resp:
                    print("    [✓] 旧资产已清理。")
            except Exception as e:
                print(f"    [!] 清理旧资产提示: {e}")

        # Upload asset
        upload_url = f"{upload_url_template}?name={urllib.parse.quote(asset_name)}"
        print(f"    正在上传至 GitHub Assets: {asset_name} (请稍候)...")
        with open(file_path, "rb") as f:
            file_data = f.read()

        upload_headers = {
            "Authorization": f"token {token}",
            "User-Agent": "XiaozhiDeployer",
            "Content-Type": content_type,
            "Content-Length": str(len(file_data))
        }

        up_req = urllib.request.Request(upload_url, data=file_data, headers=upload_headers)
        with urllib.request.urlopen(up_req) as up_resp:
            res_data = json.loads(up_resp.read().decode())
            print(f"    [✓] {asset_name} 上传成功！下载直链: {res_data.get('browser_download_url')}")

    print("\n" + "=" * 64)
    print(f"🎉 全部发布与资产上传完成！")
    print(f"🌐 Release 页面: https://github.com/{REPO}/releases/tag/{TAG}")
    print("=" * 64)

if __name__ == "__main__":
    publish()
