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
TAG = "v2.2.0"
RELEASE_NAME = "Xiaozhi AI Gateway v2.2.0 (5步图形化连网与配置向导 · 彻底解决连不上与喇叭无声)"

RELEASE_BODY = """## 🚀 小智 AI 语音网关 v2.2.0 (全新连网与配置向导 · 彻底解决连不上与喇叭无声)

本项目为小智 ESP32 AI 语音助手打造的专属离线/流式中转服务平台，集成离线极速语音识别 (SenseVoice)、微软自然神经网络语音合成 (Edge-TTS)、大模型对话中转、知识库私有化 RAG 检索、设备端 MCP 工具调控以及电脑端展厅大屏展映联动。

---

### 🌟 v2.2.0 重磅更新：内置【5步全自动化图形连网与配置向导 · 换电脑无缝连网】
为了彻底解决大家在不同电脑上使用小智、或切换不同 Wi-Fi 时老是遇到“检查新版本失败”、“中转网关连不上”或“喇叭没有声音”的困扰，**v2.2.0 进行了底层配网与网络诊断的全面重构**：

1. **📶 电脑 Wi-Fi 智能识别与 5GHz 避坑提醒**
   - 自动获取当前电脑已连接的 Wi-Fi 名称（SSID）与已保存的密码，自动填入配网表单，免去手动查找和输入的繁琐；
   - **智能频段检测**：若检测到电脑连接的是 5GHz Wi-Fi，向导将以醒目红色卡片提示（ESP32-S3 硬件仅支持 2.4GHz Wi-Fi），指引切换至 2.4G 频段或开启手机 2.4G 热点，避免盲目连接失败。
2. **🛡️ Windows 防火墙一键放行 (8001 端口)**
   - 在向导第 1 步增加防火墙入站检测，并提供【🛡️ 一键放行防火墙】按钮（自动执行管理员权限命令放行 8001 端口），彻底解决换新电脑时 Windows Defender 默认拦截导致开发板连不上网关的问题；安装程序安装时也会自动配置防火墙规则。
3. **🔌 USB 开发板自动识别与 Wi-Fi / IP 一键刷写**
   - 自动扫描电脑 USB 串口（高亮推荐识别 ESP32-S3 芯片）；
   - 点击【⚡ 一键写入】，无需改任何代码，全自动编译 NVS 配置并刷入开发板，开发板自动重启；
   - **彻底修复底层 Bug**：彻底移除以往启动程序时静默无感知覆盖烧录旧手机热点的行为，保证用户刷入的新 Wi-Fi 绝对不被篡改！
4. **📡 开发板与网关在线握手绿灯检测**
   - 动态雷达波纹与状态灯检测，板子开机 3~5 秒内自动通过 Wi-Fi 与网关建立毫秒级 WebSocket 长连接，展示 MAC 地址与版本号。
5. **🧠 AI 大模型中转与喇叭物理发音双隔离自检**
   - **大模型自测**：可直接在向导中输入/保存 API Key 并一键测试，返回首字延迟 (TTFT) 与测试回答，秒排查 401 密钥失效或余额耗尽；
   - **喇叭发声测试**：一键向在线开发板推送流式语音，板子喇叭立刻物理发声说话！彻底确认喇叭硬件正常！
6. **🎉 就绪与进入主控台**
   - 换电脑、换网络再也不用到处找人改代码，随时点击控制台右上角【🛠️ 连网配置向导】，1分钟轻松恢复连接！

---

### 📥 下载与安装指南 (Assets 说明)

| 文件名 | 类型 | 说明 |
| :--- | :--- | :--- |
| **`XiaozhiGateway-v2.1-Setup.exe`** | **原生安装程序 (强烈推荐)** | 下载后直接双击安装，自动创建桌面快捷方式，秒级开启桌面应用！ |
| **`XiaozhiGateway-v2.1-Vanilla.zip`** | **绿色便携免安装版** | 解压到任意目录，直接双击运行 `XiaozhiGateway.exe` 即可使用。 |

---

### 💡 快速上手流程
1. 下载并运行安装包；
2. 启动后网关将自动弹出【🛠️ 连网配置向导】，按照 5 步指引 1 分钟即可配网并听到板子说话；
3. 在系统设置中填入您可用的大模型 API Key（支持 DeepSeek、智谱 GLM、SiliconFlow 等）；
4. 进入【知识区管理】上传您自己的 Word、PDF、Markdown 文件即可使用！
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
