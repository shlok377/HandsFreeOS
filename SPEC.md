# HandsFreeOS ("Bit"): System Specification

## Problem Statement

Computer users, developers, and individuals with physical accessibility needs often need to interact with their operating system, desktop applications, web browsers, and files rapidly without relying exclusively on physical keyboard and mouse inputs. Traditional voice assistants are walled gardens with high latency, rigid syntax, poor desktop window management, and zero capability to visually perceive arbitrary on-screen user interfaces or navigate web applications naturally. 

Simultaneously, existing visual GUI AI agents are too slow (taking 3 to 10 seconds per action), cloud-dependent, prone to bot-detection on websites due to synthetic mouse teleportation, and lack conversational real-time responsiveness and instant abort capabilities.

## Solution

**HandsFreeOS ("Bit")** is a low-latency, hybrid, voice-and-vision hands-free operating system control layer designed for Linux (Wayland / Hyprland). It combines local continuous speech-to-text (**Phonon-2**), an ultra-fast non-generative decision engine (**Jev**), local vision element parsing (**OmniParser / YOLO**), local neural text-to-speech (**Kokoro / Piper**), and an anti-bot humanized mouse trajectory generator. 

By employing a two-tier architecture, Bit executes deterministic system commands (opening apps, switching workspaces, creating files) directly via OS APIs in under 50ms, while seamlessly falling back to visual bounding-box grounding and human-like cursor movements for arbitrary on-screen clicking and browser navigation.

## User Stories

1. As a computer user, I want to continuously speak to Bit without pressing a hotkey or repeating a wake word every turn, so that I can control my desktop hands-free and conversationally.
2. As a computer user, I want Bit to distinguish whether I am speaking a command to my PC or talking to someone else in the room, so that background chatter does not trigger accidental actions.
3. As a developer, I want to say "open webwhatsapp" and have Bit bring an existing WhatsApp Web tab/window to focus if already open, so that I avoid opening dozens of redundant browser tabs.
4. As a developer, I want to say "open webwhatsapp" and have Bit automatically launch a new browser window to `https://web.whatsapp.com` if no instance exists, so that navigation is frictionless.
5. As a computer user, I want to say "open herdr" and have Bit identify and launch the `herdr` application or relevant service automatically, so that I don't have to navigate menus manually.
6. As a writer, I want to say "make a new txt file and type in hello world", so that files are created and populated directly through the filesystem in milliseconds without clunky UI navigation.
7. As a web user, I want Bit to locate on-screen search bars, buttons, and navigation elements using OmniParser and YOLO bounding boxes, so that I can click elements purely by their visual or OCR labels.
8. As a power user, I want Jev to match my spoken phrase (e.g., "search bar") against YOLO bounding-box labels locally in under 40ms, so that on-screen clicking feels instantaneous and private.
9. As a web user, I want Bit to fall back to a Vision-Language Model when an on-screen element is a graphic icon without text labels, so that complex and unlabelled user interfaces remain fully accessible.
10. As a web user, I want mouse movements inside web browsers to follow organic Bézier curves with natural acceleration and micro-tremors, so that anti-bot detection systems (like Cloudflare and reCAPTCHA) do not flag my session.
11. As a desktop user, I want mouse clicks on native desktop applications to dispatch instantly, so that I get maximum speed when anti-bot tracking is not a factor.
12. As a typist, I want keyboard strokes in web browsers to feature realistic timing variance and micro-jitter emitted through a virtual kernel device (`/dev/uinput`), so that browser-based bot heuristics are not tripped.
13. As a busy multitasker, I want to say "wait", "no, stop", or "cancel that" while Bit is executing an action, so that Jev detects my abort intent in under 25ms and immediately halts mouse and keyboard execution.
14. As a user with multiple open windows, I want to say "switch to Discord" or "close this" and have Jev match my words against the live list of Hyprland window clients, so that window switching is instant and accurate.
15. As a cautious user, I want Bit to pause and verbally request confirmation whenever an action is potentially destructive ($P(\text{destructive}) > 0.80$), so that I never lose data accidentally.
16. As a conversational user, I want Bit to verbally acknowledge every confirmed action in under 50ms using a natural local neural voice, so that I always know what my PC is doing without looking away from my current task.
17. As an audio user, I want Bit to mute microphone ingestion while its own voice is playing, so that Bit never hears and accidentally executes its own spoken words.
18. As someone dictating messages, I want Jev to classify whether speech inside an active input field is meant as literal dictation or an imperative OS command, so that my messages are typed verbatim without executing accidentally.
19. As a terminal user, I want an interactive Rich TUI console displaying live transcripts, Jev decision scores, active window context, and action logs, so that I have complete observability into Bit's internal state.
20. As a privacy-conscious user, I want speech recognition, intent routing, and TTS to run 100% offline on my machine, so that my voice and ambient audio never leave my PC.

## Implementation Decisions

### 1. Speech Ingestion & Acoustic Safety
- Audio is ingested continuously using `sounddevice` with chunking driven by a lightweight Voice Activity Detector (`Silero VAD`).
- Streaming audio is converted to text tokens locally using **Phonon-2** (`fermion-research`), running on CUDA/CPU with Parakeet-TDT 0.6B architecture.
- An acoustic echo suppression gate (`is_speaking` mutex) halts ASR ingestion during TTS playback to prevent self-triggering loops.

### 2. High-Speed System-1 Decision Layer (Jev)
The pipeline delegates all fast discrete, boolean, and ranking decisions to Jev (`typesafe-ai` / `agent-jev`):
- **Ambient Filter**: Evaluates `Noul(utterance, question="Is this speech directed as a command to the PC?")` in <30ms.
- **YOLO Box Selector**: Evaluates `Choice(candidate_boxes, question="Which element matches: '<target>'?")` over candidate labels extracted by OmniParser/YOLO in ~40ms.
- **Live Interruption Abort**: Evaluates `Noul(chunk, question="Is the user interrupting, aborting, or correcting the current action?")` in <25ms on streaming phonemes/tokens.
- **Window & Workspace Disambiguation**: Evaluates `Choice(open_windows, question="Which window does the user want to focus or close?")` over the live JSON array from `hyprctl clients -j` in ~35ms.
- **Safety Risk Gate**: Computes a calibrated scalar score $P(\text{destructive})$. If $P > 0.80$, execution pauses and Bit triggers an interactive confirmation dialogue.
- **Dictation vs. Command**: When a text field is active, evaluates `Noul(speech, context=active_focused_input, question="Is this text meant to be typed literally as dictation?")` in ~30ms.

### 3. Execution Engine & Desktop Environment
- Tailored for **Hyprland on Wayland**.
- Direct system commands execute via `hyprctl` IPC (`hyprctl dispatch focuswindow`, `hyprctl dispatch workspace`, `hyprctl dispatch exec`).
- File creation, text editing, and CLI actions execute directly via Python system/OS bindings in <10ms.
- Smart focus brings existing windows and matching browser URLs to the foreground before falling back to new application launches.

### 4. Vision & Grounding Architecture
- Screenshot capture is performed natively using `grim` in under 15ms.
- Element detection utilizes **OmniParser / YOLO** to generate labeled interactive bounding boxes.
- **Two-Stage Grounding**:
  - Stage 1 (Local): Labeled and OCR-recognized elements are matched directly via Jev in ~40ms.
  - Stage 2 (VLM Fallback): If Jev confidence is low or the target is an unlabelled graphical icon, the screenshot is forwarded to a multimodal VLM (Gemini 2.5 Flash / Claude) for visual coordinate reasoning.

### 5. Adaptive Input Controller & Anti-Bot Protection
- Mouse and keyboard inputs are emitted via a virtual kernel device using `/dev/uinput`.
- **Desktop Mode**: Instant direct dispatch for local native windows (terminal, file manager, settings).
- **Browser Mode**: Natural humanized motion using cubic Bézier curves, Fitts's Law velocity curves, random micro-tremors, variable click dwell times (60–120ms), and natural typing intervals to bypass browser anti-bot behavioral analysis.

### 6. Conversational Feedback & Interface
- Spoken audio feedback is generated locally using **Kokoro-82M / Piper TTS** in <50ms with zero cloud latency.
- The user interface is an interactive **Rich TUI** console displaying live streaming transcripts, Jev routing gauges, active window title, and chronological action logs.

## Testing Decisions

### Testing Philosophy
Good tests must test external observable behavior across the pipeline rather than internal mock configurations or private methods. 

### Seam Architecture
The primary testing seam is the **Intent & Execution Dispatch Loop**:
- Input: An event containing an audio transcription chunk or synthetic voice event + environment state (mocked `hyprctl clients` JSON, mock screenshot, and mock OmniParser bounding boxes).
- Output: The resulting action event (`FocusWindow`, `LaunchApp`, `CreateFile`, `ClickBox`, `TypeDictation`, `TriggerConfirmation`), Jev decision payload, and generated TTS response string.
- This single high-level integration seam allows complete end-to-end verification of all user stories without requiring live microphones, physical Wayland displays, or external cloud networks.

### Verification Suite
- **Jev Decision Unit Tests**: Verifying calibrated outputs for `Choice`, `Noul`, and `Score` across representative inputs.
- **Anti-Bot Trajectory Tests**: Verifying that generated mouse paths exhibit non-zero curvature, organic acceleration, and timing jitter rather than step-function coordinates.
- **Safety Interruption Tests**: Verifying that streaming an abort token ("wait", "stop") immediately flips the execution cancellation token in <25ms.
- **Hyprland IPC Dispatch Tests**: Verifying correct IPC payload formatting for window focusing and application launching.

## Out of Scope

- Non-Linux platforms (Windows, macOS) in the initial release (focus is Wayland/Hyprland on Linux).
- Complex multi-agent web scraping workflows spanning hours without user supervision.
- Fine-tuning custom speech models from scratch (pre-trained Phonon-2 and Kokoro weights are utilized).
- Physical eye-tracking or gaze-based pointing hardware integrations.

## Further Notes

- The system runs on user-grade hardware (tested on an NVIDIA RTX 3050 with 6GB VRAM on Arch Linux/Omarchy).
- A pluggable provider interface ensures that the visual fallback tier can toggle between Google Gemini, Anthropic Claude, and local Ollama/vLLM endpoints via standard environment configuration.
