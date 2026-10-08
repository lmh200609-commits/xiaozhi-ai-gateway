import os
import json
from pathlib import Path
from pydantic import BaseModel

CONFIG_FILE = Path(__file__).parent / "config.json"
BASE_DIR = Path(__file__).resolve().parent.parent

class GatewayConfig(BaseModel):
    # Relay LLM settings (OpenAI-compatible)
    relay_base_url: str = "https://api.deepseek.com/v1"
    relay_api_key: str = ""
    model_name: str = "deepseek-chat"
    system_prompt: str = (
        "你是小智AI硬件语音助手。请用简明、生动、口语化且有亲和力的中文回答用户。"
        "因为你的回答会直接转为语音在开发板喇叭播放，切忌使用Markdown表格、复杂代码块或冗长列表，控制在1-3句话内直奔要点。"
        "若用户要求调节音量、屏幕亮度或切换主题，你可以直接调用设备端提供的工具。"
    )
    temperature: float = 0.7

    # TTS settings
    tts_voice: str = "zh-CN-YunxiNeural"  # 微软云希阳光少年音，或 zh-CN-XiaoxiaoNeural 晓晓亲切女声
    tts_rate: str = "+0%"
    tts_volume: str = "+0%"

    # ASR settings
    asr_model_path: str = str(BASE_DIR / "models" / "sense-voice" / "model.int8.onnx")
    asr_tokens_path: str = str(BASE_DIR / "models" / "sense-voice" / "tokens.txt")
    asr_num_threads: int = 4

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8001

    def get_chat_url(self) -> str:
        """Returns normalized OpenAI-compatible chat completion URL."""
        cleaned = (self.relay_base_url or "").strip().rstrip("/")
        if not cleaned:
            return "https://api.deepseek.com/v1/chat/completions"
        if cleaned.endswith("/chat/completions"):
            return cleaned
        return f"{cleaned}/chat/completions"

    @classmethod
    def load(cls) -> "GatewayConfig":
        default_model = str(BASE_DIR / "models" / "sense-voice" / "model.int8.onnx")
        default_tokens = str(BASE_DIR / "models" / "sense-voice" / "tokens.txt")
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                cfg = cls(**data)
                # Ensure model paths are valid; if path from config doesn't exist, resolve against current BASE_DIR
                if not Path(cfg.asr_model_path).is_file():
                    if (BASE_DIR / cfg.asr_model_path).is_file():
                        cfg.asr_model_path = str(BASE_DIR / cfg.asr_model_path)
                    elif Path(default_model).is_file():
                        cfg.asr_model_path = default_model
                if not Path(cfg.asr_tokens_path).is_file():
                    if (BASE_DIR / cfg.asr_tokens_path).is_file():
                        cfg.asr_tokens_path = str(BASE_DIR / cfg.asr_tokens_path)
                    elif Path(default_tokens).is_file():
                        cfg.asr_tokens_path = default_tokens
                return cfg
            except Exception as e:
                print(f"[Config] Error loading config.json, using defaults: {e}")
        cfg = cls()
        cfg.save()
        return cfg

    def save(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.model_dump(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Config] Error saving config.json: {e}")

config = GatewayConfig.load()
