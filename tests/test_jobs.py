import json
import threading
from dataclasses import replace
from pathlib import Path

from streamfetch.jobs import DownloadJobManager, JobStatus
from streamfetch.models import DownloadRequest, DownloadResult, MediaType, ProgressEvent


def request(tmp_path: Path) -> DownloadRequest:
    return DownloadRequest(
        urls=("https://youtu.be/one", "https://youtu.be/two"),
        output_dir=tmp_path,
        media_type=MediaType.AUDIO,
        container="mp3",
        quality="192K",
    )


class SuccessfulDownloader:
    def download(self, download_request, callback):
        callback(ProgressEvent("downloading", "Downloading", 0.5, "track.mp3", 1024, 2))
        output = download_request.output_dir / "track.mp3"
        output.write_bytes(b"audio")
        return DownloadResult(download_request.output_dir, (output,), 1.0, 2.0)


def test_manager_splits_sources_into_parallel_jobs(tmp_path):
    manager = DownloadJobManager(max_workers=2, downloader_factory=SuccessfulDownloader)
    job_ids = manager.submit(request(tmp_path))

    snapshots = [manager.wait(job_id) for job_id in job_ids]

    assert len(job_ids) == 2
    assert all(snapshot.status is JobStatus.COMPLETED for snapshot in snapshots)
    assert all(snapshot.progress == 1.0 for snapshot in snapshots)
    manager.remove_finished()
    assert manager.snapshots() == ()
    manager.shutdown()


class PausableDownloader:
    started = threading.Event()
    continue_download = threading.Event()
    calls = 0

    def download(self, download_request, callback):
        type(self).calls += 1
        callback(ProgressEvent("downloading", "Downloading", 0.2))
        if type(self).calls == 1:
            type(self).started.set()
            type(self).continue_download.wait(timeout=5)
            callback(ProgressEvent("downloading", "Downloading", 0.4))
        return DownloadResult(download_request.output_dir, (), 1.0, 2.0)


def test_paused_job_can_resume(tmp_path):
    PausableDownloader.started.clear()
    PausableDownloader.continue_download.clear()
    PausableDownloader.calls = 0
    manager = DownloadJobManager(max_workers=1, downloader_factory=PausableDownloader)
    job_id = manager.submit(replace(request(tmp_path), urls=("https://youtu.be/one",)))[0]
    assert PausableDownloader.started.wait(timeout=5)

    manager.pause(job_id)
    PausableDownloader.continue_download.set()
    assert manager.wait(job_id).status is JobStatus.PAUSED

    manager.resume(job_id)
    assert manager.wait(job_id).status is JobStatus.COMPLETED
    manager.shutdown()


def test_jobs_survive_manager_restart(tmp_path):
    state_path = tmp_path / "state" / "jobs.json"
    manager = DownloadJobManager(
        max_workers=1,
        downloader_factory=SuccessfulDownloader,
        state_path=state_path,
    )
    job_id = manager.submit(replace(request(tmp_path), urls=("https://youtu.be/one",)))[0]
    assert manager.wait(job_id).status is JobStatus.COMPLETED
    manager.shutdown()

    restored = DownloadJobManager(
        max_workers=1,
        downloader_factory=SuccessfulDownloader,
        state_path=state_path,
    )
    snapshot = restored.snapshots()[0]
    assert snapshot.id == job_id
    assert snapshot.status is JobStatus.COMPLETED
    assert snapshot.files[0].name == "track.mp3"
    restored.shutdown()


def test_interrupted_job_is_recovered_as_paused(tmp_path):
    state_path = tmp_path / "jobs.json"
    manager = DownloadJobManager(
        max_workers=1,
        downloader_factory=SuccessfulDownloader,
        state_path=state_path,
    )
    job = manager.submit(replace(request(tmp_path), urls=("https://youtu.be/one",)))[0]
    manager.wait(job)
    manager.shutdown()
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    payload["jobs"][0]["status"] = "running"
    state_path.write_text(json.dumps(payload), encoding="utf-8")

    restored = DownloadJobManager(max_workers=1, state_path=state_path)
    snapshot = restored.snapshots()[0]
    assert snapshot.status is JobStatus.PAUSED
    assert "restart" in snapshot.message.lower() or "paused" in snapshot.message.lower()
    restored.shutdown()
