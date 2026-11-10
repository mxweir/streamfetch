from pathlib import Path

import pytest

from streamfetch.backup import (
    create_workspace_backup,
    inspect_workspace_backup,
    restore_workspace_backup,
)
from streamfetch.library import MediaLibrary
from streamfetch.listening import ListeningLibrary
from streamfetch.transcripts import TranscriptStore


def test_backup_restores_multiple_libraries_and_rejects_damage(tmp_path):
    libraries = tuple(MediaLibrary(tmp_path / name) for name in ("first", "second"))
    for library in libraries:
        library.root.mkdir()
        source = library.root / "track.mp3"
        source.write_bytes(b"original audio")
        library.scan()
        library.set_playback_position(source, 12.5)
        library.toggle_favorite(source)
        library.add_to_playlist(library.create_playlist("Mix").id, source)
        ListeningLibrary(library).add_bookmark(source, 12.5, "Moment")
        TranscriptStore(library).save(source, [{"start": 1, "end": 2, "text": "A moment"}])
    backup = create_workspace_backup(libraries, tmp_path / "backup", include_originals=True)
    names, originals, files = inspect_workspace_backup(backup)
    assert names == ("first", "second")
    assert originals and files == 4
    for root in restore_workspace_backup(backup, tmp_path / "recovered"):
        library = MediaLibrary(root)
        item, = library.list_items()
        assert item.path.read_bytes() == b"original audio"
        assert library.playback_position(item.path) == 12.5
        assert library.favorite_items() == (item,)
        assert library.playlist_items(library.playlists()[0].id) == (item,)
        assert ListeningLibrary(library).bookmarks(item.path)[0]["label"] == "Moment"
        assert TranscriptStore(library).status(item.path)["status"] == "ready"

    (backup / "libraries/001/track.mp3").write_bytes(b"damaged")
    recovery = tmp_path / "damaged-recovery"
    with pytest.raises(ValueError, match="checksums"):
        restore_workspace_backup(backup, recovery)
    assert not recovery.exists()
    assert (libraries[0].root / "track.mp3").read_bytes() == b"original audio"


def test_metadata_only_retains_references_for_missing_media(tmp_path):
    library = MediaLibrary(tmp_path / "media")
    library.root.mkdir()
    path = library.root / "track.mp3"
    path.write_bytes(b"original audio")
    library.scan()
    library.toggle_favorite(path)
    backup = create_workspace_backup((library,), tmp_path / "backup")
    recovered, = restore_workspace_backup(backup, tmp_path / "recovered")
    restored = MediaLibrary(recovered)
    assert restored.list_items() == ()
    missing, = restored.missing_items()
    assert missing.media_id == library.list_items()[0].media_id
    assert restored.favorite_paths() == {Path("track.mp3").as_posix()}
