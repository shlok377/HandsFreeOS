# 02: Perception panel overhaul with reactive 3-line audio waveform & JSON LLM output

**What to build:** The left-hand PERCEPTION & DECISION panel rendered with slate-cyan rounded borders, showing the live speech transcript in cyan bold, microphone RMS level in green, a reactive 3-line ASCII/Unicode audio waveform that pulses with microphone amplitude, an inner syntax-highlighted JSON panel for LLM outputs (`intent`, `target`, `speech`), and bulleted state indicators (`● STANDBY`, `● IDLE`/`● SPEAKING`, active window).

**Blocked by:** None (can start immediately)

**Status:** done

- [x] Panel renders with `PERCEPTION & DECISION` title and rounded cyan borders.
- [x] `Live Speech:` displays current spoken transcript in cyan bold.
- [x] `Mic Level: [0.xxx]` displays live microphone amplitude in green.
- [x] 3-line ASCII/Unicode waveform visualizer dynamically reflects audio RMS/samples, expanding on speech and collapsing to quiet dotted baseline on silence.
- [x] `LLM OUTPUT:` inner panel renders syntax-highlighted JSON formatted with `intent`, `target`, and `speech` keys.
- [x] `Jev State:`, `Active Window:`, and `TTS Voice:` display with colored bullet indicators.
