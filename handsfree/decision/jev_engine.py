"""Jev System-1 high-speed decision engine implementation."""

import re
import time
from typing import Any, List, Optional
from difflib import SequenceMatcher

from handsfree.domain.interfaces import IDecisionEngine
from handsfree.domain.models import BoundingBox, JevDecision, WindowInfo
from handsfree.decision.safety import SafetyScorer


class JevEngine(IDecisionEngine):
    """High-speed calibrated System-1 decision engine.

    Executes Choice, Noul (boolean), and Score decisions in 5-40ms without
    requiring slow token-by-token generative decoding.
    """

    def __init__(self, safety_scorer: Optional[SafetyScorer] = None):
        self.safety_scorer = safety_scorer or SafetyScorer()

        # Compiled triggers for ambient vs command filtering
        self.command_verbs = {
            "open", "launch", "start", "switch", "focus", "close", "kill",
            "make", "create", "write", "type", "click", "tap", "press",
            "scroll", "search", "find", "goto", "navigate", "send", "save",
            "delete", "remove", "clear", "copy", "paste", "cut", "undo", "redo"
        }

        # Triggers for live interruption aborts
        self.abort_tokens = {
            "wait", "stop", "cancel", "pause", "hold on", "no", "abort",
            "don't", "dont", "never mind", "nevermind", "quit", "halt",
            "not that", "wrong"
        }

    def evaluate_noul(self, context: str, question: str) -> JevDecision:
        """Evaluates a calibrated boolean judgment."""
        start_time = time.perf_counter()
        ctx_lower = context.lower().strip()
        q_lower = question.lower().strip()

        # Interruption check
        if "interrupting" in q_lower or "aborting" in q_lower:
            is_abort = any(re.search(rf"\b{re.escape(token)}\b", ctx_lower) for token in self.abort_tokens)
            conf = 0.95 if is_abort else 0.90
            latency = (time.perf_counter() - start_time) * 1000.0
            return JevDecision(
                decision_type="noul",
                value=is_abort,
                confidence=conf,
                latency_ms=latency,
                reasoning=f"Interruption check: {is_abort}"
            )

        # Ambient check
        if "command to the pc" in q_lower:
            is_cmd = self.filter_ambient_speech(context)
            conf = 0.92 if is_cmd else 0.88
            latency = (time.perf_counter() - start_time) * 1000.0
            return JevDecision(
                decision_type="noul",
                value=is_cmd,
                confidence=conf,
                latency_ms=latency,
                reasoning=f"Command check: {is_cmd}"
            )

        # Fallback default evaluation
        latency = (time.perf_counter() - start_time) * 1000.0
        return JevDecision(
            decision_type="noul",
            value=False,
            confidence=0.5,
            latency_ms=latency
        )

    def evaluate_choice(
        self, candidates: List[Any], question: str, context: Optional[str] = None
    ) -> JevDecision:
        """Selects a discrete candidate from candidates list in <40ms."""
        start_time = time.perf_counter()
        if not candidates:
            latency = (time.perf_counter() - start_time) * 1000.0
            return JevDecision(
                decision_type="choice",
                value=None,
                confidence=0.0,
                latency_ms=latency,
                reasoning="Empty candidates list"
            )

        ctx = (context or "").lower().strip()
        best_candidate = None
        best_score = -1.0

        for cand in candidates:
            score = 0.0
            if isinstance(cand, BoundingBox):
                score = self._score_box_match(cand, ctx)
            elif isinstance(cand, WindowInfo):
                score = self._score_window_match(cand, ctx)
            elif isinstance(cand, str):
                score = SequenceMatcher(None, cand.lower(), ctx).ratio()
            elif isinstance(cand, dict):
                score = SequenceMatcher(None, str(cand).lower(), ctx).ratio()

            if score > best_score:
                best_score = score
                best_candidate = cand

        latency = (time.perf_counter() - start_time) * 1000.0
        conf = max(0.0, min(1.0, best_score))
        return JevDecision(
            decision_type="choice",
            value=best_candidate if conf > 0.3 else None,
            confidence=conf,
            latency_ms=latency,
            reasoning=f"Selected candidate with match score {conf:.2f}"
        )

    def evaluate_score(self, context: str, question: str) -> JevDecision:
        """Evaluates a continuous scalar rating (0.0 to 1.0)."""
        start_time = time.perf_counter()
        if "destructive" in question.lower():
            score, rationale = self.safety_scorer.compute_destructive_score(context)
            latency = (time.perf_counter() - start_time) * 1000.0
            return JevDecision(
                decision_type="score",
                value=score,
                confidence=0.95,
                latency_ms=latency,
                reasoning=rationale
            )

        latency = (time.perf_counter() - start_time) * 1000.0
        return JevDecision(
            decision_type="score",
            value=0.5,
            confidence=0.5,
            latency_ms=latency,
            reasoning="Default scalar rating"
        )

    def filter_ambient_speech(self, text: str) -> bool:
        """Returns True if speech is an intentional command to the PC."""
        cleaned = text.lower().strip()
        if not cleaned:
            return False

        # Explicit assistant call
        if cleaned.startswith("hey bit") or cleaned.startswith("bit") or "bit," in cleaned:
            return True

        # Check starting word or clause for command verbs
        words = re.findall(r"\b\w+\b", cleaned)
        if not words:
            return False

        first_word = words[0]
        if first_word in self.command_verbs:
            return True

        # Common multi-word phrases (e.g. "make a new txt file", "can you open")
        if re.search(r"\b(open|launch|make a|create a|switch to|click on|type in)\b", cleaned):
            return True

        return False

    def select_yolo_box(
        self, boxes: List[BoundingBox], user_intent: str
    ) -> Optional[BoundingBox]:
        """Matches user intent to a YOLO bounding box in ~40ms."""
        decision = self.evaluate_choice(boxes, "Which element matches user intent?", context=user_intent)
        return decision.value if decision.confidence >= 0.35 else None

    def detect_interruption(self, text_chunk: str) -> bool:
        """Detects whether speech is an abort/correction in <25ms."""
        decision = self.evaluate_noul(
            text_chunk, question="Is the user interrupting, aborting, or correcting the current action?"
        )
        return bool(decision.value)

    def disambiguate_window(
        self, windows: List[WindowInfo], user_phrase: str
    ) -> Optional[WindowInfo]:
        """Selects the matching window from active Hyprland clients."""
        phrase = user_phrase.lower().strip()
        # Handle "this window" / "close this" -> choose currently focused window
        if "this" in phrase or "active" in phrase or "current" in phrase:
            for w in windows:
                if w.is_focused:
                    return w

        decision = self.evaluate_choice(windows, "Which window matches user phrase?", context=user_phrase)
        return decision.value if decision.confidence >= 0.30 else None

    def classify_dictation(self, speech: str, input_focused: bool) -> bool:
        """Classifies if text should be typed literally as dictation."""
        if not input_focused:
            return False

        cleaned = speech.lower().strip()
        # If explicitly formatted as a command, not dictation
        if self.filter_ambient_speech(cleaned):
            # Unless prefixed with "type" or "write"
            if cleaned.startswith("type ") or cleaned.startswith("write "):
                return True
            return False

        # In focused input without command verbs -> dictation
        return True

    def _score_box_match(self, box: BoundingBox, query: str) -> float:
        """Computes matching score between a bounding box label and query."""
        label = box.label.lower().strip()
        q = query.lower().strip()

        if not label:
            return 0.1 if box.is_icon else 0.0

        if label == q:
            return 1.0

        if q in label or label in q:
            return 0.85

        # Word overlap excluding generic UI stopwords
        generic_stopwords = {"icon", "button", "item", "element", "clickable", "unlabelled", "image", "box"}
        q_words = set(re.findall(r"\b\w+\b", q)) - generic_stopwords
        label_words = set(re.findall(r"\b\w+\b", label)) - generic_stopwords
        overlap = q_words.intersection(label_words)
        if overlap:
            return 0.7 + (0.1 * min(len(overlap), 3))

        if not q_words or not label_words:
            return 0.1 if box.is_icon else 0.0

        return SequenceMatcher(None, label, q).ratio()

    def _score_window_match(self, window: WindowInfo, query: str) -> float:
        """Computes matching score between window info and query."""
        q = query.lower().strip()
        title = window.title.lower().strip()
        cls_name = window.class_name.lower().strip()

        # Remove filler words
        q_clean = re.sub(r"\b(switch to|open|focus|close|the|window|app)\b", "", q).strip()
        if not q_clean:
            q_clean = q

        score_title = SequenceMatcher(None, q_clean, title).ratio()
        score_class = SequenceMatcher(None, q_clean, cls_name).ratio()

        if q_clean in title or q_clean in cls_name:
            return 0.9

        # Direct token match
        if any(token in title or token in cls_name for token in q_clean.split()):
            return 0.75

        return max(score_title, score_class)
