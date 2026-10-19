"""Interactive Rich TUI Dashboard for HandsFreeOS."""

import time
from typing import Optional
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from handsfree.domain.models import ActionEvent, JevDecision, SpeechChunk, WindowInfo


class HandsFreeDashboard:
    """Real-time terminal user interface displaying speech stream, Jev gauges, and action logs."""

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self.layout = Layout()

        self.last_speech: str = "(Listening...)"
        self.last_decision: Optional[JevDecision] = None
        self.active_window: Optional[WindowInfo] = None
        self.action_logs: list[str] = []
        self.tts_status: str = "Idle"
        self.mic_level: float = 0.0

        self._setup_layout()

    def _setup_layout(self) -> None:
        """Configures the dashboard grid."""
        self.layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=3),
        )
        self.layout["body"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="right", ratio=1),
        )

    def update_speech(self, chunk: SpeechChunk) -> None:
        """Updates streaming transcript display."""
        self.last_speech = chunk.text

    def update_audio_level(self, rms: float) -> None:
        """Updates live microphone input level."""
        self.mic_level = rms

    def update_decision(self, decision: JevDecision) -> None:
        """Updates Jev decision metrics."""
        self.last_decision = decision

    def update_window(self, win: Optional[WindowInfo]) -> None:
        """Updates active window context."""
        self.active_window = win

    def add_log(self, message: str) -> None:
        """Appends to chronological action log."""
        timestamp = time.strftime("%H:%M:%S")
        self.action_logs.append(f"[{timestamp}] {message}")
        if len(self.action_logs) > 20:
            self.action_logs.pop(0)

    def render(self) -> Layout:
        """Renders the complete TUI frame."""
        # Header
        header_text = Text(" HandsFreeOS ('Bit') - Real-Time Autonomous OS Control", style="bold cyan")
        self.layout["header"].update(Panel(header_text, style="blue"))

        # Left panel: Speech Stream & Jev Decision Gauges
        left_table = Table.grid(padding=1)
        left_table.add_column("Key", style="bold white")
        left_table.add_column("Value")

        left_table.add_row("Live Speech:", Text(self.last_speech, style="green bold"))

        # Live visual mic meter
        bar_len = 15
        filled = min(bar_len, int((self.mic_level / 0.08) * bar_len))
        meter_color = "green" if filled > 3 else "dim white"
        meter = f"[{'█' * filled}{'░' * (bar_len - filled)}]"
        left_table.add_row("Mic Level:", Text(f"{meter} ({self.mic_level:.3f})", style=meter_color))

        if self.last_decision:
            conf_color = "green" if self.last_decision.confidence > 0.8 else "yellow"
            left_table.add_row("Jev Decision:", f"{self.last_decision.decision_type.upper()} ({self.last_decision.value})")
            left_table.add_row("Confidence:", Text(f"{self.last_decision.confidence * 100:.1f}%", style=conf_color))
            left_table.add_row("Latency:", f"{self.last_decision.latency_ms:.1f}ms")
        else:
            left_table.add_row("Jev State:", "Standby (<30ms System-1)")

        win_title = self.active_window.title if self.active_window else "None"
        win_cls = self.active_window.class_name if self.active_window else "None"
        left_table.add_row("Active Window:", f"{win_title} ({win_cls})")
        left_table.add_row("TTS Voice:", f"{self.tts_status}")

        self.layout["left"].update(Panel(left_table, title="[bold]Perception & Decision[/bold]", border_style="cyan"))

        # Right panel: Action logs
        log_text = "\n".join(self.action_logs[-10:]) if self.action_logs else "No actions dispatched yet."
        self.layout["right"].update(Panel(log_text, title="[bold]Action Execution Log[/bold]", border_style="magenta"))

        # Footer
        footer_text = Text("Status: Active Listening (Phonon-2 + Jev + YOLO) | Press Ctrl+C to Exit", style="dim")
        self.layout["footer"].update(Panel(footer_text, style="dim"))

        return self.layout
