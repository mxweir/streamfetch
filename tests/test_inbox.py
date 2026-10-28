import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

import streamfetch.inbox as inbox_module
from streamfetch.inbox import InboxStore, canonical_url

VIDEO = "aqz-KE-bpKQ"
URL = f"https://www.youtube.com/watch?v={VIDEO}"


@pytest.mark.parametrize("url", [
    f"https://youtu.be/{VIDEO}?si=tracking",
    f"https://m.youtube.com/shorts/{VIDEO}?feature=share",
    f"https://www.youtube.com/live/{VIDEO}#fragment",
    f"http://youtube.com:80/embed/{VIDEO}?utm_source=test",
    URL,
])
def test_video_aliases(url):
    assert canonical_url(url) == URL


def test_playlist_intent_and_secret_tokens():
    assert canonical_url(f"https://youtu.be/{VIDEO}?list=PL_123&index=2") == URL + "&list=PL_123"
    assert canonical_url("https://youtube.com/playlist?list=PL_123&si=foo") == (
        "https://www.youtube.com/playlist?list=PL_123")
    assert canonical_url("https://m.soundcloud.com/artist/track?si=x&secret_token=s-secret") == (
        "https://soundcloud.com/artist/track?secret_token=s-secret")
    assert canonical_url("https://on.soundcloud.com/ABC?si=x") == "https://on.soundcloud.com/ABC"


@pytest.mark.parametrize("url", [
    "https://user:pass@youtube.com/watch?v=aqz-KE-bpKQ",
    "https://youtube.com:8080/watch?v=aqz-KE-bpKQ", "https://localhost/video",
    "https://youtube.com.evil.test/watch?v=aqz-KE-bpKQ", "file:///tmp/video",
    "https://youtube.com/watch?v=abc", "https://youtube.com/playlist",
    "https://youtube.com/watch?v=aqz-KE-bpKQ&v=AAAAAAAAAAA", "https://soundcloud.com/",
    "https://youtube.com\\@evil.test/watch?v=aqz-KE-bpKQ",
    "https://youtube.com/watch?v=aqz-KE-bpKQ\n", "https://youtube.com:bad/video",
])
def test_reject_unsafe_or_invalid_urls(url):
    with pytest.raises(ValueError):
        canonical_url(url)


def test_persistence_dedupe_and_note(tmp_path):
    store = InboxStore(tmp_path)
    assert store.add_batch([URL, f"https://youtu.be/{VIDEO}"], "Film night") == (1, 1)
    entry, = InboxStore(tmp_path).list_entries(search="FILM")
    assert entry.status == "ready" and entry.note == "Film night"
    store.update_note(entry.id, "Watch later")
    store.handoff([entry.id])
    assert store.add_batch(URL, "Do not replace") == (0, 1)
    entry, = store.list_entries(status="handed_off")
    assert entry.note == "Watch later"
    assert store.list_entries(search="100%") == ()


def test_atomic_batch_and_limits(tmp_path):
    store = InboxStore(tmp_path)
    for batch in ([URL, "https://evil.test/track"], [URL, None], [URL] * 101, []):
        with pytest.raises(ValueError):
            store.add_batch(batch)
        assert not store.list_entries()
    with pytest.raises(ValueError):
        store.add_batch(URL, "x" * 2001)
    with pytest.raises(ValueError):
        store.list_entries(status="bad")


def test_atomic_handoff_and_job_history(tmp_path):
    store = InboxStore(tmp_path)
    store.add_batch([URL, "https://soundcloud.com/artist/track"])
    entries = store.list_entries()
    ids = [entry.id for entry in entries]
    with pytest.raises(ValueError):
        store.handoff([ids[0], 999])
    assert all(e.status == "ready" for e in store.list_entries())
    assert store.handoff(ids) == tuple(e.url for e in entries)
    store.attach_jobs(ids, ["job_123"])
    with pytest.raises(ValueError):
        store.handoff(ids)
    store.archive(ids)
    store.restore(ids)
    assert all(e.job_ids == ("job_123",) for e in store.list_entries())
    store.handoff(ids)
    store.attach_jobs(ids, ["job_123", "job_456"])
    assert store.list_entries()[0].job_ids == ("job_123", "job_456")
    with pytest.raises(ValueError):
        store.attach_jobs([ids[0], 999], ["bad_rollback"])
    assert store.list_entries()[0].job_ids == ("job_123", "job_456")


def test_concurrent_writes_and_handoff(tmp_path):
    store = InboxStore(tmp_path)
    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(workers.map(lambda _: store.add_batch(URL), range(12)))
    assert sum(value[0] for value in results) == 1
    entry, = store.list_entries()

    def handoff(_):
        try:
            return store.handoff([entry.id])
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(workers.map(handoff, range(8)))
    assert sum(result is not None for result in results) == 1
    with sqlite3.connect(store.path) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_capacity_and_invalid_updates(tmp_path, monkeypatch):
    monkeypatch.setattr(inbox_module, "MAX_ENTRIES", 1)
    store = InboxStore(tmp_path)
    store.add_batch(URL)
    with pytest.raises(ValueError):
        store.add_batch([URL, "https://soundcloud.com/artist/new"])
    assert len(store.list_entries()) == 1
    assert store.add_batch(URL) == (0, 1)
    with pytest.raises(ValueError):
        store.update_note(999, "No entry")
    with pytest.raises(ValueError):
        store.archive([True])
    with pytest.raises(ValueError):
        store.attach_jobs([1], ["../../invalid"])
    with pytest.raises(ValueError):
        store.attach_jobs([1], ["valid_but_not_handed_off"])
    with pytest.raises(ValueError):
        store.list_entries(limit=0)
    with pytest.raises(ValueError):
        store.list_entries(search="x" * 201)
    with pytest.raises(ValueError):
        store.add_batch("x" * 409701)
