import hashlib
import io
import json
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from streamfetch import engine_updates as engine


def wheel(package, version, *, unsafe=False):
    prefix = package.replace("-", "_")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(f"{prefix}/__init__.py", "")
        archive.writestr(f"{prefix}-{version}.data/scripts/tool", "not installed")
        if unsafe:
            archive.writestr("../escape.py", "bad")
    content = output.getvalue()
    return content, {
        "info": {
            "version": version,
            "requires_python": ">=3.11",
            "requires_dist": ['yt-dlp-ejs==0.8.0; extra == "default"'],
        },
        "urls": [{
            "filename": f"{prefix}-{version}-py3-none-any.whl",
            "url": f"https://files.pythonhosted.org/{package}.whl",
            "digests": {"sha256": hashlib.sha256(content).hexdigest()},
        }],
    }


@pytest.fixture
def updater(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "_status", None)
    monkeypatch.setattr(engine, "_last_attempt", 0)
    active = {"version": "2026.8.19", "loaded": False}
    calls = []
    payloads = {}
    for package, version in (("yt-dlp", "2026.10.21"), ("yt-dlp-ejs", "0.8.0"),
                             ("certifi", "2026.10.19")):
        content, release = wheel(package, version)
        suffix = "/0.8.0" if package == "yt-dlp-ejs" else ""
        payloads[f"https://pypi.org/pypi/{package}{suffix}/json"] = json.dumps(release).encode()
        payloads[f"https://files.pythonhosted.org/{package}.whl"] = content

    def fetch(url, **_kwargs):
        calls.append(url)
        return payloads[url]

    def activate(bundle):
        if not active["loaded"]:
            assert (bundle / "yt_dlp/__init__.py").is_file()
            assert (bundle / "yt_dlp_ejs/__init__.py").is_file()
            active.update(version="2026.10.21", loaded=True)

    monkeypatch.setattr(engine, "_fetch", fetch)
    monkeypatch.setattr(engine, "_version", lambda: active["version"])
    monkeypatch.setattr(engine, "_activate", activate)
    return SimpleNamespace(active=active, calls=calls, payloads=payloads, root=tmp_path)


def test_first_check_installs_then_activates_without_pip(updater, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    status = engine.ensure_engine(state_dir=updater.root)
    assert status.version == "2026.10.21"
    assert not status.error and not status.pending_version
    pointer = json.loads((updater.root / "engines/current.json").read_text())
    assert (updater.root / "engines" / pointer["bundle"] / "certifi").is_dir()
    assert not list((updater.root / "engines" / pointer["bundle"]).glob("*.data"))
    engine.ensure_engine(state_dir=updater.root)
    assert len(updater.calls) == 6


def test_loaded_engine_is_not_replaced_and_update_survives_restart(updater, monkeypatch):
    updater.active["loaded"] = True
    status = engine.ensure_engine(state_dir=updater.root)
    assert status.version == "2026.8.19"
    assert status.pending_version == "2026.10.21"
    updater.active["loaded"] = False
    monkeypatch.setattr(engine, "_status", None)
    status = engine.ensure_engine(state_dir=updater.root)
    assert status.version == "2026.10.21"
    assert len(updater.calls) == 6  # persisted six-hour cache, no second network check


def test_network_failure_keeps_current_engine_and_retries(updater, monkeypatch):
    def offline(*_args, **_kwargs):
        raise OSError("offline")

    monkeypatch.setattr(engine, "_fetch", offline)
    status = engine.ensure_engine(state_dir=updater.root)
    assert status.error and status.version == "2026.8.19"
    assert not (updater.root / "engines/current.json").exists()
    assert engine.ensure_engine(state_dir=updater.root) is status
    monkeypatch.setattr(engine.time, "time", lambda: status.checked_at + 10**12)
    assert engine.ensure_engine(state_dir=updater.root).error


def test_offline_start_uses_previously_downloaded_engine(updater, monkeypatch):
    engine.ensure_engine(state_dir=updater.root)
    updater.active.update(version="2026.8.19", loaded=False)
    monkeypatch.setattr(engine, "_status", None)

    def offline(*_args, **_kwargs):
        raise OSError("offline")

    monkeypatch.setattr(engine, "_fetch", offline)
    status = engine.ensure_engine(state_dir=updater.root, force=True)
    assert status.version == "2026.10.21" and status.error


@pytest.mark.parametrize("problem", ["checksum", "traversal", "python", "yanked"])
def test_rejects_unsafe_or_incompatible_update(updater, problem):
    url = "https://pypi.org/pypi/yt-dlp/json"
    release = json.loads(updater.payloads[url])
    if problem == "checksum":
        release["urls"][0]["digests"]["sha256"] = "0" * 64
    elif problem == "traversal":
        content, release = wheel("yt-dlp", "2026.10.21", unsafe=True)
        updater.payloads[release["urls"][0]["url"]] = content
    elif problem == "python":
        release["info"]["requires_python"] = ">=99"
    else:
        release["urls"][0]["yanked"] = True
    updater.payloads[url] = json.dumps(release).encode()
    status = engine.ensure_engine(state_dir=updater.root)
    assert status.error and status.version == "2026.8.19"
    assert not (updater.root / "engines/current.json").exists()
    assert not (updater.root / "engines/escape.py").exists()


def test_concurrent_checks_only_install_once(updater):
    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = tuple(pool.map(lambda _: engine.ensure_engine(state_dir=updater.root), range(4)))
    assert all(status.version == "2026.10.21" for status in statuses)
    assert len(updater.calls) == 6


def test_corrupt_cache_recovers(updater):
    root = updater.root / "engines"
    root.mkdir()
    (root / "current.json").write_text('{"version": "invalid"}')
    assert not engine.ensure_engine(state_dir=updater.root).error


@pytest.mark.parametrize("bundle", ["missing", "../outside"])
def test_missing_or_unsafe_cached_bundle_is_downloaded_again(updater, bundle):
    root = updater.root / "engines"
    root.mkdir()
    (root / "current.json").write_text(json.dumps({
        "version": "2026.10.21", "bundle": bundle, "checked_at": engine.time.time(),
    }))
    status = engine.ensure_engine(state_dir=updater.root)
    assert not status.error and status.version == "2026.10.21"
    assert len(updater.calls) == 6


def test_activate_never_hot_swaps_imported_engine(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace())
    before = list(sys.path)
    engine._activate(tmp_path)
    assert sys.path == before


def test_activation_failure_restores_import_path(monkeypatch, tmp_path):
    monkeypatch.delitem(sys.modules, "yt_dlp", raising=False)
    before = list(sys.path)

    def broken_import(name):
        if name == "yt_dlp":
            monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace())
            return sys.modules[name]
        raise ImportError("incompatible engine")

    monkeypatch.setattr(engine.importlib, "import_module", broken_import)
    with pytest.raises(ImportError):
        engine._activate(tmp_path)
    assert sys.path == before
    assert "yt_dlp" not in sys.modules


def test_downloader_checks_engine_before_import(monkeypatch):
    from streamfetch.downloader import _import_yt_dlp

    calls = []
    fake = SimpleNamespace()
    monkeypatch.setattr("streamfetch.downloader.ensure_engine", lambda: calls.append("checked"))
    monkeypatch.setitem(sys.modules, "yt_dlp", fake)
    assert _import_yt_dlp() is fake
    assert calls == ["checked"]


def test_download_and_preview_explicitly_enable_node(monkeypatch, tmp_path):
    from streamfetch.config import build_ydl_options
    from streamfetch.downloader import Downloader
    from streamfetch.models import DownloadRequest, MediaType

    monkeypatch.setattr(engine.shutil, "which", lambda command: "/tools/node"
                        if command == "node" else None)
    options = engine.javascript_options()
    assert options == {"js_runtimes": {"node": {"path": "/tools/node"}}}
    request = DownloadRequest(urls=("https://youtu.be/example",), output_dir=tmp_path,
                              media_type=MediaType.VIDEO, container="mp4", quality="360p")
    assert build_ydl_options(request)["js_runtimes"] == options["js_runtimes"]
    captured = {}

    class FakeYDL:
        def __init__(self, value):
            captured.update(value)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def extract_info(self, *_args, **_kwargs):
            return {"title": "Test"}

    monkeypatch.setattr("streamfetch.downloader._import_yt_dlp",
                        lambda: SimpleNamespace(YoutubeDL=FakeYDL))
    Downloader().inspect(request.urls[0])
    assert captured["js_runtimes"] == options["js_runtimes"]
