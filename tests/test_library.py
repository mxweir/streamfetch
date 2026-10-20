import wave

import pytest

from streamfetch.library import MediaLibrary


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr("streamfetch.library.shutil.which", lambda _: None)
    return MediaLibrary(tmp_path)


def write_wav(path, seconds=1):
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8_000)
        audio.writeframes(b"\x00\x00" * 8_000 * seconds)


def test_scan_indexes_supported_media_and_stats(library):
    write_wav(library.root / "Sample Track.wav")
    (library.root / "clip.mp4").write_bytes(b"not a real video")
    (library.root / "notes.txt").write_text("ignore me")

    summary = library.scan()
    items = library.list_items(sort="title")
    stats = library.stats()

    assert summary.added == 2
    assert summary.total == 2
    assert [item.title for item in items] == ["clip", "Sample Track"]
    assert items[1].duration_seconds == pytest.approx(1.0)
    assert stats.total == 2
    assert stats.audio == 1
    assert stats.video == 1
    assert stats.size_bytes > 0
    assert library.database_path.exists()


def test_search_filter_and_rescan_remove_missing_files(library):
    first = library.root / "First Song.mp3"
    second = library.root / "Second Song.flac"
    video = library.root / "concert.webm"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    video.write_bytes(b"three")
    library.scan()

    assert library.count_items(search="Second") == 1
    assert [item.path.name for item in library.list_items(media_type="video")] == [
        "concert.webm"
    ]

    first.unlink()
    replacement = library.root / "Replacement Song.mp3"
    replacement.write_bytes(b"new")
    summary = library.scan()

    assert summary.added == 1
    assert summary.removed == 1
    assert summary.total == 3
    assert library.count_items(search="First") == 0


def test_rescan_updates_changed_file_without_resetting_library(library):
    track = library.root / "changing.mp3"
    track.write_bytes(b"before")
    library.scan()
    track.write_bytes(b"after and larger")

    summary = library.scan()

    assert summary.added == 0
    assert summary.updated == 1
    assert summary.removed == 0
    assert library.list_items()[0].size_bytes == len(b"after and larger")
