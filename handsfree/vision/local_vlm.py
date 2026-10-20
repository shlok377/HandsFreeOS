"""Local Vision-Language Model (VLM) client using Ollama and Moondream."""

import base64
import io
import json
import logging
import re
import urllib.error
import urllib.request
from typing import Optional, Tuple
from PIL import Image

logger = logging.getLogger(__name__)


class LocalVLMClient:
    """Offline multimodal vision-language model client for local visual perception."""

    def __init__(
        self,
        ollama_host: str = "http://127.0.0.1:11434",
        model_name: str = "moondream",
    ):
        self.ollama_host = ollama_host.rstrip("/")
        self.model_name = model_name

    def is_available(self) -> bool:
        """Checks if the configured model is installed and accessible in Ollama."""
        try:
            req = urllib.request.Request(f"{self.ollama_host}/api/tags")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = json.loads(resp.read().decode())
                models = [m.get("name", "").split(":")[0] for m in data.get("models", [])]
                return self.model_name.split(":")[0] in models
        except Exception:
            return False

    def ensure_model_available(self) -> bool:
        """Checks if model is available, triggers non-blocking pull if missing."""
        if self.is_available():
            return True
        try:
            req = urllib.request.Request(
                f"{self.ollama_host}/api/pull",
                data=json.dumps({"name": self.model_name, "stream": False}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                return resp.status == 200
        except Exception as e:
            logger.warning(f"Could not auto-pull model {self.model_name}: {e}")
            return False

    def _prepare_image_base64(self, image_bytes: bytes, max_dim: int = 768) -> Tuple[str, int, int]:
        """Resizes image for fast edge inference and returns (base64_str, orig_w, orig_h)."""
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        orig_w, orig_h = image.size

        # Downscale proportionally if larger than max_dim to ensure <1s inference
        if max(orig_w, orig_h) > max_dim:
            scale = max_dim / max(orig_w, orig_h)
            new_size = (int(orig_w * scale), int(orig_h * scale))
            image = image.resize(new_size, Image.Resampling.BILINEAR)

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)
        b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return b64, orig_w, orig_h

    def describe_visual_scene(self, image_bytes: bytes) -> str:
        """Visually perceives non-text screen elements: people, video calls, streams, photos, UI layout."""
        if not image_bytes:
            return ""

        try:
            b64_img, _, _ = self._prepare_image_base64(image_bytes, max_dim=768)
            prompt = "Describe this image."
            req = urllib.request.Request(
                f"{self.ollama_host}/api/chat",
                data=json.dumps({
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": prompt, "images": [b64_img]}],
                    "stream": False,
                }).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                data = json.loads(resp.read().decode())
                content = data.get("message", {}).get("content", "").strip()
                if content:
                    return content

            # Fallback prompt if empty
            req2 = urllib.request.Request(
                f"{self.ollama_host}/api/chat",
                data=json.dumps({
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": "What do you see in this image?", "images": [b64_img]}],
                    "stream": False,
                }).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req2, timeout=4.0) as resp2:
                data2 = json.loads(resp2.read().decode())
                return data2.get("message", {}).get("content", "").strip()
        except Exception as e:
            logger.debug(f"Local VLM describe_visual_scene error: {e}")
            return ""

    def locate_icon(
        self, image_bytes: bytes, target_description: str
    ) -> Optional[Tuple[int, int]]:
        """Finds normalized (x, y) coordinates for an unlabelled graphical element or icon."""
        if not image_bytes or not target_description:
            return None

        try:
            b64_img, orig_w, orig_h = self._prepare_image_base64(image_bytes, max_dim=1024)
            prompt = (
                f"Identify the center location of '{target_description}' on this screen. "
                "Respond with coordinates in format: [x, y] where x and y are numbers between 0 and 1000."
            )
            req = urllib.request.Request(
                f"{self.ollama_host}/api/chat",
                data=json.dumps({
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": prompt, "images": [b64_img]}],
                    "stream": False,
                }).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = json.loads(resp.read().decode())
                ans = data.get("message", {}).get("content", "")
                m = re.search(r"\[?\s*(\d{1,4})\s*,\s*(\d{1,4})\s*\]?", ans)
                if m:
                    norm_x, norm_y = float(m.group(1)), float(m.group(2))
                    # Scale from 0-1000 normalized to screen pixel resolution
                    pixel_x = int((norm_x / 1000.0) * orig_w)
                    pixel_y = int((norm_y / 1000.0) * orig_h)
                    return pixel_x, pixel_y
        except Exception as e:
            logger.debug(f"Local VLM locate_icon error: {e}")

        return None
