"""Live interruption and abort coordinator."""

import logging
from typing import Optional

from handsfree.domain.interfaces import IDecisionEngine, IInputController

logger = logging.getLogger(__name__)


class InterruptionCoordinator:
    """Detects live abort signals in <25ms and halts execution."""

    def __init__(
        self,
        decision_engine: IDecisionEngine,
        input_controller: IInputController,
    ):
        self.decision_engine = decision_engine
        self.input_controller = input_controller
        self._is_active_action = False

    def set_action_active(self, active: bool) -> None:
        """Sets whether an execution action is currently underway."""
        self._is_active_action = active

    def check_and_handle_abort(self, speech_text: str) -> bool:
        """Evaluates speech chunk for abort intent. If detected, halts input controller immediately."""
        is_abort = self.decision_engine.detect_interruption(speech_text)
        if is_abort:
            logger.warning(f"Live abort triggered by speech: '{speech_text}'")
            self.input_controller.abort_in_flight()
            self._is_active_action = False
            return True
        return False
