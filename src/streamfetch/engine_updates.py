"""Independent, atomic downloader-engine updates, including frozen desktop builds.

Only official PyPI pure-Python wheels are accepted. Never replace imported modules:
an update found after the engine was loaded is activated on the next app restart.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import io
import json
import logging
import shutil
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from streamfetch.network import verified_context
from streamfetch.settings import default_state_dir

CHECK_INTERVAL = 6 * 60 * 60
RETRY_INTERVAL = 15 * 60
MAX_WHEEL_BYTES = 20 * 1024 * 1024
_lock = threading.RLock()
_last_attempt = 0.0
_status = None
_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EngineStatus:
    version: str
    pending_version: str | None = None
    error: str | None = None
    checked_at: float = 0


def _version() -> str:
    loaded = sys.modules.get("yt_dlp.version")
    if loaded is not None:
        return loaded.__version__
    try:
        return importlib.metadata.version("yt-dlp")
    except importlib.metadata.PackageNotFoundError:
        return "0"


def engine_status() -> EngineStatus:
    return _status or EngineStatus(_version())


def _json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path: Path, data: dict) -> None:
    # Unique temporary names also tolerate multiple desktop instances.
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            json.dump(data, output)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _fetch(url: str, *, artifact: bool = False) -> bytes:
    host = "files.pythonhosted.org" if artifact else "pypi.org"
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != host or parsed.username:
        raise ValueError("Unexpected update origin")
    request = urllib.request.Request(url, headers={"User-Agent": "StreamFetch-engine-updater"})
    with urllib.request.urlopen(request, timeout=5, context=verified_context()) as response:  # noqa: S310
        if urlparse(response.url).hostname != host or not response.url.startswith("https://"):
            raise ValueError("Unexpected update redirect")
        data = response.read(MAX_WHEEL_BYTES + 1)
    if len(data) > MAX_WHEEL_BYTES:
        raise ValueError("Update exceeds size limit")
    return data


def _release(package: str, version: str = "") -> dict:
    suffix = f"/{Version(version)}" if version else ""
    data = json.loads(_fetch(f"https://pypi.org/pypi/{package}{suffix}/json"))
    info = data["info"]
    release_version = Version(info["version"])
    if release_version.is_prerelease or release_version.is_devrelease:
        raise ValueError("Only stable engine releases are supported")
    python = ".".join(map(str, sys.version_info[:3]))
    if python not in SpecifierSet(info.get("requires_python") or ""):
        raise ValueError("This engine needs a newer Python/StreamFetch version")
    return data


def _install_wheel(release: dict, package: str, destination: Path) -> None:
    version = str(Version(release["info"]["version"]))
    prefix = package.replace("-", "_")
    filename = f"{prefix}-{version}-py3-none-any.whl"
    artifact = next(
        (item for item in release["urls"] if item["filename"] == filename
         and not item.get("yanked")),
        None,
    )
    if artifact is None:
        raise ValueError("No compatible pure-Python engine wheel")
    data = _fetch(artifact["url"], artifact=True)
    if hashlib.sha256(data).hexdigest() != artifact["digests"]["sha256"]:
        raise ValueError("Engine checksum mismatch")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = archive.infolist()
        if sum(item.file_size for item in members) > 80 * 1024 * 1024:
            raise ValueError("Unpacked engine exceeds size limit")
        for item in members:
            path = PurePosixPath(item.filename)
            if (path.is_absolute() or ".." in path.parts or "\\" in item.filename
                    or not path.parts or path.parts[0] not in
                    {prefix, f"{prefix}-{version}.dist-info", f"{prefix}-{version}.data"}
                    or (item.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError("Unsafe engine archive member")
        # Console scripts/manpages in .data are irrelevant to our Python API and
        # must not be installed into the application or any system script folder.
        archive.extractall(destination, members=[item for item in members
                           if PurePosixPath(item.filename).parts[0] != f"{prefix}-{version}.data"])


def _stage(release: dict, root: Path) -> Path:
    version = str(Version(release["info"]["version"]))
    # EJS must match the engine's declared requirement, not an arbitrary latest version.
    requirements = [Requirement(raw) for raw in release["info"].get("requires_dist") or ()]
    ejs = next(req for req in requirements if req.name == "yt-dlp-ejs"
               and (not req.marker or req.marker.evaluate({"extra": "default"})))
    pinned = next(value.version for value in ejs.specifier if value.operator == "==")
    ejs_release = _release("yt-dlp-ejs", pinned)
    certifi_release = _release("certifi")
    for requirement in requirements:
        if requirement.marker and not requirement.marker.evaluate({"extra": "default"}):
            continue
        if requirement.name in {"yt-dlp-ejs", "certifi"}:
            candidate = ejs_release if requirement.name == "yt-dlp-ejs" else certifi_release
            if candidate["info"]["version"] not in requirement.specifier:
                raise ValueError("Incompatible engine dependency")
        elif requirement.marker is None or "extra" not in str(requirement.marker):
            # Other default extras are optional; new mandatory dependencies are not.
            if importlib.metadata.version(requirement.name) not in requirement.specifier:
                raise ValueError("Engine dependencies need a StreamFetch update")
    with tempfile.TemporaryDirectory(prefix="staging-", dir=root) as temporary:
        stage = Path(temporary)
        for package, candidate in (("yt-dlp", release), ("yt-dlp-ejs", ejs_release),
                                   ("certifi", certifi_release)):
            _install_wheel(candidate, package, stage)
        # Unique immutable bundles: concurrent processes never overwrite an active bundle.
        bundle = root / f"engine-{version}-{stage.name}"
        stage.rename(bundle)
    return bundle


def _activate(bundle: Path) -> None:
    if "yt_dlp" in sys.modules:
        return
    sys.path.insert(0, str(bundle))
    importlib.invalidate_caches()
    try:
        importlib.import_module("yt_dlp")
        importlib.import_module("yt_dlp.version")
    except Exception:
        sys.path.remove(str(bundle))
        for name in tuple(sys.modules):
            if name == "yt_dlp" or name.startswith("yt_dlp."):
                del sys.modules[name]
        raise


def ensure_engine(*, force: bool = False, state_dir: Path | None = None) -> EngineStatus:
    """Check at startup/use, at most every six hours; offline failures keep the old engine."""
    global _last_attempt, _status
    with _lock:
        now = time.time()
        interval = RETRY_INTERVAL if _status and _status.error else CHECK_INTERVAL
        if not force and _status and now - _last_attempt < interval:
            return _status
        _last_attempt = now
        root = (state_dir or default_state_dir()) / "engines"
        cache = {}
        error = None
        try:
            root.mkdir(parents=True, exist_ok=True)
            cache = _json(root / "current.json")
            try:
                Version(cache.get("version", "0"))
                float(cache.get("checked_at", 0))
            except (ValueError, TypeError):
                cache = {}
            if cache.get("version"):
                name = cache.get("bundle")
                cached_bundle = root / name if isinstance(name, str) else root
                if (cached_bundle.parent != root
                        or not (cached_bundle / "yt_dlp/__init__.py").is_file()):
                    cache = {}  # Re-download a missing/corrupt cache, never claim it is current.
            if force or now - float(cache.get("checked_at", 0)) >= CHECK_INTERVAL:
                release = _release("yt-dlp")
                candidate = release["info"]["version"]
                known = max(Version(_version()), Version(cache.get("version", "0")))
                if Version(candidate) > known:
                    bundle = _stage(release, root)
                    cache.update(version=candidate, bundle=bundle.name)
                cache["checked_at"] = now
                _write_json(root / "current.json", cache)
        except Exception:
            _logger.warning("Downloader engine update failed; preserving existing engine",
                            exc_info=True)
            error = "The engine update could not be completed. The existing version is still used."
        bundle_name = cache.get("bundle", "")
        # Reject traversal in the local pointer; missing/incomplete caches fall back safely.
        bundle = root / bundle_name if isinstance(bundle_name, str) else root
        if (bundle_name and bundle.parent == root and bundle.is_dir()
                and Version(cache.get("version", "0")) >= Version(_version())):
            try:
                _activate(bundle)
            except Exception:
                _logger.warning("Updated engine activation failed; preserving existing engine",
                                exc_info=True)
                error = ("The updated engine could not be loaded. "
                         "The existing version is still used.")
        version = _version()
        pending = cache.get("version")
        if not pending or Version(pending) <= Version(version):
            pending = None
        _status = EngineStatus(version, pending, error, float(cache.get("checked_at", 0)))
        return _status


def javascript_options() -> dict:
    """Explicitly enable installed supported runtimes (Node is not enabled by default)."""
    runtimes = {}
    for name, command in (("deno", "deno"), ("node", "node"), ("quickjs", "qjs")):
        executable = shutil.which(command)
        if executable:
            runtimes[name] = {"path": executable}
    return {"js_runtimes": runtimes} if runtimes else {}
