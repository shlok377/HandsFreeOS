"""Adaptive input controller supporting instant desktop clicks and humanized browser evasion."""

import logging
import random
import subprocess
import threading
import time
from typing import Optional, Tuple

from handsfree.domain.interfaces import IInputController
from handsfree.os_layer.bezier import generate_human_trajectory

logger = logging.getLogger(__name__)


class AdaptiveInputController(IInputController):
    """Dispatches mouse clicks and keystrokes with adaptive anti-bot humanization."""

    def __init__(self, current_pos: Tuple[int, int] = (100, 100), dry_run: bool = False):
        self.current_pos = current_pos
        self.dry_run = dry_run
        self._abort_event = threading.Event()
        self.history: list[dict] = []  # For verification and testing

    def abort_in_flight(self) -> None:
        """Signals active motion or typing threads to halt immediately in <5ms."""
        self._abort_event.set()
        logger.info("Live input abort requested!")

    def reset_abort(self) -> None:
        """Clears abort signal for new tasks."""
        self._abort_event.clear()

    def move_and_click(
        self, x: int, y: int, is_browser: bool = False, double_click: bool = False
    ) -> None:
        """Executes a move and click.

        If is_browser is True: Moves along organic Bézier path, pauses, clicks,
        and introduces variable dwell time.
        If is_browser is False: Jumps instantly to coordinate and clicks.
        """
        self.reset_abort()

        if is_browser:
            logger.info(f"Browser mode: Generating organic Bézier trajectory from {self.current_pos} to ({x}, {y})")
            waypoints = generate_human_trajectory(self.current_pos, (x, y))

            for wx, wy, delay in waypoints:
                if self._abort_event.is_set():
                    logger.warning(f"Aborted mouse movement at ({wx}, {wy})")
                    self.history.append({"action": "aborted", "at": (wx, wy)})
                    return

                self._emit_mouse_move(wx, wy)
                time.sleep(delay)

            # Human pause before mouse-down (60-120ms)
            if self._abort_event.is_set():
                return
            dwell_down = random.uniform(0.06, 0.12)
            time.sleep(dwell_down)

            self._emit_click(x, y, dwell_down, double_click=double_click)
        else:
            logger.info(f"Desktop mode: Instant click at ({x}, {y}) (double_click={double_click})")
            if self._abort_event.is_set():
                return
            self._emit_mouse_move(x, y)
            self._emit_click(x, y, 0.02, double_click=double_click)

        self.current_pos = (x, y)
        self.history.append({
            "action": "click",
            "target": (x, y),
            "is_browser": is_browser,
            "double_click": double_click,
        })

    def type_text(self, text: str, is_browser: bool = False) -> None:
        """Simulates typing into active input.

        If is_browser is True: Adds variable inter-keystroke delays (40-110ms).
        If is_browser is False: Dispatches via wtype or fast input.
        """
        self.reset_abort()
        logger.info(f"Typing text (browser={is_browser}): '{text}'")

        if is_browser:
            for char in text:
                if self._abort_event.is_set():
                    logger.warning("Typing aborted mid-string")
                    self.history.append({"action": "aborted_typing", "typed": char})
                    return

                self._emit_key(char)
                # Variable typing cadence with natural digraph timing
                delay = random.uniform(0.04, 0.11)
                time.sleep(delay)
        else:
            if self._abort_event.is_set():
                return
            self._emit_string_fast(text)

        self.history.append({
            "action": "type",
            "text": text,
            "is_browser": is_browser
        })

    def send_hotkey(self, keys: list[str]) -> None:
        """Dispatches key combinations like ['ctrl', 't'] using wtype."""
        if self._abort_event.is_set():
            return

        logger.info(f"Dispatching hotkey: {keys}")
        self.history.append({"action": "hotkey", "keys": keys})

        if self.dry_run:
            return

        cmd = ["wtype"]
        modifiers = []
        regular_keys = []
        mod_map = {
            "ctrl": "ctrl", "control": "ctrl",
            "alt": "alt",
            "shift": "shift",
            "super": "logo", "win": "logo", "logo": "logo", "meta": "logo"
        }
        for k in keys:
            kl = k.lower()
            if kl in mod_map:
                modifiers.append(mod_map[kl])
            else:
                regular_keys.append(k)

        for m in modifiers:
            cmd.extend(["-M", m])
        for r in regular_keys:
            cmd.extend(["-k", r])
        for m in reversed(modifiers):
            cmd.extend(["-m", m])

        try:
            subprocess.run(cmd, check=False, capture_output=True)
        except Exception as e:
            logger.warning(f"Failed to dispatch hotkey via wtype: {e}")

    def _emit_mouse_move(self, x: int, y: int) -> None:
        """Emits mouse movement to OS via Hyprland IPC or ydotool."""
        if self.dry_run:
            return

        # 1. Hyprland compositor native cursor positioning
        try:
            res = subprocess.run(
                ["hyprctl", "dispatch", f'hl.dsp.cursor.move({{ x = {int(x)}, y = {int(y)} }})'],
                capture_output=True,
                text=True,
                check=False,
            )
            if "ok" in res.stdout:
                return
        except Exception:
            pass

        # 2. Fallback: ydotool if installed
        if shutil.which("ydotool"):
            try:
                subprocess.run(
                    ["ydotool", "mousemove", "--absolute", "-x", str(int(x)), "-y", str(int(y))],
                    check=False,
                    capture_output=True,
                )
            except Exception:
                pass

    def _emit_click(self, x: int, y: int, dwell_seconds: float, double_click: bool = False) -> None:
        """Emits mouse down and mouse up, optionally executing double-click."""
        if self.dry_run:
            return

        def _click_once() -> bool:
            # Try Hyprland compositor native mouse click
            try:
                p1 = subprocess.run(
                    ["hyprctl", "dispatch", 'hl.dsp.send_key_state({ mods = "", key = "mouse:272", state = "down" })'],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                time.sleep(max(0.02, dwell_seconds))
                p2 = subprocess.run(
                    ["hyprctl", "dispatch", 'hl.dsp.send_key_state({ mods = "", key = "mouse:272", state = "up" })'],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if "ok" in p1.stdout and "ok" in p2.stdout:
                    return True
            except Exception:
                pass

            # Fallback: ydotool click 0xC0 (left click)
            if shutil.which("ydotool"):
                try:
                    subprocess.run(["ydotool", "click", "0xC0"], check=False, capture_output=True)
                    return True
                except Exception:
                    pass

            return False

        _click_once()
        if double_click:
            time.sleep(0.06)
            _click_once()

    def _emit_key(self, char: str) -> None:
        """Emits single key press via wtype if available."""
        if self.dry_run:
            return
        try:
            subprocess.run(["wtype", char], check=False, capture_output=True)
        except Exception:
            pass

    def _emit_string_fast(self, text: str) -> None:
        """Fast instant string injection via wtype."""
        if self.dry_run:
            return
        try:
            subprocess.run(["wtype", text], check=False, capture_output=True)
        except Exception:
            pass
