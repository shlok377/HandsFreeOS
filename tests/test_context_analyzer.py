"""Unit tests for AppContextAnalyzer."""

import pytest
from handsfree.decision.context_analyzer import AppContextAnalyzer
from handsfree.domain.models import WindowInfo


def test_discord_video_call_detection():
    analyzer = AppContextAnalyzer()
    win = WindowInfo(
        address="0x1",
        title="• Discord | \"DSA\" | These Two <3",
        class_name="discord",
        app_id="discord",
    )
    screen_ocr = "mute | disconnect | camera | voice-channels | announcements"
    ctx = analyzer.analyze_context(win, screen_ocr=screen_ocr)

    assert ctx.app_name == "Discord"
    assert ctx.activity_type == "video_call"
    assert ctx.is_video_call is True
    assert "Discord video call" in ctx.context_label


def test_discord_voice_call_detection():
    analyzer = AppContextAnalyzer()
    win = WindowInfo(
        address="0x2",
        title="• Discord | Friends",
        class_name="discord",
        app_id="discord",
    )
    screen_ocr = "disconnect | mute | general | text-channels"
    ctx = analyzer.analyze_context(win, screen_ocr=screen_ocr)

    assert ctx.app_name == "Discord"
    assert ctx.activity_type == "voice_call"
    assert "on a Discord call" in ctx.context_label


def test_google_meet_detection():
    analyzer = AppContextAnalyzer()
    win = WindowInfo(
        address="0x3",
        title="Meet - abc-defg-hij - Google Chrome",
        class_name="google-chrome",
    )
    ctx = analyzer.analyze_context(win)

    assert ctx.app_name == "Video Meeting"
    assert ctx.is_video_call is True
    assert "online video meeting" in ctx.context_label


def test_zoom_meeting_detection():
    analyzer = AppContextAnalyzer()
    win = WindowInfo(
        address="0x4",
        title="Zoom Meeting",
        class_name="zoom",
    )
    ctx = analyzer.analyze_context(win)

    assert ctx.app_name == "Video Meeting"
    assert ctx.is_video_call is True
    assert "online video meeting" in ctx.context_label


def test_file_manager_context():
    analyzer = AppContextAnalyzer()
    win = WindowInfo(
        address="0x5",
        title="Downloads",
        class_name="org.gnome.Nautilus",
    )
    ctx = analyzer.analyze_context(win)

    assert ctx.app_name == "File Manager"
    assert ctx.activity_type == "browsing_files"
    assert "browsing your Downloads folder" in ctx.context_label


def test_ide_coding_context():
    analyzer = AppContextAnalyzer()
    win = WindowInfo(
        address="0x6",
        title="dispatch.py - HandsFreeOS - Visual Studio Code",
        class_name="code",
    )
    ctx = analyzer.analyze_context(win)

    assert ctx.app_name == "Code Editor"
    assert ctx.activity_type == "coding"
    assert "working in your code editor" in ctx.context_label
