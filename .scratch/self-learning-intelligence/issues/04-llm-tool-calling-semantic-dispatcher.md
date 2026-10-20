# 04: [Intelligence] LLM tool-calling semantic dispatcher

**What to build:** Inverts the command dispatch architecture so arbitrary natural language speech (e.g. "Open YouTube in my browser", "Close that Discord app", "Bye bye", "How many windows are open?") is evaluated through local Qwen 2.5 with a formal OS tool-calling schema (`close_window`, `open_url`, `launch_app`, `send_hotkey`, `answer_user`, `shutdown`, `abort`). Eliminates the brittle regex ladder while preserving Jev fast safety scoring ($P(\text{destructive}) > 0.80$).

**Blocked by:**
- 01: [Intelligence] Hyprland real window closing and lifecycle
- 02: [Intelligence] System desktop app and web service auto-discovery
- 03: [Intelligence] Context-aware interruption and abort scoper

**Status:** ready-for-agent

- [ ] Local Qwen reasoner prompt defines explicit OS tools with parameters and expected response schema.
- [ ] Dispatch seam evaluates natural speech directly through semantic tool calling without falling into blind shell execution.
- [ ] Jev safety scoring runs on proposed tool actions before execution, prompting for confirmation if $P(\text{destructive}) > 0.80$.
- [ ] TUI dashboard displays a compact, single-line summary of the LLM tool decision in "LLM O/P:".
- [ ] Comprehensive seam tests verify resolution of complex commands ("Open YouTube in my browser", "Close that Discord app", "Bye bye") across mocked and live model interfaces.
