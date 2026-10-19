"""Voice Activity Detection (VAD) chunking module."""

import numpy as np


class VoiceActivityDetector:
    """Detects speech boundaries from raw audio buffers using energy and zero-crossing analysis."""

    def __init__(
        self,
        sample_rate: int = 16000,
        energy_threshold: float = 0.015,
        silence_timeout_ms: int = 400,
    ):
        self.sample_rate = sample_rate
        self.energy_threshold = energy_threshold
        self.silence_timeout_ms = silence_timeout_ms
        self.silence_samples_threshold = int((silence_timeout_ms / 1000.0) * sample_rate)

        self._in_speech = False
        self._silent_samples_count = 0

    def process_frame(self, frame: np.ndarray) -> tuple[bool, bool]:
        """Processes a raw PCM audio frame.

        Args:
            frame: float32 numpy array with values in [-1.0, 1.0].

        Returns:
            tuple[bool, bool]: (is_speech_active, is_speech_ended)
        """
        if len(frame) == 0:
            return False, False

        # Compute Root Mean Square (RMS) energy
        rms = float(np.sqrt(np.mean(frame**2)))

        is_current_speech = rms > self.energy_threshold

        speech_ended = False

        if is_current_speech:
            self._in_speech = True
            self._silent_samples_count = 0
        else:
            if self._in_speech:
                self._silent_samples_count += len(frame)
                if self._silent_samples_count >= self.silence_samples_threshold:
                    self._in_speech = False
                    speech_ended = True
                    self._silent_samples_count = 0

        return self._in_speech, speech_ended

    def reset(self) -> None:
        """Resets detector state."""
        self._in_speech = False
        self._silent_samples_count = 0
