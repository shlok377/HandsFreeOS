# 01: [Intelligence] Hyprland real window closing and lifecycle

**What to build:** Enables HandsFreeOS to actually close or kill windows on Hyprland when asked to close a window or application (e.g. "Close that Discord app", "Close this window"). Instead of merely focusing windows, the OS layer issues genuine compositor close dispatches, reports `ActionType.CLOSE_WINDOW` in telemetry and action logs, and provides verbal confirmation to the user.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] Hyprland controller implements `close_window(address_or_class: str) -> bool` using `hyprctl dispatch closewindow address:<address>` with fallback to `killactive`.
- [x] Primary dispatch seam routes close requests to `ActionType.CLOSE_WINDOW`, targeting either the explicitly named window or the currently active window.
- [x] Verbal feedback confirms window closure (e.g., "Closed Discord").
- [x] Unit and seam tests verify that target window addresses are passed to the compositor close command and `ActionType.CLOSE_WINDOW` is returned.
