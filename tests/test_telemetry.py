"""Tests for live telemetry collector public interface."""

import os
from unittest.mock import patch, mock_open
import pytest

from handsfree.ui.telemetry import TelemetryCollector, SystemMetrics


def test_system_metrics_defaults():
    metrics = SystemMetrics()
    assert metrics.cpu_percent >= 0.0
    assert metrics.ram_total_gb >= 0.0
    assert 0 <= metrics.battery_percent <= 100


def test_system_metrics_from_proc_fs():
    collector = TelemetryCollector()
    meminfo_mock = (
        "MemTotal:       32768000 kB\n"
        "MemFree:         8192000 kB\n"
        "MemAvailable:   16384000 kB\n"
    )
    with patch("builtins.open", mock_open(read_data=meminfo_mock)):
        metrics = collector.get_system_metrics()
        assert metrics.ram_total_gb == pytest.approx(31.25, rel=0.1)
        assert metrics.ram_used_gb == pytest.approx(15.62, rel=0.1)
        assert metrics.ram_percent == pytest.approx(50.0, rel=0.1)


def test_pipeline_latencies_recording():
    collector = TelemetryCollector()
    collector.record_latency("phonon", 12.0)
    collector.record_latency("jev", 8.0)
    collector.record_latency("yolo", 15.0)

    latencies = collector.get_pipeline_latencies()
    assert latencies["phonon"] == 12.0
    assert latencies["jev"] == 8.0
    assert latencies["yolo"] == 15.0


def test_battery_reading_public():
    collector = TelemetryCollector()
    with patch("glob.glob", return_value=["/sys/class/power_supply/BAT1"]):
        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data="85\n")):
                metrics = collector.get_system_metrics()
                assert metrics.battery_percent == 85


def test_gpu_fallback_when_unavailable():
    collector = TelemetryCollector()
    with patch("torch.cuda.is_available", return_value=False):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            metrics = collector.get_system_metrics()
            assert metrics.vram_total_gb > 0.0
            assert metrics.gpu_temp_c > 0


def test_ac_power_fallback_when_no_battery():
    collector = TelemetryCollector()
    def mock_glob(pattern):
        if "BAT" in pattern:
            return []
        if "AC" in pattern:
            return ["/sys/class/power_supply/ACAD"]
        return []

    with patch("glob.glob", side_effect=mock_glob):
        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data="1\n")):
                metrics = collector.get_system_metrics()
                assert metrics.battery_percent == 100
                assert metrics.battery_charging is True
