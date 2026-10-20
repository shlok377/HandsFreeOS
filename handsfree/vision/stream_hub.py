"""Decoupled, thread-safe visual snapshot and annotation hub for live streaming."""

import io
import logging
import threading
import time
from typing import List, Optional
from pydantic import BaseModel
from PIL import Image, ImageDraw, ImageFont

from handsfree.domain.models import BoundingBox

logger = logging.getLogger(__name__)


class VisualFrame(BaseModel):
    """Represents an annotated video frame ready for streaming."""
    frame_bytes: bytes
    boxes: List[BoundingBox] = []
    latency_ms: float = 0.0
    timestamp: float = 0.0
    is_fallback: bool = False
    width: int = 1280
    height: int = 720


class VisualStreamHub:
    """Thread-safe broker between screen perception and remote streaming consumers."""

    def __init__(self, default_width: int = 1280, default_height: int = 720, jpeg_quality: int = 75):
        self.default_width = default_width
        self.default_height = default_height
        self.jpeg_quality = jpeg_quality

        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._version = 0

        fallback_bytes = self.create_fallback_frame(
            width=self.default_width,
            height=self.default_height,
            message="HandsFreeOS: Awaiting active screen capture..."
        )
        self._current_frame = VisualFrame(
            frame_bytes=fallback_bytes,
            boxes=[],
            latency_ms=0.0,
            timestamp=time.time(),
            is_fallback=True,
            width=self.default_width,
            height=self.default_height,
        )

    def create_fallback_frame(
        self, width: int = 1280, height: int = 720, message: str = "HandsFreeOS: Screen stream standby"
    ) -> bytes:
        """Generates a clean placeholder frame when screen capture is offline."""
        img = Image.new("RGB", (width, height), color=(18, 22, 28))
        draw = ImageDraw.Draw(img)

        # Center title banner
        card_w, card_h = min(600, width - 40), 120
        x0 = (width - card_w) // 2
        y0 = (height - card_h) // 2
        draw.rounded_rectangle([x0, y0, x0 + card_w, y0 + card_h], radius=10, fill=(30, 36, 48), outline=(60, 72, 96), width=2)

        # Header dot & text
        draw.ellipse([x0 + 20, y0 + 35, x0 + 36, y0 + 51], fill=(0, 200, 120))
        draw.text((x0 + 50, y0 + 35), "HandsFreeOS Visual Inspector", fill=(240, 245, 255))
        draw.text((x0 + 50, y0 + 65), message, fill=(160, 175, 200))

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=self.jpeg_quality)
        return buf.getvalue()

    def render_annotated_frame(self, image_bytes: bytes, boxes: List[BoundingBox]) -> bytes:
        """Overlays bounding box rectangles, labels, and confidence tags on image."""
        if not image_bytes:
            return self.create_fallback_frame(self.default_width, self.default_height, "No image buffer received")

        try:
            img = Image.open(io.BytesIO(image_bytes))
            if img.mode != "RGB":
                img = img.convert("RGB")
        except Exception as e:
            logger.warning(f"Failed to decode image bytes: {e}")
            return self.create_fallback_frame(self.default_width, self.default_height, f"Image decode error: {e}")

        draw = ImageDraw.Draw(img)

        # Box colors: Emerald green for interactive, Cyan for inputs, Orange for icons
        for b in boxes:
            color = (255, 140, 0) if b.is_icon else (0, 230, 130)
            text_bg = (10, 20, 25)

            # Draw outer rectangle
            draw.rectangle([b.x_min, b.y_min, b.x_max, b.y_max], outline=color, width=2)

            # Format label
            label_text = f"#{b.id} {b.label}"
            if b.confidence < 1.0:
                label_text += f" ({int(b.confidence * 100)}%)"

            # Tag dimensions
            tag_h = 18
            tag_w = max(40, len(label_text) * 7 + 8)
            tag_y0 = max(0, b.y_min - tag_h)
            tag_y1 = tag_y0 + tag_h

            # Label banner
            draw.rectangle([b.x_min, tag_y0, b.x_min + tag_w, tag_y1], fill=text_bg, outline=color, width=1)
            draw.text((b.x_min + 4, tag_y0 + 2), label_text, fill=(255, 255, 255))

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=self.jpeg_quality)
        return buf.getvalue()

    def update_frame(
        self, image_bytes: bytes, boxes: List[BoundingBox], latency_ms: float = 0.0
    ) -> None:
        """Processes and stores a newly detected screen frame."""
        annotated_bytes = self.render_annotated_frame(image_bytes, boxes)

        # Determine dimensions from decoded image if possible
        try:
            with Image.open(io.BytesIO(annotated_bytes)) as img:
                w, h = img.size
        except Exception:
            w, h = self.default_width, self.default_height

        with self._cond:
            self._version += 1
            self._current_frame = VisualFrame(
                frame_bytes=annotated_bytes,
                boxes=boxes,
                latency_ms=latency_ms,
                timestamp=time.time(),
                is_fallback=False,
                width=w,
                height=h,
            )
            self._cond.notify_all()

    def get_latest_frame(self) -> VisualFrame:
        """Returns the most recent annotated frame snapshot."""
        with self._lock:
            return self._current_frame

    def wait_for_next_frame(self, timeout: Optional[float] = None) -> bool:
        """Blocks until a newer frame arrives or timeout expires."""
        with self._cond:
            initial_version = self._version
            return self._cond.wait_for(lambda: self._version > initial_version, timeout=timeout)
