"""Atomic metadata edits with complete original-file backups."""

from __future__ import annotations

import base64
import io
import json
import shutil
import uuid
from pathlib import Path

from mutagen import File
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, TALB, TIT2, TPE1
from mutagen.mp4 import MP4, MP4Cover
from PIL import Image

from streamfetch.library import MediaLibrary

WRITABLE_FORMATS = {".mp3", ".wav", ".flac", ".ogg", ".opus", ".m4a", ".mp4"}


def validate_cover(data: bytes):
    if len(data) > 10 * 1024 * 1024:
        raise ValueError("Cover image must be smaller than 10 MB.")
    with Image.open(io.BytesIO(data)) as image:
        if image.format not in {"JPEG", "PNG"}:
            raise ValueError("Choose a JPEG or PNG cover.")
        mime = "image/jpeg" if image.format == "JPEG" else "image/png"
        image.verify()
    return mime


def write_file_metadata(library: MediaLibrary, path: Path, *, title, artist, album, cover=None):
    library.relative_path(path)
    path = path.resolve()
    if path.suffix.lower() not in WRITABLE_FORMATS or not title.strip():
        raise ValueError("Choose a supported media format and a nonempty title.")
    mime = validate_cover(cover) if cover else None
    before = path.stat()
    backup_dir = library.state_dir / "tag-backups" / uuid.uuid4().hex
    backup_dir.mkdir(parents=True)
    backup = backup_dir / path.name
    shutil.copy2(path, backup)
    (backup_dir / "restore.json").write_text(
        json.dumps(
            {
                "path": library.relative_path(path),
                "file": path.name,
            }
        )
    )
    temporary = backup_dir / f"editing{path.suffix}"
    try:
        shutil.copy2(path, temporary)
        media = File(temporary)
        if media is None:
            raise ValueError("This file cannot be tagged without re-encoding.")
        if media.tags is None:
            media.add_tags()
        if path.suffix.lower() in {".mp3", ".wav"}:
            media.tags.add(TIT2(encoding=3, text=[title]))
            media.tags.add(TPE1(encoding=3, text=[artist]))
            media.tags.add(TALB(encoding=3, text=[album]))
            if cover:
                media.tags.delall("APIC")
                media.tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=cover))
        elif isinstance(media, MP4):
            media.tags.update({"\xa9nam": [title], "\xa9ART": [artist], "\xa9alb": [album]})
            if cover:
                media.tags["covr"] = [
                    MP4Cover(
                        cover,
                        imageformat=(
                            MP4Cover.FORMAT_JPEG if mime == "image/jpeg" else MP4Cover.FORMAT_PNG
                        ),
                    )
                ]
        else:
            media.tags.update(title=[title], artist=[artist], album=[album])
            if cover:
                picture = Picture()
                picture.type, picture.mime, picture.data = 3, mime, cover
                if isinstance(media, FLAC):
                    media.clear_pictures()
                    media.add_picture(picture)
                else:
                    media["metadata_block_picture"] = [base64.b64encode(picture.write()).decode()]
        media.save()
        now = path.stat()
        if (now.st_size, now.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
            raise ValueError("The file changed during editing. Try again.")
        temporary.replace(path)
        with library._connection() as db:
            db.execute(
                "UPDATE media_items SET custom_title=NULL,custom_artist=NULL,"
                "custom_album=NULL WHERE path=?",
                (library.relative_path(path),),
            )
        library.scan()
    finally:
        temporary.unlink(missing_ok=True)
    return backup


def file_backups(library: MediaLibrary, path: Path):
    relative = library.relative_path(path)
    result = []
    for manifest in (library.state_dir / "tag-backups").glob("*/restore.json"):
        data = json.loads(manifest.read_text())
        backup = manifest.parent / data["file"]
        if (
            data["path"] == relative
            and backup.is_file()
            and backup.resolve().parent == manifest.parent.resolve()
        ):
            result.append(backup)
    return sorted(
        result, key=lambda value: (value.parent / "restore.json").stat().st_mtime, reverse=True
    )


def restore_file_backup(library: MediaLibrary, path: Path, backup: Path):
    if backup not in file_backups(library, path):
        raise ValueError("This backup does not belong to the selected file.")
    temporary = library.state_dir / f"{uuid.uuid4().hex}.restoring{path.suffix}"
    try:
        shutil.copy2(backup, temporary)
        temporary.replace(path)
        with library._connection() as db:
            db.execute(
                "UPDATE media_items SET custom_title=NULL,custom_artist=NULL,custom_album=NULL "
                "WHERE path=?",
                (library.relative_path(path),),
            )
        library.scan()
    finally:
        temporary.unlink(missing_ok=True)
