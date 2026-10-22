"""Library tools for listening, local search, metadata and private home sharing."""

from __future__ import annotations

import subprocess
from pathlib import Path
from uuid import uuid4

import streamlit as st

from streamfetch.file_metadata import file_backups, restore_file_backup, write_file_metadata
from streamfetch.listening import FolderWatcher, ListeningLibrary, read_chapters
from streamfetch.settings import default_state_dir
from streamfetch.sharing import SharingService
from streamfetch.transcripts import (
    TranscriptionService,
    TranscriptStore,
    export_transcript,
    parse_subtitles,
)


@st.cache_resource
def folder_watcher(state_dir):
    return FolderWatcher(Path(state_dir))


@st.cache_resource
def speech_service(state_dir):
    return TranscriptionService(Path(state_dir))


@st.cache_resource
def sharing_service():
    return SharingService()


def seek_to(library, item, seconds):
    library.set_current_item(item.path)
    library.set_playback_position(item.path, seconds)
    library.record_play(item.path)
    st.session_state.player_seek_request = dict(
        nonce=uuid4().hex, seconds=seconds, path=str(item.path)
    )
    st.session_state.player_autoplay = True
    st.rerun()


def timestamp(seconds):
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"


def render_studio(library, t, render_grid):
    st.markdown(f"## {t('Your library, elevated.')}")
    st.caption(t("Listening tools, local speech search and private home sharing."))
    section = st.segmented_control(
        t("Studio tools"),
        ["Smart playlists", "Listening", "Folders", "Speech search", "File tags", "Home player"],
        default="Smart playlists",
        format_func=t,
        key="studio_section",
    )
    try:
        if section == "Smart playlists":
            render_smart(library, t, render_grid)
        elif section == "Listening":
            render_listening(library, t)
        elif section == "Folders":
            render_folders(library, t)
        elif section == "Speech search":
            render_speech(library, t)
        elif section == "File tags":
            render_file_tags(library, t)
        elif section == "Home player":
            render_sharing(library, t)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        st.error(str(exc))


def choose_item(library, key, t):
    items = library.list_items(limit=10000)
    if not items:
        st.info(t("Add some media to your library first."))
        return None
    return st.selectbox(
        t("Media item"),
        items,
        format_func=lambda item: f"{item.title} · {item.artist} · {item.path.name}",
        key=key,
    )


def render_smart(library, t, render_grid):
    store = ListeningLibrary(library)
    with st.expander(t("Create or update a smart playlist")), st.form("smart_rules"):
        name = st.text_input(t("Playlist name"), max_chars=80)
        a, b, c = st.columns(3)
        rating = a.slider(t("Minimum rating"), 0, 5, 0)
        tag = b.text_input(t("Required tag"), max_chars=40)
        media_type = c.selectbox(t("Media type"), ["all", "audio", "video"])
        a, b = st.columns(2)
        minutes = a.number_input(t("Maximum minutes (0 = any)"), 0, 14400, 0)
        days = b.number_input(t("Added in last days (0 = any)"), 0, 36500, 0)
        unplayed = st.checkbox(t("Only unplayed items"))
        if st.form_submit_button(t("Save smart playlist"), type="primary"):
            store.save_smart(
                name,
                tag=tag,
                minimum_rating=rating,
                max_minutes=minutes,
                added_days=days,
                unplayed=unplayed,
                media_type=media_type,
            )
            st.rerun()
    playlists = store.smart_playlists()
    if not playlists:
        st.info(t("Save a rule once. Matching tracks update automatically."))
        return
    selected = st.selectbox(t("Smart playlist"), playlists, format_func=lambda row: row["name"])
    items = store.smart_items(selected["id"])
    st.caption(t("{count} matching items · Rules are applied live.", count=len(items)))
    a, b = st.columns(2)
    if a.button(t("Queue all matches"), disabled=not items):
        for item in items:
            library.enqueue(item.path)
        st.rerun()
    with b.popover(t("Remove smart playlist")):
        st.caption(t("This removes the rules, not your media files."))
        if st.button(t("Confirm removal"), key="delete_smart"):
            store.delete_smart(selected["id"])
            st.rerun()
    render_grid(library, items, len(items), key_prefix="smart")


def render_listening(library, t):
    st.caption(t("Playback speed, sleep timer and quick bookmarks live in the floating player."))
    item = choose_item(library, "listen_item", t)
    if not item:
        return
    store = ListeningLibrary(library)
    a, b = st.columns(2)
    seconds = a.number_input(
        t("Position (seconds)"), min_value=0.0, value=library.playback_position(item.path), step=1.0
    )
    label = b.text_input(t("Bookmark label"), max_chars=200)
    if st.button(t("Save bookmark"), disabled=not label.strip()):
        store.add_bookmark(item.path, seconds, label)
        st.rerun()
    st.markdown(f"### {t('Bookmarks')}")
    bookmarks = store.bookmarks(item.path)
    for mark in bookmarks:
        a, b = st.columns([5, 1])
        if a.button(
            f"▶ {timestamp(mark['seconds'])} · {mark['label']}",
            key=f"bookmark_{mark['id']}",
            width="stretch",
        ):
            seek_to(library, item, mark["seconds"])
        if b.button("×", key=f"remove_bookmark_{mark['id']}", help=t("Remove bookmark")):
            store.delete_bookmark(mark["id"])
            st.rerun()
    if not bookmarks:
        st.caption(t("Save a moment worth returning to."))
    st.markdown(f"### {t('Chapters')}")
    chapters = cached_chapters(str(item.path), item.path.stat().st_mtime_ns)
    for index, chapter in enumerate(chapters):
        if st.button(
            f"▶ {timestamp(chapter['seconds'])} · {chapter['title']}", key=f"chapter_{index}"
        ):
            seek_to(library, item, chapter["seconds"])
    if not chapters:
        st.caption(t("No embedded chapters found. FFprobe is required to read chapters."))


@st.cache_data(show_spinner=False)
def cached_chapters(path, modified):
    return read_chapters(Path(path))


def render_folders(library, t):
    watcher = folder_watcher(str(default_state_dir()))
    st.caption(
        t(
            "Index existing folders in place every 30 seconds while StreamFetch runs. "
            "Files are not copied. Each folder keeps its own library index."
        )
    )
    value = st.text_input(t("Existing media folder"), placeholder=str(library.root))
    if st.button(t("Watch folder"), disabled=not value.strip(), type="primary"):
        watcher.add(value)
        watcher.scan()
        st.rerun()
    if st.button(t("Scan watched folders now")):
        watcher.scan()
    for root in watcher.roots():
        with st.container(border=True):
            st.write(root)
            status = watcher.status.get(root, {})
            if status.get("error"):
                st.warning(status["error"])
            else:
                st.caption(t("{count} indexed items", count=status.get("total", "—")))
            a, b = st.columns(2)
            if a.button(t("Open library"), key=f"open_{root}"):
                st.session_state.pending_library_root = root
                st.rerun()
            if b.button(t("Stop watching"), key=f"unwatch_{root}"):
                watcher.remove(root)
                st.rerun()


def render_speech(library, t):
    store = TranscriptStore(library)
    service = speech_service(str(default_state_dir()))
    service.register(store)
    query = st.text_input(t("Search spoken words"), placeholder=t("Find a phrase in your library…"))
    if query:
        results = store.search(query)
        st.caption(t("{count} timestamped results", count=len(results)))
        for row in results:
            item = library.item_for_path(row["path"])
            if item and st.button(
                f"▶ {item.title} · {timestamp(row['start'])} — {row['text']}",
                key=f"transcript_hit_{row['id']}",
                width="stretch",
            ):
                seek_to(library, item, row["start"])
    item = choose_item(library, "speech_item", t)
    if not item:
        return
    uploaded = st.file_uploader(t("Import existing SRT or VTT subtitles"), type=["srt", "vtt"])
    status = store.status(item.path)
    busy = status is not None and status["status"] in {"queued", "running"}
    if st.button(t("Import subtitles"), disabled=uploaded is None or busy):
        if uploaded.size > 2_000_000:
            raise ValueError("Subtitle files must be smaller than 2 MB.")
        store.save(item.path, parse_subtitles(uploaded.getvalue().decode("utf-8-sig")))
        st.success(t("Subtitles indexed locally."))
    st.markdown(f"### {t('Local transcription')}")
    st.caption(
        t(
            "Speech stays on your computer. Models run on CPU; long files can take time. "
            "The first model download requires an internet connection."
        )
    )
    if not service.available():
        st.info(t("Optional speech engine not installed. Subtitle import and search still work."))
        st.code('python -m pip install ".[transcription]"', language="bash")
    model = st.selectbox(t("Speech model"), ["tiny", "base", "small"])
    consent = st.checkbox(t("Allow downloading the selected model from Hugging Face if missing."))
    status = store.status(item.path)
    busy = status is not None and status["status"] in {"queued", "running"}
    if st.button(t("Transcribe locally"), disabled=not service.available() or busy, type="primary"):
        service.submit(store, item.path, model=model, allow_download=consent)
        st.rerun()
    transcript_status(store, item.path, service, t)
    segments = store.segments(item.path)
    if segments:
        st.caption(t("{count} transcript segments", count=len(segments)))
        a, b = st.columns(2)
        a.download_button(
            t("Export SRT"),
            export_transcript(segments, srt=True),
            file_name=f"{item.path.stem}.srt",
            mime="text/plain",
        )
        b.download_button(
            t("Export text"),
            export_transcript(segments),
            file_name=f"{item.path.stem}.txt",
            mime="text/plain",
        )


@st.fragment(run_every="3s")
def transcript_status(store, path, service, t):
    status = store.status(path)
    if not status:
        return
    status_key = f"speech-status:{store.library.root}:{path}"
    previous = st.session_state.get(status_key)
    st.session_state[status_key] = status["status"]
    if previous in {"queued", "running"} and status["status"] not in {"queued", "running"}:
        st.rerun()
    st.caption(f"{t('Transcript status')}: {status['status']} · {status['model']}")
    if status["error"]:
        st.warning(status["error"])
    if status["status"] in {"queued", "running"}:
        if st.button(t("Cancel transcription")):
            service.cancel(store, path)
            st.rerun(scope="fragment")
    elif status["status"] == "ready":
        st.caption(t("Ready. Refresh the view to search or export new segments."))


def render_file_tags(library, t):
    st.warning(
        t(
            "Writes to the actual media file. An original-file backup is created first. "
            "Pause playback and close external editors before applying changes."
        )
    )
    item = choose_item(library, "tags_item", t)
    if not item:
        return
    confirmed = st.checkbox(t("I want to update the actual media file."))
    with st.form(f"file_tags_{item.path}"):
        title = st.text_input(t("Title"), value=item.title)
        artist = st.text_input(t("Artist"), value=item.artist)
        album = st.text_input(t("Album"), value=item.album)
        cover = st.file_uploader(t("Cover (PNG or JPEG, up to 10 MB)"), type=["png", "jpg", "jpeg"])
        if st.form_submit_button(
            t("Write tags with backup"), disabled=not confirmed, type="primary"
        ):
            backup = write_file_metadata(
                library,
                item.path,
                title=title,
                artist=artist,
                album=album,
                cover=cover.getvalue() if cover else None,
            )
            st.success(t("Tags written. Original saved at {path}", path=backup))
    backups = file_backups(library, item.path)
    if backups:
        selected = st.selectbox(
            t("Original-file backups"), backups, format_func=lambda path: path.parent.name[:12]
        )
        restore = st.checkbox(t("Restore this backup, replacing the current file."))
        if st.button(t("Restore original"), disabled=not restore):
            restore_file_backup(library, item.path, selected)
            st.success(t("Original file restored."))


def render_sharing(library, t):
    service = sharing_service()
    st.markdown(f"### {t('Your library. Around the house.')}")
    st.caption(
        t(
            "A separate, read-only mobile player. Downloads, settings and the rest of your "
            "computer are never exposed. Sharing is off after every full app restart."
        )
    )
    st.warning(
        t(
            "Trusted home Wi-Fi only: HTTP is not encrypted. Do not expose the port to the "
            "internet. Your computer must stay awake. Stop sharing to revoke all sessions."
        )
    )
    if service.player:
        player = service.player
        st.success(t("Sharing is active"))
        st.code(player.url, language=None)
        st.caption(t("Shared library: {path}", path=player.library.root))
        with st.popover(t("Show pairing code")):
            st.code(player.secret, language=None)
        st.caption(
            t(
                "Open this address on your phone, then enter the pairing code. "
                "Sessions expire after 12 hours. A new sharing session creates a new code."
            )
        )
        if player.address == "127.0.0.1":
            st.info(t("LAN address could not be detected. Use your computer's Wi-Fi IPv4 address."))
        if st.button(t("Stop sharing and revoke sessions"), type="primary"):
            service.stop()
            st.rerun()
    else:
        port = st.number_input(t("Home player port"), 1024, 65535, 8767)
        confirmed = st.checkbox(t("Share only this library on my trusted home network."))
        if st.button(t("Start home player"), disabled=not confirmed, type="primary"):
            service.start(library, port)
            st.rerun()
