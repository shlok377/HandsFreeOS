"""Unit tests for SmartSceneCache."""

import io
import time
from unittest.mock import MagicMock
from PIL import Image
import pytest

from handsfree.vision.scene_cache import SmartSceneCache


def _make_image_bytes(color):
    img = Image.new("RGB", (64, 64), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_frame_diff_computation():
    mock_vlm = MagicMock()
    cache = SmartSceneCache(vlm_client=mock_vlm)

    img_black = _make_image_bytes((0, 0, 0))
    img_white = _make_image_bytes((255, 255, 255))

    # First frame always returns 100.0 diff
    diff1, _ = cache._compute_frame_diff(img_black)
    assert diff1 == 100.0

    # Store first frame downsampled
    cache.update_frame(img_black)

    # Identical frame diff should be near 0
    diff_same, _ = cache._compute_frame_diff(img_black)
    assert diff_same < 1.0

    # Opposite frame diff should be large (> 200)
    diff_diff, _ = cache._compute_frame_diff(img_white)
    assert diff_diff > 200.0


def test_update_frame_throttling():
    mock_vlm = MagicMock()
    mock_vlm.describe_visual_scene.return_value = "Discord video call with person"
    cache = SmartSceneCache(vlm_client=mock_vlm, diff_threshold=10.0)

    img1 = _make_image_bytes((10, 10, 10))
    img2 = _make_image_bytes((10, 10, 12))  # Very minor diff (<1.0)
    img3 = _make_image_bytes((200, 200, 200)) # Significant diff (>150.0)

    # First update should call VLM
    updated1 = cache.update_frame(img1)
    assert updated1 is True
    assert cache.get_latest_visual_summary() == "Discord video call with person"
    assert mock_vlm.describe_visual_scene.call_count == 1

    # Second nearly identical frame should NOT call VLM (conserving CPU)
    updated2 = cache.update_frame(img2)
    assert updated2 is False
    assert mock_vlm.describe_visual_scene.call_count == 1

    # Third distinct frame should call VLM
    updated3 = cache.update_frame(img3)
    assert updated3 is True
    assert mock_vlm.describe_visual_scene.call_count == 2


def test_force_refresh():
    mock_vlm = MagicMock()
    mock_vlm.describe_visual_scene.return_value = "Refreshed scene summary"
    cache = SmartSceneCache(vlm_client=mock_vlm)

    res = cache.force_refresh(b"dummy_bytes")
    assert res == "Refreshed scene summary"
    assert cache.get_latest_visual_summary() == "Refreshed scene summary"


def test_background_poller_lifecycle():
    mock_vlm = MagicMock()
    mock_vlm.describe_visual_scene.return_value = "Polled scene"
    cache = SmartSceneCache(vlm_client=mock_vlm, min_interval=0.05, max_idle_interval=0.1)

    frame = _make_image_bytes((50, 50, 50))
    cache.start_background_poller(lambda: frame)
    time.sleep(0.15)
    cache.stop()

    assert cache.get_latest_visual_summary() == "Polled scene"
    assert not cache._worker_thread.is_alive()
