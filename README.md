# HandsFreeOS ("Bit")

> **Ultra-fast, low-latency, hands-free voice and vision operating system control for Linux (Hyprland / Wayland).**

HandsFreeOS enables real-time conversational control of your desktop, web applications, files, and browser interfaces. It pairs an ultra-fast local System-1 decision model (**Jev**) with local continuous streaming speech-to-text (**Phonon-2**), interactive element bounding-box grounding (**OmniParser / YOLO**), and anti-bot humanized mouse trajectory generation.

---

## ⚡ Core Architecture

```
                       [ Continuous Microphone Stream ]
                                      │
                           [ Silero VAD (Speech?) ]
                                      │
                        [ Phonon-2 Local ASR (<20ms) ]
                                      │
                      ┌───────────────▼───────────────┐
                      │    Jev System-1 Classifier    │
                      │  • Ambient vs. PC Command     │
                      │  • Live Interruption Abort    │
                      │  • Destructive Action Check   │
                      └───────────────┬───────────────┘
                                      │
          ┌───────────────────────────┴───────────────────────────┐
          ▼                                                       ▼
[ Fast Tier: Direct System ]                             [ Visual Tier: Screen Action ]
• Hyprland IPC (`hyprctl`)                               • Screen capture via `grim` (15ms)
• Window matching via Jev                                • YOLO finds interactive boxes (30ms)
• Direct Shell / File / URLs                             ┌────────┴────────┐
• Latency: <50ms                                         ▼                 ▼
                                                   [ Text Labeled ]  [ Icon / Graphic ]
                                                   Jev selects box   VLM Fallback
                                                   (~30ms local)     (Gemini / Claude)
                                                   ───────────────   ─────────────────
                                                   Total: ~60ms      Total: ~500ms
                                                         │                 │
                                                         └────────┬────────┘
                                                                  ▼
                                                   [ Adaptive Input Controller ]
                                                   • Desktop: Instant dispatch
                                                   • Browser: Humanized Bézier
                                                     paths & jitter via `/dev/uinput`
                                                                  │
                                                                  ▼
                                                   [ Kokoro / Piper Local TTS ]
                                                   • Verbally confirms action (<50ms)
                                                   • Echo suppression lock
```

---

## 🚀 Key Features

* **Sub-50ms Fast Path**: Commands like *"Hey bit! open webwhatsapp"* or *"make a new txt file and type in hello world"* execute directly via Hyprland IPC and OS filesystem APIs without waiting for visual model loops.
* **Smart Context & Window Focus**: Automatically checks active Hyprland windows to focus existing browser tabs/apps rather than launching redundant duplicates.
* **Jev System-1 Decision Engine**: Non-generative, calibrated decisions in 10–40ms for:
  1. Distinguishing PC commands from ambient conversation.
  2. Matching YOLO bounding boxes to user targets.
  3. Aborting running tasks instantly (<25ms) on phrases like *"wait, stop that"*.
  4. Matching target windows from `hyprctl clients -j`.
  5. Calibrated safety scoring ($P(\text{destructive}) > 0.80$ triggers verbal confirmation).
* **Two-Stage Visual Grounding**: Labeled elements are matched locally via YOLO + Jev in ~60ms. Unlabelled graphical icons seamlessly fall back to multimodal VLMs (Gemini / Claude).
* **Anti-Bot Trajectory Generation**: Simulates natural human wrist movement using cubic Bézier curves, Fitts's Law acceleration/deceleration, and organic micro-tremors inside web browsers to evade bot detection.
* **Full Conversational Voice with Acoustic Echo Cancellation**: Confirms every action verbally with local neural TTS (<50ms) while dropping incoming microphone frames during playback so Bit never talks to itself.
* **Interactive Rich TUI Dashboard**: Real-time terminal console displaying live speech transcripts, Jev confidence scores, active window context, and chronological action logs.

---

## 🛠️ Quickstart

### 1. Installation

```bash
git clone https://github.com/shlok377/HandsFreeOS.git
cd HandsFreeOS
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2. Run the Interactive Demo

```bash
handsfree demo
```

### 3. Run the Full Test Suite

```bash
pytest -v
```

### 4. Start Live Listening Daemon

```bash
handsfree run
```

---

## 📋 Running System Tests

```bash
# Test all subsystems (audio, Jev decision, Hyprland, Bézier, TTS, and dispatch seam)
pytest tests/
```

## 📜 License

MIT
