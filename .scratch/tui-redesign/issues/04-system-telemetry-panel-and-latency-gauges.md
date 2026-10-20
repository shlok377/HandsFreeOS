# 04: System telemetry panel & pipeline latency gauges

**What to build:** The bottom-right SYSTEM TELEMETRY panel containing dual columns: the left column shows CPU %, VRAM (used/total and %), RAM (used/total and %), and GPU temperature with block bar charts; the right column contains an inner `PIPELINE LATENCY` panel with block-meter latency gauges for Phonon-2, Jev OS, and YOLO.

**Blocked by:** 01: Live hardware telemetry collector & pipeline latency tracker

**Status:** done

- [x] Panel renders with `SYSTEM TELEMETRY` title and rounded cyan borders.
- [x] Left column displays CPU, VRAM, RAM, and GPU temperature metrics with filled block bars (`[████▒▒▒▒]`) and cyan/green styling.
- [x] Right column contains inner `PIPELINE LATENCY` panel with gauges for Phonon-2, Jev OS, and YOLO in milliseconds.
- [x] Values update dynamically from the telemetry collector without blocking the TUI render loop.
