"""Lightweight HTTP server providing MJPEG stream and mobile web inspector."""

import http.server
import json
import logging
import socketserver
import threading
import time
import urllib.parse
from typing import Optional

from handsfree.vision.stream_hub import VisualStreamHub

logger = logging.getLogger(__name__)

INDEX_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=3.0, user-scalable=yes">
  <title>HandsFreeOS Visual Inspector</title>
  <style>
    :root {
      --bg: #0d1117;
      --card-bg: #161b22;
      --border: #30363d;
      --text: #f0f6fc;
      --text-muted: #8b949e;
      --accent: #238636;
      --accent-cyan: #38bdf8;
      --danger: #f85149;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    header {
      background: var(--card-bg);
      border-bottom: 1px solid var(--border);
      padding: 12px 16px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky;
      top: 0;
      z-index: 10;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 10px;
      font-weight: 600;
      font-size: 1.1rem;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(35, 134, 54, 0.2);
      color: #3fb950;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 0.75rem;
      border: 1px solid rgba(63, 185, 80, 0.4);
    }
    .pulse-dot {
      width: 8px;
      height: 8px;
      background: #3fb950;
      border-radius: 50%;
      animation: pulse 1.8s infinite;
    }
    @keyframes pulse {
      0% { transform: scale(0.9); opacity: 0.8; }
      50% { transform: scale(1.3); opacity: 1; }
      100% { transform: scale(0.9); opacity: 0.8; }
    }
    .metrics {
      display: flex;
      gap: 12px;
      font-size: 0.85rem;
      color: var(--text-muted);
    }
    .metric-val {
      color: var(--accent-cyan);
      font-weight: bold;
    }
    main {
      flex: 1;
      display: flex;
      flex-direction: column;
      padding: 12px;
      gap: 12px;
      max-width: 1400px;
      margin: 0 auto;
      width: 100%;
    }
    .stream-container {
      background: #000;
      border: 1px solid var(--border);
      border-radius: 8px;
      overflow: hidden;
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 240px;
      position: relative;
    }
    .stream-container img {
      width: 100%;
      height: auto;
      display: block;
      object-fit: contain;
    }
    .hud-overlay {
      position: absolute;
      top: 8px;
      left: 8px;
      background: rgba(13, 17, 23, 0.75);
      backdrop-filter: blur(4px);
      border: 1px solid var(--border);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 0.75rem;
      pointer-events: none;
    }
    .elements-card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px;
    }
    .elements-title {
      font-size: 0.9rem;
      font-weight: 600;
      margin-bottom: 10px;
      display: flex;
      justify-content: space-between;
    }
    .box-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
      gap: 8px;
    }
    .box-item {
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--border);
      padding: 8px 10px;
      border-radius: 6px;
      font-size: 0.8rem;
    }
    .box-header {
      display: flex;
      justify-content: space-between;
      color: var(--accent-cyan);
      font-weight: bold;
    }
    .box-label {
      margin-top: 4px;
      color: var(--text);
      word-break: break-word;
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <span>HandsFreeOS</span>
      <div class="badge"><div class="pulse-dot"></div> Live Stream</div>
    </div>
    <div class="metrics">
      <div>Latency: <span id="m-latency" class="metric-val">-- ms</span></div>
      <div>Elements: <span id="m-count" class="metric-val">0</span></div>
    </div>
  </header>
  <main>
    <div class="stream-container">
      <div class="hud-overlay" id="hud">Awaiting frames...</div>
      <img id="stream" src="{stream_url}" alt="HandsFreeOS YOLO Visual Stream" />
    </div>
    <section class="elements-card">
      <div class="elements-title">
        <span>Active YOLO Detections</span>
        <span id="ts-update" style="font-size: 0.75rem; color: var(--text-muted);">Syncing...</span>
      </div>
      <div class="box-grid" id="box-list"></div>
    </section>
  </main>
  <script>
    const token = "{auth_token}";
    async function updateTelemetry() {
      try {
        const query = token ? `?token=${encodeURIComponent(token)}` : '';
        const res = await fetch(`/api/status${query}`);
        if (!res.ok) return;
        const data = await res.json();
        document.getElementById('m-latency').textContent = `${data.latency_ms.toFixed(1)} ms`;
        document.getElementById('m-count').textContent = data.box_count;
        document.getElementById('hud').textContent = `${data.width}x${data.height} | Latency: ${data.latency_ms.toFixed(1)}ms`;

        // Fetch detailed boxes
        const bRes = await fetch(`/api/boxes${query}`);
        if (bRes.ok) {
          const boxes = await bRes.json();
          const list = document.getElementById('box-list');
          list.innerHTML = '';
          boxes.forEach(b => {
            const el = document.createElement('div');
            el.className = 'box-item';
            el.innerHTML = `
              <div class="box-header">
                <span>#${b.id}</span>
                <span>${(b.confidence * 100).toFixed(0)}%</span>
              </div>
              <div class="box-label">${b.label || 'Interactive Element'}</div>
            `;
            list.appendChild(el);
          });
          document.getElementById('ts-update').textContent = `${boxes.length} elements detected`;
        }
      } catch (e) {
        console.warn('Telemetry poll error', e);
      }
    }
    setInterval(updateTelemetry, 1000);
    updateTelemetry();
  </script>
</body>
</html>
"""


class _VisualStreamHTTPHandler(http.server.BaseHTTPRequestHandler):
    """Handles HTTP requests for MJPEG stream and JSON telemetry."""

    def log_message(self, format, *args):
        # Quiet standard logging to avoid spamming the console
        return

    def _is_authorized(self) -> bool:
        auth_token = self.server.auth_token
        if not auth_token:
            return True

        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)

        # Check query param
        if qs.get("token", [None])[0] == auth_token:
            return True

        # Check authorization headers
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer ") and auth_header[7:].strip() == auth_token:
            return True

        if self.headers.get("X-Auth-Token", "") == auth_token:
            return True

        return False

    def do_GET(self):
        if not self._is_authorized():
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "Unauthorized"}\n')
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in {"", "/"}:
            self._handle_index(parsed)
        elif path == "/stream":
            self._handle_stream()
        elif path == "/api/status":
            self._handle_status()
        elif path == "/api/boxes":
            self._handle_boxes()
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not Found\n")

    def _handle_index(self, parsed):
        token_param = ""
        auth_token = self.server.auth_token or ""
        if auth_token:
            token_param = f"?token={urllib.parse.quote(auth_token)}"

        stream_url = f"/stream{token_param}"
        html = INDEX_HTML_TEMPLATE.replace("{stream_url}", stream_url).replace("{auth_token}", auth_token)

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html.encode("utf-8"))))
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _handle_status(self):
        frame = self.server.hub.get_latest_frame()
        data = {
            "status": "online",
            "latency_ms": frame.latency_ms,
            "box_count": len(frame.boxes),
            "timestamp": frame.timestamp,
            "width": frame.width,
            "height": frame.height,
            "is_fallback": frame.is_fallback,
        }
        body = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_boxes(self):
        frame = self.server.hub.get_latest_frame()
        boxes_dict = [b.model_dump() for b in frame.boxes]
        body = json.dumps(boxes_dict).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache, private")
        self.send_header("Pragma", "no-cache")
        self.end_headers()

        hub: VisualStreamHub = self.server.hub

        try:
            while self.server.is_running:
                frame = hub.get_latest_frame()
                jpeg = frame.frame_bytes

                header = (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(jpeg)).encode("ascii") + b"\r\n\r\n"
                )
                self.wfile.write(header)
                self.wfile.write(jpeg)
                self.wfile.write(b"\r\n")
                self.wfile.flush()

                # Await fresh frame or short timeout for smooth responsiveness
                hub.wait_for_next_frame(timeout=0.1)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            logger.debug(f"Stream client disconnected: {e}")


class _ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class VisualStreamServer:
    """Manages the lifecycle of the visual HTTP and MJPEG streaming daemon."""

    def __init__(
        self,
        hub: VisualStreamHub,
        host: str = "0.0.0.0",
        port: int = 8000,
        auth_token: Optional[str] = None,
    ):
        self.hub = hub
        self.host = host
        self.port = port
        self.auth_token = auth_token

        self._httpd: Optional[_ThreadedServer] = None
        self._thread: Optional[threading.Thread] = None
        self.is_running = False

    def start(self) -> None:
        """Starts the streaming server in a background thread."""
        if self.is_running:
            return

        self._httpd = _ThreadedServer((self.host, self.port), _VisualStreamHTTPHandler)
        self._httpd.hub = self.hub
        self._httpd.auth_token = self.auth_token
        self._httpd.is_running = True

        # Store bound port (relevant if self.port was 0)
        self.port = self._httpd.server_port
        self.is_running = True

        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        logger.info(f"VisualStreamServer started on http://{self.host}:{self.port}")

    def stop(self) -> None:
        """Stops the streaming server gracefully."""
        if not self.is_running:
            return

        self.is_running = False
        if self._httpd:
            self._httpd.is_running = False
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        logger.info("VisualStreamServer stopped")

    def get_url(self, host: Optional[str] = None) -> str:
        """Returns browser access URL."""
        display_host = host or ("127.0.0.1" if self.host == "0.0.0.0" else self.host)
        url = f"http://{display_host}:{self.port}/"
        if self.auth_token:
            url += f"?token={urllib.parse.quote(self.auth_token)}"
        return url
