"""Continuous microphone audio stream with acoustic echo suppression and background processing."""

import logging
import queue
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
        self._stop_event = threading.Event()
        self._frame_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=300)
        self._buffer: list[np.ndarray] = []

        # Start dedicated background audio processing worker
        self._worker_thread = threading.Thread(target=self._processing_loop, daemon=True)
        self._worker_thread.start()

    def set_echo_suppression(self, active: bool) -> None:
        """Enables/disables echo suppression (called by TTS playback engine)."""
        with self._echo_suppression_lock:
            self._is_echo_suppressed = active
            if active:
                # Flush pending audio buffer so Bit doesn't hear past speaker output
                self._buffer.clear()
                while not self._frame_queue.empty():
                    try:
                        self._frame_queue.get_nowait()
                    except queue.Empty:
                        break
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
        """Non-blocking audio feed from real-time PortAudio callback."""
        if self.is_echo_suppressed:
            return None

        try:
            self._frame_queue.put_nowait(frame)
        except queue.Full:
            # Drop oldest frame to maintain low latency
            try:
                self._frame_queue.get_nowait()
                self._frame_queue.put_nowait(frame)
            except Exception:
                pass

        return None

    def feed_frame_sync(self, frame: np.ndarray) -> Optional[SpeechChunk]:
        """Synchronous frame processing for deterministic unit testing."""
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

    def _processing_loop(self) -> None:
        """Dedicated background thread processing VAD and neural transcription."""
        while not self._stop_event.is_set():
            try:
                frame = self._frame_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if self.is_echo_suppressed:
                self._buffer.clear()
                self._frame_queue.task_done()
                continue

            is_active, is_ended = self.vad.process_frame(frame)

            if is_active:
                self._buffer.append(frame)

            if is_ended and self._buffer:
                concatenated = np.concatenate(self._buffer)
                self._buffer.clear()

                chunk = self.recognizer.transcribe_audio(concatenated, is_final=True)
                if self.on_speech_chunk:
                    try:
                        self.on_speech_chunk(chunk)
                    except Exception as e:
                        logger.error(f"Error in on_speech_chunk handler: {e}")

            self._frame_queue.task_done()

    def stop(self) -> None:
        """Stops background worker thread."""
        self._stop_event.set()
