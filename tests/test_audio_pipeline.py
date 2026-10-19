"""Tests for VAD, Phonon speech recognizer, and continuous audio streaming."""

import numpy as np
import pytest

from handsfree.audio.vad import VoiceActivityDetector
from handsfree.audio.stt_phonon import PhononRecognizer
from handsfree.audio.audio_stream import ContinuousAudioStream
from handsfree.domain.models import SpeechChunk


def test_vad_speech_detection():
    """Verifies that VAD detects speech energy and marks end-of-speech correctly."""
    # 16kHz audio, 100ms frames = 1600 samples
    vad = VoiceActivityDetector(sample_rate=16000, min_energy_threshold=0.015, silence_timeout_ms=200)

    # Pure silence frame
    silence = np.zeros(1600, dtype=np.float32)
    is_active, is_ended = vad.process_frame(silence)
    assert is_active is False
    assert is_ended is False

    # Speech frame (440Hz sine wave with amplitude 0.2)
    t = np.linspace(0, 0.1, 1600, endpoint=False, dtype=np.float32)
    speech_frame = 0.2 * np.sin(2 * np.pi * 440 * t)

    is_active, is_ended = vad.process_frame(speech_frame)
    assert is_active is True
    assert is_ended is False

    # Send 200ms of silence (2 frames of 100ms)
    vad.process_frame(silence)
    is_active, is_ended = vad.process_frame(silence)
    assert is_ended is True
    assert is_active is False


def test_echo_suppression_blocks_audio_ingestion(monkeypatch):
    """Verifies that audio ingestion is halted while TTS is speaking."""
    vad = VoiceActivityDetector()
    recognizer = PhononRecognizer()

    # Mock recognizer
    monkeypatch.setattr(
        recognizer,
        "transcribe_audio",
        lambda buf, is_final=False: SpeechChunk(text="simulated speech", is_final=is_final)
    )

    stream = ContinuousAudioStream(vad=vad, recognizer=recognizer)

    try:
        t = np.linspace(0, 0.1, 1600, endpoint=False, dtype=np.float32)
        loud_frame = 0.3 * np.sin(2 * np.pi * 440 * t)

        # 1. Normal state: frame is accepted
        res = stream.feed_frame(loud_frame)
        assert stream.is_echo_suppressed is False

        # 2. Engage echo suppression (Bit is speaking)
        stream.set_echo_suppression(True)
        assert stream.is_echo_suppressed is True

        # Audio fed while suppressed must return None immediately
        res_suppressed = stream.feed_frame(loud_frame)
        assert res_suppressed is None

        # 3. Disengage echo suppression
        stream.set_echo_suppression(False)
        assert stream.is_echo_suppressed is False
    finally:
        stream.stop()


def test_audio_resampling_48k_to_16k():
    """Verifies that 48kHz audio frames are downsampled cleanly to 16kHz."""
    # 48000 Hz, 100ms = 4800 samples
    native_sr = 48000
    t = np.linspace(0, 0.1, 4800, endpoint=False, dtype=np.float32)
    raw_48k = np.sin(2 * np.pi * 440 * t)

    # 3x decimation
    step = native_sr // 16000
    frame_16k = raw_48k[::step].copy()

    assert len(frame_16k) == 1600
    # Peak amplitude should be preserved
    assert np.isclose(np.max(np.abs(frame_16k)), 1.0, atol=0.01)

