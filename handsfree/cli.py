"""Command-line interface for HandsFreeOS."""

import argparse
import sys
import time

from rich.console import Console

from handsfree.decision.jev_engine import JevEngine
from handsfree.domain.models import SpeechChunk
from handsfree.loop.dispatch import IntentDispatcher
from handsfree.os_layer.hyprland import HyprlandController
from handsfree.os_layer.input_controller import AdaptiveInputController
from handsfree.ui.tui import HandsFreeDashboard
from handsfree.vision.grounding import TwoStageGrounder
from handsfree.voice.tts_kokoro import KokoroTTS


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="HandsFreeOS: Real-time hands-free OS control.")
    subparsers = parser.add_subparsers(dest="command")

    # `handsfree run`
    run_parser = subparsers.add_parser("run", help="Start HandsFreeOS live listening daemon with Rich TUI.")
    run_parser.add_argument("--dry-run", action="store_true", help="Simulate mouse and keystrokes without injecting.")

    # `handsfree demo`
    demo_parser = subparsers.add_parser("demo", help="Run interactive demonstration of voice commands.")

    args = parser.parse_args()

    if args.command == "demo":
        run_demo()
    elif args.command == "run":
        run_live(dry_run=args.dry_run)
    else:
        parser.print_help()


def run_demo() -> None:
    """Runs scripted demo through the IntentDispatcher seam."""
    console = Console()
    console.print("[bold cyan]Starting HandsFreeOS ('Bit') Interactive Demo...[/bold cyan]")

    jev = JevEngine()
    os_ctrl = HyprlandController()
    input_ctrl = AdaptiveInputController(dry_run=True)
    tts = KokoroTTS(dry_run=True)
    grounder = TwoStageGrounder(decision_engine=jev)

    dispatcher = IntentDispatcher(
        decision_engine=jev,
        os_controller=os_ctrl,
        input_controller=input_ctrl,
        tts=tts,
        grounder=grounder,
    )

    demo_commands = [
        "Hey bit! open webwhatsapp",
        "hey Bit! Open herdr",
        "hey bit! make a new txt file and type in hello world",
        "wait, stop that",
        "delete all files in root",
    ]

    for cmd in demo_commands:
        console.print(f"\n[bold yellow]User Spoke:[/bold yellow] '{cmd}'")
        chunk = SpeechChunk(text=cmd, is_final=True)
        event = dispatcher.process_speech_frame(chunk)
        console.print(f"[bold green]Dispatched Action:[/bold green] {event.action_type.value} -> {event.target or ''}")
        console.print(f"[bold magenta]Bit Replied:[/bold magenta] '{event.verbal_response}'")
        time.sleep(0.5)


def run_live(dry_run: bool = False) -> None:
    """Starts live daemon and dashboard."""
    console = Console()
    dashboard = HandsFreeDashboard(console=console)
    dashboard.add_log("HandsFreeOS daemon initialized.")
    console.print(dashboard.render())


if __name__ == "__main__":
    main()
