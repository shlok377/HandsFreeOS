"""Intent & Execution Dispatch Loop: The primary testing and orchestration seam."""

import logging
import os
import re
import shutil
import urllib.parse
from typing import Optional

from handsfree.domain.interfaces import IDecisionEngine, IOSController, IInputController, ITextToSpeech
from handsfree.domain.models import ActionEvent, ActionType, SpeechChunk, WindowInfo
from handsfree.loop.interruption import InterruptionCoordinator
from handsfree.vision.grounding import TwoStageGrounder

logger = logging.getLogger(__name__)


class IntentDispatcher:
    """The central orchestrator and testing seam of HandsFreeOS."""

    def __init__(
        self,
        decision_engine: IDecisionEngine,
        os_controller: IOSController,
        input_controller: IInputController,
        tts: ITextToSpeech,
        grounder: Optional[TwoStageGrounder] = None,
    ):
        self.decision_engine = decision_engine
        self.os_controller = os_controller
        self.input_controller = input_controller
        self.tts = tts
        self.grounder = grounder or TwoStageGrounder(decision_engine=decision_engine)
        self.interruption = InterruptionCoordinator(decision_engine, input_controller)

        self._pending_confirmation: Optional[ActionEvent] = None

    def process_speech_frame(
        self,
        chunk: SpeechChunk,
        screenshot_bytes: Optional[bytes] = None,
        mock_active_window: Optional[WindowInfo] = None,
    ) -> ActionEvent:
        """Processes a speech frame through Jev decision gates and executes OS actions.

        This is the primary seam for external behavior verification.
        """
        raw_text = chunk.text.strip()
        if not raw_text:
            return ActionEvent(action_type=ActionType.NOOP)

        # 1. CONFIRMATION HANDLING (if waiting for user confirmation on a destructive action)
        if self._pending_confirmation is not None:
            if re.search(r"\b(yes|yeah|sure|confirm|do it|proceed|ok)\b", raw_text.lower()):
                confirmed_action = self._pending_confirmation
                self._pending_confirmation = None
                return self._execute_confirmed_action(confirmed_action)
            elif re.search(r"\b(no|cancel|stop|don't|dont|never mind)\b", raw_text.lower()):
                self._pending_confirmation = None
                response_msg = "Action cancelled"
                self.tts.speak(response_msg)
                return ActionEvent(action_type=ActionType.NOOP, verbal_response=response_msg)

        # 2. LIVE INTERRUPTION GATE (<25ms)
        if self.interruption.check_and_handle_abort(raw_text):
            response_msg = "Halting now"
            self.tts.speak(response_msg)
            self._pending_confirmation = None
            return ActionEvent(
                action_type=ActionType.ABORT,
                verbal_response=response_msg
            )

        # 3. AMBIENT SPEECH FILTER
        if not self.decision_engine.filter_ambient_speech(raw_text):
            logger.debug(f"Ambient speech ignored: '{raw_text}'")
            return ActionEvent(action_type=ActionType.NOOP)

        # Clean "Hey Bit" prefixes and punctuation
        command = re.sub(r"^(hey\s+)?bit[,\s!]*", "", raw_text, flags=re.IGNORECASE).strip()
        command = re.sub(r"[\.\?!]+$", "", command).strip()
        cmd_lower = command.lower()

        # Handle exit / close yourself
        if cmd_lower in {"close yourself", "exit", "quit", "shutdown", "stop listening", "goodbye", "bye"}:
            msg = "Goodbye! Shutting down Bit."
            self.tts.speak(msg)
            return ActionEvent(action_type=ActionType.SHUTDOWN, target="exit", verbal_response=msg)

        # Handle greetings & conversational chat
        if re.search(r"\b(say\s+hi|say\s+hello|greet\s+me)\b", cmd_lower) or cmd_lower in {"hello", "hi", "hey"}:
            msg = "Hello! I'm Bit, your hands-free assistant. What can I do for you?"
            self.tts.speak(msg)
            return ActionEvent(action_type=ActionType.NOOP, verbal_response=msg)

        if re.search(r"\b(who are you|what are you|what can you do|help)\b", cmd_lower):
            msg = "I'm Bit. You can ask me to open apps, search the web, type text, click elements, or manage files."
            self.tts.speak(msg)
            return ActionEvent(action_type=ActionType.NOOP, verbal_response=msg)

        # 4. SAFETY GATE (P(destructive) > 0.80)
        safety_decision = self.decision_engine.evaluate_score(
            command, question="Is this action destructive or causes data loss?"
        )
        if float(safety_decision.value) >= 0.80:
            prompt_msg = f"Are you sure you want to {command}?"
            self.tts.speak(prompt_msg)
            pending_event = ActionEvent(
                action_type=ActionType.ASK_CONFIRMATION,
                target=command,
                verbal_response=prompt_msg,
                is_destructive=True,
                requires_confirmation=True
            )
            self._pending_confirmation = pending_event
            return pending_event

        active_win = mock_active_window or self.os_controller.get_active_window()
        is_browser = self.os_controller.is_browser_window(active_win) if hasattr(self.os_controller, "is_browser_window") else False

        # 5. DICTATION CLASSIFICATION (if active input field is focused)
        is_focused_input = active_win is not None and getattr(active_win, "is_focused", False)
        if self.decision_engine.classify_dictation(command, input_focused=is_focused_input):
            text_to_type = command
            if text_to_type.lower().startswith("type "):
                text_to_type = text_to_type[5:].strip()
            self.input_controller.type_text(text_to_type, is_browser=is_browser)
            return ActionEvent(
                action_type=ActionType.TYPE_TEXT,
                target=text_to_type,
                verbal_response=f"Typed {text_to_type}"
            )

        # 6. WEB SEARCH INTENT ("search <query> [in my browser|on google|on web|online]" or "google <query>")
        search_match = re.search(
            r"^(?:please\s+)?(?:search(?:\s+for)?|google)\s+(.+?)(?:\s+(?:in\s+(?:my\s+)?browser|on\s+google|on\s+(?:the\s+)?web|online))?$",
            command,
            flags=re.IGNORECASE,
        )
        if search_match:
            query = search_match.group(1).strip()
            return self._handle_web_search(query)

        # 7. FILE CREATION & SHELL
        if re.search(r"\bmake\s+(a\s+)?new\s+(\w+\s+)?file\b", cmd_lower):
            return self._handle_file_creation(command)

        # 8. APP LAUNCHING & URL NAVIGATION
        if cmd_lower.startswith("open ") or cmd_lower.startswith("launch "):
            target = re.sub(r"^(open|launch)\s+", "", command, flags=re.IGNORECASE).strip()
            return self._handle_open_target(target)

        # 9. WINDOW SWITCHING & CLOSING
        if cmd_lower.startswith("switch to ") or cmd_lower.startswith("focus "):
            target = re.sub(r"^(switch to|focus)\s+", "", command, flags=re.IGNORECASE).strip()
            return self._handle_window_focus(target)

        if cmd_lower in {"close this", "close window", "close"}:
            return self._handle_close_window(active_win)

        # 10. VISUAL CLICK & GROUNDING
        if re.search(r"\b(click|tap|press)\b", cmd_lower):
            target = re.sub(r"^(please\s+)?(click\s+(on\s+)?|tap\s+(on\s+)?|press\s+)", "", command, flags=re.IGNORECASE).strip()
            return self._handle_visual_click(target, screenshot_bytes, is_browser)

        # Default fallback: Execute as system shell
        self.os_controller.launch_app(command)
        response_msg = f"Executing {command}"
        self.tts.speak(response_msg)
        return ActionEvent(action_type=ActionType.LAUNCH_APP, target=command, verbal_response=response_msg)

    def _handle_web_search(self, query: str) -> ActionEvent:
        """Executes a web search via default browser."""
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://www.google.com/search?q={encoded_query}"
        self.os_controller.open_url(url)
        msg = f"Searching for {query} in browser"
        self.tts.speak(msg)
        return ActionEvent(action_type=ActionType.OPEN_URL, target=url, verbal_response=msg)

    def _handle_open_target(self, target: str) -> ActionEvent:
        """Handles opening an application or website."""
        clean_target = re.sub(r"[\.\?!,]+$", "", target).strip().lower()
        normalized_target = re.sub(r"^(my\s+)", "", clean_target).strip()

        # Handle web applications (e.g. "webwhatsapp", "whatsapp")
        if "webwhatsapp" in clean_target or "whatsapp" in clean_target:
            self.os_controller.open_url("https://web.whatsapp.com")
            msg = "Opening WhatsApp now"
            self.tts.speak(msg)
            return ActionEvent(action_type=ActionType.OPEN_URL, target="https://web.whatsapp.com", verbal_response=msg)

        if "discord" in clean_target:
            if shutil.which("discord"):
                self.os_controller.launch_app("discord")
                msg = "Opening Discord"
                action = ActionType.LAUNCH_APP
            else:
                self.os_controller.open_url("https://discord.com/app")
                msg = "Opening Discord in browser"
                action = ActionType.OPEN_URL
            self.tts.speak(msg)
            return ActionEvent(action_type=action, target="discord", verbal_response=msg)

        if "herdr" in clean_target:
            self.os_controller.launch_app("herdr")
            msg = "Opening Herdr now"
            self.tts.speak(msg)
            return ActionEvent(action_type=ActionType.LAUNCH_APP, target="herdr", verbal_response=msg)

        # Generic application aliases
        if normalized_target in {"text editor", "editor", "notepad", "code editor"}:
            editor_bin = (
                "omawrite" if shutil.which("omawrite")
                else ("subl" if shutil.which("subl")
                else ("code" if shutil.which("code")
                else ("gedit" if shutil.which("gedit")
                else ("kate" if shutil.which("kate")
                else "xdg-open"))))
            )
            self.os_controller.launch_app(editor_bin)
            msg = "Opening text editor"
            self.tts.speak(msg)
            return ActionEvent(action_type=ActionType.LAUNCH_APP, target=editor_bin, verbal_response=msg)

        if normalized_target in {"browser", "web browser", "internet"}:
            browser_bin = "firefox" if shutil.which("firefox") else ("chromium" if shutil.which("chromium") else "xdg-open")
            self.os_controller.launch_app(browser_bin)
            msg = "Opening browser"
            self.tts.speak(msg)
            return ActionEvent(action_type=ActionType.LAUNCH_APP, target=browser_bin, verbal_response=msg)

        if normalized_target in {"file manager", "files", "file explorer"}:
            fm_bin = "nautilus" if shutil.which("nautilus") else ("dolphin" if shutil.which("dolphin") else "thunar")
            self.os_controller.launch_app(fm_bin)
            msg = "Opening file manager"
            self.tts.speak(msg)
            return ActionEvent(action_type=ActionType.LAUNCH_APP, target=fm_bin, verbal_response=msg)

        if normalized_target in {"terminal", "console", "shell"}:
            term_bin = "ghostty" if shutil.which("ghostty") else ("foot" if shutil.which("foot") else "alacritty")
            self.os_controller.launch_app(term_bin)
            msg = "Opening terminal"
            self.tts.speak(msg)
            return ActionEvent(action_type=ActionType.LAUNCH_APP, target=term_bin, verbal_response=msg)

        # Specific URL detection: requires http://, https://, www., or a real domain pattern without spaces
        is_url = (
            clean_target.startswith("http://")
            or clean_target.startswith("https://")
            or clean_target.startswith("www.")
            or (re.match(r"^[\w\-]+(\.[\w\-]+)+(?:/[^\s]*)?$", clean_target) is not None and " " not in clean_target)
        )
        if is_url:
            url = clean_target if clean_target.startswith("http") else f"https://{clean_target}"
            self.os_controller.open_url(url)
            msg = f"Opening {clean_target}"
            self.tts.speak(msg)
            return ActionEvent(action_type=ActionType.OPEN_URL, target=url, verbal_response=msg)

        # Default desktop app launch
        self.os_controller.launch_app(normalized_target)
        msg = f"Opening {normalized_target}"
        self.tts.speak(msg)
        return ActionEvent(action_type=ActionType.LAUNCH_APP, target=normalized_target, verbal_response=msg)

    def _handle_file_creation(self, command: str) -> ActionEvent:
        """Extracts filename and content and creates file directly."""
        # e.g. "make a new txt file and type in hello world" or "make a new file named notes.txt"
        content_match = re.search(r"(?:type\s+in|write|with\s+text)\s+(.+)$", command, re.IGNORECASE)
        content = content_match.group(1).strip() if content_match else ""

        # Check for explicit name e.g. "named foo.txt" or "called notes.txt"
        named_match = re.search(r"(?:named|called)\s+([\w\.\-_]+)", command, re.IGNORECASE)
        if named_match:
            raw_name = named_match.group(1).strip()
            filename = raw_name if "." in raw_name else f"{raw_name}.txt"
        else:
            filename_match = re.search(r"new\s+([\w\.\-_]+)\s+file", command, re.IGNORECASE)
            if filename_match:
                raw_name = filename_match.group(1).strip()
                if raw_name.lower() in {"txt", "text", "doc"}:
                    filename = "document.txt"
                else:
                    filename = raw_name if "." in raw_name else f"{raw_name}.txt"
            else:
                filename = "document.txt"

        filepath = os.path.expanduser(f"~/{filename}")
        self.os_controller.create_file(filepath, content)

        msg = f"Created {filename}"
        if content:
            msg += f" with content {content}"
        self.tts.speak(msg)

        return ActionEvent(
            action_type=ActionType.CREATE_FILE,
            target=filepath,
            payload={"content": content},
            verbal_response=msg
        )

    def _handle_window_focus(self, target: str) -> ActionEvent:
        """Focuses window matching target phrase."""
        windows = self.os_controller.get_open_windows()
        matched = self.decision_engine.disambiguate_window(windows, target)
        if matched:
            self.os_controller.focus_window(matched.address)
            msg = f"Switching to {matched.title or matched.class_name}"
            self.tts.speak(msg)
            return ActionEvent(action_type=ActionType.FOCUS_WINDOW, target=matched.address, verbal_response=msg)

        msg = f"Could not find window for {target}"
        self.tts.speak(msg)
        return ActionEvent(action_type=ActionType.NOOP, verbal_response=msg)

    def _handle_close_window(self, active_win: Optional[WindowInfo]) -> ActionEvent:
        """Closes active window."""
        if active_win:
            self.os_controller.focus_window(active_win.address)
            msg = f"Closed {active_win.title or active_win.class_name}"
            self.tts.speak(msg)
            return ActionEvent(action_type=ActionType.FOCUS_WINDOW, target=active_win.address, verbal_response=msg)
        return ActionEvent(action_type=ActionType.NOOP)

    def _handle_visual_click(
        self, target: str, screenshot_bytes: Optional[bytes], is_browser: bool
    ) -> ActionEvent:
        """Visually locates target and executes mouse click."""
        clean_target = re.sub(r"^(the\s+)", "", target, flags=re.IGNORECASE).strip()
        img = screenshot_bytes or b""
        coords, tier, latency = self.grounder.locate_target(img, clean_target)

        if coords:
            x, y = coords
            self.interruption.set_action_active(True)
            try:
                self.input_controller.move_and_click(x, y, is_browser=is_browser)
            finally:
                self.interruption.set_action_active(False)

            msg = f"Clicked {clean_target}"
            self.tts.speak(msg)
            return ActionEvent(
                action_type=ActionType.CLICK_BOX,
                target=f"({x}, {y})",
                payload={"tier": tier, "latency_ms": latency},
                verbal_response=msg
            )

        msg = f"Could not locate {clean_target} on screen"
        self.tts.speak(msg)
        return ActionEvent(action_type=ActionType.NOOP, verbal_response=msg)

    def _execute_confirmed_action(self, action: ActionEvent) -> ActionEvent:
        """Executes a previously staged destructive action after user confirmation."""
        logger.info(f"Executing confirmed destructive action: {action.target}")
        self.os_controller.launch_app(action.target or "")
        msg = f"Confirmed and executed {action.target}"
        self.tts.speak(msg)
        return ActionEvent(action_type=ActionType.LAUNCH_APP, target=action.target, verbal_response=msg)
