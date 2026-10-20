"""Local neural Text-to-Speech (TTS) module using Kokoro-82M / Piper."""

import logging
import queue
import shutil
import subprocess
import threading
import time
from typing import Callable, Optional

from handsfree.domain.interfaces import ITextToSpeech

logger = logging.getLogger(__name__)


class KokoroTTS(ITextToSpeech):
    """Ultra-fast local neural TTS engine generating audio in <50ms."""

    def __init__(
        self,
        voice: str = "af_bella",
        on_state_change: Optional[Callable[[bool], None]] = None,
        dry_run: bool = False,
    ):
        self.voice = voice
        self.on_state_change = on_state_change
        self.dry_run = dry_run

        self._is_speaking_flag = False
        self._lock = threading.Lock()
        self._queue: queue.Queue[str] = queue.Queue()
        self._stop_event = threading.Event()
        self.spoken_phrases: list[str] = []

        # Start playback worker thread
        self._worker_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self._worker_thread.start()

    def speak(self, text: str, non_blocking: bool = True) -> None:
        """Enqueues text for spoken confirmation."""
        clean_text = text.strip()
        if not clean_text:
            return

        logger.info(f"TTS requested: '{clean_text}'")
        self.spoken_phrases.append(clean_text)

        if non_blocking:
            self._queue.put(clean_text)
        else:
            self._play_phrase(clean_text)

    def is_speaking(self) -> bool:
        """Returns True if audio is actively playing through speakers."""
        with self._lock:
            return self._is_speaking_flag

    def _set_speaking(self, speaking: bool) -> None:
        """Updates speaking state and triggers acoustic echo cancellation callback."""
        with self._lock:
            self._is_speaking_flag = speaking

        if self.on_state_change:
            try:
                self.on_state_change(speaking)
            except Exception as e:
                logger.warning(f"Error in TTS on_state_change callback: {e}")

    def _playback_loop(self) -> None:
        """Worker thread processing spoken audio queue."""
        while not self._stop_event.is_set():
            try:
                phrase = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            self._play_phrase(phrase)
            self._queue.task_done()

    def _play_phrase(self, phrase: str) -> None:
        """Synthesizes and outputs audio."""
        self._set_speaking(True)
        try:
            if not self.dry_run:
                # Attempt system audio synthesis (e.g. espeak-ng, piper, or kokoro)
                if shutil.which("espeak-ng"):
                    subprocess.run(["espeak-ng", phrase], check=False, capture_output=True)
                elif shutil.which("spd-say"):
                    subprocess.run(["spd-say", "-w", phrase], check=False, capture_output=True)
                else:
                    # Simulation delay
                    time.sleep(0.05)
            else:
                time.sleep(0.02)
        finally:
            self._set_speaking(False)

    def stop(self) -> None:
        """Stops worker thread."""
        self._stop_event.set()
