"""Unit tests for LocalVLMClient."""

import io
import json
from unittest.mock import MagicMock, patch
from PIL import Image
import pytest

from handsfree.vision.local_vlm import LocalVLMClient


@pytest.fixture
def sample_image_bytes():
    img = Image.new("RGB", (100, 100), color=(50, 100, 150))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_vlm_is_available():
    client = LocalVLMClient()
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"models": [{"name": "moondream:latest"}]}).encode()
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        assert client.is_available() is True


def test_describe_visual_scene_success(sample_image_bytes):
    client = LocalVLMClient()
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "message": {"content": "A person is on a video call in Discord with server channels visible."}
    }).encode()
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        desc = client.describe_visual_scene(sample_image_bytes)
        assert "Discord" in desc
        assert "video call" in desc


def test_describe_visual_scene_empty_on_error():
    client = LocalVLMClient()
    with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
        assert client.describe_visual_scene(b"dummy") == ""
    assert client.describe_visual_scene(b"") == ""


def test_locate_icon_parsing(sample_image_bytes):
    client = LocalVLMClient()
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({
        "message": {"content": "The coordinates are [500, 250]"}
    }).encode()
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        coords = client.locate_icon(sample_image_bytes, "camera icon")
        assert coords is not None
        assert coords == (50, 25)  # Normalized 500/1000 * 100, 250/1000 * 100
