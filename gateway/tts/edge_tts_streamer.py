import os
import sys
import asyncio
import re
import tempfile
import subprocess
from pathlib import Path
import miniaudio
import numpy as np
import edge_tts
from gateway.config import config
from gateway.audio.opus_codec import OpusEncoderWrapper

def get_system_proxy() -> str | None:
    """自动获取系统或环境变量配置的代理地址（兼容 Clash/v2ray 等工具）"""
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        v = os.environ.get(k)
        if v:
            if not v.startswith("http://") and not v.startswith("https://"):
                v = f"http://{v}"
            return v
    try:
        import winreg
        reg = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
        enable, _ = winreg.QueryValueEx(reg, "ProxyEnable")
        if enable:
            server, _ = winreg.QueryValueEx(reg, "ProxyServer")
            if server:
                if "=" in server:
                    for part in server.split(";"):
                        if part.startswith("http=") or part.startswith("https="):
                            server = part.split("=", 1)[1]
                            break
                if not server.startswith("http://") and not server.startswith("https://"):
                    server = f"http://{server}"
                return server
    except Exception:
        pass
    return None

def offline_sapi_tts(text: str, sample_rate: int = 24000) -> np.ndarray | None:
    """
    Windows 本地原生 SAPI 离线语音合成引擎（零网络、零外部依赖、极速稳定）。
    当微软 Edge 在线服务器 (speech.platform.bing.com) 受网络/防火墙阻断时自动兜底调用。
    """
    clean = text.replace('"', '""').replace('\n', ' ').replace('\r', ' ').strip()
    if not clean:
        return None

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as wf, \
         tempfile.NamedTemporaryFile(suffix='.vbs', delete=False) as vf:
        wav_path = wf.name
        vbs_path = vf.name

    try:
        vbs_code = f'''Set voice = CreateObject("SAPI.SpVoice")
Set stream = CreateObject("SAPI.SpFileStream")
stream.Open "{wav_path}", 3
Set voice.AudioOutputStream = stream
voice.Speak "{clean}"
stream.Close
'''
        with open(vbs_path, 'w', encoding='gbk', errors='ignore') as f:
            f.write(vbs_code)

        res = subprocess.run(['cscript', '//nologo', vbs_path], capture_output=True, timeout=8)
        if os.path.exists(wav_path) and os.path.getsize(wav_path) > 44:
            decoded = miniaudio.decode_file(wav_path, nchannels=1, sample_rate=sample_rate)
            return np.array(decoded.samples, dtype=np.int16)
    except Exception as e:
        print(f"[TTS SAPI] 离线语音合成异常: {e}")
    finally:
        for p in (wav_path, vbs_path):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
    return None

# Comprehensive Unicode emoji regex pattern (strictly within emoji code blocks, preserving all Chinese characters)
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"  # SMP: All modern emojis (pictographs, emoticons, symbols, gestures)
    "\U0001F1E6-\U0001F1FF"  # SMP: Regional flags
    "\U0001F200-\U0001F251"  # SMP: Enclosed ideographic supplement
    "\U00002600-\U000026FF"  # BMP: Misc symbols (e.g. ☀️, ☔, ⚡)
    "\U00002700-\U000027BF"  # BMP: Dingbats (e.g. ✨, ✈️, ✉️)
    "\U00002B50-\U00002B55"  # BMP: Stars
    "\U0000FE00-\U0000FE0F"  # Variation selectors
    "\U0000200D"              # Zero width joiner
    "]+",
    flags=re.UNICODE
)

# Regex to match emotion words in brackets or parentheses like [微笑], (点赞), 【害羞】, （羞涩微笑）
EMOTION_BRACKET_PATTERN = re.compile(
    r'[\[\(\（\【](?:'
    r'微笑|害羞|羞涩微笑|微笑着的脸|大笑|偷笑|冷笑|龇牙|点赞|赞|拇指向上|'
    r'鼓掌|双手合十|思考|捂脸|哭笑|流泪|抓狂|难过|伤心|生气|愤怒|得意|'
    r'调皮|可爱|眨眼|眨眼微笑|问号|困惑|叹气|惊讶|震惊|抱拳|握手|'
    r'比心|爱心|红心|玫瑰|太阳|月亮|拥抱|拜托|加油|奋斗|庆祝|彩炮|干杯|'
    r'笑脸|皱眉|撇嘴|擦汗|疑问|吐舌|呆滞|委屈|难受|尴尬|汗颜'
    r')[\]\)\）\】]',
    flags=re.IGNORECASE
)

# Regex to clean up literal spoken emotion phrases (e.g. Edge TTS translation artifacts like "拇指向上", "羞涩微笑")
EMOTION_PHRASE_PATTERN = re.compile(
    r'(?:^|(?<=[\s，。！？、~～]))(?:拇指向上|羞涩微笑|微笑着的脸|眨眼微笑|双手合十|满脸堆笑)(?:$|(?=[\s，。！？、~～]))'
)

def clean_speech_text(text: str) -> str:
    """
    Strips markdown formatting (*, **, #, `, ~, etc.), Unicode emojis (👍, 😊, etc.),
    and emotion tags/artifacts ([微笑], (点赞), 拇指向上, 羞涩微笑) from speech text.
    Ensures Edge-TTS does not speak '星号星号' or '拇指向上'/'羞涩微笑',
    and hardware screens do not display raw asterisks or empty square boxes [ ].
    """
    if not text:
        return ""
    # Strip internal stage transition markers (e.g. [NEXT_STAGE], [STAGE:2]) so TTS never pronounces them
    s = re.sub(r'\[(NEXT_STAGE|STAGE:\d+)\]', '', text, flags=re.IGNORECASE)
    # 1. Strip all Unicode emoji characters
    s = EMOJI_PATTERN.sub('', s)
    # 2. Strip bracketed / parenthesized emotion tags like [微笑], (点赞), （羞涩微笑）
    s = EMOTION_BRACKET_PATTERN.sub('', s)
    # 3. Strip standalone spoken emoji artifact phrases like "拇指向上", "羞涩微笑"
    s = EMOTION_PHRASE_PATTERN.sub('', s)
    # 4. Strip code blocks / backticks
    s = re.sub(r'`+', '', s)
    # 5. Strip asterisks (markdown bold/italic, e.g. **text** -> text, *text* -> text)
    s = re.sub(r'\*+', '', s)
    # 6. Strip underscores (markdown bold/italic)
    s = re.sub(r'_+', '', s)
    # 7. Strip markdown headers at line start (e.g. ## Title -> Title)
    s = re.sub(r'^\s*#+\s*', '', s, flags=re.MULTILINE)
    # 8. Strip blockquotes at line start (e.g. > Quote -> Quote)
    s = re.sub(r'^\s*>\s*', '', s, flags=re.MULTILINE)
    # 9. Strip tildes (strikethrough ~~)
    s = re.sub(r'~+', '', s)
    # 10. Strip markdown bullet points at line start (e.g. "- item" -> "item")
    s = re.sub(r'^\s*[-+]\s+', '', s, flags=re.MULTILINE)
    # 11. Clean redundant punctuation after emoji removal (e.g. "！，" -> "！", "，，" -> "，")
    s = re.sub(r'([，。！？])\s*[，、]', r'\1', s)
    # 12. Clean multiple whitespace
    s = re.sub(r'[ \t]+', ' ', s).strip()
    return s

class EdgeTTSStreamer:
    """
    Synthesizes speech using Edge-TTS with auto-fallback to Windows local SAPI.
    Directly encodes speech into 24kHz 60ms Opus frames (1440 samples).
    Matches ESP32 AUDIO_OUTPUT_SAMPLE_RATE = 24000.
    """
    def __init__(self, sample_rate: int = 24000):
        self.sample_rate = sample_rate
        self.encoder = OpusEncoderWrapper(sample_rate=self.sample_rate, channels=1, frame_duration_ms=60)

    async def text_to_opus_stream(self, text: str, voice: str = None):
        """
        Synthesizes a sentence to 24kHz PCM and yields 60ms Opus packets sequentially.
        Yields (opus_frame_bytes, is_last_frame).
        Dual-Engine Architecture:
        1. Primary: Edge-TTS (high quality neural voice with auto-detected proxy).
        2. Fallback: Windows SAPI (instant offline speech engine when Edge server is blocked).
        3. Failsafe: Bundled test WAV in gateway/data/ if available.
        """
        clean_text = clean_speech_text(text).strip()
        if not clean_text:
            return

        pcm_samples = None

        # 1. Primary: Try Edge-TTS
        active_voice = voice or config.tts_voice
        proxy = get_system_proxy()
        try:
            communicate = edge_tts.Communicate(
                clean_text,
                voice=active_voice,
                rate=config.tts_rate,
                volume=config.tts_volume,
                proxy=proxy,
                connect_timeout=5,
                receive_timeout=12
            )

            mp3_chunks = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_chunks.append(chunk["data"])

            if mp3_chunks:
                raw_mp3 = b"".join(mp3_chunks)
                decoded = miniaudio.decode(raw_mp3, nchannels=1, sample_rate=self.sample_rate)
                pcm_samples = np.array(decoded.samples, dtype=np.int16)
        except Exception as e:
            print(f"[TTS] Edge-TTS 在线服务不可用 ({e})，正在自动无缝切换为 Windows 本地离线语音引擎...")

        # 2. Fallback: Windows SAPI offline TTS
        if pcm_samples is None or len(pcm_samples) == 0:
            try:
                loop = asyncio.get_event_loop()
                pcm_samples = await loop.run_in_executor(None, offline_sapi_tts, clean_text, self.sample_rate)
            except Exception as e:
                print(f"[TTS] 离线 SAPI 执行失败: {e}")

        # 3. Failsafe: Bundled test WAV
        if pcm_samples is None or len(pcm_samples) == 0:
            bundled_wav = Path(__file__).resolve().parent.parent / "data" / "test_speaker.wav"
            if bundled_wav.exists():
                try:
                    decoded = miniaudio.decode_file(str(bundled_wav), nchannels=1, sample_rate=self.sample_rate)
                    pcm_samples = np.array(decoded.samples, dtype=np.int16)
                    print(f"[TTS] 已使用内置测试音频兜底输出: {bundled_wav.name}")
                except Exception:
                    pass

        if pcm_samples is None or len(pcm_samples) == 0:
            print(f"[TTS Error] 所有语音合成方案均不可用: '{clean_text}'")
            return

        # Slice PCM into 960-sample (60ms) chunks and encode
        frame_size = self.encoder.frame_size
        total_samples = len(pcm_samples)
        for offset in range(0, total_samples, frame_size):
            chunk = pcm_samples[offset:offset + frame_size]
            opus_frame = self.encoder.encode(chunk)
            if opus_frame:
                is_last = (offset + frame_size >= total_samples)
                yield opus_frame, is_last

# Split a continuous stream of tokens into natural sentence chunks for streaming TTS
SENTENCE_END_RE = re.compile(r'([。！？!?；;\n]+)')

def split_sentences(buffer: str) -> tuple[list[str], str]:
    """
    Extracts complete sentences ending with punctuation from a stream buffer.
    Returns (list_of_sentences, remaining_incomplete_text).
    """
    parts = SENTENCE_END_RE.split(buffer)
    sentences = []
    # parts: [text1, punc1, text2, punc2, remaining]
    for i in range(0, len(parts) - 1, 2):
        sentence = (parts[i] + parts[i+1]).strip()
        cleaned = clean_speech_text(sentence)
        if cleaned:
            sentences.append(cleaned)
    
    remainder = parts[-1] if len(parts) % 2 == 1 else ""
    return sentences, remainder
