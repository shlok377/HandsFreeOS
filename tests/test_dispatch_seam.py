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
        self.closed_windows: list[str] = []
        self.created_files: list[tuple[str, str]] = []
        self.windows = [
            WindowInfo(address="0x100", title="WhatsApp - Google Chrome", class_name="google-chrome", is_focused=False),
            WindowInfo(address="0x200", title="Visual Studio Code", class_name="code", is_focused=True),
            WindowInfo(address="0x300", title="Home", class_name="org.gnome.Nautilus", is_focused=False),
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

    def close_window(self, address_or_class: str) -> bool:
        self.closed_windows.append(address_or_class)
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


def test_open_new_tab_seam(dispatcher):
    """Verifies: 'bit open new tab' and 'Hey bit, open new tab in my browser.' trigger ctrl+t."""
    chunk1 = SpeechChunk(text="bit open new tab", is_final=True)
    event1 = dispatcher.process_speech_frame(chunk1)
    assert event1.action_type == ActionType.HOTKEY
    assert event1.target == "ctrl+t"
    assert "ctrl+t" in event1.llm_output

    chunk2 = SpeechChunk(text="Hey bit, open new tab in my browser.", is_final=True)
    event2 = dispatcher.process_speech_frame(chunk2)
    assert event2.action_type == ActionType.HOTKEY
    assert event2.target == "ctrl+t"


def test_screen_query_seam(dispatcher, monkeypatch):
    """Verifies: 'What do you see on my screen?' queries local reasoner."""
    monkeypatch.setattr(
        dispatcher.local_llm,
        "answer_screen_query",
        lambda *args, **kwargs: {"answer": "I see your desktop with VS Code.", "raw_response": "I see your desktop with VS Code."}
    )
    chunk = SpeechChunk(text="What do you see on my screen?", is_final=True)
    event = dispatcher.process_speech_frame(chunk)
    assert event.action_type == ActionType.ANSWER_USER
    assert "I see your desktop" in event.verbal_response
    assert "I see your desktop" in event.llm_output


def test_close_yourselves_plural_seam(dispatcher):
    """Verifies: 'Close yourselves.' triggers ActionType.SHUTDOWN."""
    chunk = SpeechChunk(text="Close yourselves.", is_final=True)
    event = dispatcher.process_speech_frame(chunk)
    assert event.action_type == ActionType.SHUTDOWN
    assert "Goodbye" in event.verbal_response


def test_close_window_seam(dispatcher):
    """Verifies: 'close window' closes active window (0x200)."""
    chunk = SpeechChunk(text="close window", is_final=True)
    event = dispatcher.process_speech_frame(chunk)
    assert event.action_type == ActionType.CLOSE_WINDOW
    assert "0x200" in dispatcher.os_controller.closed_windows
    assert "Visual Studio Code" in event.verbal_response


def test_close_targeted_window_seam(dispatcher, monkeypatch):
    """Verifies: 'Close that Discord app.' through reasoner closes targeted window."""
    monkeypatch.setattr(
        dispatcher.local_llm,
        "reason_intent",
        lambda *args, **kwargs: {"intent": "close_window", "target": "WhatsApp", "speech": "Closing WhatsApp"}
    )
    chunk = SpeechChunk(text="Close that WhatsApp app.", is_final=True)
    event = dispatcher.process_speech_frame(chunk)
    assert event.action_type == ActionType.CLOSE_WINDOW
    assert "0x100" in dispatcher.os_controller.closed_windows
    assert "WhatsApp" in event.verbal_response


def test_close_file_manager_seam(dispatcher):
    """Verifies: 'close file manager' immediately targets and closes Nautilus."""
    chunk = SpeechChunk(text="close file manager", is_final=True)
    event = dispatcher.process_speech_frame(chunk)
    assert event.action_type == ActionType.CLOSE_WINDOW
    assert "0x300" in dispatcher.os_controller.closed_windows
    assert "Home" in event.verbal_response


def test_where_is_close_file_manager_colloquial_seam(dispatcher):
    """Verifies: 'Where is close file manager?' closes Nautilus window without falling into error response."""
    chunk = SpeechChunk(text="Where is close file manager?", is_final=True)
    event = dispatcher.process_speech_frame(chunk)
    assert event.action_type == ActionType.CLOSE_WINDOW
    assert "0x300" in dispatcher.os_controller.closed_windows
    assert "Home" in event.verbal_response


def test_please_close_file_manager_seam(dispatcher):
    """Verifies: 'please close file manager' closes Nautilus window."""
    chunk = SpeechChunk(text="please close file manager", is_final=True)
    event = dispatcher.process_speech_frame(chunk)
    assert event.action_type == ActionType.CLOSE_WINDOW
    assert "0x300" in dispatcher.os_controller.closed_windows


def test_close_nonexistent_window_safe_noop(dispatcher):
    """Verifies: closing a non-existent app does NOT close the active window."""
    chunk = SpeechChunk(text="close spotify", is_final=True)
    event = dispatcher.process_speech_frame(chunk)
    assert event.action_type == ActionType.NOOP
    assert "Could not find window" in event.verbal_response
    assert "0x200" not in dispatcher.os_controller.closed_windows


def test_open_youtube_in_browser_seam(dispatcher):
    """Verifies: 'Open YouTube in my browser.' resolves to https://www.youtube.com."""
    chunk = SpeechChunk(text="Open YouTube in my browser.", is_final=True)
    event = dispatcher.process_speech_frame(chunk)
    assert event.action_type == ActionType.OPEN_URL
    assert "youtube.com" in event.target
    assert "https://www.youtube.com" in dispatcher.os_controller.opened_urls


def test_dispatch_memory_cache_fast_path(dispatcher):
    """Verifies that once a command is learned, subsequent calls hit the <5ms cache."""
    dispatcher.memory_store.record("open my project folder", "launch_app", "dolphin")

    chunk = SpeechChunk(text="open my project folder", is_final=True)
    event = dispatcher.process_speech_frame(chunk)
    assert event.action_type == ActionType.LAUNCH_APP
    assert event.target == "dolphin"
    assert "Cache <5ms" in event.llm_output


def test_screen_query_with_ocr_seam(dispatcher, monkeypatch):
    """Verifies that 'What do you see inside File Manager?' extracts OCR text and answers user."""
    monkeypatch.setattr(
        dispatcher.grounder.detector,
        "extract_screen_text",
        lambda img: "Downloads | Projects | Documents | photos.jpg"
    )
    chunk = SpeechChunk(text="What do you see inside File Manager?", is_final=True)
    event = dispatcher.process_speech_frame(chunk, screenshot_bytes=b"dummy_png")
    assert event.action_type == ActionType.ANSWER_USER
    assert "Downloads" in event.verbal_response or "Projects" in event.verbal_response or "Visual Studio Code" in event.verbal_response


def test_go_to_downloads_visual_navigation_seam(dispatcher, monkeypatch):
    """Verifies that 'Go to downloads.' visually grounds and clicks the element without touching filesystem."""
    monkeypatch.setattr(
        dispatcher.grounder,
        "locate_target",
        lambda img, target: ((350, 420), "fast_local", 12.0)
    )
    chunk = SpeechChunk(text="Go to downloads.", is_final=True)
    event = dispatcher.process_speech_frame(chunk, screenshot_bytes=b"dummy_png")
    assert event.action_type == ActionType.CLICK_BOX
    assert event.target == "(350, 420)"
    assert "downloads" in event.verbal_response.lower()
    # Confirm move_and_click was executed
    assert len(dispatcher.input_controller.history) > 0
    assert dispatcher.input_controller.history[-1]["action"] == "click"


def test_verbal_correction_invalidates_memory_cache(dispatcher):
    """Verifies that saying 'Wrong window' invalidates the last executed command from memory cache."""
    dispatcher.memory_store.record("my code editor", "launch_app", "subl")
    assert dispatcher.memory_store.lookup("my code editor") is not None

    # Run the command to set _last_executed_command
    chunk1 = SpeechChunk(text="my code editor", is_final=True)
    dispatcher.process_speech_frame(chunk1)
    assert dispatcher._last_executed_command == "my code editor"

    # User corrects: "wrong window"
    chunk2 = SpeechChunk(text="wrong window", is_final=True)
    abort_event = dispatcher.process_speech_frame(chunk2)
    assert abort_event.action_type == ActionType.ABORT

    # Cache should now be invalidated
    assert dispatcher.memory_store.lookup("my code editor") is None
    assert dispatcher._last_executed_command is None





