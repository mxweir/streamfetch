import sys
import time
from types import SimpleNamespace

import pytest

from streamfetch.library import MediaLibrary
from streamfetch.transcripts import (
    TranscriptionService,
    TranscriptStore,
    export_transcript,
    parse_subtitles,
    signature,
)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr("streamfetch.library.shutil.which", lambda _: None)
    (tmp_path / "speech.mp3").write_bytes(b"local speech")
    library = MediaLibrary(tmp_path)
    library.scan()
    return TranscriptStore(library)


def test_subtitle_import_search_and_export(store):
    text = "WEBVTT\n\n00:00.500 --> 00:03.250\n<b>Local</b> search 100%\n\n"
    segments = parse_subtitles(text)
    assert segments == [dict(start=0.5, end=3.25, text="Local search 100%")]
    path = store.library.list_items()[0].path
    store.save(path, segments)
    assert len(store.search("search")) == 1
    assert not store.search("_")
    assert len(store.search("100%")) == 1
    assert not store.search("' OR 1=1 --")
    assert "00:00:00,500 --> 00:00:03,250" in export_transcript(segments, srt=True)
    assert export_transcript(segments) == "Local search 100%"
    reopened = TranscriptStore(MediaLibrary(store.library.root))
    assert reopened.status(path)["status"] == "ready"
    assert reopened.segments(path) == segments
    path.write_bytes(b"changed speech")
    assert reopened.status(path)["status"] == "outdated"
    assert not reopened.search("Local")


@pytest.mark.parametrize(
    "text", ["", "nothing", "x" * 2_000_001, "00:00:02,000 --> 00:00:01,000\ninvalid"]
)
def test_invalid_subtitles(text):
    with pytest.raises(ValueError):
        parse_subtitles(text)


def test_atomic_replacement_and_restart_recovery(store):
    path = store.library.list_items()[0].path
    segments = [dict(start=0, end=1, text="Original")]
    store.save(path, segments)
    with pytest.raises(ValueError):
        store.save(path, [dict(start=float("inf"), end=1, text="invalid")])
    assert store.segments(path) == segments
    expected = signature(path)
    path.write_bytes(b"changed")
    with pytest.raises(ValueError):
        store.save(path, segments, expected_signature=expected)
    store.set_status(path, "running", "tiny")
    store.recover_interrupted()
    assert store.status(path)["status"] == "interrupted"


def test_missing_media_does_not_crash_status_polling(store):
    path = store.library.list_items()[0].path
    store.set_status(path, "running", "tiny")
    path.unlink()
    assert store.status(path)["status"] == "missing"
    store.set_status(path, "failed", "tiny", error="The media file was removed.")
    assert store.status(path)["error"] == "The media file was removed."


def test_background_engine_and_download_consent(store, tmp_path, monkeypatch):
    calls = []

    class Engine:
        def __init__(self, model, **kwargs):
            calls.append(kwargs)

        def transcribe(self, path, **kwargs):
            return iter(
                [SimpleNamespace(start=0, end=1, text="Hello local world")]
            ), SimpleNamespace(language="en")

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Engine))
    monkeypatch.setattr(TranscriptionService, "available", staticmethod(lambda: True))
    service = TranscriptionService(tmp_path)
    path = store.library.list_items()[0].path
    service.submit(store, path, allow_download=False)
    service._executor.shutdown(wait=True)
    assert store.status(path)["status"] == "ready"
    assert calls[0]["local_files_only"] is True
    assert calls[0]["device"] == "cpu"
    assert len(store.search("world")) == 1


def test_failed_engine_is_visible(store, tmp_path, monkeypatch):
    class Engine:
        def __init__(self, *a, **kwargs):
            raise RuntimeError("Model not cached. Allow model download.")

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Engine))
    monkeypatch.setattr(TranscriptionService, "available", staticmethod(lambda: True))
    service = TranscriptionService(tmp_path)
    path = store.library.list_items()[0].path
    service.submit(store, path)
    service._executor.shutdown(wait=True)
    assert store.status(path)["status"] == "failed"
    assert "not cached" in store.status(path)["error"]


def test_cancellation(store, tmp_path, monkeypatch):
    class Engine:
        def __init__(self, *a, **kwargs):
            pass

        def transcribe(self, path, **kwargs):
            def segments():
                time.sleep(0.1)
                yield SimpleNamespace(start=0, end=1, text="cancelled")

            return segments(), SimpleNamespace(language="en")

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Engine))
    monkeypatch.setattr(TranscriptionService, "available", staticmethod(lambda: True))
    service = TranscriptionService(tmp_path)
    path = store.library.list_items()[0].path
    service.submit(store, path)
    service.cancel(store, path)
    service._executor.shutdown(wait=True)
    assert store.status(path)["status"] == "cancelled"
    assert not store.segments(path)
