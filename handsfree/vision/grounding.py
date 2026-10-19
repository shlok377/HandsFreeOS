"""Two-stage visual grounding coordinator (Jev + YOLO with VLM fallback)."""

import logging
import time
from typing import Optional, Tuple

from handsfree.domain.interfaces import IDecisionEngine
from handsfree.domain.models import BoundingBox
from handsfree.vision.omniparser import OmniParserDetector
from handsfree.vision.vlm_fallback import MultimodalVLMFallback

logger = logging.getLogger(__name__)


class TwoStageGrounder:
    """Coordinates fast local box selection with fallback to multimodal VLM."""

    def __init__(
        self,
        decision_engine: IDecisionEngine,
        detector: Optional[OmniParserDetector] = None,
        vlm_fallback: Optional[MultimodalVLMFallback] = None,
    ):
        self.decision_engine = decision_engine
        self.detector = detector or OmniParserDetector()
        self.vlm_fallback = vlm_fallback or MultimodalVLMFallback()

    def locate_target(
        self, image_bytes: bytes, target_phrase: str
    ) -> Tuple[Optional[Tuple[int, int]], str, float]:
        """Locates on-screen target coordinates.

        Returns:
            Tuple[Optional[Tuple[int, int]], str, float]:
                ((x, y), resolution_tier ["fast_local" | "vlm_fallback"], latency_ms)
        """
        start_time = time.perf_counter()

        # Step 1: Detect interactive elements with YOLO
        boxes = self.detector.detect_elements(image_bytes)

        if boxes:
            # Stage 1: Try fast Jev match (<40ms)
            matched_box = self.decision_engine.select_yolo_box(boxes, target_phrase)
            if matched_box:
                latency = (time.perf_counter() - start_time) * 1000.0
                logger.info(
                    f"Stage 1 (Jev + YOLO) matched '{target_phrase}' to Box {matched_box.id} "
                    f"('{matched_box.label}') at {matched_box.center} in {latency:.1f}ms"
                )
                return matched_box.center, "fast_local", latency

        # Stage 2: Fall back to Multimodal VLM for unlabelled graphics / icons
        logger.info(f"Stage 1 yielded no labeled match; falling back to Multimodal VLM for '{target_phrase}'...")
        vlm_coords = self.vlm_fallback.locate_element_visually(image_bytes, target_phrase)
        latency = (time.perf_counter() - start_time) * 1000.0

        if vlm_coords:
            return vlm_coords, "vlm_fallback", latency

        return None, "none", latency
