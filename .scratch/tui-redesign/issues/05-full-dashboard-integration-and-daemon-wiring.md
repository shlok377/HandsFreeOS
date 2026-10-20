# 05: Full dashboard assembly, battery footer & live daemon wiring

**What to build:** Assemble the complete full-screen TUI dashboard without the legacy top banner, adding the bottom status bar with the live battery meter `[████▒] ✦`, hook `handsfree run` to stream audio samples and model timings directly into the dashboard, and verify visual alignment and end-to-end rendering against the reference screenshot.

**Blocked by:** 02: Perception panel overhaul with reactive 3-line audio waveform & JSON LLM output, 03: Action execution log with styled event badges & visual scrollbar track, 04: System telemetry panel & pipeline latency gauges

**Status:** done

- [x] Legacy top header panel is removed and main body occupies full vertical space above the footer.
- [x] Footer bar displays `Status: Active Listening (Phonon-2 + Jev + YOLO) | Press Ctrl+C to Exit` and right-aligned battery bar `[████▒] ✦`.
- [x] `handsfree run` audio callback passes live audio frames/RMS and latency measurements to the dashboard.
- [x] Dashboard renders at high visual fidelity matching the reference screenshot in Ghostty/terminal.
- [x] Full automated test suite passes with `pytest`.
