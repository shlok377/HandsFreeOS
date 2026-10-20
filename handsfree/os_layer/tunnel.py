"""Automated zero-config reverse SSH tunnel for phone access over public internet/mobile data."""

import logging
import re
import subprocess
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


class ReverseTunnelManager:
    """Spins up a lightweight, zero-dependency reverse SSH tunnel to expose port 8000."""

    URL_PATTERN = re.compile(r"https://[a-zA-Z0-9.-]+\.lhr\.life")

    def __init__(self, local_port: int = 8000):
        self.local_port = local_port
        self.proc: Optional[subprocess.Popen] = None
        self.public_url: Optional[str] = None
        self._reader_thread: Optional[threading.Thread] = None

    def extract_url_from_line(self, line: str) -> Optional[str]:
        """Scans output stream line for public HTTPS tunnel domain."""
        match = self.URL_PATTERN.search(line)
        if match:
            return match.group(0)
        return None

    def start(self, timeout: float = 8.0) -> Optional[str]:
        """Spins up background SSH tunnel and waits for allocated public URL."""
        cmd = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ServerAliveInterval=30",
            "-R", f"80:localhost:{self.local_port}",
            "nokey@localhost.run",
        ]

        try:
            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except Exception as e:
            logger.warning(f"Failed to launch SSH tunnel: {e}")
            return None

        # Read lines looking for the URL within timeout
        start_t = time.time()
        while time.time() - start_t < timeout:
            if self.proc.poll() is not None:
                break
            line = self.proc.stdout.readline() if self.proc.stdout else ""
            if not line:
                time.sleep(0.1)
                continue
            url = self.extract_url_from_line(line)
            if url:
                self.public_url = url
                logger.info(f"SSH Reverse Tunnel active: {self.public_url}")
                break

        return self.public_url

    def stop(self) -> None:
        """Terminates the running tunnel process."""
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=1.0)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None
            self.public_url = None
