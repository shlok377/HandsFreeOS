"""Tests for redesigned HandsFreeOS TUI Dashboard."""

from rich.console import Console
import pytest

from handsfree.domain.models import SpeechChunk, WindowInfo
from handsfree.ui.telemetry import TelemetryCollector
from handsfree.ui.tui import HandsFreeDashboard, generate_waveform, format_meter_bar


def test_waveform_generation_silence():
    top, mid, bot = generate_waveform(rms=0.001, width=30)
    assert top.startswith("[") and top.endswith("]")
    assert mid.startswith("[") and mid.endswith("]")
    assert bot.startswith("[") and bot.endswith("]")
    # In silence, top and bottom are mostly empty space
    assert top.count(" ") > 20
    assert bot.count(" ") > 20
    assert "·" in mid


def test_waveform_generation_active_voice():
    top, mid, bot = generate_waveform(rms=0.05, width=30)
    assert top.startswith("[") and top.endswith("]")
    assert mid.startswith("[") and mid.endswith("]")
    assert bot.startswith("[") and bot.endswith("]")
    # With active voice, top and bottom should have peak characters like ':' or '.'
    assert any(c in top for c in [":", ".", "'"])
    assert any(c in bot for c in [":", ".", "'"])


def test_format_meter_bar():
    bar = format_meter_bar(percent=50.0, total_blocks=8)
    assert bar.startswith("[") and bar.endswith("]")
    assert "█" in bar or "▉" in bar
    assert "▒" in bar


def test_dashboard_initial_render():
    console = Console(width=120, height=35)
    dashboard = HandsFreeDashboard(console=console)
    layout = dashboard.render()
    assert layout is not None
    # Verify console can render layout without exceptions
    with console.capture() as capture:
        console.print(layout)
    output = capture.get()
    assert "PERCEPTION & DECISION" in output
    assert "ACTION EXECUTION LOG" in output
    assert "SYSTEM TELEMETRY" in output
    assert "PIPELINE LATENCY" in output
    assert "Live Speech:" in output
    assert "Mic Level:" in output
    assert "Status: Active Listening" in output


def test_dashboard_log_entries():
    console = Console(width=120, height=35)
    dashboard = HandsFreeDashboard(console=console)
    dashboard.add_heard("How many Discords do I have open?")
    dashboard.add_action("answer_user", "You have 1 Discord open.")

    rendered = dashboard._render_action_log()
    with console.capture() as capture:
        console.print(rendered)
    output = capture.get()
    assert "HEARD" in output
    assert "How many Discords do I have open?" in output
    assert "ACTION" in output
    assert "answer_user" in output


def test_dashboard_llm_json_formatting():
    dashboard = HandsFreeDashboard()
    json_text = '{"intent": "answer_user", "target": "", "speech": "I have 2 apps open."}'
    dashboard.update_llm_output(json_text)

    panel = dashboard._render_llm_output()
    assert panel is not None
