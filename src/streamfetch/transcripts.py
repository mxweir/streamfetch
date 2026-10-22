"""Local speech jobs and timestamped subtitle search. No cloud transcription API."""

from __future__ import annotations

import html
import importlib.util
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from streamfetch.library import MediaLibrary

STAMP = r"(?:(\d{1,3}):)?(\d{2}):(\d{2})[,.](\d{3})"
CUE = re.compile(rf"^\s*{STAMP}\s*-->\s*{STAMP}[^\n]*\n(.*?)(?=\n\s*\n|\Z)", re.M | re.S)


def parse_subtitles(text: str) -> list[dict]:
    if len(text.encode("utf-8")) > 2_000_000:
        raise ValueError("Subtitle files must be smaller than 2 MB.")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    segments = []
    for match in CUE.finditer(text):
        parts = match.groups()
        start, end = [
            sum(
                float(value or 0) * factor
                for value, factor in zip(
                    parts[offset : offset + 4], (3600, 60, 1, 0.001), strict=True
                )
            )
            for offset in (0, 4)
        ]
        content = html.unescape(re.sub(r"<[^>]*>", "", parts[8])).strip()
        if end <= start or not content:
            continue
        segments.append(dict(start=start, end=end, text=content))
        if len(segments) > 50000:
            raise ValueError("Subtitle files may contain at most 50,000 cues.")
    if not segments:
        raise ValueError("No valid SRT or WebVTT subtitle cues were found.")
    return segments


def signature(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_size}:{stat.st_mtime_ns}"


class TranscriptStore:
    def __init__(self, library: MediaLibrary):
        self.library = library
        with library._connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS transcripts (
                    path TEXT PRIMARY KEY REFERENCES media_items(path) ON DELETE CASCADE,
                    signature TEXT NOT NULL, status TEXT NOT NULL, model TEXT NOT NULL,
                    language TEXT, error TEXT, updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS transcript_segments (
                    id INTEGER PRIMARY KEY,
                    path TEXT NOT NULL REFERENCES transcripts(path) ON DELETE CASCADE,
                    start REAL NOT NULL, end REAL NOT NULL, text TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS transcript_path ON transcript_segments(path,start);
            """)

    def status(self, path):
        with self.library._connection() as db:
            row = db.execute(
                "SELECT * FROM transcripts WHERE path=?", (self.library.relative_path(path),)
            ).fetchone()
        result = dict(row) if row else None
        if result:
            try:
                if result["signature"] != signature(path):
                    result["status"] = "outdated"
            except OSError:
                result["status"] = "missing"
        return result

    def set_status(self, path, status, model, *, error=None, language=None):
        with self.library._connection() as db:
            relative = self.library.relative_path(path)
            try:
                current_signature = signature(path)
            except OSError:
                existing = db.execute(
                    "SELECT signature FROM transcripts WHERE path=?", (relative,)
                ).fetchone()
                if existing is None:
                    raise
                current_signature = existing[0]
            db.execute(
                """INSERT INTO transcripts VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(path) DO UPDATE SET signature=excluded.signature,
                status=excluded.status,model=excluded.model,language=excluded.language,
                error=excluded.error,updated_at=excluded.updated_at""",
                (
                    relative,
                    current_signature,
                    status,
                    model,
                    language,
                    error,
                    time.time(),
                ),
            )

    def save(
        self, path, segments, *, model="Imported subtitles", language=None, expected_signature=None
    ):
        current_signature = signature(path)
        if expected_signature and current_signature != expected_signature:
            raise ValueError("The media file changed during transcription. Please retry.")
        clean = []
        for segment in segments:
            start, end = float(segment["start"]), float(segment["end"])
            text = str(segment["text"]).strip()
            if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end):
                raise ValueError("Invalid transcript timestamp.")
            if text:
                clean.append((start, end, text))
        if len(clean) > 50000:
            raise ValueError("Transcripts may contain at most 50,000 segments.")
        relative = self.library.relative_path(path)
        with self.library._connection() as db:
            db.execute(
                """INSERT INTO transcripts VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(path) DO UPDATE SET signature=excluded.signature,status='ready',
                model=excluded.model,language=excluded.language,error=NULL,
                updated_at=excluded.updated_at""",
                (relative, current_signature, "ready", model, language, None, time.time()),
            )
            db.execute("DELETE FROM transcript_segments WHERE path=?", (relative,))
            db.executemany(
                "INSERT INTO transcript_segments(path,start,end,text) VALUES (?,?,?,?)",
                [(relative, *segment) for segment in clean],
            )

    def segments(self, path):
        with self.library._connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT start,end,text FROM transcript_segments WHERE path=? ORDER BY start",
                    (self.library.relative_path(path),),
                )
            ]

    def search(self, query, limit=50):
        if not query.strip():
            return []
        # Escape LIKE wildcards: the search text is always literal, never SQL syntax.
        escaped = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with self.library._connection() as db:
            rows = db.execute(
                """SELECT s.*, t.signature FROM transcript_segments s
                JOIN transcripts t ON t.path=s.path
                WHERE t.status='ready' AND s.text LIKE ? ESCAPE '\\'
                ORDER BY s.path,s.start LIMIT ?""",
                (f"%{escaped}%", min(limit, 200)),
            ).fetchall()
        results = []
        for row in rows:
            path = self.library.root / row["path"]
            try:
                if signature(path) == row["signature"]:
                    results.append(dict(row))
            except OSError:
                continue
        return results

    def recover_interrupted(self):
        with self.library._connection() as db:
            db.execute("""UPDATE transcripts SET status='interrupted',
                error='App stopped before completion. Retry this job.'
                WHERE status IN ('queued','running')""")


class TranscriptionService:
    def __init__(self, state_dir):
        self.model_dir = Path(state_dir) / "models"
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="streamfetch-speech")
        self._lock = threading.RLock()
        self._registered = set()
        self._jobs = {}

    @staticmethod
    def available():
        return importlib.util.find_spec("faster_whisper") is not None

    def register(self, store):
        with self._lock:
            key = str(store.library.root)
            if key not in self._registered:
                store.recover_interrupted()
                self._registered.add(key)

    def submit(self, store, path, *, model="tiny", allow_download=False):
        if model not in {"tiny", "base", "small"}:
            raise ValueError("Choose tiny, base or small.")
        if not self.available():
            raise ValueError('Install the optional speech engine: pip install ".[transcription]"')
        self.register(store)
        key = (str(store.library.root), str(path))
        with self._lock:
            if key in self._jobs:
                raise ValueError("This item already has a transcription job.")
            stop = threading.Event()
            self._jobs[key] = stop
            try:
                store.set_status(path, "queued", model)
                self._executor.submit(self._run, key, stop, store, path, model, allow_download)
            except Exception:
                self._jobs.pop(key, None)
                raise

    def cancel(self, store, path):
        with self._lock:
            stop = self._jobs.get((str(store.library.root), str(path)))
            if stop:
                stop.set()

    def _run(self, key, stop, store, path, model, allow_download):
        try:
            if stop.is_set():
                raise InterruptedError("Transcription cancelled.")
            from faster_whisper import WhisperModel

            expected = signature(path)
            store.set_status(path, "running", model)
            engine = WhisperModel(
                model,
                device="cpu",
                compute_type="int8",
                download_root=str(self.model_dir),
                local_files_only=not allow_download,
            )
            segments, info = engine.transcribe(str(path), beam_size=1)
            result = []
            for segment in segments:
                if stop.is_set():
                    raise InterruptedError("Transcription cancelled.")
                result.append(dict(start=segment.start, end=segment.end, text=segment.text))
                if len(result) > 50000:
                    raise ValueError("Transcripts may contain at most 50,000 segments.")
            if stop.is_set():
                raise InterruptedError("Transcription cancelled.")
            store.save(
                path, result, model=model, language=info.language, expected_signature=expected
            )
        except Exception as exc:
            store.set_status(
                path, "cancelled" if stop.is_set() else "failed", model, error=str(exc)[:1500]
            )
        finally:
            with self._lock:
                self._jobs.pop(key, None)


def export_transcript(segments, *, srt=False):
    def timestamp(seconds):
        ms = round(seconds * 1000)
        hours, ms = divmod(ms, 3600000)
        minutes, ms = divmod(ms, 60000)
        seconds, ms = divmod(ms, 1000)
        return f"{hours:02}:{minutes:02}:{seconds:02},{ms:03}"

    if not srt:
        return "\n".join(row["text"] for row in segments)
    return (
        "\n\n".join(
            f"{i}\n{timestamp(row['start'])} --> {timestamp(row['end'])}\n{row['text']}"
            for i, row in enumerate(segments, 1)
        )
        + "\n"
    )
