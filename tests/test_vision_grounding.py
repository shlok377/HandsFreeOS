"""Tests for two-stage visual grounding with YOLO, Jev, and VLM fallback."""

import pytest
from handsfree.decision.jev_engine import JevEngine
from handsfree.domain.models import BoundingBox
from handsfree.vision.omniparser import OmniParserDetector
from handsfree.vision.vlm_fallback import MultimodalVLMFallback
from handsfree.vision.grounding import TwoStageGrounder


def test_stage_1_fast_local_grounding(monkeypatch):
    """Verifies that labeled text elements are resolved locally via Jev in Stage 1."""
    jev = JevEngine()
    detector = OmniParserDetector()
    vlm = MultimodalVLMFallback()

    mock_boxes = [
        BoundingBox(id=1, label="Search or start new chat", x_min=100, y_min=50, x_max=300, y_max=90),
        BoundingBox(id=2, label="Settings", x_min=320, y_min=50, x_max=360, y_max=90),
    ]

    monkeypatch.setattr(detector, "detect_elements", lambda img: mock_boxes)

    # Spy on VLM to ensure it is NOT called when Stage 1 succeeds
    vlm_called = []
    monkeypatch.setattr(vlm, "locate_element_visually", lambda img, q: vlm_called.append(q) or (500, 500))

    grounder = TwoStageGrounder(decision_engine=jev, detector=detector, vlm_fallback=vlm)

    coords, tier, latency = grounder.locate_target(b"fake_image", "search bar")

    assert coords == (200, 70)  # Center of Box 1
    assert tier == "fast_local"
    assert len(vlm_called) == 0, "VLM should not be called when Stage 1 matches"
    assert latency < 50.0


def test_stage_2_vlm_fallback_for_unlabelled_icon(monkeypatch):
    """Verifies fallback to VLM when an icon has no matching text label."""
    jev = JevEngine()
    detector = OmniParserDetector()
    vlm = MultimodalVLMFallback()

    mock_boxes = [
        BoundingBox(id=1, label="Unlabelled Icon", x_min=10, y_min=10, x_max=40, y_max=40, is_icon=True),
    ]

    monkeypatch.setattr(detector, "detect_elements", lambda img: mock_boxes)
    monkeypatch.setattr(vlm, "locate_element_visually", lambda img, q: (450, 600))

    grounder = TwoStageGrounder(decision_engine=jev, detector=detector, vlm_fallback=vlm)

    coords, tier, latency = grounder.locate_target(b"fake_image", "camera icon")

    assert coords == (450, 600)
    assert tier == "vlm_fallback"
