import re
import time
import numpy as np
import sherpa_onnx
from gateway.config import config

class SenseVoiceASR:
    """
    High-performance offline speech recognition using SenseVoice-Small INT8 ONNX.
    Provides sub-100ms inference on CPU with automatic punctuation and text normalization.
    Includes active energy gating and phantom hallucination filtering (e.g. spurious '我' on silence).
    """
    def __init__(self):
        print(f"[ASR] Loading SenseVoice model from: {config.asr_model_path}")
        t0 = time.time()
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=config.asr_model_path,
            tokens=config.asr_tokens_path,
            num_threads=config.asr_num_threads,
            sample_rate=16000,
            use_itn=True,
            language="zh"
        )
        self.tag_pattern = re.compile(r"<\|[a-zA-Z0-9_]+\|>")
        self.ghost_tokens = {
            "我", "我。", "我，", "啊", "啊。", "嗯", "嗯。", "呃", "呃。",
            "哦", "哦。", "欸", "呀", "吧", "呢", "哈", "呵", "你", "对",
            "我我", "啊啊", "嗯嗯", "在", "好", "好的", "对的", "。", ".",
            "Yeah.", "Yeah", "Okay.", "Okay", "ances of.", "you", "the"
        }
        print(f"[ASR] SenseVoice model initialized in {(time.time() - t0)*1000:.1f}ms")

    def transcribe(self, pcm_int16: np.ndarray) -> tuple[str, float]:
        """
        Transcribes 16kHz int16 PCM audio.
        Returns (clean_text, inference_duration_ms).
        """
        if len(pcm_int16) < 4800:  # Less than 300ms audio
            return "", 0.0

        # Energy gate: check RMS to ensure genuine vocal energy rather than mic floor noise
        rms = float(np.sqrt(np.mean(pcm_int16.astype(np.float32) ** 2)))
        duration_sec = len(pcm_int16) / 16000.0

        if rms < 150.0:
            # Ambient microphone hiss / breathing
            return "", 0.0

        # Convert int16 to float32 [-1.0, 1.0]
        samples_float32 = pcm_int16.astype(np.float32) / 32768.0

        t0 = time.time()
        stream = self.recognizer.create_stream()
        stream.accept_waveform(16000, samples_float32)
        self.recognizer.decode_stream(stream)
        raw_text = stream.result.text
        cost_ms = (time.time() - t0) * 1000.0

        # Clean special tokens like <|zh|>, <|NEUTRAL|>, <|Speech|>
        clean_text = self.tag_pattern.sub("", raw_text).strip()
        if not clean_text:
            return "", cost_ms

        pure_tokens = re.sub(r'[\s。，、？！?!.,\-_~`]', '', clean_text)
        if not pure_tokens:
            return "", cost_ms

        # Filter known phantom hallucination tokens triggered on low-energy ambient noise
        if pure_tokens in self.ghost_tokens or clean_text in self.ghost_tokens:
            if duration_sec < 1.2 or rms < 450.0:
                # Suppress phantom token
                return "", cost_ms

        return clean_text, cost_ms

asr_engine = None

def get_asr_engine() -> SenseVoiceASR:
    global asr_engine
    if asr_engine is None:
        asr_engine = SenseVoiceASR()
    return asr_engine
