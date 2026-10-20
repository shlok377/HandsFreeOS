# 05: [Intelligence] Persistent episodic memory and fast semantic cache

**What to build:** An autonomous self-learning memory layer that records successfully resolved commands and user corrections into a local persistent store (`~/.config/handsfree/memory.json`). When a user repeats a previously learned phrase or alias, an in-memory fast-path cache dispatches the action immediately at Jev speed (<5ms) without waiting for LLM generation. When the user verbally corrects an action (e.g. "No, close Discord, not Ghostty"), the memory store updates the association across restarts.

**Blocked by:**
- 04: [Intelligence] LLM tool-calling semantic dispatcher

**Status:** done

- [x] Persistent memory store persists user-specific phrasing-to-tool mappings to `~/.config/handsfree/memory.json`.
- [x] In-memory semantic cache achieves sub-5ms lookup before calling local Qwen, promoting recurring natural phrases to instant execution.
- [x] Verbal corrections ("No, not that", "Wrong window", "I meant X") update or invalidate existing cache entries.
- [x] Unit tests verify cache hit latency (<5ms), JSON persistence across restarts, and adaptive correction updates.
