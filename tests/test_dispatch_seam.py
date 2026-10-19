"""Integration test suite verifying HandsFreeOS at the primary process_speech_frame seam."""

import pytest
from handsfree.decision.jev_engine import JevEngine
from handsfree.domain.models import ActionType, BoundingBox, SpeechChunk, WindowInfo
from handsfree.loop.dispatch import IntentDispatcher
from handsfree.os_layer.input_controller import AdaptiveInputController
from handsfree.vision.grounding import TwoStageGrounder
from handsfree.vision.omniparser import OmniParserDetector
from handsfree.vision.vlm_fallback import MultimodalVLMFallback
from handsfree.voice.tts_kokoro import KokoroTTS


class MockOSController:
    """Mock OS controller recording dispatches."""

    def __init__(self):
        self.launched_apps: list[str] = []
        self.opened_urls: list[str] = []
        self.focused_windows: list[str] = []
        self.created_files: list[tuple[str, str]] = []
        self.windows = [
            WindowInfo(address="0x100", title="WhatsApp - Google Chrome", class_name="google-chrome", is_focused=False),
            WindowInfo(address="0x200", title="Visual Studio Code", class_name="code", is_focused=True),
        ]

    def get_open_windows(self):
        return self.windows

    def get_active_window(self):
        for w in self.windows:
            if w.is_focused:
                return w
        return None

    def focus_window(self, address_or_class: str) -> bool:
        self.focused_windows.append(address_or_class)
        return True

    def launch_app(self, command: str) -> bool:
        self.launched_apps.append(command)
        return True

    def open_url(self, url: str) -> bool:
        self.opened_urls.append(url)
        return True

    def create_file(self, filepath: str, content: str = "") -> bool:
        self.created_files.append((filepath, content))
        return True

    def is_browser_window(self, window):
        return window is not None and window.class_name == "google-chrome"


@pytest.fixture
def dispatcher():
    jev = JevEngine()
    os_ctrl = MockOSController()
    input_ctrl = AdaptiveInputController(dry_run=True)
    tts = KokoroTTS(dry_run=True)
    detector = OmniParserDetector()
    vlm = MultimodalVLMFallback()

    grounder = TwoStageGrounder(decision_engine=jev, detector=detector, vlm_fallback=vlm)

    return IntentDispatcher(
        decision_engine=jev,
        os_controller=os_ctrl,
        input_controller=input_ctrl,
        tts=tts,
        grounder=grounder,
    )


def test_open_webwhatsapp_seam(dispatcher):
    """Verifies: 'Hey bit! open webwhatsapp'."""
    chunk = SpeechChunk(text="Hey bit! open webwhatsapp", is_final=True)
    event = dispatcher.process_speech_frame(chunk)

    assert event.action_type in (ActionType.OPEN_URL, ActionType.FOCUS_WINDOW)
    assert "Opening WhatsApp now" in event.verbal_response


def test_open_herdr_seam(dispatcher):
    """Verifies: 'hey Bit! Open herdr'."""
    chunk = SpeechChunk(text="hey Bit! Open herdr", is_final=True)
    event = dispatcher.process_speech_frame(chunk)

    assert event.action_type == ActionType.LAUNCH_APP
    assert event.target == "herdr"
    assert "Opening Herdr now" in event.verbal_response
    assert "herdr" in dispatcher.os_controller.launched_apps


def test_make_txt_file_seam(dispatcher):
    """Verifies: 'hey bit! make a new txt file and type in hello world'."""
    chunk = SpeechChunk(text="hey bit! make a new txt file and type in hello world", is_final=True)
    event = dispatcher.process_speech_frame(chunk)

    assert event.action_type == ActionType.CREATE_FILE
    assert event.payload["content"] == "hello world"
    assert "hello world" in event.verbal_response
    assert len(dispatcher.os_controller.created_files) == 1
    assert dispatcher.os_controller.created_files[0][1] == "hello world"


def test_live_interruption_abort_seam(dispatcher):
    """Verifies: 'wait, stop that' aborts in <25ms."""
    chunk = SpeechChunk(text="wait, stop that", is_final=True)
    event = dispatcher.process_speech_frame(chunk)

    assert event.action_type == ActionType.ABORT
    assert event.verbal_response == "Halting now"


def test_safety_guardrail_confirmation_flow(dispatcher):
    """Verifies: Destructive commands trigger confirmation prompt before execution."""
    # Step 1: Issue destructive command
    del_chunk = SpeechChunk(text="delete all files in downloads", is_final=True)
    event = dispatcher.process_speech_frame(del_chunk)

    assert event.action_type == ActionType.ASK_CONFIRMATION
    assert event.requires_confirmation is True
    assert "Are you sure" in event.verbal_response
    assert len(dispatcher.os_controller.launched_apps) == 0  # NOT executed yet

    # Step 2: Confirm verbally
    confirm_chunk = SpeechChunk(text="yes, proceed", is_final=True)
    confirmed_event = dispatcher.process_speech_frame(confirm_chunk)

    assert confirmed_event.action_type == ActionType.LAUNCH_APP
    assert "Confirmed" in confirmed_event.verbal_response
    assert "delete all files in downloads" in dispatcher.os_controller.launched_apps


def test_safety_cancellation_flow(dispatcher):
    """Verifies: Saying 'no' cancels pending destructive command."""
    del_chunk = SpeechChunk(text="rm -rf /tmp/test", is_final=True)
    dispatcher.process_speech_frame(del_chunk)

    cancel_chunk = SpeechChunk(text="no, cancel", is_final=True)
    event = dispatcher.process_speech_frame(cancel_chunk)

    assert event.action_type == ActionType.NOOP
    assert "Action cancelled" in event.verbal_response
    assert len(dispatcher.os_controller.launched_apps) == 0


def test_ambient_speech_ignored_seam(dispatcher):
    """Verifies: Ambient room conversation does not trigger actions."""
    chunk = SpeechChunk(text="so what do you want to eat for lunch today?", is_final=True)
    event = dispatcher.process_speech_frame(chunk)

    assert event.action_type == ActionType.NOOP
    assert event.verbal_response == ""


def test_visual_click_seam(dispatcher, monkeypatch):
    """Verifies: 'click the search bar' matches YOLO box and dispatches click."""
    mock_boxes = [
        BoundingBox(id=1, label="Search or start new chat", x_min=50, y_min=50, x_max=250, y_max=90),
    ]
    monkeypatch.setattr(dispatcher.grounder.detector, "detect_elements", lambda img: mock_boxes)

    chunk = SpeechChunk(text="click on the search bar", is_final=True)
    event = dispatcher.process_speech_frame(chunk)

    assert event.action_type == ActionType.CLICK_BOX
    assert event.target == "(150, 70)"
    assert "Clicked search bar" in event.verbal_response
    assert dispatcher.input_controller.history[-1]["target"] == (150, 70)


def test_search_query_seam(dispatcher):
    """Verifies: 'Search Discord in my browser.' and 'Search hello in my browser.'."""
    chunk1 = SpeechChunk(text="Search Discord in my browser.", is_final=True)
    event1 = dispatcher.process_speech_frame(chunk1)
    assert event1.action_type == ActionType.OPEN_URL
    assert "https://www.google.com/search?q=Discord" in event1.target
    assert "Searching for Discord" in event1.verbal_response

    chunk2 = SpeechChunk(text="Search hello in my browser.", is_final=True)
    event2 = dispatcher.process_speech_frame(chunk2)
    assert event2.action_type == ActionType.OPEN_URL
    assert "https://www.google.com/search?q=hello" in event2.target
    assert "Searching for hello" in event2.verbal_response


def test_conversational_greetings_seam(dispatcher):
    """Verifies: 'Say hi to me.' responds politely."""
    chunk = SpeechChunk(text="Say hi to me.", is_final=True)
    event = dispatcher.process_speech_frame(chunk)
    assert event.action_type == ActionType.NOOP
    assert "Hello! I'm Bit" in event.verbal_response


def test_open_text_editor_alias_seam(dispatcher):
    """Verifies: 'Open my text editor.' launches an editor, not a URL."""
    chunk = SpeechChunk(text="Open my text editor.", is_final=True)
    event = dispatcher.process_speech_frame(chunk)
    assert event.action_type == ActionType.LAUNCH_APP
    assert "Opening text editor" in event.verbal_response
    assert len(dispatcher.os_controller.launched_apps) > 0


def test_close_yourself_shutdown_seam(dispatcher):
    """Verifies: 'Close yourself.' triggers ActionType.SHUTDOWN."""
    chunk = SpeechChunk(text="Close yourself.", is_final=True)
    event = dispatcher.process_speech_frame(chunk)
    assert event.action_type == ActionType.SHUTDOWN
    assert "Goodbye" in event.verbal_response

