import numpy as np

class EnergyVAD:
    """
    Adaptive energy-based Voice Activity Detection for 16kHz audio frames (60ms chunks).
    Detects speech onset quickly and trailing silence cleanly without clipping natural pauses.
    Includes maximum speech ceiling to prevent indefinite hangs in noisy environments.
    """
    def __init__(
        self,
        min_energy_threshold: float = 120.0,
        silence_duration_frames: int = 11,    # ~660ms trailing silence (11 * 60ms) for natural pauses
        min_speech_frames: int = 2,           # ~120ms of active speech required for snappy trigger
        max_speech_frames: int = 150          # ~9.0 seconds maximum utterance before auto-cutoff
    ):
        self.min_energy_threshold = min_energy_threshold
        self.silence_duration_frames = silence_duration_frames
        self.min_speech_frames = min_speech_frames
        self.max_speech_frames = max_speech_frames
        
        self.noise_floor = 40.0
        self.speech_started = False
        self.consecutive_speech = 0
        self.consecutive_silence = 0
        self.speech_frame_count = 0
        self.total_frames = 0

    def process_frame(self, pcm_int16: np.ndarray) -> tuple[bool, bool]:
        """
        Processes a single frame (e.g. 960 samples / 60ms at 16kHz).
        Returns (is_speech, speech_ended).
        """
        if len(pcm_int16) == 0:
            return False, False
            
        self.total_frames += 1
        rms = float(np.sqrt(np.mean(pcm_int16.astype(np.float32) ** 2)))
        
        # Adaptive threshold: floats with ambient room noise, never drops below min_energy_threshold
        current_threshold = max(self.min_energy_threshold, self.noise_floor * 2.2)
        is_speech = rms > current_threshold

        if is_speech:
            self.consecutive_speech += 1
            self.consecutive_silence = 0
            if self.consecutive_speech >= self.min_speech_frames:
                self.speech_started = True
        else:
            self.consecutive_speech = 0
            if self.speech_started:
                self.consecutive_silence += 1
            else:
                # Update background noise floor estimation only when user is NOT speaking
                self.noise_floor = 0.95 * self.noise_floor + 0.05 * min(rms, 250.0)

        if self.speech_started:
            self.speech_frame_count += 1

        # Finalize speech on natural silence or safety timeout
        speech_ended = (
            self.speech_started and (
                self.consecutive_silence >= self.silence_duration_frames or
                self.speech_frame_count >= self.max_speech_frames
            )
        )
        return is_speech, speech_ended

    def reset(self):
        """Resets speech tracking state for the next user utterance."""
        self.speech_started = False
        self.consecutive_speech = 0
        self.consecutive_silence = 0
        self.speech_frame_count = 0
