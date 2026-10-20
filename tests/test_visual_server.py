"""Unit tests for VisualStreamServer and mobile inspector."""

import json
import urllib.request
import urllib.error
import pytest

from handsfree.domain.models import BoundingBox
from handsfree.vision.stream_hub import VisualStreamHub
from handsfree.ui.visual_server import VisualStreamServer


@pytest.fixture
def running_server():
    hub = VisualStreamHub()
    # Populate a sample frame
    boxes = [
        BoundingBox(id=1, label="Search", x_min=10, y_min=20, x_max=100, y_max=60, confidence=0.92)
    ]
    hub.update_frame(hub.create_fallback_frame(320, 240), boxes, latency_ms=14.5)

    server = VisualStreamServer(hub=hub, host="127.0.0.1", port=0, auth_token=None)
    server.start()
    yield server
    server.stop()


def test_mobile_inspector_html_page(running_server):
    url = f"http://127.0.0.1:{running_server.port}/"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=2.0) as resp:
        assert resp.status == 200
        content = resp.read().decode("utf-8")
        assert "viewport" in content
        assert "HandsFreeOS" in content
        assert "/stream" in content


def test_api_status_and_boxes(running_server):
    # Test /api/status
    status_url = f"http://127.0.0.1:{running_server.port}/api/status"
    with urllib.request.urlopen(status_url, timeout=2.0) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "online"
        assert data["box_count"] == 1
        assert data["latency_ms"] == 14.5

    # Test /api/boxes
    boxes_url = f"http://127.0.0.1:{running_server.port}/api/boxes"
    with urllib.request.urlopen(boxes_url, timeout=2.0) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert len(data) == 1
        assert data[0]["label"] == "Search"
        assert data[0]["id"] == 1


def test_auth_token_protection():
    hub = VisualStreamHub()
    server = VisualStreamServer(hub=hub, host="127.0.0.1", port=0, auth_token="my-token-123")
    server.start()
    try:
        # Request without token should fail with 401
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"http://127.0.0.1:{server.port}/api/status", timeout=2.0)
        assert exc_info.value.code == 401

        # Request with valid query parameter token succeeds
        req = f"http://127.0.0.1:{server.port}/api/status?token=my-token-123"
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            assert resp.status == 200
    finally:
        server.stop()


def test_mjpeg_stream_header(running_server):
    stream_url = f"http://127.0.0.1:{running_server.port}/stream"
    with urllib.request.urlopen(stream_url, timeout=2.0) as resp:
        content_type = resp.headers.get("Content-Type", "")
        assert "multipart/x-mixed-replace" in content_type
        # Read the first chunk
        chunk = resp.read(256)
        assert b"--frame" in chunk
        assert b"image/jpeg" in chunk
