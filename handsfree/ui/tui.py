"""Interactive Cyberpunk / Sci-Fi Terminal User Interface Dashboard for HandsFreeOS."""

import json
import math
import time
from typing import Any, Dict, List, Optional, Tuple

from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from handsfree.domain.models import JevDecision, SpeechChunk, WindowInfo
from handsfree.ui.telemetry import SystemMetrics, TelemetryCollector


def format_meter_bar(percent: float, total_blocks: int = 8, filled_char: str = "█", empty_char: str = "▒") -> str:
    """Formats a fixed-width percentage block bar e.g. [████▒▒▒▒]."""
    clamped = max(0.0, min(100.0, percent))
    filled_count = int(round((clamped / 100.0) * total_blocks))
    filled_count = max(0, min(total_blocks, filled_count))
    empty_count = total_blocks - filled_count
    return f"[{filled_char * filled_count}{empty_char * empty_count}]"


def generate_waveform(rms: float, width: int = 42) -> Tuple[str, str, str]:
    """Generates a symmetrical 3-line ASCII/Unicode audio waveform oscilloscope.

    Line 1: High amplitude positive peaks
    Line 2: Midline carrier / zero-crossing wave
    Line 3: High amplitude negative peaks
    """
    inner_w = max(10, width - 2)

    # In near silence, render a minimal quiescent dotted baseline
    if rms < 0.003:
        top_line = " " * inner_w
        mid_chars = []
        for i in range(inner_w):
            mid_chars.append("·" if i % 3 == 0 else " ")
        mid_line = "".join(mid_chars)
        bot_line = " " * inner_w
        return f"[{top_line}]", f"[{mid_line}]", f"[{bot_line}]"

    # Active voice modulation: construct symmetrical peaks
    norm = min(1.0, max(0.15, rms / 0.025))
    top_buf = [" "] * inner_w
    mid_buf = ["·"] * inner_w
    bot_buf = [" "] * inner_w

    # Two primary voice formant pulse lobes matching the reference design
    center_1 = int(inner_w * 0.35)
    center_2 = int(inner_w * 0.72)
    sigma_1 = max(2.5, inner_w * 0.11)
    sigma_2 = max(2.0, inner_w * 0.09)

    for i in range(inner_w):
        d1 = math.exp(-((i - center_1) ** 2) / (2 * (sigma_1 ** 2)))
        d2 = math.exp(-((i - center_2) ** 2) / (2 * (sigma_2 ** 2)))
        amp = (d1 * 0.95 + d2 * 1.05) * norm

        # Midline wave modulation
        if amp > 0.65:
            mid_buf[i] = ":" if i % 2 == 0 else "·"
        elif amp > 0.30:
            mid_buf[i] = ":" if i % 2 == 0 else "."
        elif amp > 0.12:
            mid_buf[i] = "." if i % 2 == 0 else " "
        else:
            mid_buf[i] = "·" if i % 4 == 0 else " "

        # Peak lines (symmetrical top and bottom)
        if amp > 0.60:
            top_buf[i] = ":" if i % 2 == 0 else "'"
            bot_buf[i] = ":" if i % 2 == 0 else "."
        elif amp > 0.35:
            top_buf[i] = "." if i % 2 == 0 else " "
            bot_buf[i] = "." if i % 2 == 0 else " "

    return f"[{''.join(top_buf)}]", f"[{''.join(mid_buf)}]", f"[{''.join(bot_buf)}]"


class ActionLogEntry:
    """Structured entry in the action execution history."""

    def __init__(self, kind: str, message: str, target: str = "", timestamp: Optional[str] = None):
        self.kind = kind  # "HEARD", "ACTION", "SYS"
        self.message = message
        self.target = target
        self.timestamp = timestamp or time.strftime("%H:%M:%S")


class HandsFreeDashboard:
    """Real-time cyberpunk / sci-fi terminal dashboard for HandsFreeOS."""

    def __init__(self, console: Optional[Console] = None, telemetry: Optional[TelemetryCollector] = None):
        self.console = console or Console()
        self.telemetry = telemetry or TelemetryCollector()
        self.layout = Layout()

        self.last_speech: str = "How many apps do I have open?"
        self.last_decision: Optional[JevDecision] = None
        self.active_window: Optional[WindowInfo] = WindowInfo(
            address="0x562f2a8406a0",
            title="handsfree run",
            class_name="com.mitchellh.ghostty",
            is_focused=True,
        )
        self.action_entries: List[ActionLogEntry] = []
        self.tts_status: str = "IDLE"
        self.mic_level: float = 0.013
        self.llm_output: str = json.dumps(
            {
                "intent": "answer_user",
                "target": "",
                "speech": "I have 2 apps open: Handsfree Run (com.mitchellh.ghostty) and WhatsApp - Shlok - Mozilla Firefox.",
            },
            indent=2,
        )

        self._setup_layout()

    def _setup_layout(self) -> None:
        """Configures the dashboard grid: Main body and Bottom footer bar."""
        self.layout.split_column(
            Layout(name="body", ratio=1),
            Layout(name="footer", size=3),
        )
        # Split body into Left (Perception & Decision) and Right (Logs + Telemetry)
        self.layout["body"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="right", ratio=1),
        )
        # Split Right column into Action Log and System Telemetry
        self.layout["right"].split_column(
            Layout(name="action_log", ratio=1),
            Layout(name="telemetry", size=8),
        )

    def update_speech(self, chunk: SpeechChunk) -> None:
        """Updates streaming transcript display."""
        if chunk.text:
            self.last_speech = chunk.text

    def update_audio_level(self, rms: float) -> None:
        """Updates live microphone input level."""
        self.mic_level = rms

    def update_llm_output(self, output: str) -> None:
        """Updates live LLM output JSON/text."""
        if not output:
            return
        cleaned = output.strip()
        try:
            parsed = json.loads(cleaned)
            self.llm_output = json.dumps(parsed, indent=2)
        except Exception:
            self.llm_output = cleaned

    def update_decision(self, decision: JevDecision) -> None:
        """Updates Jev decision metrics."""
        self.last_decision = decision

    def update_window(self, win: Optional[WindowInfo]) -> None:
        """Updates active window context."""
        if win:
            self.active_window = win

    def add_heard(self, text: str) -> None:
        """Adds a spoken user transcription log entry."""
        self.action_entries.append(ActionLogEntry(kind="HEARD", message=text))
        if len(self.action_entries) > 50:
            self.action_entries.pop(0)

    def add_action(self, action_name: str, target: str = "") -> None:
        """Adds an executed system action log entry."""
        self.action_entries.append(ActionLogEntry(kind="ACTION", message=action_name, target=target))
        if len(self.action_entries) > 50:
            self.action_entries.pop(0)

    def add_log(self, message: str) -> None:
        """Compatibility log method that categorizes incoming raw messages."""
        if message.startswith("Heard: "):
            text = message[7:].strip().strip("'\"")
            self.add_heard(text)
        elif message.startswith("Action: "):
            parts = message[8:].split("->", 1)
            action_name = parts[0].strip()
            target = parts[1].strip() if len(parts) > 1 else ""
            self.add_action(action_name, target)
        else:
            self.action_entries.append(ActionLogEntry(kind="SYS", message=message))
            if len(self.action_entries) > 50:
                self.action_entries.pop(0)

    def _render_perception_panel(self) -> Panel:
        """Renders the Left Panel: PERCEPTION & DECISION."""
        table = Table.grid(padding=(0, 0))
        table.add_column("Content", ratio=1)

        # 1. Live Speech
        speech_text = Text()
        speech_text.append("Live Speech: ", style="bold white")
        speech_text.append(self.last_speech, style="bold #38bdf8")
        table.add_row(speech_text)
        table.add_row(Text(""))

        # 2. Mic Level & Waveform Visualizer
        mic_header = Text()
        mic_header.append("Mic Level: ", style="bold white")
        mic_header.append(f"[{self.mic_level:.3f}]", style="bold #4ade80")
        table.add_row(mic_header)

        top_w, mid_w, bot_w = generate_waveform(self.mic_level, width=42)
        table.add_row(Text(top_w, style="#22d3ee"))
        table.add_row(Text(mid_w, style="#22d3ee"))
        table.add_row(Text(bot_w, style="#22d3ee"))
        table.add_row(Text(""))

        # 3. Inner Panel: LLM OUTPUT
        llm_panel = self._render_llm_output()
        table.add_row(llm_panel)
        table.add_row(Text(""))

        # 4. State & Window Indicators
        jev_text = Text()
        jev_text.append("Jev State:      ", style="bold white")
        jev_text.append("● ", style="bold #4ade80")
        jev_text.append("STANDBY ", style="bold #4ade80")
        jev_text.append("(<30ms System-1)", style="dim white")
        table.add_row(jev_text)

        win_title = self.active_window.title if self.active_window else "None"
        win_cls = self.active_window.class_name if self.active_window else "None"
        win_text = Text()
        win_text.append("Active Window:  ", style="bold white")
        win_text.append(f"{win_title} ", style="#94a3b8")
        win_text.append(f"({win_cls})", style="#64748b")
        table.add_row(win_text)

        tts_bullet_style = "bold #f59e0b" if "SPEAK" in self.tts_status.upper() else "bold #4ade80"
        tts_label_style = "bold #f59e0b" if "SPEAK" in self.tts_status.upper() else "bold #4ade80"
        tts_text = Text()
        tts_text.append("TTS Voice:      ", style="bold white")
        tts_text.append("● ", style=tts_bullet_style)
        tts_text.append(self.tts_status.upper(), style=tts_label_style)
        table.add_row(tts_text)

        return Panel(
            table,
            title="[bold #38bdf8] PERCEPTION & DECISION [/bold #38bdf8]",
            border_style="#3882a5",
            box=box.ROUNDED,
            padding=(1, 1),
        )

    def _render_llm_output(self) -> Panel:
        """Renders the syntax-highlighted JSON inside LLM OUTPUT inner box."""
        formatted_text = Text()

        try:
            parsed = json.loads(self.llm_output) if isinstance(self.llm_output, str) else self.llm_output
            formatted_text.append("{\n", style="bold white")
            items = list(parsed.items())
            for idx, (k, v) in enumerate(items):
                comma = "," if idx < len(items) - 1 else ""
                formatted_text.append(f'  "{k}"', style="bold #fb923c")
                formatted_text.append(": ", style="white")
                if isinstance(v, str):
                    formatted_text.append(f'"{v}"', style="#2dd4bf")
                else:
                    formatted_text.append(f"{v}", style="#38bdf8")
                formatted_text.append(f"{comma}\n", style="white")
            formatted_text.append("}", style="bold white")
        except Exception:
            formatted_text.append(self.llm_output, style="cyan")

        return Panel(
            formatted_text,
            title="[bold #94a3b8] LLM OUTPUT: [/bold #94a3b8]",
            border_style="#334155",
            box=box.ROUNDED,
            padding=(0, 1),
        )

    def _render_action_log(self) -> Panel:
        """Renders the Top-Right Panel: ACTION EXECUTION LOG with scrollbar track."""
        table = Table.grid(expand=True, padding=(0, 0))
        table.add_column("LogLine", ratio=1)
        table.add_column("Scrollbar", width=3, justify="right")

        # Show the most recent 12 entries to fill the upper-right panel
        rows_to_display = 12
        visible_entries = self.action_entries[-rows_to_display:] if self.action_entries else []

        for i in range(rows_to_display):
            line_text = Text()
            if i < len(visible_entries):
                entry = visible_entries[i]
                line_text.append(f"[{entry.timestamp}] ", style="#64748b")
                if entry.kind == "HEARD":
                    line_text.append("HEARD  ", style="bold #38bdf8")
                    line_text.append(f'"{entry.message}"', style="white")
                elif entry.kind == "ACTION":
                    line_text.append("ACTION ", style="bold #4ade80")
                    line_text.append(f"{entry.message}", style="white")
                    if entry.target:
                        line_text.append(" → ", style="bold white")
                        target_style = "#facc15" if entry.target.startswith("0x") else "#38bdf8" if "http" in entry.target else "white"
                        line_text.append(f"{entry.target}", style=target_style)
                else:
                    line_text.append(entry.message, style="dim white")

            # Stylized right scrollbar track matching reference UI
            if i == 0:
                scroll_indicator = Text("1", style="#475569")
            elif i == rows_to_display - 1:
                scroll_indicator = Text("1", style="#475569")
            elif i in {1, 2}:
                # Slider position indicator
                scroll_indicator = Text("█", style="#94a3b8")
            else:
                scroll_indicator = Text("│", style="#334155")

            table.add_row(line_text, scroll_indicator)

        return Panel(
            table,
            title="[bold #38bdf8] ACTION EXECUTION LOG [/bold #38bdf8]",
            border_style="#3882a5",
            box=box.ROUNDED,
            padding=(0, 1),
        )

    def _render_telemetry_panel(self) -> Panel:
        """Renders the Bottom-Right Panel: SYSTEM TELEMETRY and Pipeline Latency."""
        metrics: SystemMetrics = self.telemetry.get_system_metrics()
        latencies = self.telemetry.get_pipeline_latencies()

        grid = Table.grid(expand=True, padding=(0, 1))
        grid.add_column("SystemMetrics", ratio=1)
        grid.add_column("PipelineLatency", width=24)

        # Left Column: CPU, VRAM, RAM, GPU
        left_table = Table.grid(padding=(0, 0))
        left_table.add_column("Label", width=5)
        left_table.add_column("Percent", width=6)
        left_table.add_column("Bar", width=10)
        left_table.add_column("Usage", width=12)

        # CPU
        cpu_bar = format_meter_bar(metrics.cpu_percent, total_blocks=8)
        left_table.add_row(
            Text("CPU", style="bold #4ade80"),
            Text(f"{metrics.cpu_percent:>5.1f}%", style="bold #4ade80"),
            Text(cpu_bar, style="#22c55e"),
            Text(""),
        )

        # VRAM
        vram_bar = format_meter_bar(metrics.vram_percent, total_blocks=8)
        left_table.add_row(
            Text("VRAM", style="bold #38bdf8"),
            Text(f"{metrics.vram_percent:>5.1f}%", style="bold #38bdf8"),
            Text(vram_bar, style="#06b6d4"),
            Text(f"{metrics.vram_used_gb:.1f}GB/{metrics.vram_total_gb:.1f}GB", style="#94a3b8"),
        )

        # RAM
        ram_bar = format_meter_bar(metrics.ram_percent, total_blocks=8)
        left_table.add_row(
            Text("RAM", style="bold #38bdf8"),
            Text(f"{metrics.ram_percent:>5.1f}%", style="bold #38bdf8"),
            Text(ram_bar, style="#06b6d4"),
            Text(f"{metrics.ram_used_gb:.1f}GB/{metrics.ram_total_gb:.1f}GB", style="#94a3b8"),
        )

        # GPU
        gpu_bar = format_meter_bar((metrics.gpu_temp_c / 90.0) * 100.0, total_blocks=8)
        left_table.add_row(
            Text("GPU", style="bold #4ade80"),
            Text(f"{metrics.gpu_temp_c:>4d}°C", style="bold #4ade80"),
            Text(gpu_bar, style="#4ade80"),
            Text(""),
        )

        # Right Column: PIPELINE LATENCY inner panel
        lat_table = Table.grid(padding=(0, 0))
        lat_table.add_column("Name", width=9)
        lat_table.add_column("Bar", width=7)
        lat_table.add_column("Time", width=5, justify="right")

        phonon_ms = latencies.get("phonon", 12.0)
        jev_ms = latencies.get("jev", 8.0)
        yolo_ms = latencies.get("yolo", 15.0)

        lat_table.add_row(
            Text("Phonon-2", style="#38bdf8"),
            Text(format_meter_bar((phonon_ms / 30.0) * 100.0, total_blocks=5, empty_char=" "), style="#38bdf8"),
            Text(f"{int(round(phonon_ms)):>2d}ms", style="white"),
        )
        lat_table.add_row(
            Text("Jev OS", style="#4ade80"),
            Text(format_meter_bar((jev_ms / 30.0) * 100.0, total_blocks=5, empty_char=" "), style="#4ade80"),
            Text(f"{int(round(jev_ms)):>2d}ms", style="white"),
        )
        lat_table.add_row(
            Text("YOLO", style="#4ade80"),
            Text(format_meter_bar((yolo_ms / 30.0) * 100.0, total_blocks=5, empty_char=" "), style="#86efac"),
            Text(f"{int(round(yolo_ms)):>2d}ms", style="white"),
        )

        latency_panel = Panel(
            lat_table,
            title="[bold #94a3b8] PIPELINE LATENCY [/bold #94a3b8]",
            border_style="#334155",
            box=box.ROUNDED,
            padding=(0, 1),
        )

        grid.add_row(left_table, latency_panel)

        return Panel(
            grid,
            title="[bold #38bdf8] SYSTEM TELEMETRY [/bold #38bdf8]",
            border_style="#3882a5",
            box=box.ROUNDED,
            padding=(0, 1),
        )

    def _render_footer(self) -> Panel:
        """Renders the Bottom Footer status line with battery meter."""
        table = Table.grid(expand=True, padding=(0, 0))
        table.add_column("Status", ratio=1)
        table.add_column("Battery", justify="right")

        metrics = self.telemetry.get_system_metrics()
        bat_bar = format_meter_bar(metrics.battery_percent, total_blocks=5, empty_char="▒")
        bat_symbol = "⚡" if metrics.battery_charging else "✦"

        status_text = Text()
        status_text.append("Status: Active Listening (Phonon-2 + Jev + YOLO) | Press Ctrl+C to Exit", style="bold #94a3b8")

        bat_text = Text()
        bat_text.append(f"{bat_bar} {bat_symbol}", style="bold #94a3b8")

        table.add_row(status_text, bat_text)

        return Panel(
            table,
            border_style="#3882a5",
            box=box.ROUNDED,
            padding=(0, 1),
        )

    def render(self) -> Layout:
        """Renders the complete TUI frame."""
        self.layout["left"].update(self._render_perception_panel())
        self.layout["action_log"].update(self._render_action_log())
        self.layout["telemetry"].update(self._render_telemetry_panel())
        self.layout["footer"].update(self._render_footer())
        return self.layout
