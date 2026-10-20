"""Network discovery helper for resolving local LAN and Tailscale mesh IP addresses."""

import logging
import shutil
import socket
import subprocess
import urllib.parse
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class NetworkDiscovery:
    """Detects available network interfaces for mobile tunnel/streaming connections."""

    def __init__(self, tailscale_bin: str = "tailscale"):
        self.tailscale_bin = tailscale_bin

    def get_local_ip(self) -> str:
        """Determines host's primary LAN IPv4 address."""
        try:
            # Connect UDP socket to probe routing table without transmitting
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"

    def get_tailscale_ip(self) -> Optional[str]:
        """Resolves active Tailscale IPv4 address if Tailscale is running."""
        bin_path = shutil.which(self.tailscale_bin) or self.tailscale_bin
        try:
            res = subprocess.run(
                [bin_path, "ip", "-4"],
                capture_output=True,
                text=True,
                timeout=1.5,
                check=True
            )
            lines = res.stdout.strip().splitlines()
            return lines[0].strip() if lines else None
        except Exception as e:
            logger.debug(f"Tailscale not active or query failed: {e}")
            return None

    def get_connection_endpoints(self, port: int = 8000, auth_token: Optional[str] = None) -> Dict[str, str]:
        """Builds reachable URLs for LAN, Tailscale, and localhost."""
        query = f"?token={urllib.parse.quote(auth_token)}" if auth_token else ""
        endpoints = {
            "local": f"http://127.0.0.1:{port}/{query}"
        }

        lan_ip = self.get_local_ip()
        if lan_ip:
            endpoints["lan"] = f"http://{lan_ip}:{port}/{query}"

        ts_ip = self.get_tailscale_ip()
        if ts_ip:
            endpoints["tailscale"] = f"http://{ts_ip}:{port}/{query}"

        return endpoints
