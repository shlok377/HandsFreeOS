# 02: [Intelligence] System desktop app and web service auto-discovery

**What to build:** An automated application and web destination discovery engine that dynamically scans the local Linux system's desktop entries (`/usr/share/applications` and `~/.local/share/applications`) and resolves common web services (e.g. YouTube, Reddit, WhatsApp, Discord, GitHub). When a user asks to open an app or service, Bit resolves the exact executable command or web URL dynamically without requiring hand-coded regex aliases.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Desktop scanner parses `.desktop` files into a searchable app catalog with display names, executable binaries, and keywords.
- [ ] Web destination resolver recognizes colloquial references (e.g., "YouTube", "Discord in my browser") and returns valid HTTPS URLs.
- [ ] Strips trailing intent fluff such as "in my browser", "on my screen", or "from my computer" before resolving targets.
- [ ] Unit tests verify discovery of desktop applications and resolution of web targets without hardcoded string matching in the main dispatch loop.
