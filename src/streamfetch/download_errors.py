"""Actionable, conservative error classification; never retry permanent failures blindly."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DownloadFailure:
    code: str
    title: str
    guidance: str
    retryable: bool = False


def classify_download_error(error: str) -> DownloadFailure:
    text = error.lower()
    rules = (
        (("no space left", "disk full", "errno 28"), "storage", "Not enough disk space.",
         "Free space or choose a different output folder, then retry.", False),
        (("permission denied", "access is denied", "errno 13"), "permission",
         "The output folder is not writable.",
         "Choose a folder you can write to. Do not run the app as administrator.", False),
        (("ffmpeg not found", "ffmpeg is not installed", "ffprobe and ffmpeg not found",
          "ffprobe not found"), "ffmpeg", "FFmpeg is missing.",
         "Open System for FFmpeg installation instructions, then restart StreamFetch.", False),
        (("private video", "video is private", "members-only", "premium-only"), "private",
         "This item requires access permission.",
         "Use your own authorised browser session under Advanced → Use cookies from browser. "
         "No access controls are bypassed.", False),
        (("sign in", "login required", "log in", "confirm your age", "age-restricted",
          "use --cookies"), "authentication", "The source requires authentication.",
         "If you have access, explicitly select your signed-in browser under Advanced. "
         "Cookies are never read without your selection.", False),
        (("not available in your country", "geo-restricted", "not available in your region"),
         "region", "This item is not available in your region.",
         "Choose a source available to you. StreamFetch does not bypass regional restrictions.",
         False),
        (("video unavailable", "video is unavailable", "has been removed", "video has been deleted",
          "does not exist",
          "http error 404", "unsupported url"), "unavailable", "This source is unavailable.",
         "Check the link and whether the item is still publicly available.", False),
        (("requested format is not available", "no video formats found"), "format",
         "The requested format is unavailable.",
         "Try best quality or a different container. Check engine updates in System.", False),
        (("http error 429", "too many requests"), "rate_limit", "The source is rate-limiting.",
         "Wait before retrying and reduce concurrent fragments. No automatic rapid retries.",
         False),
        (("http error 403", "http error 401", "signature", "challenge", "nsig"), "extractor",
         "The source rejected extraction.",
         "Check engine updates and the JavaScript runtime in System. Restart if an engine "
         "update is ready, then retry. This can also be a source-side restriction.", False),
        (("timed out", "timeout", "connection reset", "connection refused", "temporary", "network",
          "name resolution", "http error 500", "http error 502", "http error 503",
          "http error 504"), "network", "A temporary connection problem occurred.",
         "Check your connection. StreamFetch retries temporary failures automatically.", True),
    )
    for patterns, code, title, guidance, retryable in rules:
        if any(pattern in text for pattern in patterns):
            return DownloadFailure(code, title, guidance, retryable)
    return DownloadFailure(
        "unknown", "The download could not be completed.",
        "Review the technical details below. Check System health before retrying.",
    )


def safe_error_detail(error: str) -> str:
    text = re.sub(r"\x1b\[[0-9;]*m", "", error)
    text = text.replace(str(Path.home()), "<home>")
    text = re.sub(r"https?://\S+", "<source URL>", text)
    text = re.sub(r"(?im)\b(authorization|cookie|token|password)\s*[:=]\s*[^\r\n]*",
                  r"\1=<redacted>", text)
    return text[-4000:]
