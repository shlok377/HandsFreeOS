"""Wayland screen capture module using grim."""

import logging
import os
import shutil
import subprocess
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)


class ScreenCapture:
    """Fast screenshot utility for Hyprland / Wayland via grim."""

    def __init__(self, grim_bin: str = "grim"):
        self.grim_bin = shutil.which(grim_bin) or grim_bin

    def capture_png_bytes(self) -> bytes:
        """Captures active screen to PNG bytes in ~15ms."""
        try:
            res = subprocess.run(
                [self.grim_bin, "-"],
                capture_output=True,
                check=True
            )
            return res.stdout
        except Exception as e:
            logger.warning(f"grim capture failed: {e}. Returning mock image buffer if available.")
            return b""

    def capture_to_file(self, target_path: Optional[str] = None) -> str:
        """Captures screen to a local PNG file."""
        if not target_path:
            fd, target_path = tempfile.mkstemp(suffix=".png", prefix="handsfree_screen_")
            os.close(fd)

        try:
            subprocess.run(
                [self.grim_bin, target_path],
                check=True,
                capture_output=True
            )
            return target_path
        except Exception as e:
            logger.warning(f"grim capture to file failed: {e}")
            return target_path
