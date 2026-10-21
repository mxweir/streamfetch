"""Durable, privacy-friendly application settings."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


def default_state_dir() -> Path:
    configured = os.environ.get("STREAMFETCH_STATE_DIR")
    return Path(configured).expanduser() if configured else Path.home() / ".streamfetch"


def default_media_dir() -> Path:
    return Path.home() / "Downloads" / "StreamFetch"


@dataclass(frozen=True)
class AppSettings:
    first_run_completed: bool = False
    language: str = "English"
    download_dir: str = ""
    check_updates: bool = True
    auto_update: bool = False

    @property
    def media_dir(self) -> Path:
        return Path(self.download_dir).expanduser() if self.download_dir else default_media_dir()


def settings_path(state_dir: Path | None = None) -> Path:
    return (state_dir or default_state_dir()) / "settings.json"


def load_settings(state_dir: Path | None = None) -> AppSettings:
    path = settings_path(state_dir)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return AppSettings()
    allowed = {field.name for field in AppSettings.__dataclass_fields__.values()}
    values = {key: value for key, value in payload.items() if key in allowed}
    try:
        return AppSettings(**values)
    except TypeError:
        return AppSettings()


def save_settings(settings: AppSettings, state_dir: Path | None = None) -> Path:
    path = settings_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(asdict(settings), indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)
    return path
