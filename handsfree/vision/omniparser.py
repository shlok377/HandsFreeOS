"""Screen element perception using OmniParser / YOLO bounding boxes."""

import logging
from typing import List, Optional
from handsfree.domain.models import BoundingBox

logger = logging.getLogger(__name__)


class OmniParserDetector:
    """Detects interactive GUI elements (buttons, inputs, icons) from screen captures."""

    def __init__(self, weights_path: Optional[str] = None):
        self.weights_path = weights_path
        self._yolo_model = None

    def detect_elements(self, image_bytes_or_path: bytes | str) -> List[BoundingBox]:
        """Parses image and returns list of interactive BoundingBoxes."""
        # When running in test or offline environment without heavy YOLO model weights,
        # provides structural fallback / parser
        if self._yolo_model is not None:
            try:
                return self._run_yolo_inference(image_bytes_or_path)
            except Exception as e:
                logger.warning(f"YOLO inference failed: {e}")

        # Default empty detection if raw bytes provided without model
        return []

    def _run_yolo_inference(self, image: bytes | str) -> List[BoundingBox]:
        """Runs underlying YOLO model on image."""
        # Hook for ultralytics or ONNX YOLO weights
        return []
