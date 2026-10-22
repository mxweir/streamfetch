"""Smart playlists, bookmarks, chapter navigation, and watched library folders."""

from __future__ import annotations

import json
import math
import shutil
import sqlite3
import subprocess
import threading
import time
from pathlib import Path

from streamfetch.library import MediaLibrary


class ListeningLibrary:
    def __init__(self, library: MediaLibrary):
        self.library = library
        with library._connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS smart_playlists (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
                    rules TEXT NOT NULL, created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS bookmarks (
                    id INTEGER PRIMARY KEY, path TEXT NOT NULL
                        REFERENCES media_items(path) ON DELETE CASCADE,
                    seconds REAL NOT NULL, label TEXT NOT NULL, created_at REAL NOT NULL
                );
            """)

    def save_smart(
        self,
        name,
        *,
        tag="",
        minimum_rating=0,
        max_minutes=0,
        added_days=0,
        unplayed=False,
        media_type="all",
    ):
        if not name.strip() or len(name.strip()) > 80:
            raise ValueError("Use a playlist name between 1 and 80 characters.")
        if media_type not in {"all", "audio", "video"} or not 0 <= minimum_rating <= 5:
            raise ValueError("Invalid playlist filters.")
        if not 0 <= max_minutes <= 14400 or not 0 <= added_days <= 36500 or len(tag) > 40:
            raise ValueError("Playlist filter is outside the supported range.")
        rules = dict(
            tag=tag.strip(),
            minimum_rating=int(minimum_rating),
            max_minutes=float(max_minutes),
            added_days=int(added_days),
            unplayed=bool(unplayed),
            media_type=media_type,
        )
        with self.library._connection() as db:
            db.execute(
                """INSERT INTO smart_playlists(name,rules,created_at) VALUES (?,?,?)
                ON CONFLICT(name) DO UPDATE SET rules=excluded.rules""",
                (name.strip(), json.dumps(rules), time.time()),
            )

    def smart_playlists(self):
        with self.library._connection() as db:
            return [dict(row) for row in db.execute("SELECT * FROM smart_playlists ORDER BY name")]

    def smart_items(self, playlist_id):
        with self.library._connection() as db:
            row = db.execute(
                "SELECT rules FROM smart_playlists WHERE id=?", (playlist_id,)
            ).fetchone()
        if row is None:
            raise ValueError("Smart playlist no longer exists.")
        rules = json.loads(row[0])
        conditions, args = ["rating >= ?"], [rules["minimum_rating"]]
        if rules["tag"]:
            conditions.append(
                "EXISTS (SELECT 1 FROM json_each(tags_json) WHERE value = ? COLLATE NOCASE)"
            )
            args.append(rules["tag"])
        if rules["media_type"] != "all":
            conditions.append("media_type=?")
            args.append(rules["media_type"])
        if rules["max_minutes"]:
            conditions.append("duration_seconds <= ?")
            args.append(rules["max_minutes"] * 60)
        if rules["added_days"]:
            conditions.append("added_at >= ?")
            args.append(time.time() - rules["added_days"] * 86400)
        if rules["unplayed"]:
            conditions.append(
                "NOT EXISTS (SELECT 1 FROM play_history WHERE play_history.path=media_items.path)"
            )
        return self.library._items_for_query(
            f"SELECT * FROM media_items WHERE {' AND '.join(conditions)} ORDER BY added_at DESC",
            tuple(args),
        )

    def delete_smart(self, playlist_id):
        with self.library._connection() as db:
            db.execute("DELETE FROM smart_playlists WHERE id=?", (playlist_id,))

    def add_bookmark(self, path, seconds, label):
        relative = self.library.relative_path(path)
        if not math.isfinite(seconds) or seconds < 0 or not label.strip() or len(label) > 200:
            raise ValueError("Use a valid position and a bookmark label up to 200 characters.")
        with self.library._connection() as db:
            db.execute(
                "INSERT INTO bookmarks(path,seconds,label,created_at) VALUES (?,?,?,?)",
                (relative, seconds, label.strip(), time.time()),
            )

    def bookmarks(self, path):
        with self.library._connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM bookmarks WHERE path=? ORDER BY seconds,id",
                    (self.library.relative_path(path),),
                )
            ]

    def delete_bookmark(self, bookmark_id):
        with self.library._connection() as db:
            db.execute("DELETE FROM bookmarks WHERE id=?", (bookmark_id,))


def read_chapters(path: Path):
    if not shutil.which("ffprobe"):
        return []
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_chapters", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if result.returncode:
        return []
    chapters = []
    for index, row in enumerate(json.loads(result.stdout).get("chapters", [])[:2000]):
        seconds = float(row.get("start_time", 0))
        if math.isfinite(seconds) and seconds >= 0:
            chapters.append(
                dict(
                    seconds=seconds,
                    title=row.get("tags", {}).get("title") or f"Chapter {index + 1}",
                )
            )
    return chapters


class FolderWatcher:
    """Incrementally index selected existing folders without copying their media."""

    def __init__(self, state_dir: Path, *, start=True):
        self.path = state_dir / "watched-folders.json"
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self.status = {}
        try:
            values = json.loads(self.path.read_text())
            if not isinstance(values, list) or not all(isinstance(root, str) for root in values):
                raise ValueError("Invalid watched folders file")
            self._roots = list(dict.fromkeys(values))
        except (OSError, ValueError):
            self._roots = []
        if start:
            threading.Thread(target=self._loop, daemon=True, name="streamfetch-folders").start()

    def roots(self):
        with self._lock:
            return list(self._roots)

    def add(self, value):
        root = Path(value).expanduser().resolve()
        if not root.is_dir():
            raise ValueError("Choose an existing media folder.")
        with self._lock:
            if str(root) not in self._roots:
                self._roots.append(str(root))
            self._save()

    def remove(self, value):
        with self._lock:
            self._roots = [root for root in self._roots if root != value]
            self._save()

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._roots, indent=2))
        temporary.replace(self.path)

    def scan(self):
        for value in self.roots():
            try:
                if not Path(value).is_dir():
                    raise OSError("Folder is currently unavailable.")
                summary = MediaLibrary(Path(value)).scan()
                self.status[value] = dict(checked_at=time.time(), total=summary.total, error=None)
            except (OSError, ValueError, sqlite3.Error) as exc:
                self.status[value] = dict(checked_at=time.time(), error=str(exc))

    def _loop(self):
        while not self._stop.is_set():
            self.scan()
            self._stop.wait(30)

    def shutdown(self):
        self._stop.set()
