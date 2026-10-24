"""Durable, allowlisted download presets without paths, URLs or credentials."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from streamfetch.settings import default_state_dir

_lock = threading.RLock()
CHOICES = {
    "media_type": {"video", "audio"},
    "video_format": {"mp4", "mkv", "webm"},
    "audio_format": {"mp3", "m4a", "opus", "flac", "wav"},
    "video_quality": {"best", "2160p", "1440p", "1080p", "720p", "480p", "360p"},
    "audio_quality": {"0", "320K", "256K", "192K", "128K"},
    "conflict_policy": {"resume", "skip", "overwrite"},
}
BOOL_KEYS = {
    "allow_playlists", "use_limit", "embed_metadata", "embed_thumbnail",
    "embed_subtitles", "use_rate_limit", "use_clip_range", "split_chapters",
}
RANGES = {
    "max_items": (1, 10_000), "concurrent_fragments": (1, 16),
    "rate_limit_mbps": (0.1, 1000), "clip_start": (0, 10**8), "clip_end": (0.1, 10**8),
}


def preset_options(values: dict) -> dict:
    """Validate a snapshot, silently excluding unapproved/sensitive fields."""
    result = {}
    for key, allowed in CHOICES.items():
        if key in values:
            if not isinstance(values[key], str) or values[key] not in allowed:
                raise ValueError("Invalid preset option")
            result[key] = values[key]
    for key in BOOL_KEYS:
        if key in values:
            if type(values[key]) is not bool:
                raise ValueError("Invalid preset switch")
            result[key] = values[key]
    for key, (minimum, maximum) in RANGES.items():
        if key in values:
            value = values[key]
            if type(value) not in (int, float) or not minimum <= value <= maximum:
                raise ValueError("Invalid preset range")
            if key in {"max_items", "concurrent_fragments"} and type(value) is not int:
                raise ValueError("Invalid preset count")
            result[key] = value
    if "subtitle_languages" in values:
        languages = values["subtitle_languages"]
        if not isinstance(languages, str) or len(languages) > 120:
            raise ValueError("Invalid subtitle languages")
        result["subtitle_languages"] = languages
    if "sponsorblock_remove" in values:
        categories = values["sponsorblock_remove"]
        allowed = {"sponsor", "intro", "outro", "selfpromo", "interaction", "filler"}
        if not isinstance(categories, (list, tuple)) or any(
            not isinstance(value, str) or value not in allowed for value in categories
        ):
            raise ValueError("Invalid segment categories")
        result["sponsorblock_remove"] = list(dict.fromkeys(categories))
    media = result.get("media_type")
    if media not in {"audio", "video"} or any(
        key not in result for key in (f"{media}_format", f"{media}_quality")
    ):
        raise ValueError("Preset needs media type, format and quality")
    if result.get("use_clip_range") and result.get("clip_end", 0) <= result.get("clip_start", 0):
        raise ValueError("The clip end must be after its start.")
    return result


class PresetStore:
    def __init__(self, state_dir: Path | None = None):
        self.path = (state_dir or default_state_dir()) / "download-presets.json"

    def load(self) -> dict[str, dict]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            records = payload["presets"]
            if payload.get("version") != 1 or not isinstance(records, dict):
                return {}
        except (OSError, ValueError, KeyError, TypeError):
            return {}
        valid = {}
        for name, options in records.items():
            try:
                if not isinstance(name, str) or not 1 <= len(name) <= 48:
                    continue
                valid[name] = preset_options(options)
            except (ValueError, TypeError):
                continue
        return valid

    def save(self, name: str, values: dict) -> None:
        name = name.strip()
        if not 1 <= len(name) <= 48 or any(ord(char) < 32 for char in name):
            raise ValueError("Use a preset name with 1–48 characters.")
        options = preset_options(values)
        with _lock:
            records = self.load()
            if name not in records and len(records) >= 30:
                raise ValueError("You can save up to 30 presets.")
            records[name] = options
            self._write(records)

    def delete(self, name: str) -> None:
        with _lock:
            records = self.load()
            records.pop(name, None)
            self._write(records)

    def _write(self, records: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps({"version": 1, "presets": records}, indent=2),
                             encoding="utf-8")
        temporary.replace(self.path)
