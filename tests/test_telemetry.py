"""Tests for live telemetry collector."""

import os
from unittest.mock import patch, mock_open
import pytest

from handsfree.ui.telemetry import TelemetryCollector, SystemMetrics


def test_system_metrics_defaults():
    metrics = SystemMetrics()
    assert metrics.cpu_percent >= 0.0
    assert metrics.ram_total_gb >= 0.0
    assert 0 <= metrics.battery_percent <= 100


def test_parse_proc_stat():
    collector = TelemetryCollector()
    proc_stat_mock = (
        "cpu  1000 200 300 5000 100 50 20 0 0 0\n"
        "cpu0 500 100 150 2500 50 25 10 0 0 0\n"
    )
    with patch("builtins.open", mock_open(read_data=proc_stat_mock)):
        busy, total = collector._read_cpu_raw()
        assert total == 1000 + 200 + 300 + 5000 + 100 + 50 + 20
        assert busy == total - 5000 - 100  # idle and iowait excluded


def test_parse_proc_meminfo():
    collector = TelemetryCollector()
    meminfo_mock = (
        "MemTotal:       32768000 kB\n"
        "MemFree:         8192000 kB\n"
        "MemAvailable:   16384000 kB\n"
    )
    with patch("builtins.open", mock_open(read_data=meminfo_mock)):
        ram_pct, used_gb, total_gb = collector._read_ram()
        assert total_gb == pytest.approx(31.25, rel=0.1)
        assert used_gb == pytest.approx(15.62, rel=0.1)
        assert ram_pct == pytest.approx(50.0, rel=0.1)


def test_pipeline_latencies_recording():
    collector = TelemetryCollector()
    collector.record_latency("phonon", 12.0)
    collector.record_latency("jev", 8.0)
    collector.record_latency("yolo", 15.0)

    latencies = collector.get_pipeline_latencies()
    assert latencies["phonon"] == 12.0
    assert latencies["jev"] == 8.0
    assert latencies["yolo"] == 15.0


def test_battery_reading():
    collector = TelemetryCollector()
    with patch("os.path.exists", return_value=True):
        with patch("builtins.open", mock_open(read_data="85\n")):
            pct, charging = collector._read_battery()
            assert pct == 85
