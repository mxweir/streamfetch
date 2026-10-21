"""Thread-safe background download jobs for the Streamlit interface."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from streamfetch.downloader import Downloader
from streamfetch.models import DownloadRequest, DownloadResult, MediaType, ProgressEvent


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED = "paused"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class DownloadJobSnapshot:
    id: str
    url: str
    status: JobStatus
    progress: float
    message: str
    filename: str | None
    speed_bytes_per_second: float | None
    eta_seconds: float | None
    files: tuple[Path, ...]
    error: str | None
    created_at: float


@dataclass
class _DownloadJob:
    id: str
    request: DownloadRequest
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    message: str = "Queued"
    filename: str | None = None
    speed_bytes_per_second: float | None = None
    eta_seconds: float | None = None
    files: tuple[Path, ...] = ()
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    pause_requested: threading.Event = field(default_factory=threading.Event)
    future: Future[Any] | None = None
    cancel_requested: threading.Event = field(default_factory=threading.Event)
    cleanup_partial: bool = False
    attempt: int = 0


class DownloadJobManager:
    """Execute individual source downloads concurrently and expose snapshots."""

    def __init__(
        self,
        max_workers: int = 2,
        downloader_factory=Downloader,
        state_path: Path | None = None,
        retry_delays: tuple[float, ...] = (1.0, 3.0),
    ):
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="streamfetch",
        )
        self._downloader_factory = downloader_factory
        self._jobs: dict[str, _DownloadJob] = {}
        self._lock = threading.RLock()
        self._state_path = Path(state_path).expanduser().resolve() if state_path else None
        self._last_persisted_at = 0.0
        self._retry_delays = retry_delays
        self._closed = False
        self._load()

    def submit(self, request: DownloadRequest) -> tuple[str, ...]:
        job_ids = []
        for url in request.urls:
            job = _DownloadJob(uuid.uuid4().hex[:12], replace(request, urls=(url,)))
            with self._lock:
                self._jobs[job.id] = job
                self._persist_locked()
                job.future = self._executor.submit(self._run, job.id)
            job_ids.append(job.id)
        return tuple(job_ids)

    def pause(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if job.status not in {JobStatus.QUEUED, JobStatus.RUNNING}:
                return
            job.pause_requested.set()
            if job.future and job.future.cancel():
                job.status = JobStatus.PAUSED
                job.message = "Paused before starting"
            else:
                job.status = JobStatus.PAUSING
                job.message = "Pausing after the current fragment…"
            self._persist_locked()

    def resume(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if job.status not in {JobStatus.PAUSED, JobStatus.FAILED}:
                return
            if job.status is JobStatus.FAILED:
                job.attempt = 0
            job.pause_requested.clear()
            job.status = JobStatus.QUEUED
            job.message = "Queued to resume"
            job.error = None
            job.future = self._executor.submit(self._run, job.id)
            self._persist_locked()

    def retry(self, job_id: str) -> None:
        self.resume(job_id)

    def cancel(self, job_id: str, *, cleanup_partial: bool = False) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if job.status not in {
                JobStatus.QUEUED,
                JobStatus.RUNNING,
                JobStatus.PAUSING,
                JobStatus.PAUSED,
                JobStatus.FAILED,
            }:
                return
            job.cancel_requested.set()
            job.cleanup_partial = cleanup_partial
            if (job.future and job.future.cancel()) or job.status in {
                JobStatus.PAUSED,
                JobStatus.FAILED,
            }:
                self._cancelled(job)
            else:
                job.status = JobStatus.CANCELLING
                job.message = "Cancelling safely…"
            self._persist_locked()

    def snapshots(self) -> tuple[DownloadJobSnapshot, ...]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)
            return tuple(self._snapshot(job) for job in jobs)

    def remove_finished(self) -> None:
        with self._lock:
            removable = [
                job_id
                for job_id, job in self._jobs.items()
                if job.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}
            ]
            for job_id in removable:
                del self._jobs[job_id]
            self._persist_locked()

    def wait(self, job_id: str, timeout: float = 10) -> DownloadJobSnapshot:
        with self._lock:
            future = self._jobs[job_id].future
        if future:
            future.result(timeout=timeout)
        with self._lock:
            return self._snapshot(self._jobs[job_id])

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
            self._persist_locked()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _run(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if job.pause_requested.is_set():
                job.status = JobStatus.PAUSED
                return
            if job.cancel_requested.is_set():
                self._cancelled(job)
                return
            job.status = JobStatus.RUNNING
            job.message = "Preparing download…"
            job.attempt += 1
            self._persist_locked()

        def on_progress(event: ProgressEvent) -> None:
            with self._lock:
                active_job = self._jobs[job_id]
                if active_job.cancel_requested.is_set():
                    raise _CancelRequested
                if active_job.pause_requested.is_set():
                    raise _PauseRequested
                active_job.progress = event.progress or active_job.progress
                active_job.message = event.message
                active_job.filename = event.filename
                active_job.speed_bytes_per_second = event.speed_bytes_per_second
                active_job.eta_seconds = event.eta_seconds
                self._persist_locked(throttle=True)

        try:
            result = self._downloader_factory().download(job.request, on_progress)
        except Exception as exc:
            with self._lock:
                if job.cancel_requested.is_set() or isinstance(exc, _CancelRequested):
                    self._cancelled(job)
                elif job.pause_requested.is_set() or isinstance(exc, _PauseRequested):
                    job.status = JobStatus.PAUSED
                    job.message = "Paused — resume to continue the partial download"
                    job.error = None
                elif job.attempt <= len(self._retry_delays):
                    delay = self._retry_delays[job.attempt - 1]
                    job.status = JobStatus.QUEUED
                    job.message = f"Retrying automatically in {delay:g}s"
                    job.error = str(exc)
                    self._persist_locked()
                    timer = threading.Timer(delay, self._retry, args=(job.id,))
                    timer.daemon = True
                    timer.start()
                    return
                else:
                    job.status = JobStatus.FAILED
                    job.message = "Download failed"
                    job.error = str(exc)
                self._persist_locked()
            return

        self._complete(job, result)

    def _complete(self, job: _DownloadJob, result: DownloadResult) -> None:
        with self._lock:
            job.status = JobStatus.COMPLETED
            job.progress = 1.0
            job.message = "Complete"
            job.files = result.files
            job.error = None
            self._persist_locked()

    def _retry(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if (
                self._closed
                or job is None
                or job.status is not JobStatus.QUEUED
                or job.cancel_requested.is_set()
            ):
                return
            job.future = self._executor.submit(self._run, job_id)

    def _cancelled(self, job: _DownloadJob) -> None:
        job.status = JobStatus.CANCELLED
        job.message = "Cancelled"
        job.error = None
        if job.cleanup_partial:
            removed = cleanup_partial_files(
                job.request.output_dir,
                filename=job.filename,
                since=job.created_at,
            )
            job.message = f"Cancelled · removed {removed} partial file(s)"
        self._persist_locked()

    def _load(self) -> None:
        if self._state_path is None or not self._state_path.exists():
            return
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for record in payload.get("jobs", []):
            try:
                job = _job_from_record(record)
            except (KeyError, TypeError, ValueError):
                continue
            if job.status in {
                JobStatus.QUEUED,
                JobStatus.RUNNING,
                JobStatus.PAUSING,
                JobStatus.CANCELLING,
            }:
                job.status = JobStatus.PAUSED
                job.message = "Recovered after restart — resume to continue"
                job.error = None
            self._jobs[job.id] = job

    def _persist_locked(self, *, throttle: bool = False) -> None:
        if self._state_path is None:
            return
        now = time.monotonic()
        if throttle and now - self._last_persisted_at < 0.75:
            return
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "jobs": [_job_record(job) for job in self._jobs.values()],
        }
        temporary = self._state_path.with_suffix(f"{self._state_path.suffix}.tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self._state_path)
        self._last_persisted_at = now

    @staticmethod
    def _snapshot(job: _DownloadJob) -> DownloadJobSnapshot:
        return DownloadJobSnapshot(
            id=job.id,
            url=job.request.urls[0],
            status=job.status,
            progress=job.progress,
            message=job.message,
            filename=job.filename,
            speed_bytes_per_second=job.speed_bytes_per_second,
            eta_seconds=job.eta_seconds,
            files=job.files,
            error=job.error,
            created_at=job.created_at,
        )


class _PauseRequested(RuntimeError):
    pass


class _CancelRequested(RuntimeError):
    pass


def default_job_state_path() -> Path:
    """Return the local state file used by the Streamlit and desktop apps."""

    configured = os.environ.get("STREAMFETCH_STATE_DIR")
    state_dir = Path(configured).expanduser() if configured else Path.home() / ".streamfetch"
    return state_dir / "download-jobs.json"


def _job_record(job: _DownloadJob) -> dict[str, Any]:
    request = job.request
    return {
        "id": job.id,
        "request": {
            "urls": list(request.urls),
            "output_dir": str(request.output_dir),
            "media_type": request.media_type.value,
            "container": request.container,
            "quality": request.quality,
            "allow_playlists": request.allow_playlists,
            "max_items": request.max_items,
            "embed_metadata": request.embed_metadata,
            "embed_thumbnail": request.embed_thumbnail,
            "embed_subtitles": request.embed_subtitles,
            "subtitle_languages": list(request.subtitle_languages),
            "cookie_browser": request.cookie_browser,
            "concurrent_fragments": request.concurrent_fragments,
            "rate_limit": request.rate_limit,
            "download_sections": list(request.download_sections),
            "split_chapters": request.split_chapters,
            "sponsorblock_remove": list(request.sponsorblock_remove),
            "conflict_policy": request.conflict_policy,
        },
        "status": job.status.value,
        "progress": job.progress,
        "message": job.message,
        "filename": job.filename,
        "speed_bytes_per_second": job.speed_bytes_per_second,
        "eta_seconds": job.eta_seconds,
        "files": [str(path) for path in job.files],
        "error": job.error,
        "created_at": job.created_at,
        "attempt": job.attempt,
    }


def _job_from_record(record: dict[str, Any]) -> _DownloadJob:
    request_data = record["request"]
    request = DownloadRequest(
        urls=tuple(request_data["urls"]),
        output_dir=Path(request_data["output_dir"]),
        media_type=MediaType(request_data["media_type"]),
        container=request_data["container"],
        quality=request_data["quality"],
        allow_playlists=bool(request_data.get("allow_playlists", True)),
        max_items=request_data.get("max_items"),
        embed_metadata=bool(request_data.get("embed_metadata", True)),
        embed_thumbnail=bool(request_data.get("embed_thumbnail", True)),
        embed_subtitles=bool(request_data.get("embed_subtitles", False)),
        subtitle_languages=tuple(request_data.get("subtitle_languages", ("en",))),
        cookie_browser=request_data.get("cookie_browser"),
        concurrent_fragments=int(request_data.get("concurrent_fragments", 4)),
        rate_limit=request_data.get("rate_limit"),
        download_sections=tuple(request_data.get("download_sections", ())),
        split_chapters=bool(request_data.get("split_chapters", False)),
        sponsorblock_remove=tuple(request_data.get("sponsorblock_remove", ())),
        conflict_policy=str(request_data.get("conflict_policy", "resume")),
    )
    return _DownloadJob(
        id=str(record["id"]),
        request=request,
        status=JobStatus(record.get("status", JobStatus.PAUSED.value)),
        progress=float(record.get("progress", 0.0)),
        message=str(record.get("message", "Recovered")),
        filename=record.get("filename"),
        speed_bytes_per_second=record.get("speed_bytes_per_second"),
        eta_seconds=record.get("eta_seconds"),
        files=tuple(Path(value) for value in record.get("files", ())),
        error=record.get("error"),
        created_at=float(record.get("created_at", time.time())),
        attempt=int(record.get("attempt", 0)),
    )


def cleanup_partial_files(
    output_dir: Path,
    *,
    filename: str | None,
    since: float = 0,
) -> int:
    """Remove only yt-dlp temporary files created for the selected job."""

    root = Path(output_dir).expanduser()
    if not root.exists() or not filename:
        return 0
    reported = Path(filename).expanduser()
    candidates = {reported}
    if not reported.name.endswith((".part", ".ytdl", ".temp")):
        candidates.update(
            reported.with_name(f"{reported.name}{suffix}")
            for suffix in (".part", ".ytdl", ".temp")
        )
    removed = 0
    resolved_root = root.resolve()
    for path in candidates:
        resolved = path.resolve()
        if resolved_root not in resolved.parents or not resolved.name.endswith(
            (".part", ".ytdl", ".temp")
        ):
            continue
        if not resolved.is_file() or resolved.stat().st_mtime < since - 1:
            continue
        try:
            resolved.unlink()
        except OSError:
            continue
        removed += 1
    return removed
