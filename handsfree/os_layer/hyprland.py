"""Hyprland compositor IPC and OS interaction wrapper."""

import json
import logging
import os
import shutil
import subprocess
from typing import List, Optional

from handsfree.domain.interfaces import IOSController
from handsfree.domain.models import WindowInfo

logger = logging.getLogger(__name__)


class HyprlandController(IOSController):
    """Controls Hyprland compositor via `hyprctl` IPC and OS shell primitives."""

    def __init__(self, hyprctl_bin: str = "hyprctl"):
        self.hyprctl_bin = shutil.which(hyprctl_bin) or hyprctl_bin
        self.browser_classes = {
            "google-chrome", "chromium", "firefox", "brave-browser",
            "zen-browser", "microsoft-edge", "opera", "vivaldi"
        }

    def _run_hyprctl(self, args: List[str]) -> str:
        """Executes a hyprctl command and returns stdout."""
        try:
            res = subprocess.run(
                [self.hyprctl_bin] + args,
                capture_output=True,
                text=True,
                check=False
            )
            return res.stdout.strip()
        except Exception as e:
            logger.warning(f"Error running hyprctl {args}: {e}")
            return ""

    def get_open_windows(self) -> List[WindowInfo]:
        """Queries `hyprctl clients -j` to get active windows."""
        output = self._run_hyprctl(["clients", "-j"])
        if not output:
            return []

        try:
            raw_clients = json.loads(output)
            windows: List[WindowInfo] = []
            for client in raw_clients:
                # hyprctl client schema
                addr = client.get("address", "")
                title = client.get("title", "")
                cls_name = client.get("class", "")
                ws = client.get("workspace", {}).get("id", 1) if isinstance(client.get("workspace"), dict) else client.get("workspace", 1)
                is_focused = bool(client.get("focusHistoryID", 1) == 0)

                windows.append(
                    WindowInfo(
                        address=addr,
                        title=title,
                        class_name=cls_name,
                        workspace_id=int(ws) if str(ws).isdigit() else 1,
                        is_focused=is_focused
                    )
                )
            return windows
        except Exception as e:
            logger.warning(f"Failed to parse hyprctl clients JSON: {e}")
            return []

    def get_active_window(self) -> Optional[WindowInfo]:
        """Queries `hyprctl activewindow -j`."""
        output = self._run_hyprctl(["activewindow", "-j"])
        if not output:
            return None

        try:
            data = json.loads(output)
            if not data or not data.get("address"):
                return None
            return WindowInfo(
                address=data.get("address", ""),
                title=data.get("title", ""),
                class_name=data.get("class", ""),
                workspace_id=data.get("workspace", {}).get("id", 1) if isinstance(data.get("workspace"), dict) else 1,
                is_focused=True
            )
        except Exception as e:
            logger.warning(f"Failed to parse activewindow JSON: {e}")
            return None

    def focus_window(self, address_or_class: str) -> bool:
        """Focuses target window via `hyprctl dispatch focuswindow`."""
        if address_or_class.startswith("0x"):
            # Focus by address
            out = self._run_hyprctl(["dispatch", "focuswindow", f"address:{address_or_class}"])
        else:
            out = self._run_hyprctl(["dispatch", "focuswindow", address_or_class])
        return "ok" in out.lower() or out == ""

    def close_window(self, address_or_class: str = "") -> bool:
        """Closes target window via `hyprctl dispatch closewindow` or `killactive`."""
        if address_or_class.startswith("0x"):
            out = self._run_hyprctl(["dispatch", "closewindow", f"address:{address_or_class}"])
        elif address_or_class:
            out = self._run_hyprctl(["dispatch", "closewindow", address_or_class])
        else:
            out = self._run_hyprctl(["dispatch", "killactive"])
        return "ok" in out.lower() or out == ""

    def launch_app(self, command: str) -> bool:
        """Launches application via `hyprctl dispatch exec` or subprocess."""
        # Clean command
        cmd = command.strip()
        try:
            # First try hyprctl dispatch exec
            out = self._run_hyprctl(["dispatch", "exec", cmd])
            if "ok" in out.lower() or out == "":
                return True
        except Exception:
            pass

        # Fallback to background subprocess
        try:
            subprocess.Popen(cmd, shell=True)
            return True
        except Exception as e:
            logger.error(f"Failed to launch app '{cmd}': {e}")
            return False

    def open_url(self, url: str) -> bool:
        """Opens URL or focuses existing tab/window matching target."""
        clean_url = url.strip()
        if not clean_url.startswith("http://") and not clean_url.startswith("https://"):
            clean_url = "https://" + clean_url

        # Check existing windows for match (e.g. WhatsApp from web.whatsapp.com)
        domain = clean_url.split("//")[-1].split("/")[0].replace("www.", "")
        domain_tokens = [p.lower() for p in domain.split(".") if p.lower() not in {"web", "app", "m", "mail", "com", "net", "org", "io", "ai", "co", "uk", "in"}]

        open_windows = self.get_open_windows()
        for win in open_windows:
            title_lower = win.title.lower()
            class_lower = win.class_name.lower()
            for token in domain_tokens:
                if len(token) >= 3 and (token in title_lower or token in class_lower):
                    logger.info(f"Smart focus found existing window for '{token}': {win.title}")
                    return self.focus_window(win.address)

        # No existing window -> launch fresh URL via xdg-open
        try:
            subprocess.Popen(["xdg-open", clean_url])
            return True
        except Exception as e:
            logger.error(f"Failed to open URL '{clean_url}': {e}")
            return False

    def create_file(self, filepath: str, content: str = "") -> bool:
        """Creates or writes text to a file directly via filesystem."""
        expanded_path = os.path.expanduser(filepath)
        try:
            parent_dir = os.path.dirname(expanded_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)

            with open(expanded_path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except Exception as e:
            logger.error(f"Failed to create file '{expanded_path}': {e}")
            return False

    def is_browser_window(self, window: Optional[WindowInfo]) -> bool:
        """Checks if a window belongs to a web browser."""
        if not window:
            return False
        return window.class_name.lower() in self.browser_classes
