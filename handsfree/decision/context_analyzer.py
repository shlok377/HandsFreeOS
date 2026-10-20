"""Application activity and session context analyzer."""

import logging
import re
from dataclasses import dataclass
from typing import List, Optional
from handsfree.domain.models import WindowInfo

logger = logging.getLogger(__name__)


@dataclass
class ActivityContext:
    """Structured high-level user activity context."""
    app_name: str
    activity_type: str  # e.g. "video_call", "voice_call", "browsing_files", "coding", "general"
    context_label: str  # e.g. "on a Discord video call", "browsing your Home folder"
    details: str        # e.g. "with server 'DSA'"

    @property
    def is_video_call(self) -> bool:
        return self.activity_type == "video_call"


class AppContextAnalyzer:
    """Infers high-level user activities by fusing window metadata and on-screen cues."""

    def analyze_context(
        self,
        active_window: Optional[WindowInfo],
        open_windows: Optional[List[WindowInfo]] = None,
        screen_ocr: str = "",
    ) -> ActivityContext:
        """Determines the active application and human-understandable activity."""
        if not active_window:
            return ActivityContext(
                app_name="Desktop",
                activity_type="general",
                context_label="viewing your desktop",
                details=""
            )

        title = (active_window.title or "").strip()
        cls = (active_window.class_name or "").lower().strip()
        title_lower = title.lower()
        ocr_lower = (screen_ocr or "").lower()

        # 1. DISCORD DETECTION (Desktop client or Browser tab)
        if "discord" in cls or "discord" in title_lower:
            # Check for call / video cues in title or OCR
            is_call = any(
                token in ocr_lower
                for token in ["disconnect", "voice connected", "rtc connected", "screen share", "video", "camera"]
            ) or bool(re.search(r"\|\s*[\"']?.*[\"']?\s*\|", title))

            # Look for partner / channel name in Discord title e.g. `• Discord | "DSA" | These Two <3 ...`
            parts = [p.strip() for p in title.split("|") if p.strip()]
            channel_info = ""
            if len(parts) >= 2:
                channel_info = parts[1].strip('"\' ')
                if len(parts) >= 3 and "mozilla" not in parts[2].lower():
                    channel_info += f" ({parts[2].strip()})"

            if is_call:
                label = "on a Discord video call" if any(k in ocr_lower for k in ["camera", "video", "stream"]) or "camera" in title_lower else "on a Discord call"
                return ActivityContext(
                    app_name="Discord",
                    activity_type="video_call" if "video" in label else "voice_call",
                    context_label=label,
                    details=f"in {channel_info}" if channel_info else ""
                )
            else:
                return ActivityContext(
                    app_name="Discord",
                    activity_type="chat",
                    context_label="using Discord",
                    details=f"in {channel_info}" if channel_info else ""
                )

        # 2. WEB MEETINGS (Google Meet, Zoom, MS Teams, Jitsi)
        if any(m in title_lower or m in cls for m in ["meet.google.com", "google meet", "meet -", "zoom", "teams", "jitsi"]):
            return ActivityContext(
                app_name="Video Meeting",
                activity_type="video_call",
                context_label="in an online video meeting",
                details=title[:30]
            )

        # 3. FILE MANAGER (Nautilus, Dolphin, Thunar)
        if any(fm in cls for fm in ["nautilus", "dolphin", "thunar", "nemo", "pcmanfm"]) or title_lower in {"home", "files", "downloads", "documents", "projects"}:
            folder_name = title if title and title != "Files" else "Files"
            return ActivityContext(
                app_name="File Manager",
                activity_type="browsing_files",
                context_label=f"browsing your {folder_name} folder",
                details=folder_name
            )

        # 4. CODE EDITOR & IDE
        if any(ed in cls for ed in ["code", "subl", "gedit", "kate", "cursor", "nvim"]) or "visual studio code" in title_lower:
            return ActivityContext(
                app_name="Code Editor",
                activity_type="coding",
                context_label="working in your code editor",
                details=title[:35]
            )

        # 5. TERMINAL
        if any(t in cls for t in ["ghostty", "foot", "kitty", "alacritty", "terminal"]):
            return ActivityContext(
                app_name="Terminal",
                activity_type="terminal",
                context_label="in your terminal",
                details=title[:25]
            )

        # 6. BROWSER WEB BROWSING
        if any(b in cls for b in ["firefox", "chrome", "chromium", "brave", "zen"]):
            clean_page = re.sub(r"—\s*(?:Mozilla Firefox|Google Chrome|Chromium).*$", "", title).strip()
            return ActivityContext(
                app_name="Browser",
                activity_type="web_browsing",
                context_label=f"browsing {clean_page[:35]}",
                details=clean_page
            )

        # Fallback general window
        return ActivityContext(
            app_name=cls or title or "App",
            activity_type="general",
            context_label=f"using {title or cls}",
            details=""
        )
