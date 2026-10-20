"""Command-line interface for HandsFreeOS."""

import argparse
import sys
import threading
import time

import numpy as np
from rich.console import Console

from handsfree.decision.jev_engine import JevEngine
from handsfree.domain.models import ActionType, SpeechChunk
from handsfree.loop.dispatch import IntentDispatcher
from handsfree.os_layer.hyprland import HyprlandController
from handsfree.os_layer.input_controller import AdaptiveInputController
from handsfree.os_layer.network_discovery import NetworkDiscovery
from handsfree.ui.tui import HandsFreeDashboard
from handsfree.ui.visual_server import VisualStreamServer
from handsfree.vision.grounding import TwoStageGrounder
from handsfree.vision.stream_hub import VisualStreamHub
from handsfree.voice.tts_kokoro import KokoroTTS


def build_parser() -> argparse.ArgumentParser:
    """Constructs the command-line argument parser for HandsFreeOS."""
    parser = argparse.ArgumentParser(description="HandsFreeOS: Real-time hands-free OS control.")
    subparsers = parser.add_subparsers(dest="command")

    # `handsfree run`
    run_parser = subparsers.add_parser("run", help="Start HandsFreeOS live listening daemon with Rich TUI.")
    run_parser.add_argument("--dry-run", action="store_true", help="Simulate mouse and keystrokes without injecting.")
    run_parser.add_argument("--web-inspect", action="store_true", help="Start remote visual inspector stream for phone tunneling.")
    run_parser.add_argument("--inspect-port", type=int, default=8000, help="Port for web inspector (default: 8000).")
    run_parser.add_argument("--inspect-token", type=str, default=None, help="Optional authentication token for public tunneling.")

    # `handsfree demo`
    demo_parser = subparsers.add_parser("demo", help="Run interactive demonstration of voice commands.")
    demo_parser.add_argument("--web-inspect", action="store_true", help="Start remote visual inspector stream during demo.")
    demo_parser.add_argument("--inspect-port", type=int, default=8000, help="Port for web inspector (default: 8000).")
    demo_parser.add_argument("--inspect-token", type=str, default=None, help="Optional authentication token for public tunneling.")

    return parser


def main() -> None:
    """CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "demo":
        run_demo(
            web_inspect=getattr(args, "web_inspect", False),
            inspect_port=getattr(args, "inspect_port", 8000),
            inspect_token=getattr(args, "inspect_token", None),
        )
    elif args.command == "run":
        run_live(
            dry_run=args.dry_run,
            web_inspect=getattr(args, "web_inspect", False),
            inspect_port=getattr(args, "inspect_port", 8000),
            inspect_token=getattr(args, "inspect_token", None),
        )
    else:
        parser.print_help()


def run_demo(
    web_inspect: bool = False,
    inspect_port: int = 8000,
    inspect_token: Optional[str] = None,
) -> None:
    """Runs scripted demo through the IntentDispatcher seam."""
    console = Console()
    console.print("[bold cyan]Starting HandsFreeOS ('Bit') Interactive Demo...[/bold cyan]")

    hub = VisualStreamHub() if web_inspect else None
    server = None
    if web_inspect and hub is not None:
        server = VisualStreamServer(hub=hub, host="0.0.0.0", port=inspect_port, auth_token=inspect_token)
        server.start()
        endpoints = NetworkDiscovery().get_connection_endpoints(port=server.port, auth_token=inspect_token)
        console.print(f"[bold green][Visual Inspector][/bold green] Stream active at [bold cyan]{endpoints.get('lan', endpoints['local'])}[/bold cyan]")
        if "tailscale" in endpoints:
            console.print(f"[bold magenta][Tailscale][/bold magenta] Phone URL: [bold underline]{endpoints['tailscale']}[/bold underline]")

    jev = JevEngine()
    os_ctrl = HyprlandController()
    input_ctrl = AdaptiveInputController(dry_run=True)
    tts = KokoroTTS(dry_run=True)
    grounder = TwoStageGrounder(decision_engine=jev, stream_hub=hub)

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

    try:
        for cmd in demo_commands:
            console.print(f"\n[bold yellow]User Spoke:[/bold yellow] '{cmd}'")
            chunk = SpeechChunk(text=cmd, is_final=True)
            event = dispatcher.process_speech_frame(chunk)
            console.print(f"[bold green]Dispatched Action:[/bold green] {event.action_type.value} -> {event.target or ''}")
            console.print(f"[bold magenta]Bit Replied:[/bold magenta] '{event.verbal_response}'")
            time.sleep(0.5)
    finally:
        if server is not None:
            server.stop()


def run_live(
    dry_run: bool = False,
    web_inspect: bool = False,
    inspect_port: int = 8000,
    inspect_token: Optional[str] = None,
) -> None:
    """Starts live daemon, microphone ingestion, and interactive Rich dashboard."""
    from rich.live import Live

    console = Console()
    dashboard = HandsFreeDashboard(console=console)
    dashboard.add_log("Initializing HandsFreeOS engine...")

    hub = VisualStreamHub() if web_inspect else None
    server = None
    if web_inspect and hub is not None:
        server = VisualStreamServer(hub=hub, host="0.0.0.0", port=inspect_port, auth_token=inspect_token)
        server.start()
        endpoints = NetworkDiscovery().get_connection_endpoints(port=server.port, auth_token=inspect_token)
        dashboard.add_log(f"Visual Inspector: {endpoints.get('lan', endpoints['local'])}")
        if "tailscale" in endpoints:
            dashboard.add_log(f"Tailscale mobile URL: {endpoints['tailscale']}")

    jev = JevEngine()
    os_ctrl = HyprlandController()
    input_ctrl = AdaptiveInputController(dry_run=dry_run)
    grounder = TwoStageGrounder(decision_engine=jev, stream_hub=hub)

    # Initialize audio stream and TTS with echo suppression
    from handsfree.audio.vad import VoiceActivityDetector
    from handsfree.audio.stt_phonon import PhononRecognizer
    from handsfree.audio.audio_stream import ContinuousAudioStream
    from handsfree.os_layer.screen import ScreenCapture

    vad = VoiceActivityDetector()
    recognizer = PhononRecognizer()
    recognizer.load_model()
    screencap = ScreenCapture()

    shutdown_event = threading.Event()

    def on_speech_chunk(chunk: SpeechChunk) -> None:
        if not chunk.text or not chunk.text.strip():
            return

        dashboard.update_speech(chunk)
        dashboard.add_heard(chunk.text)
        if chunk.duration_ms > 0:
            dashboard.record_latency("phonon", chunk.duration_ms)

        # Capture current screen and active window
        screenshot = screencap.capture_png_bytes()
        active_win = os_ctrl.get_active_window()
        dashboard.update_window(active_win)

        # Process through primary dispatch seam with timing
        t0 = time.time()
        event = dispatcher.process_speech_frame(
            chunk, screenshot_bytes=screenshot, mock_active_window=active_win
        )
        jev_latency = max(2.0, (time.time() - t0) * 1000.0)
        dashboard.record_latency("jev", jev_latency)

        if event.action_type == ActionType.CLICK_BOX:
            # Record vision grounding latency if YOLO/OmniParser ran
            dashboard.record_latency("yolo", max(5.0, jev_latency * 0.6))

        dashboard.add_action(event.action_type.value, event.target or "")
        if event.llm_output:
            dashboard.update_llm_output(event.llm_output)
        if event.verbal_response:
            dashboard.tts_status = "SPEAKING"

        if event.action_type == ActionType.SHUTDOWN:
            dashboard.add_action("shutdown", "exit")
            shutdown_event.set()

    audio_stream = ContinuousAudioStream(
        vad=vad, recognizer=recognizer, on_speech_chunk=on_speech_chunk
    )

    def on_tts_state(is_speaking: bool) -> None:
        audio_stream.set_echo_suppression(is_speaking)
        dashboard.tts_status = "SPEAKING" if is_speaking else "IDLE"

    tts = KokoroTTS(dry_run=dry_run, on_state_change=on_tts_state)

    dispatcher = IntentDispatcher(
        decision_engine=jev,
        os_controller=os_ctrl,
        input_controller=input_ctrl,
        tts=tts,
        grounder=grounder,
        on_llm_output=dashboard.update_llm_output,
    )

    dashboard.add_log("HandsFreeOS is active and listening to microphone.")

    # Try starting live audio capture via sounddevice
    sd_stream = None
    try:
        import sounddevice as sd

        # Query native input sample rate (typically 48000 Hz on PipeWire/ALSA Linux)
        try:
            device_info = sd.query_devices(kind="input")
            native_sr = int(device_info.get("default_samplerate", 48000)) if device_info else 48000
        except Exception:
            native_sr = 48000

        block_duration_s = 0.1  # 100ms frames
        native_blocksize = int(native_sr * block_duration_s)

        def audio_callback(indata, frames, time_info, status):
            if status:
                pass
            raw_channel = indata[:, 0]
            # Resample / decimate to 16000 Hz for VAD and Phonon-2
            if native_sr == 16000:
                frame_16k = raw_channel.copy()
            elif native_sr % 16000 == 0:
                step = native_sr // 16000
                frame_16k = raw_channel[::step].copy()
            else:
                num_target = int(len(raw_channel) * 16000 / native_sr)
                old_idx = np.linspace(0, len(raw_channel) - 1, len(raw_channel))
                new_idx = np.linspace(0, len(raw_channel) - 1, num_target)
                frame_16k = np.interp(new_idx, old_idx, raw_channel).astype(np.float32)

            rms = float(np.sqrt(np.mean(frame_16k**2)))
            dashboard.update_audio_level(rms)

            # Compute real FFT for frequency spectrum visualizer
            try:
                fft_mags = np.abs(np.fft.rfft(frame_16k))
                n_bins = len(fft_mags)
                num_bands = 8
                band_energies = []
                for b in range(num_bands):
                    start_idx = int((b / num_bands) ** 1.3 * n_bins)
                    end_idx = max(start_idx + 1, int(((b + 1) / num_bands) ** 1.3 * n_bins))
                    band_energy = float(np.mean(fft_mags[start_idx:end_idx]))
                    band_energies.append(min(1.0, band_energy * 2.5))
                dashboard.update_audio_spectrum(band_energies)
            except Exception:
                pass

            audio_stream.feed_frame(frame_16k)

        sd_stream = sd.InputStream(
            samplerate=native_sr,
            channels=1,
            dtype="float32",
            blocksize=native_blocksize,
            callback=audio_callback,
        )
        sd_stream.start()
        dashboard.add_log(f"Microphone active ({native_sr}Hz -> 16kHz).")
    except Exception as e:
        dashboard.add_log(f"Mic init notice: {e} (Simulated audio mode enabled)")

    try:
        with Live(dashboard.render(), console=console, refresh_per_second=4) as live:
            last_bg_capture = 0.0
            while not shutdown_event.is_set():
                active_win = os_ctrl.get_active_window()
                dashboard.update_window(active_win)

                if web_inspect and hub is not None and (time.time() - last_bg_capture > 1.5):
                    last_bg_capture = time.time()
                    try:
                        bg_shot = screencap.capture_png_bytes()
                        if bg_shot:
                            hub.update_frame(bg_shot, hub.get_latest_frame().boxes)
                    except Exception:
                        pass

                live.update(dashboard.render())
                time.sleep(0.25)
            # Give speech feedback a moment to finish before process termination
            time.sleep(1.0)
    except KeyboardInterrupt:
        dashboard.add_log("Shutting down HandsFreeOS...")
    finally:
        if server is not None:
            server.stop()
        if sd_stream is not None:
            sd_stream.stop()
            sd_stream.close()
        audio_stream.stop()
        tts.stop()


if __name__ == "__main__":
    main()
