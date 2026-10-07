import asyncio
import re
import miniaudio
import numpy as np
import edge_tts
from gateway.config import config
from gateway.audio.opus_codec import OpusEncoderWrapper

def clean_speech_text(text: str) -> str:
    """
    Strips markdown formatting (*, **, #, `, ~, etc.) from speech text
    so Edge-TTS does not speak '星号星号' and hardware screens do not display raw asterisks.
    """
    if not text:
        return ""
    # 1. Strip code blocks / backticks
    s = re.sub(r'`+', '', text)
    # 2. Strip asterisks (markdown bold/italic, e.g. **text** -> text, *text* -> text)
    s = re.sub(r'\*+', '', s)
    # 3. Strip underscores (markdown bold/italic)
    s = re.sub(r'_+', '', s)
    # 4. Strip markdown headers at line start (e.g. ## Title -> Title)
    s = re.sub(r'^\s*#+\s*', '', s, flags=re.MULTILINE)
    # 5. Strip blockquotes at line start (e.g. > Quote -> Quote)
    s = re.sub(r'^\s*>\s*', '', s, flags=re.MULTILINE)
    # 6. Strip tildes (strikethrough ~~)
    s = re.sub(r'~+', '', s)
    # 7. Strip markdown bullet points at line start (e.g. "- item" -> "item")
    s = re.sub(r'^\s*[-+]\s+', '', s, flags=re.MULTILINE)
    # 8. Clean multiple whitespace
    s = re.sub(r'[ \t]+', ' ', s).strip()
    return s

class EdgeTTSStreamer:
    """
    Synthesizes speech using Edge-TTS and directly encodes it to 24kHz 60ms Opus frames (1440 samples).
    Matches ESP32 AUDIO_OUTPUT_SAMPLE_RATE = 24000.
    """
    def __init__(self, sample_rate: int = 24000):
        self.sample_rate = sample_rate
        self.encoder = OpusEncoderWrapper(sample_rate=self.sample_rate, channels=1, frame_duration_ms=60)

    async def text_to_opus_stream(self, text: str, voice: str = None):
        """
        Synthesizes a sentence to 24kHz PCM and yields 60ms Opus packets (1440 samples) sequentially.
        Yields (opus_frame_bytes, is_last_frame).
        """
        clean_text = clean_speech_text(text).strip()
        if not clean_text:
            return

        active_voice = voice or config.tts_voice
        communicate = edge_tts.Communicate(
            clean_text,
            voice=active_voice,
            rate=config.tts_rate,
            volume=config.tts_volume
        )

        mp3_chunks = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                mp3_chunks.append(chunk["data"])

        if not mp3_chunks:
            return

        raw_mp3 = b"".join(mp3_chunks)
        # Decode MP3 to 24kHz mono int16 PCM in memory
        try:
            decoded = miniaudio.decode(raw_mp3, nchannels=1, sample_rate=self.sample_rate)
            pcm_samples = np.array(decoded.samples, dtype=np.int16)
        except Exception as e:
            print(f"[TTS] miniaudio decode failed: {e}")
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
