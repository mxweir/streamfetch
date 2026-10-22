"""Local EBU R128 measurements, cached by file identity; originals stay untouched."""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import threading
from functools import lru_cache

from streamfetch.library import MediaLibrary


def safe_gain(integrated, peak):
    integrated, peak = float(integrated), float(peak)
    if not math.isfinite(integrated) or not math.isfinite(peak):
        return 0.0  # Silence/invalid measurements are never boosted.
    return max(-60.0, min(12.0, -18.0 - integrated, -1.0 - peak))


class LoudnessService:
    def __init__(self, root):
        self.library = MediaLibrary(root)
        self.lock = threading.Lock()
        self.running = False
        self.completed = self.total = self.failed = 0
        self.cancel = threading.Event()
        with self.library._connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS loudness (
                path TEXT PRIMARY KEY, size INTEGER, modified INTEGER, gain REAL)""")

    def gain(self, item):
        try:
            relative = self.library.relative_path(item.path)
            stat = item.path.stat()
            with self.library._connection() as db:
                row = db.execute(
                    "SELECT gain FROM loudness WHERE path=? AND size=? AND modified=?",
                    (relative, stat.st_size, stat.st_mtime_ns),
                ).fetchone()
            return float(row[0]) if row else None
        except (OSError, ValueError):
            return None

    def start(self):
        executable = shutil.which("ffmpeg")
        if not executable:
            raise ValueError("Install FFmpeg before analysing loudness.")
        with self.lock:
            if self.running:
                return
            items = [
                i
                for i in self.library.list_items(limit=100000)
                if i.media_type == "audio" and self.gain(i) is None
            ]
            self.completed = self.failed = 0
            self.total = len(items)
            self.cancel.clear()
            self.running = True

        def work():
            try:
                for item in items:
                    if self.cancel.is_set():
                        break
                    try:
                        relative = self.library.relative_path(item.path)
                        before = item.path.stat()
                        result = subprocess.run(
                            [
                                executable,
                                "-nostdin",
                                "-hide_banner",
                                "-i",
                                str(item.path),
                                "-map",
                                "0:a:0",
                                "-af",
                                "loudnorm=I=-18:TP=-1:print_format=json",
                                "-f",
                                "null",
                                "-",
                            ],
                            capture_output=True,
                            text=True,
                            timeout=600,
                            check=True,
                        )
                        matches = re.findall(r'\{\s*"input_i".*?\}', result.stderr, re.S)
                        measurement = json.loads(matches[-1])
                        gain = safe_gain(measurement["input_i"], measurement["input_tp"])
                        after = item.path.stat()
                        if (before.st_size, before.st_mtime_ns) != (
                            after.st_size,
                            after.st_mtime_ns,
                        ):
                            raise ValueError("File changed during analysis")
                        with self.library._connection() as db:
                            db.execute(
                                "INSERT OR REPLACE INTO loudness VALUES (?,?,?,?)",
                                (relative, after.st_size, after.st_mtime_ns, gain),
                            )
                    except (OSError, ValueError, IndexError, KeyError, subprocess.SubprocessError):
                        self.failed += 1
                    self.completed += 1
            finally:
                self.running = False

        threading.Thread(target=work, name="streamfetch-loudness", daemon=True).start()


@lru_cache(maxsize=64)
def loudness_service(root):
    return LoudnessService(root)
