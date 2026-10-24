import io
import json
import sqlite3
import subprocess
import zipfile

from streamfetch.updates import (
    InstallationMode,
    ReleaseInfo,
    apply_update,
    cached_update_check,
    create_pre_update_backup,
    fetch_latest_release,
    is_newer_version,
    launch_downloaded_update,
)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def test_version_comparison_rejects_invalid_values():
    assert is_newer_version("1.1.0", "1.2.0") is True
    assert is_newer_version("1.2.0", "1.2.0") is False
    assert is_newer_version("1.2.0", "latest") is False


def test_fetch_and_cache_latest_release(monkeypatch, tmp_path):
    payload = {
        "tag_name": "v1.2.0",
        "name": "Daily driver",
        "html_url": "https://github.com/example/release",
        "body": "notes",
        "assets": [
            {
                "name": "StreamFetch-macos.dmg",
                "browser_download_url": "https://example.invalid/app.dmg",
            }
        ],
    }
    monkeypatch.setattr(
        "streamfetch.updates.urllib.request.urlopen",
        lambda *_args, **_kwargs: FakeResponse(json.dumps(payload).encode()),
    )

    fetched = fetch_latest_release()
    cached = cached_update_check("1.1.0", tmp_path)

    assert fetched.version == "1.2.0"
    assert fetched.assets[0]["name"].endswith(".dmg")
    assert cached == fetched
    assert (tmp_path / "update-cache.json").exists()
    assert cached_update_check("1.2.0", tmp_path) is None


def test_update_backup_contains_state_and_library_database(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    (state / "settings.json").write_text("{}", encoding="utf-8")
    (state / "download-presets.json").write_text('{"version":1,"presets":{}}')
    library = tmp_path / "media"
    database = library / ".streamfetch" / "library.db"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE media (title TEXT)")
        connection.execute("INSERT INTO media VALUES ('kept')")

    backup = create_pre_update_backup(state, library, "1.2.0")

    with zipfile.ZipFile(backup) as archive:
        assert "state/settings.json" in archive.namelist()
        assert "state/download-presets.json" in archive.namelist()
        extracted = tmp_path / "restored.db"
        extracted.write_bytes(archive.read("library/library.db"))
    with sqlite3.connect(extracted) as connection:
        assert connection.execute("SELECT title FROM media").fetchone() == ("kept",)


def test_update_backup_includes_watched_library_and_listening_state(tmp_path):
    from streamfetch.library import MediaLibrary
    from streamfetch.listening import ListeningLibrary

    state = tmp_path / "state"
    state.mkdir()
    root = tmp_path / "watched"
    library = MediaLibrary(root)
    library.scan()
    ListeningLibrary(library).save_smart("Keep my rules", minimum_rating=4)
    (state / "watched-folders.json").write_text(json.dumps([str(root)]))
    backup = create_pre_update_backup(state, None, "1.6.0")
    with zipfile.ZipFile(backup) as archive:
        assert json.loads(archive.read("state/watched-folders.json")) == [str(root)]
        snapshot = tmp_path / "snapshot.db"
        snapshot.write_bytes(archive.read("libraries/watched-0/library.db"))
    with sqlite3.connect(snapshot) as db:
        assert db.execute("SELECT name FROM smart_playlists").fetchone() == ("Keep my rules",)


def test_source_update_refuses_dirty_checkout(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    release = ReleaseInfo("1.2.0", "Release", "https://example.invalid")

    def fake_run(command, **_kwargs):
        if command[1:3] == ["status", "--porcelain"]:
            return subprocess.CompletedProcess(command, 0, stdout=" M app.py\n", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="main\n", stderr="")

    monkeypatch.setattr("streamfetch.updates.subprocess.run", fake_run)
    result = apply_update(
        release,
        state_dir=tmp_path / "state",
        project_root=tmp_path,
    )

    assert result.success is False
    assert "clean checkout" in result.message
    assert result.backup_file and result.backup_file.exists()


def test_update_stops_when_safety_backup_fails(monkeypatch, tmp_path):
    release = ReleaseInfo("1.2.0", "Release", "https://example.invalid")
    monkeypatch.setattr(
        "streamfetch.updates.create_pre_update_backup",
        lambda *_args: (_ for _ in ()).throw(OSError("disk full")),
    )

    result = apply_update(release, state_dir=tmp_path / "state")

    assert result.success is False
    assert "backup" in result.message


def test_package_update_runs_pip_after_backup(monkeypatch, tmp_path):
    release = ReleaseInfo("1.2.0", "Release", "https://example.invalid")
    commands = []
    monkeypatch.setattr(
        "streamfetch.updates.installation_mode",
        lambda *_args: InstallationMode.PACKAGE,
    )

    def fake_run(command, **_kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("streamfetch.updates.subprocess.run", fake_run)
    result = apply_update(release, state_dir=tmp_path / "state")

    assert result.success is True
    assert result.restart_required is True
    assert commands[0][1:4] == ["-m", "pip", "install"]
    assert result.backup_file and result.backup_file.exists()


def test_frozen_update_is_staged_after_backup(monkeypatch, tmp_path):
    release = ReleaseInfo("1.2.0", "Release", "https://example.invalid")
    staged = tmp_path / "StreamFetch-macos.dmg"
    staged.write_bytes(b"installer")
    monkeypatch.setattr(
        "streamfetch.updates.installation_mode",
        lambda *_args: InstallationMode.FROZEN,
    )
    monkeypatch.setattr(
        "streamfetch.updates._download_packaged_asset",
        lambda *_args: staged,
    )

    result = apply_update(release, state_dir=tmp_path / "state")

    assert result.success is True
    assert result.downloaded_file == staged
    assert result.backup_file and result.backup_file.exists()


def test_downloaded_update_can_be_opened_with_platform_handler(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr("streamfetch.updates.platform.system", lambda: "Darwin")
    monkeypatch.setattr(
        "streamfetch.updates.subprocess.Popen",
        lambda command, **kwargs: calls.append((command, kwargs)),
    )

    assert launch_downloaded_update(tmp_path / "StreamFetch.dmg") is True
    assert calls[0][0][0] == "open"
