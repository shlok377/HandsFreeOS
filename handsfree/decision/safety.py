"""Calibrated safety guardrail scorer for HandsFreeOS."""

import re
from typing import Tuple


class SafetyScorer:
    """Computes calibrated probability P(destructive) for actions and shell commands."""

    DESTRUCTIVE_PATTERNS = [
        (r"\b(delete|remove|rm\s+-rf|rmdir|erase|purge|wipe|destroy)\b", 0.95),
        (r"\b(format|drop\s+database|drop\s+table|kill\s+-9)\b", 0.98),
        (r"\b(close\s+all|killall|shutdown|reboot|poweroff)\b", 0.90),
        (r"\b(send\s+payment|transfer\s+money|checkout|pay\s+now)\b", 0.92),
        (r"\b(overwrite|truncate|reset\s+--hard)\b", 0.88),
        (r"\b(discard\s+changes|revert\s+all)\b", 0.85),
    ]

    BENIGN_PATTERNS = [
        (r"\b(open|launch|focus|switch|read|view|show|list)\b", 0.05),
        (r"\b(make\s+(a\s+)?new|create|touch|write|type)\b", 0.10),
        (r"\b(scroll|click|search|find)\b", 0.05),
    ]

    def compute_destructive_score(self, command_or_speech: str) -> Tuple[float, str]:
        """Calculates calibrated P(destructive) between 0.0 and 1.0.

        Returns:
            Tuple[float, str]: (score, rationale)
        """
        text = command_or_speech.lower().strip()

        # Check explicit destructive triggers
        for pattern, score in self.DESTRUCTIVE_PATTERNS:
            match = re.search(pattern, text)
            if match:
                return score, f"Triggered destructive pattern: '{match.group(0)}'"

        # Check benign triggers
        for pattern, score in self.BENIGN_PATTERNS:
            if re.search(pattern, text):
                return score, "Recognized benign action pattern"

        # Default neutral prior
        return 0.15, "Standard non-destructive command context"

    def requires_confirmation(self, command_or_speech: str, threshold: float = 0.80) -> bool:
        """Determines if command crosses safety threshold requiring confirmation."""
        score, _ = self.compute_destructive_score(command_or_speech)
        return score >= threshold
