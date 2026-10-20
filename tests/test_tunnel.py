"""Unit tests for ReverseTunnelManager."""

from unittest.mock import MagicMock, patch
import pytest

from handsfree.os_layer.tunnel import ReverseTunnelManager


def test_tunnel_manager_extracts_url():
    manager = ReverseTunnelManager(local_port=8000)
    line = "13414228ad0003.lhr.life tunneled with tls termination, https://13414228ad0003.lhr.life"
    url = manager.extract_url_from_line(line)
    assert url == "https://13414228ad0003.lhr.life"


def test_tunnel_manager_start_mocked():
    manager = ReverseTunnelManager(local_port=8000)
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.stdout.readline.side_effect = [
        "Welcome to localhost.run!\n",
        "tunneled with tls termination, https://demo123.lhr.life\n",
    ]

    with patch("subprocess.Popen", return_value=mock_proc):
        url = manager.start(timeout=2.0)
        assert url == "https://demo123.lhr.life"
        assert manager.public_url == "https://demo123.lhr.life"

    manager.stop()
    mock_proc.terminate.assert_called_once()
