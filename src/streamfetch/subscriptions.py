"""Persistent source subscriptions, discovery, and download reconciliation."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, suppress
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from streamfetch.config import detect_source
from streamfetch.downloader import Downloader
from streamfetch.jobs import DownloadJobManager, JobStatus
from streamfetch.library import MediaLibrary
from streamfetch.models import DownloadRequest, MediaType, PreviewEntry

PROFILES = {
    "Music MP3": (MediaType.AUDIO, "mp3", "192K"),
    "Lossless audio": (MediaType.AUDIO, "flac", "0"),
    "Video 1080p": (MediaType.VIDEO, "mp4", "1080p"),
    "Archive quality": (MediaType.VIDEO, "mkv", "best"),
}


def media_key(url: str) -> str:
    """Ignore YouTube playlist/tracking parameters when matching an item."""
    parsed = urlparse(url)
    if detect_source(url) == "youtube":
        identifier = parse_qs(parsed.query).get("v", [None])[0]
        if parsed.hostname in {"youtu.be", "www.youtu.be"}:
            identifier = parsed.path.strip("/")
        elif parsed.path.startswith(("/shorts/", "/live/", "/embed/")):
            identifier = parsed.path.split("/")[2]
        if identifier:
            return f"youtube:{identifier}"
    return f"{detect_source(url)}:{parsed.hostname}{parsed.path.rstrip('/')}"


class SubscriptionStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sources (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
                    profile TEXT NOT NULL, root TEXT NOT NULL, batch_limit INTEGER NOT NULL,
                    scan_limit INTEGER NOT NULL, check_on_start INTEGER NOT NULL,
                    interval_minutes INTEGER NOT NULL, make_playlist INTEGER NOT NULL,
                    playlist_name TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1, checked_at REAL,
                    error TEXT, created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS source_items (
                    source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                    key TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL,
                    identifier TEXT, position INTEGER NOT NULL, status TEXT NOT NULL,
                    job_id TEXT, files TEXT NOT NULL DEFAULT '[]', error TEXT,
                    PRIMARY KEY (source_id, key)
                );
                CREATE TABLE IF NOT EXISTS sync_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, source_id TEXT NOT NULL
                        REFERENCES sources(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL, created_at REAL NOT NULL, detail TEXT NOT NULL
                );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def sources(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM sources ORDER BY created_at")]

    def source(self, source_id: str):
        with self.connect() as db:
            row = db.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        if row is None:
            raise ValueError("Subscription no longer exists.")
        return dict(row)

    def save(
        self,
        *,
        name,
        url,
        profile,
        root,
        batch_limit=20,
        scan_limit=200,
        check_on_start=False,
        interval_minutes=0,
        make_playlist=True,
        source_id=None,
    ):
        platform = detect_source(url)
        if not name.strip() or len(name.strip()) > 60:
            raise ValueError("Use a source name between 1 and 60 characters.")
        if profile not in PROFILES:
            raise ValueError("Choose a supported download preset.")
        if platform == "soundcloud" and PROFILES[profile][0] == MediaType.VIDEO:
            raise ValueError("Choose an audio preset for SoundCloud.")
        if not 1 <= batch_limit <= 100 or not 1 <= scan_limit <= 500:
            raise ValueError("Batch limit must be 1–100; inspection limit must be 1–500.")
        if interval_minutes not in {0, 15, 30, 60, 360, 1440}:
            raise ValueError("Choose a supported check interval.")
        root = str(Path(root).expanduser().resolve())
        source_id = source_id or uuid.uuid4().hex[:12]
        with self.connect() as db:
            previous = db.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
            if previous and (previous["url"] != url or previous["root"] != root):
                raise ValueError("Create a new subscription to change the URL or media folder.")
            db.execute(
                """
                INSERT INTO sources (id,name,url,profile,root,batch_limit,scan_limit,
                    check_on_start,interval_minutes,make_playlist,playlist_name,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name, profile=excluded.profile,
                    batch_limit=excluded.batch_limit, scan_limit=excluded.scan_limit,
                    check_on_start=excluded.check_on_start,
                    interval_minutes=excluded.interval_minutes,make_playlist=excluded.make_playlist
                """,
                (
                    source_id,
                    name.strip(),
                    url.strip(),
                    profile,
                    root,
                    batch_limit,
                    scan_limit,
                    check_on_start,
                    interval_minutes,
                    make_playlist,
                    f"{name.strip()} · {source_id}",
                    time.time(),
                ),
            )
        return source_id

    def items(self, source_id):
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM source_items WHERE source_id=? ORDER BY position, key",
                    (source_id,),
                )
            ]

    def history(self, source_id):
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM sync_history WHERE source_id=? ORDER BY id DESC LIMIT 50",
                    (source_id,),
                )
            ]

    def log(self, source_id, kind, detail):
        with self.connect() as db:
            db.execute(
                "INSERT INTO sync_history(source_id,kind,created_at,detail) VALUES (?,?,?,?)",
                (source_id, kind, time.time(), detail),
            )
            db.execute(
                """DELETE FROM sync_history WHERE source_id=? AND id NOT IN
                (SELECT id FROM sync_history WHERE source_id=? ORDER BY id DESC LIMIT 100)""",
                (source_id, source_id),
            )

    def toggle(self, source_id, enabled):
        with self.connect() as db:
            db.execute("UPDATE sources SET enabled=? WHERE id=?", (enabled, source_id))

    def delete(self, source_id):
        with self.connect() as db:
            active = db.execute(
                "SELECT 1 FROM source_items WHERE source_id=? AND status='queued'", (source_id,)
            ).fetchone()
            if active:
                raise ValueError("Finish or cancel the queued downloads before removing a source.")
            db.execute("DELETE FROM sources WHERE id=?", (source_id,))


class SubscriptionService:
    """One process-wide worker; checks discover items but never auto-download."""

    def __init__(
        self,
        store: SubscriptionStore,
        jobs: DownloadJobManager,
        downloader_factory=Downloader,
        *,
        start=True,
    ):
        self.store, self.jobs = store, jobs
        self.downloader_factory = downloader_factory
        self._lock = threading.RLock()
        self._busy: set[str] = set()
        self._startup_checked: set[str] = set()
        self._stop = threading.Event()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="streamfetch-sync")
        if start:
            threading.Thread(target=self._loop, daemon=True, name="streamfetch-sources").start()

    def busy(self, source_id):
        with self._lock:
            return source_id in self._busy

    def request_check(self, source_id):
        with self._lock:
            if source_id in self._busy or self._stop.is_set():
                return False
            self._busy.add(source_id)
            self._executor.submit(self._check_guarded, source_id)
        return True

    def _check_guarded(self, source_id):
        try:
            self.check(source_id)
        except Exception as exc:
            with self.store.connect() as db:
                db.execute(
                    "UPDATE sources SET checked_at=?,error=? WHERE id=?",
                    (time.time(), str(exc), source_id),
                )
            self.store.log(source_id, "error", str(exc))
        finally:
            with self._lock:
                self._busy.discard(source_id)

    def check(self, source_id):
        source = self.store.source(source_id)
        preview = self.downloader_factory().inspect(source["url"], limit=source["scan_limit"])
        entries = preview.entries
        if not entries and preview.source_type not in {"playlist", "multi_video"}:
            entries = (PreviewEntry(preview.title, webpage_url=source["url"]),)
        library = MediaLibrary(Path(source["root"]))
        library.scan()
        existing = {}
        for item in library.list_items(limit=100000):
            if item.source_url:
                with suppress(ValueError):
                    existing[media_key(item.source_url)] = item.path
        # Items already synchronized through another source in this library are shared.
        with self.store.connect() as db:
            for row in db.execute(
                """SELECT source_items.key, source_items.files FROM source_items
                JOIN sources ON sources.id=source_items.source_id
                WHERE sources.root=? AND source_items.status='downloaded'""",
                (source["root"],),
            ):
                files = [Path(value) for value in json.loads(row["files"]) if Path(value).is_file()]
                if files:
                    existing[row["key"]] = files[0]
        new = 0
        seen = set()
        with self.store.connect() as db:
            # Older locally held items stay after the latest inspected source window.
            db.execute(
                "UPDATE source_items SET position=position+1000 WHERE source_id=?", (source_id,)
            )
            for position, entry in enumerate(entries):
                if not entry.webpage_url:
                    continue
                try:
                    key = media_key(entry.webpage_url)
                except ValueError:
                    continue
                if key in seen:
                    continue
                seen.add(key)
                previous = db.execute(
                    "SELECT * FROM source_items WHERE source_id=? AND key=?", (source_id, key)
                ).fetchone()
                local = existing.get(key)
                status = previous["status"] if previous else "new"
                files = previous["files"] if previous else "[]"
                if local and status != "queued":
                    status, files = "downloaded", json.dumps([str(local)])
                if not previous and not local:
                    new += 1
                db.execute(
                    """INSERT INTO source_items
                    (source_id,key,title,url,identifier,position,status,files)
                    VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(source_id,key) DO UPDATE SET title=excluded.title,url=excluded.url,
                        identifier=excluded.identifier,position=excluded.position,
                        status=excluded.status,files=excluded.files""",
                    (
                        source_id,
                        key,
                        entry.title,
                        entry.webpage_url,
                        entry.identifier,
                        position,
                        status,
                        files,
                    ),
                )
            db.execute(
                "UPDATE sources SET checked_at=?,error=NULL WHERE id=?", (time.time(), source_id)
            )
        self.store.log(source_id, "checked", f"{len(seen)} inspected · {new} new")
        self._playlist(source_id)

    def queue(self, source_id, keys):
        if self.busy(source_id):
            raise ValueError("Wait until the source check has finished.")
        with self._lock:
            source = self.store.source(source_id)
            selected = [
                item
                for item in self.store.items(source_id)
                if item["key"] in keys and item["status"] in {"new", "failed", "cancelled"}
            ]
            selected = selected[: source["batch_limit"]]
            media_type, container, quality = PROFILES[source["profile"]]
            for item in selected:
                # Stable per-item output isolates concurrent downloads and their result files.
                digest = hashlib.sha256(item["key"].encode()).hexdigest()[:16]
                output = Path(source["root"]) / "Subscriptions" / source_id / digest
                request = DownloadRequest(
                    (item["url"],),
                    output,
                    media_type,
                    container,
                    quality,
                    allow_playlists=False,
                    max_items=1,
                )
                job_id = self.jobs.submit(request)[0]
                with self.store.connect() as db:
                    db.execute(
                        "UPDATE source_items SET status='queued',job_id=?,error=NULL "
                        "WHERE source_id=? AND key=?",
                        (job_id, source_id, item["key"]),
                    )
            if selected:
                self.store.log(source_id, "queued", f"{len(selected)} download(s) queued")
            return len(selected)

    def reconcile(self):
        snapshots = {job.id: job for job in self.jobs.snapshots()}
        changed = set()
        with self.store.connect() as db:
            for row in db.execute("SELECT * FROM source_items WHERE status='queued'").fetchall():
                job = snapshots.get(row["job_id"])
                if job is None:
                    status, files, error = "failed", [], "Download job is no longer available."
                elif job.status == JobStatus.COMPLETED:
                    files = [str(path) for path in job.files if path.is_file()]
                    # An archive skip can return no new files after a restart.
                    if not files:
                        source = self.store.source(row["source_id"])
                        digest = hashlib.sha256(row["key"].encode()).hexdigest()[:16]
                        root = Path(source["root"]) / "Subscriptions" / row["source_id"] / digest
                        files = [
                            str(path)
                            for path in root.rglob("*")
                            if path.is_file()
                            and path.suffix.lower()
                            in {".mp3", ".flac", ".m4a", ".opus", ".wav", ".mp4", ".mkv", ".webm"}
                        ]
                    status = "downloaded" if files else "failed"
                    error = None if files else "No completed media file was found."
                elif job.status in {JobStatus.FAILED, JobStatus.CANCELLED}:
                    status, files, error = job.status.value, [], job.error
                else:
                    continue
                db.execute(
                    "UPDATE source_items SET status=?,files=?,error=? WHERE source_id=? AND key=?",
                    (status, json.dumps(files), error, row["source_id"], row["key"]),
                )
                changed.add(row["source_id"])
        for source_id in changed:
            items = self.store.items(source_id)
            ready = sum(item["status"] == "downloaded" for item in items)
            failed = sum(item["status"] == "failed" for item in items)
            self.store.log(source_id, "result", f"{ready} downloaded · {failed} failed")
            self._playlist(source_id)

    def _playlist(self, source_id):
        source = self.store.source(source_id)
        if not source["make_playlist"]:
            return
        paths = [
            Path(path)
            for item in self.store.items(source_id)
            if item["status"] == "downloaded"
            for path in json.loads(item["files"])
            if Path(path).is_file()
        ]
        if not paths:
            return
        library = MediaLibrary(Path(source["root"]))
        library.scan()
        library.sync_source_playlist(source["playlist_name"], paths)

    def tick(self, now=None):
        now = time.time() if now is None else now
        self.reconcile()
        for source in self.store.sources():
            if not source["enabled"]:
                continue
            startup = source["check_on_start"] and source["id"] not in self._startup_checked
            due = source["interval_minutes"] and (
                not source["checked_at"]
                or now - source["checked_at"] >= source["interval_minutes"] * 60
            )
            if (startup or due) and self.request_check(source["id"]):
                self._startup_checked.add(source["id"])

    def _loop(self):
        while not self._stop.wait(5):
            try:
                self.tick()
            except Exception:
                # Keep the scheduler alive; individual extraction errors are recorded per source.
                continue

    def shutdown(self):
        self._stop.set()
        self._executor.shutdown(wait=False, cancel_futures=True)
