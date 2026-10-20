"""Tests for redesigned HandsFreeOS TUI Dashboard public interface."""

from rich.console import Console
import pytest

from handsfree.domain.models import JevDecision, SpeechChunk, WindowInfo
from handsfree.ui.telemetry import TelemetryCollector
from handsfree.ui.tui import (
    HandsFreeDashboard,
    generate_waveform,
    generate_inward_spectrum_box,
    format_meter_bar,
)


def test_inward_spectrum_box_calm_mode():
    box_lines = generate_inward_spectrum_box(input_level=0.08, width=56, height=10)
    assert len(box_lines) == 10
    top = box_lines[0]
    bot = box_lines[-1]
    assert top.startswith("╭") and top.endswith("╮")
    assert bot.startswith("╰") and bot.endswith("╯")

    # In calm mode (<= 0.2), inner rows must stay calm with faint ticks and no deep blocks
    inner_rows = box_lines[1:-1]
    for row in inner_rows:
        assert row.startswith("│") and row.endswith("│")
        # Center should be empty / calm
        center = row[10:-10]
        assert center.strip() == ""


def test_inward_spectrum_box_active_mode():
    box_lines = generate_inward_spectrum_box(input_level=0.55, width=56, height=10)
    assert len(box_lines) == 10
    inner_rows = box_lines[1:-1]
    # In active mode (> 0.2), vertical walls project block bars inward
    has_inward_blocks = any("█" in row or "▉" in row or "▊" in row for row in inner_rows)
    assert has_inward_blocks


def test_inward_spectrum_box_frequency_mapping():
    # Provide heavy bass in bottom band, silent treble in top band
    bands = [0.9, 0.7, 0.4, 0.1, 0.0, 0.0, 0.0, 0.0]
    box_lines = generate_inward_spectrum_box(input_level=0.6, spectrum_bands=bands, width=56, height=10)
    # Bottom inner row (near end) should project deeper than top inner row (near start)
    top_row = box_lines[1]
    bottom_row = box_lines[-2]
    top_blocks = sum(top_row.count(c) for c in ["█", "▉", "▊", "▋", "▌", "▍", "▎"])
    bot_blocks = sum(bottom_row.count(c) for c in ["█", "▉", "▊", "▋", "▌", "▍", "▎"])
    assert bot_blocks > top_blocks


def test_format_meter_bar():
    bar = format_meter_bar(percent=50.0, total_blocks=8)
    assert bar.startswith("[") and bar.endswith("]")
    assert "█" in bar or "▉" in bar
    assert "▒" in bar


def test_dashboard_initial_render():
    console = Console(width=130, height=35)
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
    console = Console(width=130, height=35)
    dashboard = HandsFreeDashboard(console=console)
    dashboard.add_heard("How many Discords do I have open?")
    dashboard.add_action("answer_user", "You have 1 Discord open.")

    layout = dashboard.render()
    with console.capture() as capture:
        console.print(layout)
    output = capture.get()
    assert "HEARD" in output
    assert "How many Discords do I have open?" in output
    assert "ACTION" in output
    assert "answer_user" in output


def test_dashboard_llm_json_formatting():
    console = Console(width=130, height=35)
    dashboard = HandsFreeDashboard(console=console)
    json_text = '{"intent": "answer_user", "target": "", "speech": "I have 2 apps open."}'
    dashboard.update_llm_output(json_text)

    layout = dashboard.render()
    with console.capture() as capture:
        console.print(layout)
    output = capture.get()
    assert '"intent"' in output
    assert '"answer_user"' in output


def test_dashboard_decision_rendering():
    console = Console(width=130, height=35)
    dashboard = HandsFreeDashboard(console=console)
    decision = JevDecision(
        decision_type="choice",
        value="focus_window",
        confidence=0.95,
        latency_ms=7.5,
    )
    dashboard.update_decision(decision)

    layout = dashboard.render()
    with console.capture() as capture:
        console.print(layout)
    output = capture.get()
    assert "Jev Decision:" in output
    assert "CHOICE" in output
    assert "95%" in output
