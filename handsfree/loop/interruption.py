"""Live interruption and abort coordinator."""

import logging
import re
from typing import Optional

from handsfree.domain.interfaces import IDecisionEngine, IInputController

logger = logging.getLogger(__name__)


class InterruptionCoordinator:
    """Detects live abort signals in <25ms and halts execution."""

    STANDALONE_ABORT_TOKENS = {
        "wait", "stop", "cancel", "pause", "hold on", "no", "abort",
        "don't", "dont", "never mind", "nevermind", "halt", "not that", "wrong"
    }

    ACTION_IGNORE_PATTERNS = [
        r"^quit\s+\w+",
        r"^stop\s+listening\b",
        r"^stop\s+(?:the\s+)?music\b",
        r"^bye\b",
    ]

    def __init__(
        self,
        decision_engine: IDecisionEngine,
        input_controller: IInputController,
    ):
        self.decision_engine = decision_engine
        self.input_controller = input_controller
        self._is_active_action = False

    def set_action_active(self, active: bool) -> None:
        """Sets whether an execution action is currently underway."""
        self._is_active_action = active

    def is_action_active(self) -> bool:
        """Checks if an action is currently active."""
        return self._is_active_action

    def check_and_handle_abort(self, speech_text: str) -> bool:
        """Evaluates speech chunk for abort intent. If detected, halts input controller immediately."""
        cleaned = speech_text.lower().strip().rstrip(".?!,")
        if not cleaned:
            return False

        # Exclude commands with verb-object patterns
        for pat in self.ACTION_IGNORE_PATTERNS:
            if re.search(pat, cleaned):
                return False

        # If an action is actively running in background (e.g. mouse trajectory, typing)
        if self._is_active_action:
            is_abort = self.decision_engine.detect_interruption(speech_text)
            if is_abort:
                logger.warning(f"In-flight action aborted by speech: '{speech_text}'")
                self.input_controller.abort_in_flight()
                self._is_active_action = False
                return True

        # When idle, pure standalone abort keywords or corrections trigger an abort event
        if re.search(r"\b(wrong\s+window|not\s+that|wrong\s+app|that's\s+wrong)\b", cleaned):
            logger.warning(f"Verbal correction detected: '{speech_text}'")
            self.input_controller.abort_in_flight()
            return True

        words = re.findall(r"\b\w+\b", cleaned)
        abort_modifiers = {"that", "it", "there"}
        if words and any(w in self.STANDALONE_ABORT_TOKENS for w in words):
            if all(w in self.STANDALONE_ABORT_TOKENS or w in abort_modifiers for w in words):
                logger.warning(f"Standalone abort signal detected: '{speech_text}'")
                self.input_controller.abort_in_flight()
                return True

        if cleaned in self.STANDALONE_ABORT_TOKENS:
            self.input_controller.abort_in_flight()
            return True

        return False
