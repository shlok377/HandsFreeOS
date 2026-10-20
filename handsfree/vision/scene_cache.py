"""Smart background scene caching with dynamic frame-diff throttling."""

import io
import logging
import threading
import time
from typing import Optional, Tuple
import numpy as np
from PIL import Image

from handsfree.vision.local_vlm import LocalVLMClient

logger = logging.getLogger(__name__)


class SmartSceneCache:
    """Maintains a warm, thread-safe cache of the visual scene without burning CPU."""

    def __init__(
        self,
        vlm_client: Optional[LocalVLMClient] = None,
        min_interval: float = 2.0,
        max_idle_interval: float = 5.0,
        diff_threshold: float = 6.0,
    ):
        self.vlm = vlm_client or LocalVLMClient()
        self.min_interval = min_interval
        self.max_idle_interval = max_idle_interval
        self.diff_threshold = diff_threshold

        self._lock = threading.Lock()
        self._latest_summary: str = ""
        self._last_updated: float = 0.0
        self._last_frame_bytes: Optional[bytes] = None
        self._last_downsampled: Optional[np.ndarray] = None

        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

    def _compute_frame_diff(self, img_bytes: bytes) -> Tuple[float, np.ndarray]:
        """Downsamples image to 64x64 grayscale and computes mean absolute pixel difference."""
        try:
            img = Image.open(io.BytesIO(img_bytes)).convert("L").resize((64, 64), Image.Resampling.BILINEAR)
            arr = np.asarray(img, dtype=np.float32)
            if self._last_downsampled is None:
                return 100.0, arr
            diff = float(np.mean(np.abs(arr - self._last_downsampled)))
            return diff, arr
        except Exception as e:
            logger.debug(f"Frame diff error: {e}")
            return 100.0, np.zeros((64, 64), dtype=np.float32)

    def update_frame(self, frame_bytes: Optional[bytes]) -> bool:
        """Evaluates whether current frame warrants a VLM update. Returns True if updated."""
        if not frame_bytes:
            return False

        diff, downsampled = self._compute_frame_diff(frame_bytes)
        now = time.time()

        # Update if frame changed significantly or if cache is stale (>10s)
        is_stale = (now - self._last_updated) > 10.0
        has_changed = diff >= self.diff_threshold

        if has_changed or is_stale or not self._latest_summary:
            summary = self.vlm.describe_visual_scene(frame_bytes)
            if summary:
                with self._lock:
                    self._latest_summary = summary
                    self._last_updated = now
                    self._last_downsampled = downsampled
                    self._last_frame_bytes = frame_bytes
                logger.debug(f"Scene cache updated (diff={diff:.1f}): {summary[:40]}...")
                return True

        with self._lock:
            self._last_downsampled = downsampled
            self._last_frame_bytes = frame_bytes
        return False

    def get_latest_visual_summary(self) -> str:
        """Returns the most recent cached visual scene description in <1ms."""
        with self._lock:
            return self._latest_summary

    def force_refresh(self, frame_bytes: bytes) -> str:
        """Forces an immediate on-demand visual scene analysis."""
        summary = self.vlm.describe_visual_scene(frame_bytes)
        if summary:
            with self._lock:
                self._latest_summary = summary
                self._last_updated = time.time()
                self._last_frame_bytes = frame_bytes
        return summary

    def start_background_poller(self, screen_capture_func) -> None:
        """Starts background worker polling screen with smart idle backoff."""
        if self._worker_thread and self._worker_thread.is_alive():
            return

        self._stop_event.clear()

        def _worker_loop():
            current_sleep = self.min_interval
            while not self._stop_event.is_set():
                try:
                    frame = screen_capture_func()
                    if frame:
                        updated = self.update_frame(frame)
                        if updated:
                            # Screen is dynamic (video call / active motion) -> fast poll
                            current_sleep = self.min_interval
                        else:
                            # Screen is static -> backoff sleep to conserve battery/CPU
                            current_sleep = min(self.max_idle_interval, current_sleep + 0.5)
                except Exception as e:
                    logger.debug(f"Scene cache worker error: {e}")

                self._stop_event.wait(timeout=current_sleep)

        self._worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="SmartSceneCacheWorker")
        self._worker_thread.start()
        logger.info("SmartSceneCache background poller started.")

    def stop(self) -> None:
        """Stops background worker thread."""
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
            logger.info("SmartSceneCache background poller stopped.")
