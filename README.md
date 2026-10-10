# 小智 AI 硬件与语音网关 (Xiaozhi AI Hardware & Voice Gateway)

本项目是基于 ESP32 硬件与自建 Python 后端网关的小智 AI 语音助手全套工作区，支持离线语音识别 (SenseVoice)、在线流式语音合成 (Edge-TTS)、大模型对话中转、知识库 RAG 检索、设备端 MCP 工具调用及电脑端展厅展映控制。

> 📦 **【Windows 免安装独立版 EXE 直接下载】**:
> 如果您不想安装 Python 环境，可以直接下载我们为您打包的 **纯净空白便携运行版**：
> * 📥 **直接下载安装包**: [release/XiaozhiGateway-v2.0-Vanilla.zip](release/XiaozhiGateway-v2.0-Vanilla.zip)
> * ✨ **纯净原装**: 零测试残留数据，仅内置单一通用【专属知识库客服】角色，知识库全空白待导入。
> * 🚀 **双击秒开**: 解压后直接双击【启动小智网关.bat】即可，内置完整 Web 管理后台、RAG 向量检索与语音服务！
>
> 📖 **通用化配置指南**: 请参阅 [ADAPTATION_GUIDE.md](ADAPTATION_GUIDE.md)，了解如何接入 DeepSeek、SiliconFlow、WiFi 配网与场景人设隔离。

---

## 快速上手指南（新电脑部署）

### 1. 运行环境要求
* **操作系统**：Windows 10 / 11 (64位)
* **Python**：Python 3.10 或 3.11（安装时请勾选 `Add Python to PATH`）

### 2. 一键自动化部署 (推荐)
在新电脑克隆或下载代码后，只需在项目根目录双击执行：
```bat
setup_env.bat
```
向导将全自动完成：
1. 建立独立的 Python 虚拟环境 (`.venv`)
2. 自动切换国内高速镜像源并安装所有运行依赖
3. 自动从 ModelScope 高速通道拉取离线 SenseVoice 语音识别模型权重
4. 自动生成默认配置文件模板

### 3. 配置与启动
1. 用文本编辑器打开 `gateway/config.json`：
   * 将 `relay_api_key` 替换为你可用的大模型 API 密钥。
   * 如有需要，可修改模型名称 `model_name` 或语音角色 `tts_voice`。
3. 一键启动网关 (任选以下任一方式)：
   * **方式 A (推荐命令行)**：在根目录运行 `py -3.11 run.py` 或 `python run.py`
   * **方式 B (便携双击)**：双击根目录下的 `start_gateway.bat`
   * **方式 C (桌面快捷方式)**：运行 `python setup_desktop_launcher.py` 可在电脑桌面一键生成【启动小智AI网关】图标
4. 系统将自动释放端口、同步网络并打开 Web 控制台：
   * 浏览器访问：[http://localhost:8001](http://localhost:8001)

---

## 脱离本地硬件连接与开发指南

你**不需要时刻将小智开发板插在电脑主机上**即可进行完整的项目开发与体验：

### 模式 A：纯软件开发调试（无需开发板）
* **Web 控制台直接交互**：在浏览器控制台中可直接进行提示词调优、知识库文档录入、角色切换与业务指令测试。
* **硬件全协议模拟器**：运行以下命令，可直接模拟 ESP32 硬件进行 Opus 语音流与 MCP 工具测试：
  ```bash
  python gateway/scripts/test_hardware_ws.py
  ```

### 模式 B：局域网纯无线运行（无需电脑 USB 连线）
小智开发板本质上是通过 Wi-Fi 与电脑网关通信：
* 在开发板通过电脑烧录过一次局域网 Wi-Fi 与电脑 IP 之后，**即可拔掉电脑 USB**；
* 将开发板插在任意手机充电头或充电宝上，放在房间任何位置，只要连接相同 Wi-Fi，即可无线与电脑交互。

---

## 目录结构说明

```text
├── gateway/                    # Python 网关服务端核心源码
│   ├── agent/                  # PC 电脑端工具执行器与智能体调度
│   ├── asr/                    # SenseVoice 离线语音识别封装
│   ├── audio/                  # Opus 音频编解码与能量 VAD 检测
│   ├── llm/                    # 大模型中转与流式对话客户端
│   ├── rag/                    # 知识库向量检索与全文搜索 (FastEmbed + Jieba + SQLite FTS5)
│   ├── roles/                  # 语音助手人设与角色管理
│   ├── tts/                    # 微软 Edge-TTS 流式语音合成
│   ├── web/                    # 现代化 Web 控制台与展厅 Kiosk 前端界面
│   ├── config.example.json     # 网关配置模板 (脱敏)
│   └── requirements.txt        # 完整 Python 依赖清单
├── xiaozhi-esp32/              # ESP32 硬件端固件源码 (C++ / ESP-IDF)
├── run.py                      # 网关统一入口启动器 (命令行/终端直启)
├── start_gateway.bat           # 便携式自适应网关启动脚本 (双击启动)
├── setup_desktop_launcher.py   # 一键生成电脑桌面启动图标工具
├── setup_env.bat               # 新电脑一键部署环境批处理向导
└── README.md                   # 项目工程说明文档
```
