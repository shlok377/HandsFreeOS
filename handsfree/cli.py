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
    """Starts live daemon, microphone ingestion, and interactive Rich dashboard."""
    from rich.live import Live

    console = Console()
    dashboard = HandsFreeDashboard(console=console)
    dashboard.add_log("Initializing HandsFreeOS engine...")

    jev = JevEngine()
    os_ctrl = HyprlandController()
    input_ctrl = AdaptiveInputController(dry_run=dry_run)
    grounder = TwoStageGrounder(decision_engine=jev)

    # Initialize audio stream and TTS with echo suppression
    from handsfree.audio.vad import VoiceActivityDetector
    from handsfree.audio.stt_phonon import PhononRecognizer
    from handsfree.audio.audio_stream import ContinuousAudioStream
    from handsfree.os_layer.screen import ScreenCapture

    vad = VoiceActivityDetector()
    recognizer = PhononRecognizer()
    recognizer.load_model()
    screencap = ScreenCapture()

    def on_speech_chunk(chunk: SpeechChunk) -> None:
        dashboard.update_speech(chunk)
        dashboard.add_log(f"Heard: '{chunk.text}'")

        # Capture current screen and active window
        screenshot = screencap.capture_png_bytes()
        active_win = os_ctrl.get_active_window()
        dashboard.update_window(active_win)

        # Process through primary dispatch seam
        event = dispatcher.process_speech_frame(
            chunk, screenshot_bytes=screenshot, mock_active_window=active_win
        )

        dashboard.add_log(f"Action: {event.action_type.value} -> {event.target or ''}")
        if event.verbal_response:
            dashboard.tts_status = f"Speaking: '{event.verbal_response}'"

    audio_stream = ContinuousAudioStream(
        vad=vad, recognizer=recognizer, on_speech_chunk=on_speech_chunk
    )

    def on_tts_state(is_speaking: bool) -> None:
        audio_stream.set_echo_suppression(is_speaking)
        dashboard.tts_status = "Speaking..." if is_speaking else "Idle"

    tts = KokoroTTS(dry_run=dry_run, on_state_change=on_tts_state)

    dispatcher = IntentDispatcher(
        decision_engine=jev,
        os_controller=os_ctrl,
        input_controller=input_ctrl,
        tts=tts,
        grounder=grounder,
    )

    dashboard.add_log("HandsFreeOS is active and listening to microphone.")

    # Try starting live audio capture via sounddevice
    sd_stream = None
    try:
        import sounddevice as sd

        def audio_callback(indata, frames, time_info, status):
            if status:
                pass
            frame = indata[:, 0].copy()  # Mono float32
            audio_stream.feed_frame(frame)

        sd_stream = sd.InputStream(
            samplerate=16000,
            channels=1,
            dtype="float32",
            blocksize=1600,
            callback=audio_callback,
        )
        sd_stream.start()
        dashboard.add_log("Microphone stream opened successfully.")
    except Exception as e:
        dashboard.add_log(f"Mic init notice: {e} (Simulated audio mode enabled)")

    try:
        with Live(dashboard.render(), console=console, refresh_per_second=4) as live:
            while True:
                active_win = os_ctrl.get_active_window()
                dashboard.update_window(active_win)
                live.update(dashboard.render())
                time.sleep(0.25)
    except KeyboardInterrupt:
        dashboard.add_log("Shutting down HandsFreeOS...")
    finally:
        if sd_stream is not None:
            sd_stream.stop()
            sd_stream.close()
        tts.stop()


if __name__ == "__main__":
    main()
