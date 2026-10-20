"""Unit tests for persistent episodic memory store and fast semantic cache."""

import os
import tempfile
import time
import pytest
from handsfree.decision.memory import EpisodicMemoryStore


def test_memory_record_and_fast_lookup():
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = os.path.join(tmpdir, "test_memory.json")
        store = EpisodicMemoryStore(storage_path=store_path)

        # Record intent
        store.record(
            phrase="Open YouTube in my browser",
            intent="open_url",
            target="https://www.youtube.com",
            speech="Opening YouTube",
        )

        # Fast lookup benchmark (<5ms SLA)
        start = time.perf_counter()
        result = store.lookup("Hey Bit, open youtube in my browser.")
        latency_ms = (time.perf_counter() - start) * 1000.0

        assert result is not None
        assert result["intent"] == "open_url"
        assert result["target"] == "https://www.youtube.com"
        assert result["from_cache"] is True
        assert latency_ms < 5.0, f"Memory lookup took {latency_ms:.2f}ms, exceeding 5ms SLA"


def test_memory_persistence_across_restarts():
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = os.path.join(tmpdir, "test_memory.json")
        store1 = EpisodicMemoryStore(storage_path=store_path)
        store1.record("close that discord app", "close_window", "discord", "Closing Discord")

        # New instance pointing to same file
        store2 = EpisodicMemoryStore(storage_path=store_path)
        cached = store2.lookup("close that discord app")
        assert cached is not None
        assert cached["intent"] == "close_window"
        assert cached["target"] == "discord"


def test_memory_invalidation_on_correction():
    with tempfile.TemporaryDirectory() as tmpdir:
        store_path = os.path.join(tmpdir, "test_memory.json")
        store = EpisodicMemoryStore(storage_path=store_path)
        store.record("my editor", "launch_app", "gedit")

        assert store.lookup("my editor") is not None

        # User corrects: invalidate and re-record
        store.invalidate("my editor")
        assert store.lookup("my editor") is None

        store.record("my editor", "launch_app", "subl")
        updated = store.lookup("my editor")
        assert updated is not None
        assert updated["target"] == "subl"
