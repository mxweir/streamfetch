import io
import json
import shutil
import subprocess
import wave

import pytest
from mutagen import File
from PIL import Image

from streamfetch.file_metadata import (
    file_backups,
    restore_file_backup,
    validate_cover,
    write_file_metadata,
)
from streamfetch.library import MediaLibrary
from streamfetch.listening import FolderWatcher, ListeningLibrary, read_chapters


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "media"
    root.mkdir()
    with wave.open(str(root / "Morning.wav"), "wb") as media:
        media.setnchannels(1)
        media.setsampwidth(2)
        media.setframerate(8000)
        media.writeframes(b"\x00\x00" * 16000)
    library = MediaLibrary(root)
    library.scan()
    return library


def test_smart_rules_are_live_and_persist(library):
    item = library.list_items()[0]
    library.update_metadata(
        item.path, title="Morning", artist="Artist", album="Album", rating=4, tags=("Focus",)
    )
    store = ListeningLibrary(library)
    store.save_smart(
        "Focus",
        tag="focus",
        minimum_rating=4,
        max_minutes=1,
        added_days=1,
        unplayed=True,
        media_type="audio",
    )
    playlist = store.smart_playlists()[0]
    assert [row.path for row in store.smart_items(playlist["id"])] == [item.path]
    library.record_play(item.path)
    assert store.smart_items(playlist["id"]) == ()
    store.save_smart("Focus", tag="Focus", minimum_rating=4)
    assert len(store.smart_playlists()) == 1
    reopened = ListeningLibrary(MediaLibrary(library.root))
    assert len(reopened.smart_items(playlist["id"])) == 1
    store.delete_smart(playlist["id"])
    with pytest.raises(ValueError):
        store.smart_items(playlist["id"])


@pytest.mark.parametrize(
    "rules", [dict(name=""), dict(name="x", minimum_rating=9), dict(name="x", max_minutes=-1)]
)
def test_invalid_smart_rules(library, rules):
    with pytest.raises(ValueError):
        ListeningLibrary(library).save_smart(**rules)


def test_bookmarks_persist_and_cascade(library):
    item = library.list_items()[0]
    store = ListeningLibrary(library)
    store.add_bookmark(item.path, 1.25, "The useful part")
    assert ListeningLibrary(MediaLibrary(library.root)).bookmarks(item.path)[0]["seconds"] == 1.25
    with pytest.raises(ValueError):
        store.add_bookmark(item.path, float("nan"), "Bad")
    mark = store.bookmarks(item.path)[0]
    store.delete_bookmark(mark["id"])
    assert not store.bookmarks(item.path)
    store.add_bookmark(item.path, 0, "Start")
    item.path.unlink()
    library.scan()
    assert not store.bookmarks(item.path)


def test_watched_folders_index_without_copying(library, tmp_path):
    watcher = FolderWatcher(tmp_path / "state", start=False)
    watcher.add(str(library.root))
    watcher.add(str(library.root))
    watcher.scan()
    assert watcher.status[str(library.root)]["total"] == 1
    assert len(watcher.roots()) == 1
    reopened = FolderWatcher(tmp_path / "state", start=False)
    assert reopened.roots() == [str(library.root)]
    watcher.remove(str(library.root))
    assert not watcher.roots()
    assert (library.root / "Morning.wav").is_file()
    with pytest.raises(ValueError):
        watcher.add(tmp_path / "missing")
    watcher.shutdown()


def test_metadata_write_backup_and_restore(library):
    item = library.list_items()[0]
    original = item.path.read_bytes()
    cover = io.BytesIO()
    Image.new("RGB", (10, 10), "green").save(cover, format="PNG")
    backup = write_file_metadata(
        library,
        item.path,
        title="New title",
        artist="New artist",
        album="New album",
        cover=cover.getvalue(),
    )
    assert backup.read_bytes() == original
    assert str(File(item.path).tags["TIT2"]) == "New title"
    assert File(item.path).tags.getall("APIC")[0].data == cover.getvalue()
    assert library.item_for_path(item.path).title == "New title"
    assert file_backups(library, item.path) == [backup]
    assert library.count_items() == 1  # Backup copies must not appear as tracks.
    restore_file_backup(library, item.path, backup)
    assert item.path.read_bytes() == original
    assert library.item_for_path(item.path).title == "Morning"
    with pytest.raises(ValueError):
        restore_file_backup(library, item.path, item.path)


@pytest.mark.parametrize(
    "extension,codec",
    [
        ("mp3", "libmp3lame"),
        ("flac", "flac"),
        ("m4a", "aac"),
        ("ogg", "libvorbis"),
        ("opus", "libopus"),
    ],
)
def test_real_format_tags(library, extension, codec):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg integration test")
    path = library.root / f"track.{extension}"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(library.root / "Morning.wav"),
            "-c:a",
            codec,
            str(path),
        ],
        check=True,
    )
    library.scan()
    cover = io.BytesIO()
    Image.new("RGB", (10, 10), "purple").save(cover, format="PNG")
    backup = write_file_metadata(
        library, path, title="Tagged", artist="Artist", album="Album", cover=cover.getvalue()
    )
    assert library.item_for_path(path).title == "Tagged"
    assert library.item_for_path(path).cover_path.is_file()
    assert backup.is_file()


def test_real_embedded_chapters(library, tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg integration test")
    metadata = tmp_path / "chapters.txt"
    metadata.write_text(
        ";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=1000\n"
        "title=Introduction\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=1000\n"
        "END=2000\ntitle=The useful part\n"
    )
    path = library.root / "chapters.m4a"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(library.root / "Morning.wav"),
            "-i",
            str(metadata),
            "-map_metadata",
            "1",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
    )
    assert read_chapters(path) == [
        dict(seconds=0, title="Introduction"),
        dict(seconds=1, title="The useful part"),
    ]


def test_invalid_cover_and_backup_traversal(library):
    with pytest.raises(ValueError):
        validate_cover(b"a" * (10 * 1024 * 1024 + 1))
    with pytest.raises(OSError):
        validate_cover(b"not an image")
    item = library.list_items()[0]
    directory = library.state_dir / "tag-backups" / "fake"
    directory.mkdir(parents=True)
    (directory / "restore.json").write_text(
        json.dumps({"path": "Morning.wav", "file": str(item.path)})
    )
    assert file_backups(library, item.path) == []


def test_chapters_parsed(library, monkeypatch):
    monkeypatch.setattr("streamfetch.listening.shutil.which", lambda _: "ffprobe")
    monkeypatch.setattr(
        "streamfetch.listening.subprocess.run",
        lambda *a, **k: subprocess.CompletedProcess(
            [],
            0,
            stdout=json.dumps(
                {
                    "chapters": [
                        {"start_time": "0", "tags": {"title": "Intro"}},
                        {"start_time": "1.5"},
                        {"start_time": "nan"},
                    ]
                }
            ),
        ),
    )
    assert read_chapters(library.list_items()[0].path) == [
        dict(seconds=0, title="Intro"),
        dict(seconds=1.5, title="Chapter 2"),
    ]
