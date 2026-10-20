"""Tests for conversational TTS feedback and echo suppression triggering."""

import time
import pytest
from handsfree.voice.tts_kokoro import KokoroTTS


def test_tts_state_callback_and_echo_trigger():
    """Verifies that TTS properly signals when it starts and stops speaking."""
    state_transitions = []

    def on_change(is_speaking: bool):
        state_transitions.append(is_speaking)

    tts = KokoroTTS(on_state_change=on_change, dry_run=True)

    try:
        # Speak synchronously
        tts.speak("Opening WhatsApp now", non_blocking=False)

        assert "Opening WhatsApp now" in tts.spoken_phrases
        assert True in state_transitions
        assert False in state_transitions
        # The last transition should be False (finished speaking)
        assert state_transitions[-1] is False
    finally:
        tts.stop()


def test_tts_non_blocking_queue():
    """Verifies non-blocking speech enqueueing."""
    tts = KokoroTTS(dry_run=True)

    try:
        tts.speak("First action")
        tts.speak("Second action")

        assert len(tts.spoken_phrases) == 2
        time.sleep(0.1)  # Allow worker to process
    finally:
        tts.stop()
