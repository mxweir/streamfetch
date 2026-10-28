"""Opt-in, authenticated read-only player for a selected library on a trusted LAN."""

from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import re
import secrets
import socket
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

from streamfetch.connected import bounded_number, playback_hub
from streamfetch.home_tls import HomeIdentity, validate_address
from streamfetch.library import MediaLibrary
from streamfetch.loudness import loudness_service
from streamfetch.settings import default_state_dir

ASSETS = Path(__file__).parent / "assets" / "mobile"


def local_address():
    """Ask the OS for its outgoing interface without DNS or sending a packet.

    Hostname resolution can block for over a minute on disconnected Macs. A UDP
    connect only selects a local route; it does not transmit application data.
    The address is still a suggestion, never permission to start sharing.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.settimeout(0.25)
            probe.connect(("192.0.2.1", 9))
            return validate_address(probe.getsockname()[0])
    except (OSError, ValueError):
        return "127.0.0.1"


def byte_range(header, size):
    if not header:
        return 0, size - 1, False
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", header)
    if not match or not any(match.groups()) or size == 0:
        raise ValueError("Invalid byte range")
    first, last = match.groups()
    if not first:
        count = int(last)
        if count <= 0:
            raise ValueError("Invalid suffix range")
        start, end = max(0, size - count), size - 1
    else:
        start, end = int(first), min(int(last) if last else size - 1, size - 1)
    if start >= size or start > end:
        raise ValueError("Unsatisfiable byte range")
    return start, end, True


class HomePlayer:
    def __init__(
        self,
        library: MediaLibrary,
        *,
        identity,
        host="0.0.0.0",
        port=8767,
        address=None,
        allow_remote=False,
        allow_downloads=False,
    ):
        self.library = library
        self.allow_remote = allow_remote
        self.allow_downloads = allow_downloads
        self.hub = playback_hub(library.root)
        self.loudness = loudness_service(library.root)
        self._control_attempts = {}
        self._stopped = False
        self.secret = secrets.token_urlsafe(18)
        self._key = secrets.token_bytes(32)
        self._sessions = {}
        self._attempts = {}
        self._lock = threading.RLock()
        self.address = validate_address(address or local_address())
        # Reject an interface that does not belong to this computer before issuing its certificate.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((self.address, 0))
        self.identity = identity
        self.instance_id = secrets.token_hex(16)
        self.pair_generation = 0
        self._pair_digest = None
        self.pair_expires = 0
        self.pair_used = False
        self._allowed_hosts = {self.address, "127.0.0.1", "localhost"}
        context = identity.context(self.address)
        owner = self

        class TLSServer(ThreadingHTTPServer):
            def get_request(self):
                connection, client = super().get_request()
                connection.settimeout(15)
                return context.wrap_socket(
                    connection, server_side=True, do_handshake_on_connect=False
                ), client

            def handle_error(self, request, client_address):
                pass  # Invalid TLS requests must not log user data.

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def setup(self):
                self.request.do_handshake()
                super().setup()
                self.connection.settimeout(15)

            def log_message(self, *args):
                pass  # Never log credentials, cookies or library filenames.

            def respond(self, status, body=b"", mime="text/plain; charset=utf-8", headers=None):
                self.send_response(status)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                # Keep same-origin form POSTs verifiable; no-referrer makes Origin null.
                self.send_header("Referrer-Policy", "same-origin")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; "
                    "script-src 'self'; style-src 'self'; media-src 'self'; "
                    "img-src 'self' data:; frame-ancestors 'none'; form-action 'self'",
                )
                for name, value in (headers or {}).items():
                    self.send_header(name, value)
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)

            def valid_host(self):
                try:
                    parsed = urlsplit("http://" + self.headers.get("Host", ""))
                    return (
                        parsed.hostname in owner._allowed_hosts
                        and parsed.port == owner.port
                        and parsed.username is None
                    )
                except ValueError:
                    return False

            def authenticated(self):
                cookie = SimpleCookie()
                try:
                    cookie.load(self.headers.get("Cookie", ""))
                    token = cookie["streamfetch_session"].value
                except (KeyError, ValueError):
                    return False
                with owner._lock:
                    return owner._sessions.get(token, 0) > time.time()

            def do_HEAD(self):
                self.do_GET()

            def do_GET(self):
                if not self.valid_host():
                    self.respond(403, b"Unrecognized host")
                    return
                route = urlsplit(self.path).path
                if route == "/logo.svg":
                    logo = Path(__file__).parent / "assets" / "streamfetch-mark.svg"
                    if not logo.exists():
                        logo = (
                            Path(__file__).resolve().parents[2] / "docs/assets/streamfetch-mark.svg"
                        )
                    self.respond(200, logo.read_bytes(), "image/svg+xml")
                    return
                if route in {"/login", "/pair"}:
                    self.respond(
                        200,
                        (ASSETS / ("pair.html" if route == "/pair" else "login.html")).read_bytes(),
                        "text/html; charset=utf-8",
                    )
                    return
                if route in {"/style.css", "/player.js", "/pair.js"}:
                    self.respond(
                        200,
                        (ASSETS / route[1:]).read_bytes(),
                        "text/css" if route.endswith("css") else "text/javascript",
                    )
                    return
                if not self.authenticated():
                    self.respond(303, headers={"Location": "/login"})
                    return
                if route == "/":
                    self.respond(
                        200, (ASSETS / "index.html").read_bytes(), "text/html; charset=utf-8"
                    )
                elif route == "/api/library":
                    items = owner.items()
                    self.respond(200, json.dumps(items).encode(), "application/json")
                elif route == "/api/playback":
                    snapshot = owner.hub.snapshot()
                    path = snapshot.pop("path", None)
                    try:
                        snapshot["item"] = owner.identifier(Path(path)) if path else None
                    except ValueError:
                        snapshot["item"] = None
                    snapshot["remote_allowed"] = owner.allow_remote
                    snapshot["downloads_allowed"] = owner.allow_downloads
                    if not owner.allow_remote:
                        snapshot = dict(
                            remote_allowed=False,
                            downloads_allowed=owner.allow_downloads,
                            online=False,
                        )
                    self.respond(200, json.dumps(snapshot).encode(), "application/json")
                elif route.startswith("/media/"):
                    self.stream(route.removeprefix("/media/"))
                elif route.startswith("/download/"):
                    if not owner.allow_downloads:
                        self.respond(403, b"Downloads are not enabled by the computer owner.")
                        return
                    self.stream(route.removeprefix("/download/"), download=True)
                else:
                    self.respond(404)

            def stream(self, identifier, download=False):
                item = owner.find_item(identifier)
                if item is None:
                    self.respond(404)
                    return
                try:
                    owner.library.relative_path(item.path)  # Revalidate symlink containment.
                    with item.path.open("rb") as media:
                        size = item.path.stat().st_size
                        try:
                            start, end, partial = byte_range(self.headers.get("Range"), size)
                        except ValueError:
                            self.respond(416, headers={"Content-Range": f"bytes */{size}"})
                            return
                        length = max(0, end - start + 1)
                        self.send_response(206 if partial else 200)
                        self.send_header(
                            "Content-Type",
                            mimetypes.guess_type(item.path.name)[0] or "application/octet-stream",
                        )
                        self.send_header("Content-Length", str(length))
                        self.send_header("Accept-Ranges", "bytes")
                        self.send_header("Cache-Control", "private, no-store")
                        self.send_header("X-Content-Type-Options", "nosniff")
                        if download:
                            self.send_header(
                                "Content-Disposition",
                                "attachment; filename*=UTF-8''" + quote(item.path.name, safe=""),
                            )
                        if partial:
                            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                        self.end_headers()
                        if self.command == "HEAD":
                            return
                        media.seek(start)
                        while length:
                            if owner._stopped or (download and not owner.allow_downloads):
                                self.close_connection = True
                                break
                            chunk = media.read(min(length, 256 * 1024))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            length -= len(chunk)
                except (OSError, ValueError):
                    self.close_connection = True

            def do_POST(self):
                origin = self.headers.get("Origin")
                if (
                    not self.valid_host()
                    or (origin and origin != f"https://{self.headers.get('Host')}")
                    or self.headers.get("Sec-Fetch-Site") == "cross-site"
                ):
                    self.respond(403)
                    return
                route = urlsplit(self.path).path
                if route in {"/api/control", "/api/progress"}:
                    if not self.authenticated():
                        self.respond(401)
                        return
                    if route == "/api/control" and not owner.allow_remote:
                        self.respond(403, b"Computer control is disabled.")
                        return
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                        if not 0 < length <= 4096:
                            self.close_connection = True
                            self.respond(413)
                            return
                        with owner._lock:
                            now = time.monotonic()
                            attempts = [
                                stamp
                                for stamp in owner._control_attempts.get(self.client_address[0], [])
                                if stamp > now - 60
                            ]
                            if len(attempts) >= 120:
                                self.respond(429)
                                return
                            owner._control_attempts[self.client_address[0]] = [*attempts, now]
                        payload = json.loads(self.rfile.read(length))
                        if not isinstance(payload, dict):
                            raise ValueError("Expected an object")
                        item = owner.find_item(payload.get("item")) if payload.get("item") else None
                        if payload.get("item") and item is None:
                            raise ValueError("Track is no longer available.")
                        position = payload.get("position")
                        if position is not None:
                            position = bounded_number(position, 0, 864000)
                            if item and item.duration_seconds:
                                position = min(position, item.duration_seconds)
                        if route == "/api/progress":
                            if item is None or position is None:
                                raise ValueError("Track and position are required.")
                            owner.library.set_playback_position(item.path, position)
                            self.respond(200, b"{}", "application/json")
                            return
                        with owner._lock:
                            if not owner.allow_remote or owner._stopped:
                                self.respond(403)
                                return
                            command = owner.hub.send(
                                payload.get("action"),
                                path=str(item.path) if item else None,
                                position=position,
                                volume=payload.get("volume"),
                            )
                        self.respond(
                            202, json.dumps({"command": command}).encode(), "application/json"
                        )
                    except (ValueError, TypeError) as error:
                        self.respond(
                            400, json.dumps({"error": str(error)}).encode(), "application/json"
                        )
                    return
                if route == "/logout":
                    cookie = SimpleCookie(self.headers.get("Cookie", ""))
                    with owner._lock:
                        if "streamfetch_session" in cookie:
                            owner._sessions.pop(cookie["streamfetch_session"].value, None)
                    self.respond(
                        303,
                        headers={
                            "Location": "/login",
                            "Set-Cookie": "streamfetch_session=; Path=/; HttpOnly; "
                            "Secure; SameSite=Strict; Max-Age=0",
                        },
                    )
                    return
                if route not in {"/login", "/pair"}:
                    self.respond(404)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 1024:
                        raise ValueError
                except ValueError:
                    self.respond(413)
                    self.close_connection = True
                    return
                form = parse_qs(self.rfile.read(length).decode("utf-8", errors="replace"))
                with owner._lock:
                    now = time.time()
                    owner._attempts = {
                        ip: attempts
                        for ip, attempts in owner._attempts.items()
                        if attempts and attempts[-1] > now - 60
                    }
                    attempts = [
                        ts
                        for ts in owner._attempts.get(self.client_address[0], [])
                        if ts > now - 60
                    ]
                    if len(attempts) >= 5:
                        self.respond(429, b"Too many attempts. Try again in one minute.")
                        return
                    attempts.append(now)
                    owner._attempts[self.client_address[0]] = attempts
                    supplied = form.get("token" if route == "/pair" else "secret", [""])[0]
                    valid = (
                        (
                            owner._pair_digest is not None
                            and owner.pair_expires > now
                            and hmac.compare_digest(
                                hashlib.sha256(supplied.encode()).digest(), owner._pair_digest
                            )
                        )
                        if route == "/pair"
                        else hmac.compare_digest(supplied.encode(), owner.secret.encode())
                    )
                    if not valid:
                        self.respond(403, b"Incorrect pairing code. Return to /login to retry.")
                        return
                    owner._sessions = {
                        key: expiry for key, expiry in owner._sessions.items() if expiry > now
                    }
                    if len(owner._sessions) >= 32:
                        self.respond(429, b"Too many sessions. Restart sharing to revoke them.")
                        return
                    token = secrets.token_urlsafe(32)
                    owner._sessions[token] = now + 43200
                    if route == "/pair":
                        owner._pair_digest = None
                        owner.pair_used = True
                self.respond(
                    200 if route == "/pair" else 303,
                    headers={
                        "Location": "/",
                        "Set-Cookie": f"streamfetch_session={token}; Path=/; HttpOnly; "
                        "Secure; SameSite=Strict; Max-Age=43200",
                    },
                )

        self._server = TLSServer((host, int(port)), Handler)
        self._server.daemon_threads = True
        self.port = self._server.server_port
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True, name="streamfetch-home-player"
        )
        self._thread.start()

    @property
    def url(self):
        return f"https://{self.address}:{self.port}"

    def pairing_url(self):
        return self.pairing_grant()[0]

    def pairing_grant(self):
        with self._lock:
            token = secrets.token_urlsafe(32)
            self._pair_digest = hashlib.sha256(token.encode()).digest()
            self.pair_expires = time.time() + 120
            self.pair_used = False
            self.pair_generation += 1
            return f"{self.url}/pair#{token}", self.pair_generation

    def identifier(self, path):
        return hmac.new(
            self._key, self.library.relative_path(path).encode(), hashlib.sha256
        ).hexdigest()[:32]

    def find_item(self, identifier):
        for item in self.library.list_items(limit=100000):
            try:
                if self.identifier(item.path) == identifier and item.path.is_file():
                    return item
            except (OSError, ValueError):
                continue
        return None

    def items(self):
        memberships = {}
        for playlist in self.library.playlists():
            for item in self.library.playlist_items(playlist.id):
                memberships.setdefault(str(item.path), []).append(playlist.name)
        result = []
        for item in self.library.list_items(limit=100000):
            try:
                identifier = self.identifier(item.path)
                if not item.path.is_file():
                    continue
            except (OSError, ValueError):
                continue
            result.append(
                dict(
                    id=identifier,
                    title=item.title,
                    artist=item.artist,
                    album=item.album,
                    media_type=item.media_type,
                    duration=item.duration_seconds,
                    playlists=memberships.get(str(item.path), []),
                    resume=self.library.playback_position(item.path),
                    gain_db=self.loudness.gain(item)
                    if self.library.player_setting("normalize", "off") == "on"
                    else None,
                )
            )
        return result

    def stop(self):
        with self._lock:
            self._stopped = True
            self._sessions.clear()
            self._pair_digest = None
            self.hub.revoke()
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)

    def set_permissions(self, remote, downloads):
        with self._lock:
            self.allow_remote = bool(remote)
            self.allow_downloads = bool(downloads)
            if not self.allow_remote:
                self.hub.revoke()


class SharingService:
    def __init__(self):
        self.player = None
        self._lock = threading.RLock()

    def start(self, library, port, address=None, allow_remote=False, allow_downloads=False):
        with self._lock:
            if self.player:
                raise ValueError("Stop the existing sharing session first.")
            self.player = HomePlayer(
                library,
                identity=HomeIdentity(default_state_dir()),
                port=port,
                address=address,
                allow_remote=allow_remote,
                allow_downloads=allow_downloads,
            )

    def stop(self):
        with self._lock:
            if self.player:
                self.player.stop()
                self.player = None
