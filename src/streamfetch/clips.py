"""Create clips from existing media without touching the original."""

from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

from streamfetch.library import MediaItem, MediaLibrary


def export_local_clip(library: MediaLibrary, item: MediaItem, start: float, end: float) -> Path:
    source = item.path.resolve()
    if not source.is_relative_to(library.root) or not source.is_file():
        raise ValueError("The selected media is no longer available.")
    if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end):
        raise ValueError("The clip end must be after its start.")
    if item.duration_seconds is not None and end > item.duration_seconds + 0.01:
        raise ValueError("The clip end is beyond the original duration.")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise ValueError("FFmpeg is required to export a local clip.")
    folder = library.root / "Clips"
    if folder.is_symlink():
        raise ValueError("The clips folder cannot be a symbolic link.")
    folder.mkdir(exist_ok=True)
    is_video = item.media_type == "video"
    suffix = ".mp4" if is_video else ".m4a"
    target = folder / f"{source.stem[:80]}-{start:g}-{uuid4().hex[:10]}{suffix}"
    codecs = ["-c:v", "libx264", "-pix_fmt", "yuv420p"] if is_video else ["-vn"]
    with tempfile.TemporaryDirectory(dir=folder, prefix=".streamfetch-clip-") as tmp:
        staged = Path(tmp) / f"clip{suffix}"
        result = subprocess.run(  # noqa: S603
            [ffmpeg, "-nostdin", "-v", "error", "-ss", str(start), "-i", str(source),
             "-t", str(end - start), *codecs, "-c:a", "aac", str(staged)],
            check=False, capture_output=True, timeout=300,
        )
        if result.returncode or not staged.is_file() or not staged.stat().st_size:
            raise ValueError("FFmpeg could not export the selected clip.")
        with library._connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS local_clips (
                path TEXT PRIMARY KEY, source_id TEXT NOT NULL,
                start REAL NOT NULL, end REAL NOT NULL)""")
            db.execute("INSERT INTO local_clips VALUES (?, ?, ?, ?)", (
                library.relative_path(target), item.media_id or "", start, end,
            ))
            staged.rename(target)
    return target
