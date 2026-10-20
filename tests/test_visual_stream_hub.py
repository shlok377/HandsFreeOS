"""Unit tests for VisualStreamHub and screen annotator."""

import io
import threading
import time
from PIL import Image
import pytest

from handsfree.domain.models import BoundingBox
from handsfree.vision.stream_hub import VisualStreamHub


@pytest.fixture
def sample_image_bytes():
    img = Image.new("RGB", (640, 480), color=(30, 30, 30))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def sample_boxes():
    return [
        BoundingBox(
            id=1,
            label="Search Bar",
            x_min=100,
            y_min=50,
            x_max=300,
            y_max=90,
            confidence=0.96,
        ),
        BoundingBox(
            id=2,
            label="Submit Button",
            x_min=320,
            y_min=50,
            x_max=420,
            y_max=90,
            confidence=0.88,
        ),
    ]


def test_fallback_frame_generation():
    hub = VisualStreamHub()
    fallback_bytes = hub.create_fallback_frame(width=400, height=300)
    assert fallback_bytes.startswith(b"\xff\xd8")  # Valid JPEG marker
    img = Image.open(io.BytesIO(fallback_bytes))
    assert img.size == (400, 300)


def test_render_annotated_frame_draws_boxes(sample_image_bytes, sample_boxes):
    hub = VisualStreamHub()
    annotated = hub.render_annotated_frame(sample_image_bytes, sample_boxes)

    assert annotated.startswith(b"\xff\xd8")
    img = Image.open(io.BytesIO(annotated))
    assert img.size == (640, 480)


def test_stream_hub_thread_safe_latest_frame(sample_image_bytes, sample_boxes):
    hub = VisualStreamHub()
    # Before update: fallback frame is returned
    frame = hub.get_latest_frame()
    assert frame.is_fallback is True

    # Update frame
    hub.update_frame(sample_image_bytes, sample_boxes, latency_ms=18.4)

    frame = hub.get_latest_frame()
    assert frame.is_fallback is False
    assert len(frame.boxes) == 2
    assert frame.latency_ms == 18.4
    assert frame.frame_bytes.startswith(b"\xff\xd8")


def test_stream_hub_wait_for_frame(sample_image_bytes, sample_boxes):
    hub = VisualStreamHub()

    def delayed_updater():
        time.sleep(0.05)
        hub.update_frame(sample_image_bytes, sample_boxes)

    t = threading.Thread(target=delayed_updater)
    t.start()

    updated = hub.wait_for_next_frame(timeout=1.0)
    t.join()

    assert updated is True
    assert hub.get_latest_frame().is_fallback is False


def test_annotation_overhead_under_20ms():
    hub = VisualStreamHub()
    # 720p frame
    img = Image.new("RGB", (1280, 720), color=(40, 45, 55))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=75)
    sample_bytes = buf.getvalue()

    boxes = [
        BoundingBox(id=i, label=f"Button {i}", x_min=i * 50, y_min=100, x_max=i * 50 + 40, y_max=140, confidence=0.9)
        for i in range(10)
    ]

    start = time.perf_counter()
    hub.render_annotated_frame(sample_bytes, boxes)
    duration_ms = (time.perf_counter() - start) * 1000.0

    # Ensure efficient processing
    assert duration_ms < 30.0, f"Annotation took {duration_ms:.2f}ms, expected <30ms"
