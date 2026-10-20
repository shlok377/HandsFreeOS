# 03: CLI Integration, Tunneling/IP Discovery & Daemon Wiring

**What to build:** Command-line options `--web-inspect` and `--inspect-port` for `handsfree run` and `handsfree demo`, with automated network discovery that probes active local LAN IP addresses and Tailscale IP addresses, displays accessible phone URLs in terminal/TUI with ASCII QR codes, and runs the streaming inspector alongside the live daemon.

**Blocked by:** 02: Lightweight Streaming Server & Mobile Inspector Web View

**Status:** done

- [x] Network discovery helper resolves host's primary LAN IP and Tailscale mesh IP (`tailscale ip -4`).
- [x] Terminal / dashboard logs connection URLs for instant mobile phone access.
- [x] Integration with `handsfree run` and `handsfree demo` flags with clean graceful shutdown on exit.
- [x] Dispatcher / grounder hooks push fresh frames into the visual hub whenever screen perception runs.
- [x] Unit & integration tests verify network discovery, CLI argument parsing, and daemon lifecycle hooks.
