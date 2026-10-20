"""Integration tests for CLI arguments, network discovery, and grounder streaming hook."""

from io import BytesIO
from unittest.mock import MagicMock, patch
from PIL import Image
import pytest

from handsfree.cli import build_parser
from handsfree.decision.jev_engine import JevEngine
from handsfree.domain.models import BoundingBox
from handsfree.vision.grounding import TwoStageGrounder
from handsfree.vision.stream_hub import VisualStreamHub


class DummyDetector:
    def detect_elements(self, image_bytes):
        return [
            BoundingBox(id=1, label="Submit", x_min=50, y_min=50, x_max=150, y_max=100, confidence=0.95)
        ]


def test_cli_parser_web_inspect_arguments():
    parser = build_parser()
    args = parser.parse_args(["run", "--web-inspect", "--inspect-port", "8888", "--inspect-token", "secret99", "--tunnel"])
    assert args.command == "run"
    assert args.web_inspect is True
    assert args.inspect_port == 8888
    assert args.inspect_token == "secret99"
    assert args.tunnel is True


def test_grounder_updates_stream_hub():
    jev = JevEngine()
    detector = DummyDetector()
    hub = VisualStreamHub()

    grounder = TwoStageGrounder(
        decision_engine=jev,
        detector=detector,
        stream_hub=hub
    )

    # Initial frame in hub is fallback
    assert hub.get_latest_frame().is_fallback is True

    # Generate test image
    img = Image.new("RGB", (320, 240), color=(50, 50, 50))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    image_bytes = buf.getvalue()

    coords, tier, latency = grounder.locate_target(image_bytes, "Submit")
    assert coords == (100, 75)

    # Verify stream hub received frame and boxes
    latest = hub.get_latest_frame()
    assert latest.is_fallback is False
    assert len(latest.boxes) == 1
    assert latest.boxes[0].label == "Submit"


def test_cli_run_tunnel_invokes_unified_instance():
    from handsfree.cli import main
    with patch("handsfree.cli.run_live") as mock_run_live:
        with patch("sys.argv", ["handsfree", "run", "--tunnel"]):
            main()
            mock_run_live.assert_called_once_with(
                dry_run=False,
                web_inspect=True,
                inspect_port=8000,
                inspect_token=None,
                tunnel=True,
            )


def test_cli_run_live_acquires_and_releases_lock():
    from handsfree.cli import run_live
    from handsfree.os_layer.lock import SingleInstanceLock

    with patch.object(SingleInstanceLock, "acquire", return_value=True) as mock_acquire, \
         patch.object(SingleInstanceLock, "release") as mock_release, \
         patch("handsfree.decision.jev_engine.JevEngine"), \
         patch("handsfree.os_layer.hyprland.HyprlandController"), \
         patch("handsfree.audio.vad.VoiceActivityDetector"), \
         patch("handsfree.audio.stt_phonon.PhononRecognizer"), \
         patch("handsfree.audio.audio_stream.ContinuousAudioStream"), \
         patch("handsfree.voice.tts_kokoro.KokoroTTS"), \
         patch("rich.live.Live") as mock_live_cls:

        mock_live_cls.return_value.__enter__.side_effect = KeyboardInterrupt

        with patch("handsfree.cli.VisualStreamServer") as mock_server, \
             patch("handsfree.cli.ReverseTunnelManager") as mock_tunnel_cls:
            mock_tunnel = MagicMock()
            mock_tunnel_cls.return_value = mock_tunnel

            run_live(dry_run=True, web_inspect=True, tunnel=True)

            mock_acquire.assert_called_once_with(takeover=True)
            mock_release.assert_called_once()
            mock_tunnel.stop.assert_called()


def test_cli_run_live_aborts_if_lock_not_acquired():
    from handsfree.cli import run_live
    from handsfree.os_layer.lock import SingleInstanceLock

    with patch.object(SingleInstanceLock, "acquire", return_value=False) as mock_acquire, \
         patch("handsfree.cli.VisualStreamServer") as mock_server:
        run_live(dry_run=True, web_inspect=True, tunnel=True)
        mock_acquire.assert_called_once_with(takeover=True)
        mock_server.assert_not_called()


