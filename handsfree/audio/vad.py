"""Adaptive Voice Activity Detection (VAD) with dynamic noise calibration."""

import numpy as np


class VoiceActivityDetector:
    """Detects speech boundaries with dynamic noise floor tracking and max duration safety."""

    def __init__(
        self,
        sample_rate: int = 16000,
        energy_threshold: float = 0.045,
        min_energy_threshold: float = 0.030,
        silence_timeout_ms: int = 450,
        max_speech_duration_ms: int = 4500,
    ):
        self.sample_rate = sample_rate
        self.energy_threshold = energy_threshold
        self.min_energy_threshold = min_energy_threshold
        self.silence_timeout_ms = silence_timeout_ms
        self.silence_samples_threshold = int((silence_timeout_ms / 1000.0) * sample_rate)
        self.max_speech_samples = int((max_speech_duration_ms / 1000.0) * sample_rate)

        self.ambient_noise_rms: float = 0.020
        self._in_speech = False
        self._silent_samples_count = 0
        self._active_samples_count = 0
        self.last_rms: float = 0.0

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
        self.last_rms = rms

        # Compute dynamic threshold based on ambient noise floor
        effective_threshold = max(self.min_energy_threshold, self.ambient_noise_rms * 1.8)

        is_current_speech = rms > effective_threshold

        speech_ended = False

        if is_current_speech:
            self._in_speech = True
            self._silent_samples_count = 0
            self._active_samples_count += len(frame)

            # Max duration safety: emit chunk if speech continues past 4.5s
            if self._active_samples_count >= self.max_speech_samples:
                self._in_speech = False
                speech_ended = True
                self._silent_samples_count = 0
                self._active_samples_count = 0
        else:
            if self._in_speech:
                self._silent_samples_count += len(frame)
                if self._silent_samples_count >= self.silence_samples_threshold:
                    self._in_speech = False
                    speech_ended = True
                    self._silent_samples_count = 0
                    self._active_samples_count = 0
            else:
                # Update ambient noise baseline when silent using exponential moving average
                self.ambient_noise_rms = 0.95 * self.ambient_noise_rms + 0.05 * rms

        return self._in_speech, speech_ended

    def reset(self) -> None:
        """Resets detector state."""
        self._in_speech = False
        self._silent_samples_count = 0
        self._active_samples_count = 0
