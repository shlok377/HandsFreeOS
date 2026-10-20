"""Tests for Hyprland controller, screen capture, and Bézier input emulation."""

import os
import tempfile
import threading
import time
import pytest

from handsfree.os_layer.bezier import generate_human_trajectory
from handsfree.os_layer.input_controller import AdaptiveInputController
from handsfree.os_layer.hyprland import HyprlandController
from handsfree.domain.models import WindowInfo


def test_bezier_trajectory_curvature_and_humanization():
    """Verifies that mouse paths exhibit natural non-linear curvature and easing."""
    start = (100, 100)
    end = (800, 600)
    steps = 30

    waypoints = generate_human_trajectory(start, end, steps=steps)

    assert len(waypoints) == steps
    # Check end coordinate
    final_x, final_y, _ = waypoints[-1]
    assert final_x == end[0]
    assert final_y == end[1]

    # Verify curvature: points should not lie strictly on the straight chord
    # Chord slope: m = (600 - 100) / (800 - 100) = 5/7 = ~0.714
    chord_deviations = []
    for x, y, delay in waypoints[5:25]:
        expected_y = 100 + 0.714 * (x - 100)
        chord_deviations.append(abs(y - expected_y))
        assert delay > 0.0, "Step delay must be positive"

    # There should be non-zero organic curvature
    assert max(chord_deviations) > 2.0, "Trajectory lacks organic curve deviation"


def test_adaptive_input_dispatch_modes():
    """Verifies adaptive input differentiation between desktop and browser."""
    controller = AdaptiveInputController(current_pos=(50, 50), dry_run=True)

    # Desktop mode
    controller.move_and_click(200, 200, is_browser=False)
    assert controller.history[-1]["action"] == "click"
    assert controller.history[-1]["is_browser"] is False
    assert controller.current_pos == (200, 200)

    # Browser mode
    controller.move_and_click(400, 300, is_browser=True)
    assert controller.history[-1]["action"] == "click"
    assert controller.history[-1]["is_browser"] is True
    assert controller.current_pos == (400, 300)


def test_live_input_interruption():
    """Verifies that abort_in_flight() interrupts in-flight browser movement immediately."""
    controller = AdaptiveInputController(current_pos=(0, 0), dry_run=True)

    # Run browser movement in background thread
    def move_task():
        controller.move_and_click(1000, 1000, is_browser=True)

    thread = threading.Thread(target=move_task)
    thread.start()

    # Trigger abort quickly (<20ms)
    time.sleep(0.015)
    controller.abort_in_flight()
    thread.join(timeout=1.0)

    # Verify that the action was aborted
    aborted_actions = [h for h in controller.history if h.get("action") == "aborted"]
    assert len(aborted_actions) > 0, "Expected movement to be halted by abort signal"


def test_hyprland_controller_smart_focus(monkeypatch):
    """Verifies that open_url focuses existing browser window instead of re-launching."""
    controller = HyprlandController()

    # Mock open windows with an existing WhatsApp window
    mock_windows = [
        WindowInfo(address="0xabc", title="WhatsApp - Google Chrome", class_name="google-chrome", is_focused=False),
        WindowInfo(address="0xdef", title="Terminal", class_name="kitty", is_focused=True),
    ]

    focused_addresses = []
    monkeypatch.setattr(controller, "get_open_windows", lambda: mock_windows)
    monkeypatch.setattr(controller, "focus_window", lambda addr: focused_addresses.append(addr) or True)

    # Ask to open WhatsApp Web
    result = controller.open_url("https://web.whatsapp.com")
    assert result is True
    assert "0xabc" in focused_addresses, "Smart focus did not target existing WhatsApp window"


def test_hyprland_controller_create_file():
    """Verifies direct file creation with automatic parent directories."""
    controller = HyprlandController()

    with tempfile.TemporaryDirectory() as tmpdir:
        target_file = os.path.join(tmpdir, "nested", "test_doc.txt")
        success = controller.create_file(target_file, "hello world")
        assert success is True
        assert os.path.exists(target_file)
        with open(target_file, "r") as f:
            assert f.read() == "hello world"


def test_hyprland_is_browser_window():
    """Verifies browser class recognition."""
    controller = HyprlandController()
    w_chrome = WindowInfo(address="0x1", title="", class_name="google-chrome")
    w_firefox = WindowInfo(address="0x2", title="", class_name="firefox")
    w_term = WindowInfo(address="0x3", title="", class_name="kitty")

    assert controller.is_browser_window(w_chrome) is True
    assert controller.is_browser_window(w_firefox) is True
    assert controller.is_browser_window(w_term) is False
    assert controller.is_browser_window(None) is False


def test_hyprland_controller_close_window(monkeypatch):
    """Verifies close_window issues hyprctl dispatch closewindow or killactive."""
    controller = HyprlandController()
    dispatched = []
    monkeypatch.setattr(controller, "_run_hyprctl", lambda args: dispatched.append(args) or "ok")

    # Close specific address
    res1 = controller.close_window("0xabc")
    assert res1 is True
    assert dispatched[-1] == ["dispatch", "closewindow", "address:0xabc"]

    # Close specific class
    res2 = controller.close_window("discord")
    assert res2 is True
    assert dispatched[-1] == ["dispatch", "closewindow", "discord"]

    # Close active window
    res3 = controller.close_window("")
    assert res3 is True
    assert dispatched[-1] == ["dispatch", "killactive"]

