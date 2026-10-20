"""Unit tests for NetworkDiscovery and endpoint resolution."""

import socket
from unittest.mock import patch, MagicMock
import pytest

from handsfree.os_layer.network_discovery import NetworkDiscovery


def test_get_local_ip_returns_valid_ipv4():
    discovery = NetworkDiscovery()
    ip = discovery.get_local_ip()
    assert ip is not None
    # Verify standard dotted quad format
    parts = ip.split(".")
    assert len(parts) == 4
    for p in parts:
        assert 0 <= int(p) <= 255


def test_get_tailscale_ip_when_present():
    discovery = NetworkDiscovery()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="100.85.12.34\n")
        ts_ip = discovery.get_tailscale_ip()
        assert ts_ip == "100.85.12.34"


def test_get_tailscale_ip_when_absent():
    discovery = NetworkDiscovery()
    with patch("subprocess.run", side_effect=FileNotFoundError):
        ts_ip = discovery.get_tailscale_ip()
        assert ts_ip is None


def test_get_connection_endpoints():
    discovery = NetworkDiscovery()
    with patch.object(discovery, "get_local_ip", return_value="192.168.1.100"), \
         patch.object(discovery, "get_tailscale_ip", return_value="100.64.0.5"):
        endpoints = discovery.get_connection_endpoints(port=8000, auth_token="abc")
        assert "http://192.168.1.100:8000/?token=abc" == endpoints["lan"]
        assert "http://100.64.0.5:8000/?token=abc" == endpoints["tailscale"]
        assert "http://127.0.0.1:8000/?token=abc" == endpoints["local"]
