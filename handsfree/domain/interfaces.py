"""Domain interfaces defining contracts for HandsFreeOS subsystems."""

from abc import ABC, abstractmethod
from typing import Any, List, Optional
from handsfree.domain.models import BoundingBox, JevDecision, WindowInfo


class IDecisionEngine(ABC):
    """Abstract interface for Jev System-1 decision operations."""

    @abstractmethod
    def evaluate_noul(self, context: str, question: str) -> JevDecision:
        """Evaluates a calibrated boolean judgment P(true)."""
        pass

    @abstractmethod
    def evaluate_choice(
        self, candidates: List[Any], question: str, context: Optional[str] = None
    ) -> JevDecision:
        """Selects a discrete candidate from a given list."""
        pass

    @abstractmethod
    def evaluate_score(self, context: str, question: str) -> JevDecision:
        """Evaluates a continuous scalar rating (0.0 to 1.0)."""
        pass

    @abstractmethod
    def filter_ambient_speech(self, text: str) -> bool:
        """Returns True if the speech is an intentional command to the PC."""
        pass

    @abstractmethod
    def select_yolo_box(
        self, boxes: List[BoundingBox], user_intent: str
    ) -> Optional[BoundingBox]:
        """Matches user intent to a YOLO bounding box in ~40ms."""
        pass

    @abstractmethod
    def detect_interruption(self, text_chunk: str) -> bool:
        """Detects whether speech is an abort/correction in <25ms."""
        pass

    @abstractmethod
    def disambiguate_window(
        self, windows: List[WindowInfo], user_phrase: str
    ) -> Optional[WindowInfo]:
        """Selects the matching window from active Hyprland clients."""
        pass

    @abstractmethod
    def classify_dictation(self, speech: str, input_focused: bool) -> bool:
        """Classifies if text should be typed literally as dictation."""
        pass


class IOSController(ABC):
    """Abstract interface for OS, Hyprland, and shell control."""

    @abstractmethod
    def get_open_windows(self) -> List[WindowInfo]:
        """Retrieves list of open windows from compositor IPC."""
        pass

    @abstractmethod
    def get_active_window(self) -> Optional[WindowInfo]:
        """Gets currently focused window."""
        pass

    @abstractmethod
    def focus_window(self, address_or_class: str) -> bool:
        """Focuses target window via compositor IPC."""
        pass

    @abstractmethod
    def launch_app(self, command: str) -> bool:
        """Launches application via OS dispatch."""
        pass

    @abstractmethod
    def open_url(self, url: str) -> bool:
        """Opens URL in default or active browser."""
        pass

    @abstractmethod
    def create_file(self, filepath: str, content: str = "") -> bool:
        """Creates or appends text to a file directly."""
        pass


class IInputController(ABC):
    """Abstract interface for mouse and keyboard simulation."""

    @abstractmethod
    def move_and_click(self, x: int, y: int, is_browser: bool = False) -> None:
        """Moves cursor to (x, y) and clicks, using Bézier if is_browser."""
        pass

    @abstractmethod
    def type_text(self, text: str, is_browser: bool = False) -> None:
        """Types text with natural timing variance if is_browser."""
        pass

    @abstractmethod
    def abort_in_flight(self) -> None:
        """Immediately halts any active mouse movement or typing."""
        pass

    @abstractmethod
    def send_hotkey(self, keys: List[str]) -> None:
        """Dispatches key combinations like ['ctrl', 't'] to active window."""
        pass


class ITextToSpeech(ABC):
    """Abstract interface for local neural voice feedback."""

    @abstractmethod
    def speak(self, text: str, non_blocking: bool = True) -> None:
        """Converts text to speech and plays audio."""
        pass

    @abstractmethod
    def is_speaking(self) -> bool:
        """Returns True if audio is actively playing."""
        pass
