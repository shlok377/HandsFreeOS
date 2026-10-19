"""Continuous microphone audio stream with acoustic echo suppression."""

import logging
import threading
from typing import Callable, Optional
import numpy as np

from handsfree.audio.vad import VoiceActivityDetector
from handsfree.audio.stt_phonon import PhononRecognizer
from handsfree.domain.models import SpeechChunk

logger = logging.getLogger(__name__)


class ContinuousAudioStream:
    """Manages continuous audio ingestion with VAD and echo cancellation lock."""

    def __init__(
        self,
        vad: Optional[VoiceActivityDetector] = None,
        recognizer: Optional[PhononRecognizer] = None,
        on_speech_chunk: Optional[Callable[[SpeechChunk], None]] = None,
    ):
        self.vad = vad or VoiceActivityDetector()
        self.recognizer = recognizer or PhononRecognizer()
        self.on_speech_chunk = on_speech_chunk

        self._echo_suppression_lock = threading.Lock()
        self._is_echo_suppressed = False
        self._is_running = False
        self._buffer: list[np.ndarray] = []

    def set_echo_suppression(self, active: bool) -> None:
        """Enables/disables echo suppression (called by TTS playback engine)."""
        with self._echo_suppression_lock:
            self._is_echo_suppressed = active
            if active:
                # Flush pending audio buffer so Bit doesn't hear past speaker output
                self._buffer.clear()
                self.vad.reset()
                logger.debug("Echo suppression engaged: dropping mic frames")
            else:
                logger.debug("Echo suppression disengaged: listening to mic")

    @property
    def is_echo_suppressed(self) -> bool:
        """Returns True if microphone frames are currently dropped."""
        with self._echo_suppression_lock:
            return self._is_echo_suppressed

    def feed_frame(self, frame: np.ndarray) -> Optional[SpeechChunk]:
        """Feeds a single audio PCM frame into the stream pipeline.

        Returns:
            Optional[SpeechChunk]: Transcribed chunk if speech chunk completed.
        """
        # If Bit is currently speaking, discard input to avoid hearing self
        if self.is_echo_suppressed:
            return None

        is_active, is_ended = self.vad.process_frame(frame)

        if is_active:
            self._buffer.append(frame)

        if is_ended and self._buffer:
            concatenated = np.concatenate(self._buffer)
            self._buffer.clear()

            chunk = self.recognizer.transcribe_audio(concatenated, is_final=True)
            if self.on_speech_chunk:
                self.on_speech_chunk(chunk)
            return chunk

        return None
