import json
import sqlite3
import time
import zipfile
from pathlib import Path

import pytest

from streamfetch.jobs import DownloadJobManager
from streamfetch.library import MediaLibrary
from streamfetch.models import DownloadResult, PreviewEntry, SourcePreview
from streamfetch.subscriptions import SubscriptionService, SubscriptionStore, media_key
from streamfetch.updates import create_pre_update_backup


class DemoDownloader:
    entries = ()
    fail = False

    def inspect(self, url, limit=200):
        if self.fail:
            raise RuntimeError("Source unavailable")
        return SourcePreview(
            url, "Demo source", "playlist", "Demo", len(self.entries), entries=self.entries[:limit]
        )

    def download(self, request, callback=None):
        if self.fail:
            raise RuntimeError("Network interrupted")
        request.output_dir.mkdir(parents=True, exist_ok=True)
        path = request.output_dir / "track.mp3"
        path.write_bytes(b"demo audio")
        return DownloadResult(request.output_dir, (path,), time.time(), time.time())


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr("streamfetch.library.shutil.which", lambda _: None)
    DemoDownloader.fail = False
    DemoDownloader.entries = tuple(
        PreviewEntry(f"Track {i}", webpage_url=f"https://www.youtube.com/watch?v=demo{i}")
        for i in range(3)
    )
    jobs = DownloadJobManager(
        downloader_factory=DemoDownloader, state_path=tmp_path / "jobs.json", retry_delays=()
    )
    store = SubscriptionStore(tmp_path / "state" / "subscriptions.db")
    svc = SubscriptionService(store, jobs, DemoDownloader, start=False)
    source_id = store.save(
        name="Demo source",
        url="https://www.youtube.com/@demo/videos",
        profile="Music MP3",
        root=tmp_path / "media",
        batch_limit=2,
    )
    yield svc, source_id
    svc.shutdown()
    jobs.shutdown()


def finish(service):
    for job in service.jobs.snapshots():
        service.jobs.wait(job.id)
    service.reconcile()


def test_sources_persist_and_invalid_settings_are_rejected(service):
    svc, source_id = service
    reopened = SubscriptionStore(svc.store.path)
    assert reopened.source(source_id)["profile"] == "Music MP3"
    with pytest.raises(ValueError, match="audio"):
        reopened.save(
            name="Cloud", url="https://soundcloud.com/demo", profile="Video 1080p", root="media"
        )
    with pytest.raises(sqlite3.IntegrityError):
        reopened.save(
            name="Duplicate",
            url=svc.store.source(source_id)["url"],
            profile="Music MP3",
            root="media",
        )


def test_youtube_identity_ignores_tracking_and_playlist_context():
    assert media_key("https://youtu.be/abc?t=30") == media_key(
        "https://www.youtube.com/watch?v=abc&list=playlist&index=2"
    )
    assert media_key("https://youtube.com/shorts/abc") == "youtube:abc"
    assert media_key("https://soundcloud.com/demo/track?utm_source=test") == media_key(
        "https://soundcloud.com/demo/track/"
    )


def test_rechecks_deduplicate_and_preserve_downloads(service):
    svc, source_id = service
    svc.check(source_id)
    svc.check(source_id)
    assert len(svc.store.items(source_id)) == 3
    keys = [item["key"] for item in svc.store.items(source_id)]
    assert svc.queue(source_id, keys) == 2
    assert svc.queue(source_id, keys[:2]) == 0
    finish(svc)
    svc.check(source_id)
    assert [item["status"] for item in svc.store.items(source_id)] == [
        "downloaded",
        "downloaded",
        "new",
    ]
    assert len(svc.store.history(source_id)) >= 4


def test_source_playlist_follows_updated_order_and_keeps_files(service):
    svc, source_id = service
    svc.check(source_id)
    svc.queue(source_id, [item["key"] for item in svc.store.items(source_id)])
    finish(svc)
    library = MediaLibrary(Path(svc.store.source(source_id)["root"]))
    playlist = library.playlists()[0]
    original = [item.path for item in library.playlist_items(playlist.id)]
    DemoDownloader.entries = tuple(reversed(DemoDownloader.entries))
    svc.check(source_id)
    assert [item.path for item in library.playlist_items(playlist.id)] == list(reversed(original))
    assert all(path.is_file() for path in original)


def test_existing_library_source_url_is_recognized(service):
    svc, source_id = service
    library = MediaLibrary(Path(svc.store.source(source_id)["root"]))
    library.root.mkdir(parents=True)
    path = library.root / "existing.mp3"
    path.write_bytes(b"existing media")
    library.scan()
    with library._connection() as db:
        db.execute("UPDATE media_items SET source_url=?", ("https://youtu.be/demo0",))
    svc.check(source_id)
    first = svc.store.items(source_id)[0]
    assert first["status"] == "downloaded"
    assert json.loads(first["files"]) == [str(path)]


def test_failed_jobs_remain_retryable_and_are_not_marked_downloaded(service):
    svc, source_id = service
    svc.check(source_id)
    key = svc.store.items(source_id)[0]["key"]
    DemoDownloader.fail = True
    svc.queue(source_id, [key])
    finish(svc)
    assert svc.store.items(source_id)[0]["status"] == "failed"
    DemoDownloader.fail = False
    assert svc.queue(source_id, [key]) == 1
    finish(svc)
    assert svc.store.items(source_id)[0]["status"] == "downloaded"


def test_discovery_errors_are_recorded_for_the_source(service):
    svc, source_id = service
    DemoDownloader.fail = True
    svc._check_guarded(source_id)
    assert svc.store.source(source_id)["error"] == "Source unavailable"
    assert svc.store.history(source_id)[0]["kind"] == "error"


def test_scheduler_honors_opt_in_interval_and_disabled_sources(service, monkeypatch):
    svc, source_id = service
    calls = []
    monkeypatch.setattr(svc, "request_check", lambda key: calls.append(key) or True)
    svc.tick(now=100)
    assert calls == []
    with svc.store.connect() as db:
        db.execute("UPDATE sources SET check_on_start=1 WHERE id=?", (source_id,))
    svc.tick(now=100)
    svc.tick(now=101)
    assert calls == [source_id]
    with svc.store.connect() as db:
        db.execute("UPDATE sources SET checked_at=100,interval_minutes=15 WHERE id=?", (source_id,))
    svc.tick(now=999)
    assert len(calls) == 1
    svc.tick(now=1001)
    assert len(calls) == 2
    svc.store.toggle(source_id, False)
    svc.tick(now=2000)
    assert len(calls) == 2


def test_removing_source_preserves_media_and_playlist(service):
    svc, source_id = service
    svc.check(source_id)
    svc.queue(source_id, [svc.store.items(source_id)[0]["key"]])
    finish(svc)
    library = MediaLibrary(Path(svc.store.source(source_id)["root"]))
    paths = [item.path for item in library.list_items()]
    svc.store.delete(source_id)
    assert svc.store.sources() == []
    assert library.playlists()
    assert all(path.exists() for path in paths)


def test_update_backup_includes_subscriptions_and_source_libraries(service):
    svc, source_id = service
    svc.check(source_id)
    backup = create_pre_update_backup(svc.store.path.parent, None, "1.3.0")
    with zipfile.ZipFile(backup) as archive:
        assert "state/subscriptions.db" in archive.namelist()
        assert "libraries/source-0/library.db" in archive.namelist()


def test_discovery_never_enqueues_downloads_and_preserves_old_window(service):
    svc, source_id = service
    svc.check(source_id)
    DemoDownloader.entries = DemoDownloader.entries[:1]
    svc.check(source_id)
    assert len(svc.store.items(source_id)) == 3
    assert svc.jobs.snapshots() == ()


def test_completed_jobs_reconcile_after_service_and_job_manager_restart(service):
    svc, source_id = service
    svc.check(source_id)
    svc.queue(source_id, [svc.store.items(source_id)[0]["key"]])
    for job in svc.jobs.snapshots():
        svc.jobs.wait(job.id)
    # A full restart happens before the subscription poller consumes completion.
    svc.jobs.shutdown()
    recovered_jobs = DownloadJobManager(
        downloader_factory=DemoDownloader,
        state_path=svc.store.path.parent.parent / "jobs.json",
        retry_delays=(),
    )
    recovered = SubscriptionService(
        SubscriptionStore(svc.store.path), recovered_jobs, DemoDownloader, start=False
    )
    try:
        recovered.reconcile()
        assert recovered.store.items(source_id)[0]["status"] == "downloaded"
        assert recovered.queue(source_id, [recovered.store.items(source_id)[0]["key"]]) == 0
    finally:
        recovered.shutdown()
        recovered_jobs.shutdown()


def test_completed_media_is_shared_with_another_source_in_same_library(service):
    svc, source_id = service
    svc.check(source_id)
    svc.queue(source_id, [svc.store.items(source_id)[0]["key"]])
    finish(svc)
    second = svc.store.save(
        name="Another collection",
        url="https://www.youtube.com/playlist?list=demo",
        profile="Music MP3",
        root=svc.store.source(source_id)["root"],
    )
    svc.check(second)
    assert svc.store.items(second)[0]["status"] == "downloaded"
    assert svc.store.items(second)[0]["files"] == svc.store.items(source_id)[0]["files"]
