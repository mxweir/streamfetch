"""In-memory, leased desktop playback bridge. No socket or OS remote control."""

from __future__ import annotations

import math
import secrets
import threading
import time
from collections import deque
from functools import lru_cache


def bounded_number(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("A numeric value is required.")
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError("Value outside the allowed range.")
    return float(value)


class PlaybackHub:
    def __init__(self):
        self.lock = threading.RLock()
        self.owner = None
        self.updated = 0
        self.state = {}
        self.pending = deque()
        self.results = {}

    def publish(self, owner, path, *, position=0, paused=True, volume=1, blocked=False, ack=None):
        with self.lock:
            if self.owner not in {None, owner} and time.monotonic() - self.updated < 10:
                return False
            self.owner = owner
            self.updated = time.monotonic()
            self.state = dict(
                path=str(path),
                position=bounded_number(position, 0, 864000),
                paused=bool(paused),
                volume=bounded_number(volume, 0, 1),
                blocked=bool(blocked),
            )
            if ack in self.results:
                self.results[ack] = "blocked" if blocked else "applied"
            return True

    def snapshot(self):
        with self.lock:
            return {
                **self.state,
                "online": bool(self.owner) and time.monotonic() - self.updated < 10,
                "results": dict(self.results),
            }

    def send(self, action, *, path=None, position=None, volume=None):
        if action not in {"play", "pause", "seek", "volume", "next", "previous"}:
            raise ValueError("Unsupported player command.")
        if action == "seek" and position is None or action == "volume" and volume is None:
            raise ValueError("This command needs a value.")
        with self.lock:
            if not self.snapshot()["online"]:
                raise ValueError("Open the computer player and press play once to connect it.")
            now = time.monotonic()
            self.pending = deque(c for c in self.pending if c["expires"] > now)
            if len(self.pending) >= 16:
                raise ValueError("The computer is busy. Try again shortly.")
            command = dict(nonce=secrets.token_hex(16), action=action, path=path, expires=now + 10)
            if position is not None:
                command["position"] = bounded_number(position, 0, 864000)
            if volume is not None:
                command["volume"] = bounded_number(volume, 0, 1)
            self.results = dict(list(self.results.items())[-31:])
            self.results[command["nonce"]] = "pending"
            self.pending.append(command)
            return command["nonce"]

    def take(self, owner):
        with self.lock:
            if self.owner != owner:
                return None
            while self.pending:
                command = self.pending.popleft()
                if command["expires"] > time.monotonic():
                    return command
                self.results[command["nonce"]] = "expired"
            return None

    def revoke(self):
        with self.lock:
            self.pending.clear()
            self.results.clear()


@lru_cache(maxsize=64)
def playback_hub(root):
    return PlaybackHub()
