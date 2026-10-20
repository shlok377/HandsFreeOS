"""Unit tests for context-aware interruption and abort scoping."""

import pytest
from handsfree.decision.jev_engine import JevEngine
from handsfree.loop.interruption import InterruptionCoordinator
from handsfree.os_layer.input_controller import AdaptiveInputController


@pytest.fixture
def coordinator():
    jev = JevEngine()
    input_ctrl = AdaptiveInputController(dry_run=True)
    return InterruptionCoordinator(decision_engine=jev, input_controller=input_ctrl)


def test_standalone_abort_keywords_trigger_abort(coordinator):
    """Verifies that standalone halt keywords trigger abort."""
    for word in ["wait", "stop", "hold on", "cancel", "nevermind"]:
        assert coordinator.check_and_handle_abort(word) is True


def test_verb_object_commands_do_not_trigger_abort(coordinator):
    """Verifies that commands like 'Quit Discord' are not falsely intercepted as aborts."""
    non_aborts = [
        "Quit Discord from my browser.",
        "quit discord",
        "stop listening",
        "stop the music",
        "bye bye",
        "Quit, quit.",
        "File manager please.",
        "please",
        "now",
    ]
    for phrase in non_aborts:
        assert coordinator.check_and_handle_abort(phrase) is False, f"Expected '{phrase}' to not be an abort"


def test_in_flight_action_interruption(coordinator):
    """Verifies that any abort token during an active in-flight action halts immediately."""
    coordinator.set_action_active(True)
    assert coordinator.is_action_active() is True

    # User says 'no not that' while moving mouse
    assert coordinator.check_and_handle_abort("no not that") is True
    assert coordinator.is_action_active() is False
