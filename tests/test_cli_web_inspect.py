"""Integration tests for CLI arguments, network discovery, and grounder streaming hook."""

from io import BytesIO
from unittest.mock import MagicMock, patch
from PIL import Image
import pytest

from handsfree.cli import build_parser
from handsfree.decision.jev_engine import JevEngine
from handsfree.domain.models import BoundingBox
from handsfree.vision.grounding import TwoStageGrounder
from handsfree.vision.stream_hub import VisualStreamHub


class DummyDetector:
    def detect_elements(self, image_bytes):
        return [
            BoundingBox(id=1, label="Submit", x_min=50, y_min=50, x_max=150, y_max=100, confidence=0.95)
        ]


def test_cli_parser_web_inspect_arguments():
    parser = build_parser()
    args = parser.parse_args(["run", "--web-inspect", "--inspect-port", "8888", "--inspect-token", "secret99", "--tunnel"])
    assert args.command == "run"
    assert args.web_inspect is True
    assert args.inspect_port == 8888
    assert args.inspect_token == "secret99"
    assert args.tunnel is True


def test_grounder_updates_stream_hub():
    jev = JevEngine()
    detector = DummyDetector()
    hub = VisualStreamHub()

    grounder = TwoStageGrounder(
        decision_engine=jev,
        detector=detector,
        stream_hub=hub
    )

    # Initial frame in hub is fallback
    assert hub.get_latest_frame().is_fallback is True

    # Generate test image
    img = Image.new("RGB", (320, 240), color=(50, 50, 50))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    image_bytes = buf.getvalue()

    coords, tier, latency = grounder.locate_target(image_bytes, "Submit")
    assert coords == (100, 75)

    # Verify stream hub received frame and boxes
    latest = hub.get_latest_frame()
    assert latest.is_fallback is False
    assert len(latest.boxes) == 1
    assert latest.boxes[0].label == "Submit"
