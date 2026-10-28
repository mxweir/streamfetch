import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from streamfetch.collections import MAX_COLLECTION_TRACKS, Collections
from streamfetch.library import MediaLibrary


@pytest.fixture
def collection(tmp_path, monkeypatch):
    monkeypatch.setattr("streamfetch.library.shutil.which", lambda _: None)
    root = tmp_path / "media"
    root.mkdir()
    for name, data in (("one.mp3", b"first-original"), ("two.mp3", b"second-original")):
        (root / name).write_bytes(data)
    library = MediaLibrary(root)
    library.scan()
    return Collections(library)


def test_bulk_favorites_and_queue_are_idempotent_ordered_and_persistent(collection):
    selected = ["two.mp3", "one.mp3", "two.mp3"]
    assert collection.apply(selected, "favorite") == 2
    assert collection.apply(selected, "favorite") == 0
    assert collection.library.favorite_paths() == {"one.mp3", "two.mp3"}
    assert collection.apply(selected, "queue") == 2
    assert collection.apply(selected, "queue") == 0
    reopened = MediaLibrary(collection.library.root)
    assert [entry.item.path.name for entry in reopened.queue()] == ["two.mp3", "one.mp3"]
    assert collection.apply(selected, "unfavorite") == 2
    assert collection.apply(selected, "unfavorite") == 0


def test_bulk_new_and_existing_playlist_are_idempotent(collection):
    assert collection.apply(["two.mp3"], "playlist", playlist_name=" Travel ") == 1
    playlist = collection.library.playlists()[0]
    assert collection.apply(["two.mp3"], "playlist", playlist_name="travel") == 0
    assert collection.apply(["two.mp3", "one.mp3"], "playlist", playlist_id=playlist.id) == 1
    assert [item.path.name for item in collection.library.playlist_items(playlist.id)] == [
        "two.mp3",
        "one.mp3",
    ]
    with pytest.raises(ValueError, match="no longer exists"):
        collection.apply(["one.mp3"], "playlist", playlist_id=999)
    assert len(collection.library.playlists()) == 1


@pytest.mark.parametrize("action", ["favorite", "queue", "playlist"])
def test_invalid_selection_is_atomic(collection, action):
    with pytest.raises(ValueError, match="no longer indexed"):
        collection.apply(["one.mp3", "unindexed.mp3"], action, playlist_name="No partials")
    assert collection.library.favorite_paths() == set()
    assert collection.library.queue() == ()
    assert collection.library.playlists() == ()


def test_export_preserves_bytes_order_metadata_unicode_and_privacy(collection, tmp_path):
    library = collection.library
    for filename in ("one.mp3", "two.mp3"):
        library.update_metadata(
            filename,
            title="../Été/夏\nSong",
            artist="Artist: *?",
            album="Album",
            rating=4,
            tags=["旅行", "Road"],
        )
    with library._connection() as connection:
        connection.execute(
            "UPDATE media_items SET source_url = ?", ("https://secret/?token=hidden",)
        )
    artifact = collection.export(["two.mp3", "one.mp3"], export_dir=tmp_path / "exports")
    assert artifact.item_count == 2
    assert artifact.size_bytes == artifact.path.stat().st_size
    with zipfile.ZipFile(artifact.path) as archive:
        files = archive.namelist()
        assert len(files) == 4
        media = files[:2]
        assert len(set(name.casefold() for name in media)) == 2
        assert all(not Path(name).is_absolute() and ".." not in Path(name).parts for name in files)
        assert "Été" in media[0] and "夏" in media[0]
        assert archive.read(media[0]) == b"second-original"
        assert archive.read(media[1]) == b"first-original"
        playlist = archive.read("playlist.m3u8").decode()
        assert playlist.startswith("#EXTM3U\n")
        assert [line for line in playlist.splitlines() if not line.startswith("#")] == media
        metadata = archive.read("manifest.json").decode()
        manifest = json.loads(metadata)
        assert manifest["version"] == 1
        assert manifest["schema"] == "streamfetch.collection"
        assert manifest["created_at"].endswith("+00:00")
        assert manifest["items"][0]["tags"] == ["旅行", "Road"]
        assert manifest["items"][0]["rating"] == 4
        assert manifest["items"][0]["sha256"] == hashlib.sha256(b"second-original").hexdigest()
        assert manifest["items"][0]["size_bytes"] == len(b"second-original")
        assert "source_url" not in metadata and "hidden" not in metadata
        assert str(library.root) not in metadata
        assert "cover_path" not in metadata
    artifact.remove()
    artifact.remove()
    assert not artifact.path.exists()


def test_missing_original_aborts_without_archive(collection, tmp_path):
    (collection.library.root / "two.mp3").unlink()
    directory = tmp_path / "exports"
    with pytest.raises(FileNotFoundError):
        collection.export(["one.mp3", "two.mp3"], export_dir=directory)
    assert not directory.exists()


def test_very_long_unicode_names_extract_within_filesystem_limits(collection, tmp_path):
    collection.library.update_metadata("one.mp3", title="😀" * 250, artist="夏" * 300, album="")
    artifact = collection.export(["one.mp3"], export_dir=tmp_path / "exports")
    with zipfile.ZipFile(artifact.path) as archive:
        media = archive.namelist()[0]
        assert len(Path(media).name.encode("utf-8")) < 255
        archive.extractall(tmp_path / "extracted")
        assert (tmp_path / "extracted" / media).read_bytes() == b"first-original"


def test_symlink_escape_and_relative_traversal_rejected(collection, tmp_path):
    outside = tmp_path / "private.mp3"
    outside.write_bytes(b"private")
    original = collection.library.root / "one.mp3"
    original.unlink()
    original.symlink_to(outside)
    with pytest.raises(ValueError, match="inside the library"):
        collection.export(["one.mp3"], export_dir=tmp_path / "exports")
    with pytest.raises(ValueError, match="inside the library"):
        collection.export(["../private.mp3"], export_dir=tmp_path / "exports")


def test_unindexed_original_and_empty_selection_rejected(collection, tmp_path):
    (collection.library.root / "unindexed.mp3").write_bytes(b"not indexed")
    with pytest.raises(ValueError, match="no longer indexed"):
        collection.export(["unindexed.mp3"])
    with pytest.raises(ValueError, match="at least one"):
        collection.export([])
    with pytest.raises(ValueError, match="200 tracks"):
        collection.items([f"{i}.mp3" for i in range(MAX_COLLECTION_TRACKS + 1)])


def test_export_size_limits_include_archive_and_cleanup_own_partial(collection, tmp_path):
    directory = tmp_path / "exports"
    directory.mkdir()
    unrelated = directory / "leave-me.zip"
    unrelated.write_bytes(b"user file")
    for limit in (1, 30):
        with pytest.raises(ValueError, match="size limit"):
            collection.export(["one.mp3", "two.mp3"], export_dir=directory, max_bytes=limit)
        assert list(directory.iterdir()) == [unrelated]
    with pytest.raises(ValueError, match="200 MiB"):
        collection.export(["one.mp3"], max_bytes=201 * 1024 * 1024)


def test_export_write_failure_cleans_own_artifacts(collection, tmp_path, monkeypatch):
    directory = tmp_path / "exports"

    def fail(*args, **kwargs):
        raise OSError("Disk full")

    monkeypatch.setattr("streamfetch.collections.zipfile.ZipFile.writestr", fail)
    with pytest.raises(OSError, match="Disk full"):
        collection.export(["one.mp3"], export_dir=directory)
    assert list(directory.iterdir()) == []


def test_symlink_directory_escape_is_rejected(collection, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.mp3").write_bytes(b"private")
    linked = collection.library.root / "linked"
    linked.symlink_to(outside, target_is_directory=True)
    with collection.library._connection() as connection:
        connection.execute(
            "INSERT INTO media_items SELECT 'linked/private.mp3', title, artist, album, "
            "duration_seconds, size_bytes, media_type, format, modified_at, added_at, "
            "cover_path, source_url, custom_title, custom_artist, custom_album, rating, tags_json "
            "FROM media_items WHERE path = 'one.mp3'"
        )
    with pytest.raises(ValueError, match="inside the library"):
        collection.export(["linked/private.mp3"], export_dir=tmp_path / "exports")


def test_file_growth_during_export_still_enforces_size_limit(collection, tmp_path, monkeypatch):
    import os

    original_open = os.open
    media = collection.library.root / "one.mp3"

    def growing_open(path, flags, *args, **kwargs):
        if Path(path).name == media.name:
            media.write_bytes(b"a" * 200)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr("streamfetch.collections.os.open", growing_open)
    directory = tmp_path / "exports"
    with pytest.raises(ValueError, match="size limit"):
        collection.export(["one.mp3"], export_dir=directory, max_bytes=150)
    assert list(directory.iterdir()) == []


@pytest.mark.skipif(__import__("os").name == "nt", reason="POSIX openat race regression")
def test_parent_swap_between_containment_check_and_open_cannot_escape(
    collection, tmp_path, monkeypatch
):
    import os

    library = collection.library
    nested = library.root / "nested"
    nested.mkdir()
    (nested / "race.mp3").write_bytes(b"allowed original")
    library.scan()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "race.mp3").write_bytes(b"private outside bytes")
    original_open = os.open
    swapped = False

    def swapping_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if path == "nested" and not swapped:
            swapped = True
            nested.rename(library.root / "original-nested")
            nested.symlink_to(outside, target_is_directory=True)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr("streamfetch.collections.os.open", swapping_open)
    export_dir = tmp_path / "exports"
    with pytest.raises(OSError):
        collection.export(["nested/race.mp3"], export_dir=export_dir)
    assert swapped
    assert list(export_dir.iterdir()) == []


@pytest.mark.skipif(__import__("os").name == "nt", reason="POSIX descriptor anchoring regression")
def test_parent_swapped_after_open_uses_original_directory_descriptor(
    collection, tmp_path, monkeypatch
):
    import os

    library = collection.library
    nested = library.root / "nested"
    nested.mkdir()
    (nested / "race.mp3").write_bytes(b"allowed original")
    library.scan()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "race.mp3").write_bytes(b"private outside bytes")
    original_open = os.open

    def swapping_open(path, flags, *args, **kwargs):
        if path == "race.mp3":
            nested.rename(library.root / "original-nested")
            nested.symlink_to(outside, target_is_directory=True)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr("streamfetch.collections.os.open", swapping_open)
    artifact = collection.export(["nested/race.mp3"], export_dir=tmp_path / "exports")
    with zipfile.ZipFile(artifact.path) as archive:
        assert archive.read(archive.namelist()[0]) == b"allowed original"


@pytest.mark.skipif(__import__("os").name != "nt", reason="Windows opened-handle verification")
def test_windows_export_verifies_opened_handle_path(collection, tmp_path, monkeypatch):
    outside = tmp_path / "outside.mp3"
    outside.write_bytes(b"outside")
    monkeypatch.setattr("streamfetch.collections._windows_final_path", lambda descriptor: outside)
    with pytest.raises(ValueError):
        collection.export(["one.mp3"], export_dir=tmp_path / "exports")
    assert list((tmp_path / "exports").iterdir()) == []


@pytest.mark.skipif(__import__("os").name == "nt", reason="POSIX nonblocking FIFO verification")
def test_opened_descriptor_must_be_regular_file(collection):
    import os

    from streamfetch.collections import _open_original

    fifo = collection.library.root / "replaced.mp3"
    os.mkfifo(fifo)
    with pytest.raises(ValueError, match="original media files"):
        _open_original(collection.library.root, fifo)


def test_pagination_reaches_all_filtered_items_beyond_120(tmp_path, monkeypatch):
    monkeypatch.setattr("streamfetch.library.shutil.which", lambda _: None)
    for i in range(131):
        (tmp_path / f"track-{i:03d}.mp3").write_bytes(b"sample")
    library = MediaLibrary(tmp_path)
    library.scan()
    assert library.count_items(search="track") == 131
    items = [
        item
        for offset in range(0, 131, 25)
        for item in library.list_items(search="track", sort="title", limit=25, offset=offset)
    ]
    assert len(items) == len({item.path for item in items}) == 131
    assert items[-1].title == "track-130"


def test_old_database_migrates_without_losing_added_at_or_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr("streamfetch.library.shutil.which", lambda _: None)
    library = MediaLibrary(tmp_path)
    library.state_dir.mkdir()
    (tmp_path / "old.mp3").write_bytes(b"original")
    with sqlite3.connect(library.database_path) as connection:
        connection.execute("""CREATE TABLE media_items (
            path TEXT PRIMARY KEY, title TEXT NOT NULL, artist TEXT NOT NULL,
            album TEXT NOT NULL, duration_seconds REAL, size_bytes INTEGER NOT NULL,
            media_type TEXT NOT NULL, format TEXT NOT NULL, modified_at REAL NOT NULL,
            added_at REAL NOT NULL, cover_path TEXT, source_url TEXT)""")
        connection.execute(
            "INSERT INTO media_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "old.mp3",
                "Old title",
                "Artist",
                "Album",
                1,
                8,
                "audio",
                "MP3",
                1.0,
                123.0,
                None,
                None,
            ),
        )
    service = Collections(library)
    assert service.apply(["old.mp3"], "favorite") == 1
    item = service.items(["old.mp3"])[0]
    assert item.added_at == 123.0 and item.rating == 0 and item.tags == ()
    assert item.title == "Old title"
