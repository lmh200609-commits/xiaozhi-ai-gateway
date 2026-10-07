import ctypes
import numpy as np
from pyogg import opus

class OpusDecoderWrapper:
    """Decodes raw Opus frames from ESP32 into 16kHz int16 PCM audio samples."""
    def __init__(self, sample_rate: int = 16000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_size = int(sample_rate * 0.06)  # 60ms = 960 samples
        err = ctypes.c_int()
        self._decoder = opus.opus_decoder_create(self.sample_rate, self.channels, ctypes.byref(err))
        if err.value != 0:
            raise RuntimeError(f"Failed to create Opus decoder, error code: {err.value}")

    def decode(self, opus_bytes: bytes) -> np.ndarray:
        """Decodes an Opus packet into an array of int16 PCM samples."""
        if not opus_bytes:
            return np.array([], dtype=np.int16)
        
        in_len = len(opus_bytes)
        in_buf = (ctypes.c_ubyte * in_len).from_buffer_copy(opus_bytes)
        # Allocate buffer for decoded samples (max 120ms frame = 1920 samples)
        max_samples = 2880
        out_pcm = (ctypes.c_int16 * max_samples)()
        
        samples_decoded = opus.opus_decode(
            self._decoder,
            in_buf,
            in_len,
            out_pcm,
            max_samples,
            0
        )
        if samples_decoded < 0:
            return np.array([], dtype=np.int16)
            
        return np.frombuffer(out_pcm, dtype=np.int16, count=samples_decoded)

    def reset(self):
        if self._decoder:
            opus.opus_decoder_ctl(self._decoder, opus.OPUS_RESET_STATE)

    def __del__(self):
        if hasattr(self, "_decoder") and self._decoder:
            try:
                opus.opus_decoder_destroy(self._decoder)
            except Exception:
                pass


class OpusEncoderWrapper:
    """Encodes 16kHz int16 PCM audio samples into 60ms Opus frames for ESP32."""
    def __init__(self, sample_rate: int = 16000, channels: int = 1, frame_duration_ms: int = 60):
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_size = int(sample_rate * (frame_duration_ms / 1000.0))  # 960 samples
        err = ctypes.c_int()
        # 2048 = OPUS_APPLICATION_VOIP
        self._encoder = opus.opus_encoder_create(self.sample_rate, self.channels, 2048, ctypes.byref(err))
        if err.value != 0:
            raise RuntimeError(f"Failed to create Opus encoder, error code: {err.value}")
        
        # Optimize for speech (complexity 5, bitrate 24000)
        opus.opus_encoder_ctl(self._encoder, opus.OPUS_SET_COMPLEXITY_REQUEST, 5)
        opus.opus_encoder_ctl(self._encoder, opus.OPUS_SET_BITRATE_REQUEST, 24000)

    def encode(self, pcm_int16: np.ndarray) -> bytes:
        """Encodes exactly one frame (960 samples) of int16 PCM to Opus bytes."""
        if len(pcm_int16) != self.frame_size:
            # Pad or truncate to frame_size
            padded = np.zeros(self.frame_size, dtype=np.int16)
            n = min(len(pcm_int16), self.frame_size)
            padded[:n] = pcm_int16[:n]
            pcm_int16 = padded

        in_pcm = (ctypes.c_int16 * self.frame_size).from_buffer_copy(pcm_int16.tobytes())
        out_buf = (ctypes.c_ubyte * 1024)()
        
        encoded_bytes = opus.opus_encode(
            self._encoder,
            in_pcm,
            self.frame_size,
            out_buf,
            1024
        )
        if encoded_bytes < 0:
            return b""
            
        return bytes(out_buf[:encoded_bytes])

    def encode_stream(self, full_pcm_int16: np.ndarray):
        """Generator that slices full PCM audio into 60ms frames and yields Opus packets."""
        total_samples = len(full_pcm_int16)
        offset = 0
        while offset < total_samples:
            chunk = full_pcm_int16[offset:offset + self.frame_size]
            yield self.encode(chunk)
            offset += self.frame_size

    def __del__(self):
        if hasattr(self, "_encoder") and self._encoder:
            try:
                opus.opus_encoder_destroy(self._encoder)
            except Exception:
                pass
