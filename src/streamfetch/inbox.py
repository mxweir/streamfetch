"""Offline link inbox, not a download scheduler.

``handoff`` atomically moves ready links to the download editor. It never starts
jobs. ``attach_jobs`` can record IDs after the existing job manager accepts them.
Duplicates retain their status and notes; resubmission always needs an explicit
``restore``. All batch mutations validate before writing and use SQLite transactions.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .settings import default_state_dir

MAX_BATCH = 100
MAX_ENTRIES = 10_000
MAX_NOTE = 2000
STATUSES = ("ready", "handed_off", "archived")
_YOUTUBE = {
    "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
    "youtube-nocookie.com", "www.youtube-nocookie.com", "youtu.be", "www.youtu.be",
}
_SOUNDCLOUD = {"soundcloud.com", "www.soundcloud.com", "m.soundcloud.com",
               "on.soundcloud.com", "snd.sc"}


def canonical_url(value: str) -> str:
    """Canonicalize supported public links without making network requests.

    Video aliases merge, but video+playlist remains distinct from video-only.
    SoundCloud's secret_token is preserved (it can authorize an unlisted track).
    Redirect shortlinks are retained, never resolved by this offline store.
    """
    if not isinstance(value, str) or len(value) > 4096 or any(
        char.isspace() or ord(char) < 32 or char == "\\" for char in value
    ):
        raise ValueError("Use a valid YouTube or SoundCloud link.")
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Use a valid YouTube or SoundCloud link.") from exc
    if (
        parsed.scheme not in {"http", "https"} or host not in _YOUTUBE | _SOUNDCLOUD
        or parsed.username is not None or parsed.password is not None
        or port not in (None, 80 if parsed.scheme == "http" else 443)
    ):
        raise ValueError("Use a valid YouTube or SoundCloud link.")
    pairs = parse_qsl(parsed.query, keep_blank_values=True, max_num_fields=100)
    query: dict[str, str] = {}
    for key, item in pairs:
        if key in query and query[key] != item:
            raise ValueError("Ambiguous link parameters are not supported.")
        query[key] = item
    path = parsed.path.rstrip("/") or "/"
    if host in _YOUTUBE:
        video = None
        if host in {"youtu.be", "www.youtu.be"}:
            video = path.lstrip("/")
        elif path == "/watch":
            video = query.get("v")
        elif re.fullmatch(r"/(shorts|live|embed)/[^/]+", path):
            video = path.rsplit("/", 1)[1]
        kept = {}
        if video is not None:
            if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video):
                raise ValueError("Use a valid YouTube video ID.")
            path = "/watch"
            kept["v"] = video
        if query.get("list"):
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", query["list"]):
                raise ValueError("Use a valid YouTube playlist ID.")
            kept["list"] = query["list"]
        if path == "/playlist" and "list" not in kept:
            raise ValueError("A playlist link needs a playlist ID.")
        if path in {"/", "/watch"} and video is None:
            raise ValueError("Add a video, playlist or channel link.")
        return urlunsplit(("https", "www.youtube.com", path, urlencode(kept), ""))
    if path == "/":
        raise ValueError("Add a track, playlist or artist link.")
    host = "soundcloud.com" if host in {"www.soundcloud.com", "m.soundcloud.com"} else host
    kept = {key: query[key] for key in ("secret_token",) if query.get(key)}
    return urlunsplit(("https", host, path, urlencode(kept), ""))


@dataclass(frozen=True)
class InboxEntry:
    id: int
    url: str
    note: str
    status: str
    created_at: str
    updated_at: str
    job_ids: tuple[str, ...]


class InboxStore:
    def __init__(self, state_dir: Path | None = None):
        self.path = (state_dir or default_state_dir()) / "inbox.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS inbox (
                id INTEGER PRIMARY KEY, url TEXT NOT NULL UNIQUE, note TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('ready','handed_off','archived')),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                job_ids TEXT NOT NULL DEFAULT '[]')""")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _note(note):
        if not isinstance(note, str) or len(note) > MAX_NOTE or "\x00" in note:
            raise ValueError("Notes can contain up to 2000 characters.")
        return note.strip()

    @staticmethod
    def _ids(ids):
        values = list(islice(ids, MAX_BATCH + 1))
        if not 1 <= len(values) <= MAX_BATCH or any(type(i) is not int for i in values):
            raise ValueError("Select between 1 and 100 inbox entries.")
        return tuple(dict.fromkeys(values))

    def add_batch(self, urls: str | Iterable[str], note: str = "") -> tuple[int, int]:
        """Return (inserted, duplicates); any invalid input rolls back the batch."""
        note = self._note(note)
        if isinstance(urls, str) and len(urls) > MAX_BATCH * 4097:
            raise ValueError("Add between 1 and 100 links at a time.")
        values = urls.splitlines() if isinstance(urls, str) else list(islice(urls, MAX_BATCH + 1))
        if any(not isinstance(value, str) for value in values):
            raise ValueError("Use a valid YouTube or SoundCloud link.")
        values = [value.strip() for value in values if value.strip()]
        if not 1 <= len(values) <= MAX_BATCH:
            raise ValueError("Add between 1 and 100 links at a time.")
        canonical = list(dict.fromkeys(canonical_url(value) for value in values))
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = {row[0] for row in db.execute("SELECT url FROM inbox")}
            additions = [url for url in canonical if url not in existing]
            if len(existing) + len(additions) > MAX_ENTRIES:
                raise ValueError("The inbox can hold up to 10000 links.")
            db.executemany("INSERT INTO inbox(url,note,status) VALUES (?,?,'ready')",
                           [(url, note) for url in additions])
        return len(additions), len(values) - len(additions)

    def list_entries(self, *, status: str | None = None, search: str = "",
                     limit: int = 200) -> tuple[InboxEntry, ...]:
        if status is not None and status not in STATUSES:
            raise ValueError("Unknown inbox status.")
        if not isinstance(search, str) or len(search) > 200 or not 1 <= limit <= 1000:
            raise ValueError("Invalid inbox search or limit.")
        with self._connect() as db:
            rows = db.execute("""SELECT * FROM inbox WHERE (? IS NULL OR status=?)
                AND (instr(lower(url),lower(?))>0 OR instr(lower(note),lower(?))>0)
                ORDER BY id DESC LIMIT ?""", (status, status, search, search, limit))
            return tuple(InboxEntry(**{**dict(row), "job_ids": tuple(json.loads(row["job_ids"]))})
                         for row in rows)

    def update_note(self, entry_id: int, note: str) -> None:
        note = self._note(note)
        with self._connect() as db:
            result = db.execute("""UPDATE inbox SET note=?,
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?""", (note, entry_id))
            if result.rowcount != 1:
                raise ValueError("Inbox entry no longer exists.")

    def _transition(self, ids, target, *, ready_only=False):
        ids = self._ids(ids)
        marks = ",".join("?" for _ in ids)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = list(db.execute(f"SELECT * FROM inbox WHERE id IN ({marks})", ids))
            if len(rows) != len(ids) or (ready_only and any(r["status"] != "ready" for r in rows)):
                raise ValueError("Only ready entries can be handed to Downloads.")
            db.execute(f"""UPDATE inbox SET status=?,
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id IN ({marks})""",
                       (target, *ids))
            by_id = {row["id"]: row["url"] for row in rows}
            return tuple(by_id[i] for i in ids)

    def handoff(self, ids: Iterable[int]) -> tuple[str, ...]:
        return self._transition(ids, "handed_off", ready_only=True)

    def archive(self, ids: Iterable[int]) -> None:
        self._transition(ids, "archived")

    def restore(self, ids: Iterable[int]) -> None:
        """Explicit user action; old job references remain as history."""
        self._transition(ids, "ready")

    def attach_jobs(self, ids: Iterable[int], job_ids: Iterable[str]) -> None:
        ids = self._ids(ids)
        jobs = list(islice(job_ids, 101))
        if not 1 <= len(jobs) <= 100 or any(
            not isinstance(j, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", j)
            for j in jobs
        ):
            raise ValueError("Invalid job references.")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for entry_id in ids:
                row = db.execute("SELECT status,job_ids FROM inbox WHERE id=?",
                                 (entry_id,)).fetchone()
                if row is None or row["status"] != "handed_off":
                    raise ValueError("Job references need a handed-off inbox entry.")
                history = list(dict.fromkeys((*json.loads(row["job_ids"]), *jobs)))
                if len(history) > 100:
                    raise ValueError("Too many job references for this inbox entry.")
                db.execute("""UPDATE inbox SET job_ids=?,
                    updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?""",
                           (json.dumps(history), entry_id))
