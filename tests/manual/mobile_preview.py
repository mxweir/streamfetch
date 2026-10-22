"""Isolated UI fixture, NOT a sharing server: no real media, PC, sessions or TLS.

Run with .venv/bin/python tests/manual/mobile_preview.py and open port 8518.
Real TLS and desktop bridge integration are tested separately. Never use this
fixture to share a library: every response is synthetic and no authentication exists.
"""

import io
import json
import secrets
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from streamfetch.sharing import ASSETS

ITEMS = [
    dict(
        id=str(i),
        title=name,
        artist="Open Audio Studio",
        album="Synthetic Sessions",
        duration=30,
        media_type="audio",
        playlists=["Focus"],
        resume=4,
        gain_db=-4.5,
    )
    for i, name in enumerate(["Coastal Air", "Afterglow", "City Lights", "Golden Hour"])
]
STATE = dict(
    online=True,
    item="0",
    position=12,
    paused=True,
    volume=0.5,
    results={},
    remote_allowed=True,
    downloads_allowed=True,
)
audio = io.BytesIO()
with wave.open(audio, "wb") as sample:
    sample.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
    sample.writeframes(b"\0\0" * 8000 * 30)


class Preview(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def respond(self, body, mime="application/json", download=False):
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        if download:
            self.send_header("Content-Disposition", 'attachment; filename="synthetic.wav"')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/library":
            self.respond(json.dumps(ITEMS).encode())
        elif self.path == "/api/playback":
            self.respond(json.dumps(STATE).encode())
        elif self.path.startswith(("/media/", "/download/")):
            self.respond(audio.getvalue(), "audio/wav", self.path.startswith("/download/"))
        elif self.path == "/":
            html = (
                (ASSETS / "index.html")
                .read_text()
                .replace(
                    "<body>",
                    '<body><div style="background:#ffd65a;color:#17141d;padding:8px;'
                    'text-align:center;font:11px system-ui">ISOLATED UI PREVIEW · '
                    "SYNTHETIC DATA · NO REAL COMPUTER</div>",
                )
            )
            self.respond(html.encode(), "text/html")
        elif self.path in {"/player.js", "/style.css"}:
            self.respond(
                (ASSETS / self.path[1:]).read_bytes(),
                "text/css" if self.path.endswith("css") else "text/javascript",
            )
        elif self.path == "/logo.svg":
            self.respond(
                (
                    Path(__file__).resolve().parents[2] / "docs/assets/streamfetch-mark.svg"
                ).read_bytes(),
                "image/svg+xml",
            )
        else:
            self.send_error(404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        if self.path == "/api/progress":
            self.respond(b"{}")
            return
        nonce = secrets.token_hex(8)
        STATE["results"][nonce] = "applied"
        if body.get("item") is not None:
            STATE["item"] = body["item"]
        if body.get("position") is not None:
            STATE["position"] = body["position"]
        if body.get("volume") is not None:
            STATE["volume"] = body["volume"]
        if body.get("action") in {"play", "pause"}:
            STATE["paused"] = body["action"] == "pause"
        self.respond(json.dumps({"command": nonce}).encode())


if __name__ == "__main__":
    print("Isolated synthetic UI fixture: http://127.0.0.1:8518/", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8518), Preview).serve_forever()
