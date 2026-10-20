"""Domain models for HandsFreeOS."""

from enum import Enum
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class IntentType(str, Enum):
    """Categorized intent resolved by Jev System-1."""
    AMBIENT_IGNORE = "ambient_ignore"
    ABORT_INTERRUPT = "abort_interrupt"
    FAST_SYSTEM = "fast_system"
    FAST_FILE = "fast_file"
    FAST_URL = "fast_url"
    VISUAL_CLICK = "visual_click"
    DICTATION = "dictation"
    CONFIRMATION_RESPONSE = "confirmation_response"


class SpeechChunk(BaseModel):
    """Chunk of streaming speech tokens from STT (Phonon-2)."""
    text: str
    is_final: bool = False
    confidence: float = 1.0
    timestamp: float = 0.0
    duration_ms: float = 0.0


class BoundingBox(BaseModel):
    """Interactive screen element parsed by OmniParser / YOLO."""
    id: int
    label: str
    x_min: int
    y_min: int
    x_max: int
    y_max: int
    confidence: float = 1.0
    is_icon: bool = False

    @property
    def center(self) -> tuple[int, int]:
        """Calculates center coordinate (x, y)."""
        return ((self.x_min + self.x_max) // 2, (self.y_min + self.y_max) // 2)


class WindowInfo(BaseModel):
    """Window client metadata from Hyprland IPC."""
    address: str
    title: str
    class_name: str
    workspace_id: int = 1
    is_focused: bool = False


class DesktopApp(BaseModel):
    """Metadata representing an installed Linux desktop application."""
    name: str
    exec_cmd: str
    desktop_file: str
    generic_name: str = ""
    comment: str = ""
    categories: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)


class MemoryEntry(BaseModel):
    """A remembered mapping from a natural user phrasing to a canonical OS action."""
    phrase: str
    intent: str
    target: Any
    speech: str = ""
    hit_count: int = 1
    last_updated: float = Field(default_factory=time.time)


class JevDecision(BaseModel):
    """Result of a calibrated Jev System-1 decision."""
    decision_type: str  # "choice" | "score" | "noul"
    value: Any          # Selected candidate, bool, or float
    confidence: float
    latency_ms: float = 0.0
    reasoning: Optional[str] = None


class ActionType(str, Enum):
    """Types of executable OS actions."""
    FOCUS_WINDOW = "focus_window"
    CLOSE_WINDOW = "close_window"
    LAUNCH_APP = "launch_app"
    CREATE_FILE = "create_file"
    OPEN_URL = "open_url"
    CLICK_BOX = "click_box"
    TYPE_TEXT = "type_text"
    HOTKEY = "hotkey"
    ANSWER_USER = "answer_user"
    ABORT = "abort"
    SHUTDOWN = "shutdown"
    ASK_CONFIRMATION = "ask_confirmation"
    NOOP = "noop"


class ActionEvent(BaseModel):
    """Dispatched OS action resulting from intent evaluation."""
    action_type: ActionType
    target: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    verbal_response: str = ""
    is_destructive: bool = False
    requires_confirmation: bool = False
    target_window_class: Optional[str] = None  # To determine browser vs desktop
    llm_output: str = ""
