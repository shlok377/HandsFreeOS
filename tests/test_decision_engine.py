"""Tests for Jev System-1 decision engine and safety scorer."""

import time
import pytest
from handsfree.decision.jev_engine import JevEngine
from handsfree.decision.safety import SafetyScorer
from handsfree.domain.models import BoundingBox, WindowInfo


@pytest.fixture
def jev():
    return JevEngine()


@pytest.fixture
def safety():
    return SafetyScorer()


def test_ambient_speech_filtering(jev):
    """Verifies that PC commands are accepted and ambient chit-chat is ignored."""
    assert jev.filter_ambient_speech("Hey Bit! open webwhatsapp") is True
    assert jev.filter_ambient_speech("hey bit! Open herdr") is True
    assert jev.filter_ambient_speech("make a new txt file and type in hello world") is True
    assert jev.filter_ambient_speech("click on the search bar") is True
    assert jev.filter_ambient_speech("close this window") is True

    # Ambient non-commands
    assert jev.filter_ambient_speech("yeah so then he told me that yesterday") is False
    assert jev.filter_ambient_speech("I really love eating pizza on Fridays") is False
    assert jev.filter_ambient_speech("") is False


def test_yolo_box_selection(jev):
    """Verifies Jev matches user intent to a YOLO bounding box in <40ms."""
    boxes = [
        BoundingBox(id=1, label="Search or start new chat", x_min=10, y_min=20, x_max=200, y_max=60),
        BoundingBox(id=2, label="New chat", x_min=210, y_min=20, x_max=250, y_max=60),
        BoundingBox(id=3, label="Settings", x_min=260, y_min=20, x_max=300, y_max=60),
        BoundingBox(id=4, label="Mom", x_min=10, y_min=80, x_max=200, y_max=120),
    ]

    start = time.perf_counter()
    match = jev.select_yolo_box(boxes, "search bar")
    latency = (time.perf_counter() - start) * 1000.0

    assert match is not None
    assert match.id == 1
    assert latency < 40.0, f"Latency {latency:.2f}ms exceeded 40ms SLA"

    # Match contact
    match_mom = jev.select_yolo_box(boxes, "chat with Mom")
    assert match_mom is not None
    assert match_mom.id == 4


def test_live_interruption_detection(jev):
    """Verifies Jev detects abort signals in <25ms."""
    test_aborts = ["wait", "no stop", "cancel that", "hold on", "nevermind"]
    for phrase in test_aborts:
        start = time.perf_counter()
        is_abort = jev.detect_interruption(phrase)
        latency = (time.perf_counter() - start) * 1000.0
        assert is_abort is True
        assert latency < 25.0, f"Latency {latency:.2f}ms exceeded 25ms SLA"

    # Non-aborts
    assert jev.detect_interruption("now type hello world") is False
    assert jev.detect_interruption("and send the message") is False


def test_window_disambiguation(jev):
    """Verifies Jev matches open Hyprland windows in <35ms."""
    windows = [
        WindowInfo(address="0x123", title="WhatsApp - Google Chrome", class_name="google-chrome", workspace_id=1),
        WindowInfo(address="0x456", title="Visual Studio Code", class_name="code", workspace_id=2),
        WindowInfo(address="0x789", title="kitty ~", class_name="kitty", workspace_id=3, is_focused=True),
    ]

    start = time.perf_counter()
    w = jev.disambiguate_window(windows, "switch to WhatsApp")
    latency = (time.perf_counter() - start) * 1000.0

    assert w is not None
    assert w.class_name == "google-chrome"
    assert latency < 35.0, f"Latency {latency:.2f}ms exceeded 35ms SLA"

    # "close this" should resolve focused window
    w_this = jev.disambiguate_window(windows, "close this")
    assert w_this is not None
    assert w_this.class_name == "kitty"


def test_safety_scoring(safety):
    """Verifies calibrated P(destructive) scoring."""
    # Destructive
    score_del, _ = safety.compute_destructive_score("delete all files in downloads")
    assert score_del >= 0.80
    assert safety.requires_confirmation("rm -rf ~/test") is True
    assert safety.requires_confirmation("wipe database") is True

    # Benign
    score_open, _ = safety.compute_destructive_score("open webwhatsapp")
    assert score_open <= 0.20
    assert safety.requires_confirmation("make a new txt file") is False
    assert safety.requires_confirmation("scroll down") is False


def test_dictation_classification(jev):
    """Verifies dictation vs command classification when an input is focused."""
    # In focused input, conversational text is dictation
    assert jev.classify_dictation("I will be home by 7pm", input_focused=True) is True
    assert jev.classify_dictation("hello there world", input_focused=True) is True

    # Explicit commands should still not be dictation
    assert jev.classify_dictation("close this window", input_focused=True) is False
    assert jev.classify_dictation("open webwhatsapp", input_focused=True) is False

    # Not focused -> never dictation
    assert jev.classify_dictation("I will be home by 7pm", input_focused=False) is False
