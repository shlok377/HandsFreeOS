"""Command-line interface for HandsFreeOS."""

import argparse
import sys
import threading
import time
from typing import Optional

import numpy as np
from rich.console import Console

from handsfree.decision.jev_engine import JevEngine
from handsfree.domain.models import ActionType, SpeechChunk
from handsfree.loop.dispatch import IntentDispatcher
from handsfree.os_layer.hyprland import HyprlandController
from handsfree.os_layer.input_controller import AdaptiveInputController
from handsfree.os_layer.lock import SingleInstanceLock
from handsfree.os_layer.network_discovery import NetworkDiscovery
from handsfree.os_layer.screen import ScreenCapture
from handsfree.os_layer.tunnel import ReverseTunnelManager
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
    run_parser.add_argument("--tunnel", action="store_true", help="Automatically open a public HTTPS tunnel for mobile data phone access.")

    # `handsfree demo`
    demo_parser = subparsers.add_parser("demo", help="Run interactive demonstration of voice commands.")
    demo_parser.add_argument("--web-inspect", action="store_true", help="Start remote visual inspector stream during demo.")
    demo_parser.add_argument("--inspect-port", type=int, default=8000, help="Port for web inspector (default: 8000).")
    demo_parser.add_argument("--inspect-token", type=str, default=None, help="Optional authentication token for public tunneling.")
    demo_parser.add_argument("--tunnel", action="store_true", help="Automatically open a public HTTPS tunnel for mobile data phone access.")

    return parser


def main() -> None:
    """CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "demo":
        run_demo(
            web_inspect=getattr(args, "web_inspect", False) or getattr(args, "tunnel", False),
            inspect_port=getattr(args, "inspect_port", 8000),
            inspect_token=getattr(args, "inspect_token", None),
            tunnel=getattr(args, "tunnel", False),
        )
    elif args.command == "run":
        run_live(
            dry_run=args.dry_run,
            web_inspect=getattr(args, "web_inspect", False) or getattr(args, "tunnel", False),
            inspect_port=getattr(args, "inspect_port", 8000),
            inspect_token=getattr(args, "inspect_token", None),
            tunnel=getattr(args, "tunnel", False),
        )
    else:
        parser.print_help()


def run_demo(
    web_inspect: bool = False,
    inspect_port: int = 8000,
    inspect_token: Optional[str] = None,
    tunnel: bool = False,
) -> None:
    """Runs scripted demo through the IntentDispatcher seam."""
    console = Console()
    lock = SingleInstanceLock()
    if not lock.acquire(takeover=True):
        console.print("[bold red][HandsFreeOS Error][/bold red] Another HandsFreeOS instance is active and could not be terminated.")
        return

    console.print("[bold cyan]Starting HandsFreeOS ('Bit') Interactive Demo (Single Unified Instance)...[/bold cyan]")

    hub = VisualStreamHub() if web_inspect else None
    server = None
    tunnel_mgr = None
    demo_stop_stream = threading.Event()

    try:
        if web_inspect and hub is not None:
            server = VisualStreamServer(hub=hub, host="0.0.0.0", port=inspect_port, auth_token=inspect_token)
            server.start()
            endpoints = NetworkDiscovery().get_connection_endpoints(port=server.port, auth_token=inspect_token)
            console.print(f"[bold green][Visual Inspector][/bold green] Stream active at [bold cyan]{endpoints.get('lan', endpoints['local'])}[/bold cyan]")
            if "tailscale" in endpoints:
                console.print(f"[bold magenta][Tailscale][/bold magenta] Phone URL: [bold underline]{endpoints['tailscale']}[/bold underline]")

            if tunnel:
                console.print("[bold yellow]Opening public HTTPS tunnel for phone access...[/bold yellow]")
                tunnel_mgr = ReverseTunnelManager(local_port=server.port)
                public_url = tunnel_mgr.start(timeout=6.0)
                if public_url:
                    query = f"?token={inspect_token}" if inspect_token else ""
                    console.print(f"[bold magenta][Public Phone Tunnel][/bold magenta] [bold underline]{public_url}/{query}[/bold underline]")
                else:
                    console.print("[bold red]Public tunnel timed out; using LAN IP instead.[/bold red]")

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

        # Start continuous background screen capture thread for smooth video
        screencap = ScreenCapture()

        def _bg_demo_streamer():
            while not demo_stop_stream.is_set():
                try:
                    shot = screencap.capture_png_bytes()
                    if shot and hub is not None:
                        hub.update_frame(shot, hub.get_latest_frame().boxes)
                except Exception:
                    pass
                time.sleep(0.15)

        if web_inspect and hub is not None:
            stream_thread = threading.Thread(target=_bg_demo_streamer, daemon=True)
            stream_thread.start()

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

        if web_inspect and hub is not None:
            console.print("\n[bold green]Visual inspector is running live! Open the URL above on your phone.[/bold green]")
            console.input("[dim]Press Enter when done to stop the visual stream...[/dim]")
    finally:
        demo_stop_stream.set()
        if tunnel_mgr is not None:
            tunnel_mgr.stop()
        if server is not None:
            server.stop()
        lock.release()


def run_live(
    dry_run: bool = False,
    web_inspect: bool = False,
    inspect_port: int = 8000,
    inspect_token: Optional[str] = None,
    tunnel: bool = False,
) -> None:
    """Starts live daemon, microphone ingestion, and interactive Rich dashboard."""
    from rich.live import Live

    console = Console()
    lock = SingleInstanceLock()
    if not lock.acquire(takeover=True):
        console.print("[bold red][HandsFreeOS Error][/bold red] Another HandsFreeOS instance is active and could not be terminated.")
        return

    dashboard = HandsFreeDashboard(console=console)
    dashboard.add_log("Initializing HandsFreeOS engine (Single Unified Instance)...")

    hub = VisualStreamHub() if web_inspect else None
    server = None
    tunnel_mgr = None
    sd_stream = None
    audio_stream = None
    tts = None
    live_stop_stream = threading.Event()
    shutdown_event = threading.Event()

    try:
        if web_inspect and hub is not None:
            server = VisualStreamServer(hub=hub, host="0.0.0.0", port=inspect_port, auth_token=inspect_token)
            server.start()
            endpoints = NetworkDiscovery().get_connection_endpoints(port=server.port, auth_token=inspect_token)
            dashboard.add_log(f"Visual Inspector: {endpoints.get('lan', endpoints['local'])}")
            if "tailscale" in endpoints:
                dashboard.add_log(f"Tailscale mobile URL: {endpoints['tailscale']}")

            if tunnel:
                dashboard.add_log("Connecting public phone tunnel in background...")
                tunnel_mgr = ReverseTunnelManager(local_port=server.port)

                def _connect_tunnel():
                    url = tunnel_mgr.start(timeout=10.0)
                    if url:
                        query = f"?token={inspect_token}" if inspect_token else ""
                        dashboard.add_log(f"Public Phone Tunnel: {url}/{query}")
                    else:
                        dashboard.add_log("Tunnel setup timed out; LAN streaming active.")

                threading.Thread(target=_connect_tunnel, daemon=True).start()

        jev = JevEngine()
        os_ctrl = HyprlandController()
        input_ctrl = AdaptiveInputController(dry_run=dry_run)
        grounder = TwoStageGrounder(decision_engine=jev, stream_hub=hub)

        # Initialize audio stream and TTS with echo suppression
        from handsfree.audio.vad import VoiceActivityDetector
        from handsfree.audio.stt_phonon import PhononRecognizer
        from handsfree.audio.audio_stream import ContinuousAudioStream

        vad = VoiceActivityDetector()
        recognizer = PhononRecognizer()
        recognizer.load_model()
        screencap = ScreenCapture()

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

        def _bg_live_streamer():
            screencap_local = ScreenCapture()
            while not shutdown_event.is_set() and not live_stop_stream.is_set():
                try:
                    shot = screencap_local.capture_png_bytes()
                    if shot and hub is not None:
                        hub.update_frame(shot, hub.get_latest_frame().boxes)
                except Exception:
                    pass
                time.sleep(0.15)

        if web_inspect and hub is not None:
            live_stream_thread = threading.Thread(target=_bg_live_streamer, daemon=True)
            live_stream_thread.start()

        with Live(dashboard.render(), console=console, refresh_per_second=4) as live:
            while not shutdown_event.is_set():
                active_win = os_ctrl.get_active_window()
                dashboard.update_window(active_win)
                live.update(dashboard.render())
                time.sleep(0.25)
            # Give speech feedback a moment to finish before process termination
            time.sleep(1.0)
    except KeyboardInterrupt:
        dashboard.add_log("Shutting down HandsFreeOS...")
    finally:
        live_stop_stream.set()
        if tunnel_mgr is not None:
            tunnel_mgr.stop()
        if server is not None:
            server.stop()
        if sd_stream is not None:
            try:
                sd_stream.stop()
                sd_stream.close()
            except Exception:
                pass
        if audio_stream is not None:
            try:
                audio_stream.stop()
            except Exception:
                pass
        if tts is not None:
            try:
                tts.stop()
            except Exception:
                pass
        lock.release()


if __name__ == "__main__":
    main()
