"""System application and web destination discovery service."""

import configparser
import glob
import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class DesktopApp:
    """Metadata representing an installed Linux desktop application."""
    name: str
    exec_cmd: str
    desktop_file: str
    generic_name: str = ""
    comment: str = ""
    categories: List[str] = field(default_factory=list)


class AppDiscoveryService:
    """Scans and indexes installed desktop applications from .desktop files."""

    DEFAULT_SEARCH_PATHS = [
        "/usr/share/applications",
        "/usr/local/share/applications",
        os.path.expanduser("~/.local/share/applications"),
    ]

    def __init__(self, search_paths: Optional[List[str]] = None):
        self.search_paths = search_paths or self.DEFAULT_SEARCH_PATHS
        self._apps: Dict[str, DesktopApp] = {}
        self._name_index: Dict[str, str] = {}
        self._generic_index: Dict[str, str] = {}
        self.refresh()

    def refresh(self) -> None:
        """Scans filesystem and rebuilds application indices."""
        self._apps.clear()
        self._name_index.clear()
        self._generic_index.clear()

        for path in self.search_paths:
            if not os.path.isdir(path):
                continue
            for file_path in glob.glob(os.path.join(path, "*.desktop")):
                self._parse_desktop_file(file_path)

        logger.debug(f"Indexed {len(self._apps)} desktop applications.")

    def _parse_desktop_file(self, file_path: str) -> None:
        """Parses a single .desktop file into DesktopApp."""
        parser = configparser.RawConfigParser(strict=False)
        try:
            parser.read(file_path, encoding="utf-8")
            section = "Desktop Entry"
            if not parser.has_section(section):
                return

            if parser.has_option(section, "NoDisplay") and parser.getboolean(section, "NoDisplay"):
                return
            if parser.has_option(section, "Type") and parser.get(section, "Type").lower() != "application":
                return

            name = parser.get(section, "Name") if parser.has_option(section, "Name") else ""
            exec_raw = parser.get(section, "Exec") if parser.has_option(section, "Exec") else ""
            if not name or not exec_raw:
                return

            # Clean exec field (strip field codes %u, %F, %k etc.)
            clean_exec = re.sub(r"%[a-zA-Z]", "", exec_raw).strip()
            # Split executable binary
            binary = clean_exec.split()[0].strip('"').strip("'")
            if not shutil.which(binary) and not os.path.exists(binary):
                # Only keep executable apps
                return

            generic_name = parser.get(section, "GenericName") if parser.has_option(section, "GenericName") else ""
            comment = parser.get(section, "Comment") if parser.has_option(section, "Comment") else ""
            cat_raw = parser.get(section, "Categories") if parser.has_option(section, "Categories") else ""
            categories = [c.strip() for c in cat_raw.split(";") if c.strip()]

            desktop_id = os.path.basename(file_path)
            app = DesktopApp(
                name=name,
                exec_cmd=binary,
                desktop_file=desktop_id,
                generic_name=generic_name,
                comment=comment,
                categories=categories,
            )

            self._apps[desktop_id] = app
            self._name_index[name.lower()] = binary
            file_base = re.sub(r"\.desktop$", "", desktop_id).lower()
            self._name_index[file_base] = binary

            if generic_name:
                self._generic_index[generic_name.lower()] = binary

        except Exception as e:
            logger.debug(f"Failed parsing desktop file {file_path}: {e}")

    def find_app(self, query: str) -> Optional[str]:
        """Finds executable binary matching application name or generic category."""
        q = query.lower().strip()
        if not q:
            return None

        # 1. Exact match on app name
        if q in self._name_index:
            return self._name_index[q]

        # 2. Exact match on generic name (e.g. "text editor", "web browser", "file manager")
        if q in self._generic_index:
            return self._generic_index[q]

        # 3. Substring matching in names
        for name, binary in self._name_index.items():
            if q == name or q in name or name in q:
                return binary

        # 4. Substring matching in generic names or categories
        for gen_name, binary in self._generic_index.items():
            if q in gen_name or gen_name in q:
                return binary

        # 5. Direct PATH fallback
        bin_path = shutil.which(q)
        if bin_path:
            return q

        return None

    def list_apps(self) -> List[DesktopApp]:
        """Returns list of all indexed applications."""
        return list(self._apps.values())


class WebDestinationResolver:
    """Resolves colloquial web services and URL intents."""

    KNOWN_SERVICES = {
        "youtube": "https://www.youtube.com",
        "whatsapp": "https://web.whatsapp.com",
        "webwhatsapp": "https://web.whatsapp.com",
        "web whatsapp": "https://web.whatsapp.com",
        "reddit": "https://www.reddit.com",
        "discord": "https://discord.com/app",
        "github": "https://github.com",
        "twitter": "https://twitter.com",
        "x": "https://x.com",
        "google": "https://www.google.com",
        "gmail": "https://mail.google.com",
        "chatgpt": "https://chatgpt.com",
        "claude": "https://claude.ai",
        "spotify": "https://open.spotify.com",
        "twitch": "https://www.twitch.tv",
        "netflix": "https://www.netflix.com",
        "wikipedia": "https://www.wikipedia.org",
    }

    FLUFF_SUFFIXES = [
        r"\s+in\s+(?:my\s+|the\s+)?browser$",
        r"\s+from\s+(?:my\s+|the\s+)?browser$",
        r"\s+on\s+(?:the\s+)?web$",
        r"\s+online$",
        r"\s+website$",
        r"\s+web$",
        r"\s+page$",
        r"\s+app$",
        r"\s+application$",
    ]

    def __init__(self, app_discovery: Optional[AppDiscoveryService] = None):
        self.app_discovery = app_discovery or AppDiscoveryService()

    def clean_target(self, target: str) -> str:
        """Strips filler phrasing like 'in my browser' or 'app'."""
        cleaned = target.strip()
        for suffix_pat in self.FLUFF_SUFFIXES:
            cleaned = re.sub(suffix_pat, "", cleaned, flags=re.IGNORECASE).strip()
        return cleaned

    def resolve(self, target: str) -> Tuple[str, str]:
        """Resolves target string to ('url', destination) or ('app', binary) or ('unknown', target)."""
        raw = target.strip()
        cleaned = self.clean_target(raw)
        has_browser_fluff = cleaned.lower() != raw.lower() and re.search(r"\bbrowser\b|\bweb\b|\bonline\b", raw, re.I)

        # 1. Direct URL check
        if (
            cleaned.startswith("http://")
            or cleaned.startswith("https://")
            or cleaned.startswith("www.")
            or (re.match(r"^[\w\-]+(\.[\w\-]+)+(?:/[^\s]*)?$", cleaned) is not None and " " not in cleaned)
        ):
            url = cleaned if cleaned.startswith("http") else f"https://{cleaned}"
            return ("url", url)

        # 2. Known web service match
        cleaned_lower = cleaned.lower()
        if cleaned_lower in self.KNOWN_SERVICES:
            return ("url", self.KNOWN_SERVICES[cleaned_lower])

        # 3. If explicit browser context requested ("Open X in my browser")
        if has_browser_fluff:
            return ("url", f"https://www.google.com/search?q={cleaned}")

        # 4. Desktop app discovery
        app_bin = self.app_discovery.find_app(cleaned)
        if app_bin:
            return ("app", app_bin)

        return ("unknown", cleaned)
