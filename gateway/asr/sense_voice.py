import re
import time
import numpy as np
import sherpa_onnx
from gateway.config import config

class SenseVoiceASR:
    """
    High-performance offline speech recognition using SenseVoice-Small INT8 ONNX.
    Provides sub-100ms inference on CPU with automatic punctuation and text normalization.
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
        print(f"[ASR] SenseVoice model initialized in {(time.time() - t0)*1000:.1f}ms")

    def transcribe(self, pcm_int16: np.ndarray) -> tuple[str, float]:
        """
        Transcribes 16kHz int16 PCM audio.
        Returns (clean_text, inference_duration_ms).
        """
        if len(pcm_int16) < 1600:  # Less than 100ms
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
        if clean_text in [".", "。", "！", "!", "?", "？", ",", "，", "Yeah.", "Yeah", "Okay.", "Okay", "ances of."]:
            return "", cost_ms
        return clean_text, cost_ms

asr_engine = None

def get_asr_engine() -> SenseVoiceASR:
    global asr_engine
    if asr_engine is None:
        asr_engine = SenseVoiceASR()
    return asr_engine
