"""Multimodal Vision-Language Model fallback for unlabelled graphical icons."""

import logging
import os
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class MultimodalVLMFallback:
    """Invokes Gemini 2.5 Flash or Claude Computer Use for visual coordinate grounding."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")

    def locate_element_visually(
        self, image_bytes: bytes, target_description: str
    ) -> Optional[Tuple[int, int]]:
        """Sends screenshot to VLM to visually predict (x, y) coordinates for target.

        Used strictly when YOLO text labels do not match or the target is an
        unlabelled graphical icon (e.g. camera, gear, emoji, avatar).
        """
        if not self.api_key or not image_bytes:
            logger.info("VLM fallback skipped (no API key or empty image buffer).")
            return None

        try:
            # Integration with google-genai SDK
            from google import genai  # type: ignore
            client = genai.Client(api_key=self.api_key)
            prompt = (
                f"You are a GUI grounding assistant. Look at this screenshot and identify the "
                f"exact center (x, y) coordinates of the element matching: '{target_description}'. "
                f"Respond ONLY in format: x, y"
            )
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    genai.types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                    prompt,
                ],
            )
            text = response.text.strip()
            parts = text.split(",")
            if len(parts) == 2:
                return int(parts[0].strip()), int(parts[1].strip())
        except Exception as e:
            logger.warning(f"VLM visual fallback error: {e}")

        return None
