"""Startup health checks and privacy-safe diagnostics."""

from __future__ import annotations

import io
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import zipfile
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from streamfetch import __version__


class HealthStatus(StrEnum):
    READY = "ready"
    WARNING = "warning"
    MISSING = "missing"


@dataclass(frozen=True)
class HealthCheck:
    key: str
    name: str
    status: HealthStatus
    detail: str
    guidance: str = ""
    required: bool = False


def dependency_guidance(system: str | None = None) -> dict[str, str]:
    current = (system or platform.system()).lower()
    if current == "darwin":
        return {
            "ffmpeg": "Install Homebrew, then run: brew install ffmpeg",
            "javascript": "Install Node.js with: brew install node",
        }
    if current == "windows":
        return {
            "ffmpeg": "Open Terminal as your user and run: winget install Gyan.FFmpeg",
            "javascript": "Install Node.js with: winget install OpenJS.NodeJS.LTS",
        }
    return {
        "ffmpeg": "On Ubuntu/Debian run: sudo apt update && sudo apt install ffmpeg",
        "javascript": "On Ubuntu/Debian run: sudo apt install nodejs",
    }


def _command_version(command: str, *arguments: str) -> str | None:
    executable = shutil.which(command)
    if not executable:
        return None
    try:
        result = subprocess.run(
            [executable, *arguments],
            capture_output=True,
            check=False,
            text=True,
            timeout=4,
        )
    except (OSError, subprocess.SubprocessError):
        return "installed"
    first_line = (result.stdout or result.stderr).splitlines()
    return first_line[0].strip() if first_line else "installed"


def run_health_checks(output_dir: Path) -> tuple[HealthCheck, ...]:
    guidance = dependency_guidance()
    ffmpeg = _command_version("ffmpeg", "-version")
    ffmpeg_detail = " ".join(ffmpeg.split()[:3]) if ffmpeg else None
    runtimes = [
        (name, _command_version(name, "--version"))
        for name in ("node", "deno", "bun", "qjs")
    ]
    runtime = next(((name, version) for name, version in runtimes if version), None)
    try:
        import yt_dlp

        ytdlp_version = getattr(getattr(yt_dlp, "version", None), "__version__", "installed")
    except ImportError:
        ytdlp_version = None

    target = output_dir.expanduser()
    existing = target
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    writable = existing.exists() and os.access(existing, os.W_OK)
    try:
        free_bytes = shutil.disk_usage(existing).free if existing.exists() else 0
    except OSError:
        free_bytes = 0

    return (
        HealthCheck(
            "ffmpeg",
            "FFmpeg",
            HealthStatus.READY if ffmpeg else HealthStatus.MISSING,
            ffmpeg_detail or "Required for media conversion and merging.",
            "" if ffmpeg else guidance["ffmpeg"],
            required=True,
        ),
        HealthCheck(
            "yt_dlp",
            "yt-dlp",
            HealthStatus.READY if ytdlp_version else HealthStatus.MISSING,
            f"Version {ytdlp_version}" if ytdlp_version else "Downloader engine is unavailable.",
            "Reinstall StreamFetch to restore yt-dlp.",
            required=True,
        ),
        HealthCheck(
            "javascript",
            "JavaScript runtime",
            HealthStatus.READY if runtime else HealthStatus.WARNING,
            (
                f"{runtime[0]} · {runtime[1]}"
                if runtime
                else "Recommended for reliable YouTube extraction."
            ),
            "" if runtime else guidance["javascript"],
        ),
        HealthCheck(
            "storage",
            "Media folder",
            HealthStatus.READY if writable else HealthStatus.MISSING,
            (
                f"Writable · {free_bytes / (1024**3):.1f} GB available"
                if writable
                else "The selected folder or its parent is not writable."
            ),
            "Choose a writable folder with enough free space.",
            required=True,
        ),
    )


def diagnostics_archive(
    checks: tuple[HealthCheck, ...],
    *,
    language: str,
    jobs: tuple[Any, ...] = (),
) -> bytes:
    """Build a diagnostic ZIP without URLs, cookies, or absolute user paths."""

    job_summary: dict[str, int] = {}
    for job in jobs:
        status = str(getattr(job, "status", "unknown"))
        job_summary[status] = job_summary.get(status, 0) + 1
    payload = {
        "generated_at": int(time.time()),
        "streamfetch_version": __version__,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "executable_mode": "frozen" if getattr(sys, "frozen", False) else "python",
        "language": language,
        "checks": [
            {
                **asdict(check),
                "status": check.status.value,
                "detail": _redact_home(check.detail),
            }
            for check in checks
        ],
        "job_counts": job_summary,
        "privacy": "No URLs, cookies, media filenames, or absolute media paths are included.",
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("streamfetch-diagnostics.json", json.dumps(payload, indent=2))
        archive.writestr(
            "README.txt",
            "StreamFetch diagnostics. Review the JSON before sharing it.\n",
        )
    return buffer.getvalue()


def _redact_home(value: str) -> str:
    home = str(Path.home())
    return value.replace(home, "~") if home else value
