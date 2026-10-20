"""Thread-safe background download jobs for the Streamlit interface."""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from streamfetch.downloader import Downloader
from streamfetch.models import DownloadRequest, DownloadResult, ProgressEvent


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED = "paused"
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


class DownloadJobManager:
    """Execute individual source downloads concurrently and expose snapshots."""

    def __init__(self, max_workers: int = 2, downloader_factory=Downloader):
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="streamfetch",
        )
        self._downloader_factory = downloader_factory
        self._jobs: dict[str, _DownloadJob] = {}
        self._lock = threading.RLock()

    def submit(self, request: DownloadRequest) -> tuple[str, ...]:
        job_ids = []
        for url in request.urls:
            job = _DownloadJob(uuid.uuid4().hex[:12], replace(request, urls=(url,)))
            with self._lock:
                self._jobs[job.id] = job
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

    def resume(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if job.status not in {JobStatus.PAUSED, JobStatus.FAILED}:
                return
            job.pause_requested.clear()
            job.status = JobStatus.QUEUED
            job.message = "Queued to resume"
            job.error = None
            job.future = self._executor.submit(self._run, job.id)

    def retry(self, job_id: str) -> None:
        self.resume(job_id)

    def snapshots(self) -> tuple[DownloadJobSnapshot, ...]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)
            return tuple(self._snapshot(job) for job in jobs)

    def remove_finished(self) -> None:
        with self._lock:
            removable = [
                job_id
                for job_id, job in self._jobs.items()
                if job.status in {JobStatus.COMPLETED, JobStatus.FAILED}
            ]
            for job_id in removable:
                del self._jobs[job_id]

    def wait(self, job_id: str, timeout: float = 10) -> DownloadJobSnapshot:
        with self._lock:
            future = self._jobs[job_id].future
        if future:
            future.result(timeout=timeout)
        with self._lock:
            return self._snapshot(self._jobs[job_id])

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _run(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if job.pause_requested.is_set():
                job.status = JobStatus.PAUSED
                return
            job.status = JobStatus.RUNNING
            job.message = "Preparing download…"

        def on_progress(event: ProgressEvent) -> None:
            with self._lock:
                active_job = self._jobs[job_id]
                if active_job.pause_requested.is_set():
                    raise _PauseRequested
                active_job.progress = event.progress or active_job.progress
                active_job.message = event.message
                active_job.filename = event.filename
                active_job.speed_bytes_per_second = event.speed_bytes_per_second
                active_job.eta_seconds = event.eta_seconds

        try:
            result = self._downloader_factory().download(job.request, on_progress)
        except Exception as exc:
            with self._lock:
                if job.pause_requested.is_set() or isinstance(exc, _PauseRequested):
                    job.status = JobStatus.PAUSED
                    job.message = "Paused — resume to continue the partial download"
                    job.error = None
                else:
                    job.status = JobStatus.FAILED
                    job.message = "Download failed"
                    job.error = str(exc)
            return

        self._complete(job, result)

    def _complete(self, job: _DownloadJob, result: DownloadResult) -> None:
        with self._lock:
            job.status = JobStatus.COMPLETED
            job.progress = 1.0
            job.message = "Complete"
            job.files = result.files
            job.error = None

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
