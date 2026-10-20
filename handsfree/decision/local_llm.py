"""Local LLM Reasoner: Offline intelligence using Qwen2.5 via Ollama."""

import json
import logging
import os
import shutil
import subprocess
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

from handsfree.domain.models import WindowInfo

logger = logging.getLogger(__name__)


class LocalLLMReasoner:
    """Offline System-2 semantic reasoning engine powered by local Qwen2.5 via Ollama."""

    def __init__(
        self,
        model_name: str = "qwen2.5:1.5b",
        ollama_host: str = "http://127.0.0.1:11434",
    ):
        self.model_name = model_name
        self.ollama_host = ollama_host
        self._ensure_ollama_server()

    def _ensure_ollama_server(self) -> bool:
        """Verifies local Ollama server is running, or launches it if available."""
        try:
            req = urllib.request.Request(f"{self.ollama_host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass

        # Attempt to spawn background server if ollama binary is installed
        ollama_bin = shutil.which("ollama")
        if ollama_bin:
            try:
                logger.info("Spawning local 'ollama serve' background daemon...")
                subprocess.Popen(
                    [ollama_bin, "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                time.sleep(1.5)
                return True
            except Exception as e:
                logger.warning(f"Could not auto-start ollama serve: {e}")
        return False

    def is_available(self) -> bool:
        """Checks if local Ollama model is accessible."""
        try:
            req = urllib.request.Request(f"{self.ollama_host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=0.8) as resp:
                return resp.status == 200
        except Exception:
            return False

    def reason_intent(
        self,
        command: str,
        active_window: Optional[WindowInfo] = None,
        open_windows: Optional[List[WindowInfo]] = None,
        discovered_apps: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Classifies arbitrary natural speech into structured OS actions using Qwen."""
        win_title = active_window.title if active_window else "None"
        win_cls = active_window.class_name if active_window else "None"
        other_windows = (
            ", ".join([f"'{w.title}' ({w.class_name})" for w in open_windows[:6]])
            if open_windows
            else "None"
        )
        apps_summary = (
            ", ".join(discovered_apps[:15])
            if discovered_apps
            else "Dolphin, Ghostty, Code, Firefox, Discord, Spotify, Gedit"
        )

        prompt = (
            f"You are Bit, an offline autonomous AI assistant controlling a Linux desktop (Hyprland).\n"
            f"Given the user's oral command and active desktop window, choose the best action.\n"
            f"Return ONLY a JSON object in this exact schema:\n"
            f'{{\n'
            f'  "intent": "hotkey" | "launch_app" | "open_url" | "web_search" | "close_window" | "shutdown" | "answer_user" | "noop",\n'
            f'  "target": "<keys list e.g. [\\"ctrl\\", \\"t\\"] or app name or url or answer string>",\n'
            f'  "speech": "<concise verbal response to speak to user>"\n'
            f'}}\n\n'
            f"Examples:\n"
            f"- 'open new tab in my browser' -> {{\"intent\": \"hotkey\", \"target\": [\"ctrl\", \"t\"], \"speech\": \"Opening a new tab\"}}\n"
            f"- 'close this tab' -> {{\"intent\": \"hotkey\", \"target\": [\"ctrl\", \"w\"], \"speech\": \"Closing tab\"}}\n"
            f"- 'close that discord app' or 'close this discord window' -> {{\"intent\": \"close_window\", \"target\": \"discord\", \"speech\": \"Closing Discord\"}}\n"
            f"- 'open youtube in my browser' -> {{\"intent\": \"open_url\", \"target\": \"https://www.youtube.com\", \"speech\": \"Opening YouTube\"}}\n"
            f"- 'close yourselves' or 'bye bye' or 'quit, quit' or 'exit' -> {{\"intent\": \"shutdown\", \"target\": \"exit\", \"speech\": \"Goodbye! Shutting down Bit.\"}}\n"
            f"- 'how many apps do I have open?' -> {{\"intent\": \"answer_user\", \"target\": \"\", \"speech\": \"You have 2 apps open.\"}}\n"
            f"- 'open dolphin' -> {{\"intent\": \"launch_app\", \"target\": \"dolphin\", \"speech\": \"Opening Dolphin\"}}\n\n"
            f"Context:\n"
            f"- Active Window: '{win_title}' ({win_cls})\n"
            f"- Open Windows: {other_windows}\n"
            f"- Installed Apps: {apps_summary}\n\n"
            f"User command: '{command}'\n"
            f"JSON:"
        )

        try:
            req = urllib.request.Request(
                f"{self.ollama_host}/api/generate",
                data=json.dumps({
                    "model": self.model_name,
                    "prompt": prompt,
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": 0.1, "num_predict": 100},
                }).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = json.loads(resp.read().decode())
                raw_text = data.get("response", "").strip()
                parsed = json.loads(raw_text)
                parsed["raw_response"] = raw_text

                # Build concise single-line summary for dashboard
                intent = parsed.get("intent", "noop")
                target = parsed.get("target", "")
                speech = parsed.get("speech", "")
                if intent == "answer_user":
                    parsed["formatted_summary"] = f'answer_user: "{speech[:35]}"'
                elif intent == "close_window":
                    parsed["formatted_summary"] = f"close_window: {target}"
                elif intent == "open_url":
                    parsed["formatted_summary"] = f"open_url: {target}"
                elif intent == "launch_app":
                    parsed["formatted_summary"] = f"launch_app: {target}"
                elif intent == "hotkey":
                    parsed["formatted_summary"] = f"hotkey: {target}"
                elif intent == "shutdown":
                    parsed["formatted_summary"] = "shutdown"
                else:
                    parsed["formatted_summary"] = f"{intent}: {target}"

                return parsed
        except Exception as e:
            logger.warning(f"Local Qwen reasoning error: {e}")
            return {
                "intent": "noop",
                "target": command,
                "speech": "",
                "raw_response": f"Err: {str(e)[:25]}",
                "formatted_summary": f"noop: {command[:20]}",
            }

    def answer_screen_query(
        self,
        question: str,
        active_window: Optional[WindowInfo] = None,
        open_windows: Optional[List[WindowInfo]] = None,
        screen_ocr: str = "",
    ) -> Dict[str, str]:
        """Answers questions about what is on screen using local desktop metadata and OCR."""
        win_title = active_window.title if active_window else "None"
        win_cls = active_window.class_name if active_window else "None"
        open_wins = (
            ", ".join([f"'{w.title}'" for w in open_windows[:6]])
            if open_windows
            else "None"
        )

        prompt = (
            f"You are Bit, an offline autonomous AI assistant controlling a Linux desktop.\n"
            f"The user asked: '{question}'.\n"
            f"Desktop Context:\n"
            f"- Active window: '{win_title}' ({win_cls})\n"
            f"- Open windows: {open_wins}\n"
        )
        if screen_ocr:
            prompt += f"- On-screen detected text: {screen_ocr[:200]}\n"

        prompt += "\nAnswer the user directly and concisely in 1 or 2 natural sentences.\nAnswer:"

        try:
            req = urllib.request.Request(
                f"{self.ollama_host}/api/generate",
                data=json.dumps({
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 70},
                }).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = json.loads(resp.read().decode())
                ans = data.get("response", "").strip()
                return {"answer": ans, "raw_response": ans}
        except Exception as e:
            fallback = f"You are viewing '{win_title}', with {open_wins} open."
            return {"answer": fallback, "raw_response": fallback}
