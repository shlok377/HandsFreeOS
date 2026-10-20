# 01: Live hardware telemetry collector & pipeline latency tracker

**What to build:** A lightweight, non-blocking telemetry engine that samples Linux `/proc/stat` (CPU %), `/proc/meminfo` (RAM usage and GBs), PyTorch CUDA / nvidia-smi (VRAM and GPU temp), `/sys/class/power_supply` (battery meter), and tracks rolling execution latencies for Phonon-2, Jev OS, and YOLO, backed by unit tests verifying accurate parsing and safe fallbacks.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] Non-blocking polling function returns CPU utilization percentage, RAM used/total in GB and percentage.
- [x] GPU VRAM usage and temperature are read via PyTorch CUDA / nvidia-smi with graceful fallback if no GPU is active.
- [x] Battery meter capacity (0-100%) and charging status are retrieved from `/sys/class/power_supply/BAT*` or AC supply.
- [x] Pipeline latencies for Phonon-2, Jev OS, and YOLO can be recorded and queried with rolling averages.
- [x] Unit tests cover `/proc/stat`, `/proc/meminfo`, GPU fallback, battery detection, and latency tracking.
