"""Streamlit entry point for StreamFetch."""

from __future__ import annotations

import hashlib
import html
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import streamlit as st

from streamfetch.config import (
    ValidationError,
    human_size,
    parse_subtitle_languages,
    parse_urls,
    validate_request,
)
from streamfetch.downloader import Downloader, DownloaderError
from streamfetch.library import MediaItem, MediaLibrary, Playlist
from streamfetch.models import DownloadRequest, MediaType, ProgressEvent
from streamfetch.theme import (
    APP_CSS,
    HERO_HTML,
    LEGAL_HTML,
    LIBRARY_LABEL_HTML,
    LIBRARY_SIDEBAR_HTML,
    PREVIEW_LABEL_HTML,
    RESULT_LABEL_HTML,
    SIDEBAR_HEADER_HTML,
    SOURCE_LABEL_HTML,
)

st.set_page_config(page_title="StreamFetch", page_icon="⚡", layout="wide")

AUDIO_MIME_TYPES = {
    "FLAC": "audio/flac",
    "M4A": "audio/mp4",
    "MP3": "audio/mpeg",
    "OGG": "audio/ogg",
    "OPUS": "audio/ogg",
    "WAV": "audio/wav",
}


def render_header() -> None:
    st.markdown(APP_CSS, unsafe_allow_html=True)
    st.markdown(HERO_HTML, unsafe_allow_html=True)
    st.markdown(LEGAL_HTML, unsafe_allow_html=True)


def render_preview(preview) -> None:
    with st.container(border=True):
        st.markdown('<span class="sf-card-marker"></span>', unsafe_allow_html=True)
        left, right = st.columns([1, 3])
        with left:
            if preview.thumbnail:
                st.image(preview.thumbnail, width="stretch")
        with right:
            st.subheader(preview.title)
            details = [preview.source_type]
            if preview.uploader:
                details.append(preview.uploader)
            if preview.entry_count:
                details.append(f"{preview.entry_count} item(s)")
            st.caption(" · ".join(details))
            if preview.entries:
                with st.expander(f"First {len(preview.entries)} entries"):
                    for index, entry in enumerate(preview.entries, start=1):
                        duration = format_duration(entry.duration)
                        st.write(f"{index}. {entry.title}{duration}")


def format_duration(seconds: int | None) -> str:
    if not seconds:
        return ""
    minutes, remainder = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    value = f"{hours}:{minutes:02d}:{remainder:02d}" if hours else f"{minutes}:{remainder:02d}"
    return f" — {value}"


def default_download_dir() -> str:
    return str((Path.cwd() / "downloads").resolve())


def build_request(urls: tuple[str, ...]) -> DownloadRequest:
    media_type = MediaType(st.session_state.media_type)
    container = (
        st.session_state.audio_format
        if media_type is MediaType.AUDIO
        else st.session_state.video_format
    )
    quality = (
        st.session_state.audio_quality
        if media_type is MediaType.AUDIO
        else st.session_state.video_quality
    )
    max_items = st.session_state.max_items if st.session_state.use_limit else None
    cookie_browser = (
        None
        if st.session_state.cookie_browser == "None"
        else st.session_state.cookie_browser.lower()
    )
    embed_thumbnail = st.session_state.embed_thumbnail and not (
        media_type is MediaType.AUDIO and container == "wav"
    )
    request = DownloadRequest(
        urls=urls,
        output_dir=Path(st.session_state.output_dir),
        media_type=media_type,
        container=container,
        quality=quality,
        allow_playlists=st.session_state.allow_playlists,
        max_items=max_items,
        embed_metadata=st.session_state.embed_metadata,
        embed_thumbnail=embed_thumbnail,
        embed_subtitles=st.session_state.embed_subtitles,
        subtitle_languages=parse_subtitle_languages(st.session_state.subtitle_languages),
        cookie_browser=cookie_browser,
    )
    validate_request(request)
    return request


def render_download_sidebar() -> None:
    with st.sidebar:
        st.markdown(SIDEBAR_HEADER_HTML, unsafe_allow_html=True)
        st.radio("Media type", ["video", "audio"], horizontal=True, key="media_type")

        if st.session_state.media_type == "video":
            st.selectbox("Container", ["mp4", "mkv", "webm"], key="video_format")
            st.selectbox(
                "Maximum resolution",
                ["best", "2160p", "1440p", "1080p", "720p", "480p", "360p"],
                index=3,
                key="video_quality",
            )
        else:
            st.selectbox("Audio format", ["mp3", "m4a", "opus", "flac", "wav"], key="audio_format")
            st.selectbox(
                "Audio quality",
                ["0", "320K", "256K", "192K", "128K"],
                index=3,
                key="audio_quality",
                help="0 is yt-dlp/FFmpeg's best variable-bitrate setting.",
            )

        st.divider()
        st.checkbox(
            "Process playlists, channels, sets, and profiles",
            value=True,
            key="allow_playlists",
        )
        st.checkbox("Limit collection size", value=True, key="use_limit")
        st.number_input(
            "Maximum items per source",
            min_value=1,
            max_value=10_000,
            value=50,
            disabled=not st.session_state.use_limit,
            key="max_items",
        )
        st.divider()
        st.checkbox("Embed metadata", value=True, key="embed_metadata")
        st.checkbox("Embed thumbnail", value=True, key="embed_thumbnail")
        st.checkbox(
            "Embed subtitles",
            value=False,
            disabled=st.session_state.media_type == "audio",
            key="embed_subtitles",
        )
        st.text_input(
            "Subtitle languages",
            value="en,de",
            disabled=not st.session_state.embed_subtitles,
            help="Comma-separated yt-dlp language codes.",
            key="subtitle_languages",
        )

        with st.expander("Advanced"):
            st.selectbox(
                "Use cookies from browser",
                ["None", "Chrome", "Firefox", "Edge", "Safari", "Brave"],
                key="cookie_browser",
                help=(
                    "Useful for age-restricted or signed-in content. "
                    "Cookies stay on this computer."
                ),
            )


def render_library_sidebar() -> None:
    with st.sidebar:
        st.markdown(LIBRARY_SIDEBAR_HTML, unsafe_allow_html=True)
        default_dir = st.session_state.get("output_dir", default_download_dir())
        st.text_input("Library folder", value=default_dir, key="library_dir")
        st.divider()
        st.text_input(
            "Search",
            placeholder="Title, artist, album, or path",
            key="library_search",
        )
        st.selectbox(
            "Media type",
            ["all", "audio", "video"],
            format_func=str.title,
            key="library_media_type",
        )
        st.selectbox(
            "Sort by",
            ["newest", "title", "artist", "largest", "oldest"],
            format_func=str.title,
            key="library_sort",
        )


def render_download_view() -> None:
    render_download_sidebar()

    with st.container(border=True):
        st.markdown(SOURCE_LABEL_HTML, unsafe_allow_html=True)
        st.text_input("Output directory", value=default_download_dir(), key="output_dir")
        raw_urls = st.text_area(
            "YouTube or SoundCloud URLs",
            height=160,
            placeholder=(
                "One URL per line:\n"
                "https://www.youtube.com/watch?v=...\n"
                "https://www.youtube.com/playlist?list=...\n"
                "https://soundcloud.com/artist/track\n"
                "https://soundcloud.com/artist/sets/collection"
            ),
        )
        if "soundcloud.com" in raw_urls.lower() or "snd.sc/" in raw_urls.lower():
            st.info("SoundCloud sources are audio-only. Select **Audio** in the sidebar.")
        accepted = st.checkbox(
            "I have permission to download these items and accept responsibility for their use."
        )

        analyze_col, download_col, _ = st.columns([1, 1, 2])
        analyze_clicked = analyze_col.button("Analyze", width="stretch")
        download_clicked = download_col.button(
            "Start download", type="primary", width="stretch", disabled=not accepted
        )

    if analyze_clicked:
        analyze(raw_urls)
    if st.session_state.get("previews"):
        st.markdown(PREVIEW_LABEL_HTML, unsafe_allow_html=True)
        for preview in st.session_state.previews:
            render_preview(preview)
    if download_clicked:
        download(raw_urls)


def render_library_view() -> None:
    render_library_sidebar()
    root = Path(st.session_state.library_dir).expanduser().resolve()
    library = MediaLibrary(root)

    st.markdown(LIBRARY_LABEL_HTML, unsafe_allow_html=True)
    refresh_col, path_col = st.columns([1, 3])
    refresh_clicked = refresh_col.button(
        "Refresh library",
        type="primary",
        width="stretch",
    )
    path_col.caption(f"Watching {root}")

    scan_needed = (
        not library.database_path.exists()
        or st.session_state.get("library_scanned_root") != str(root)
    )
    try:
        if scan_needed or refresh_clicked:
            with st.spinner("Scanning local media…"):
                summary = library.scan()
            st.session_state.library_scanned_root = str(root)
            if refresh_clicked or summary.added or summary.updated or summary.removed:
                st.success(
                    "Library refreshed — "
                    f"{summary.added} added, {summary.updated} updated, "
                    f"{summary.removed} removed."
                )

        stats = library.stats()
    except (OSError, sqlite3.Error) as exc:
        st.error(f"The library could not be opened: {exc}")
        return

    render_player(library)

    metric_columns = st.columns(5)
    metric_columns[0].metric("Items", stats.total)
    metric_columns[1].metric("Audio", stats.audio)
    metric_columns[2].metric("Video", stats.video)
    metric_columns[3].metric("Artists", stats.artists)
    metric_columns[4].metric("Storage", human_size(stats.size_bytes))

    section = st.radio(
        "Library section",
        ["Browse", "Favorites", "Playlists", "History"],
        horizontal=True,
        label_visibility="collapsed",
        key="library_section",
    )
    if section == "History":
        render_history(library)
        return
    if section == "Playlists":
        render_playlists(library)
        return

    search = st.session_state.library_search
    media_type = st.session_state.library_media_type
    sort = st.session_state.library_sort
    if section == "Favorites":
        items = filter_collection(library.favorite_items(), search, media_type, sort)
        total_matches = len(items)
    else:
        total_matches = library.count_items(search, media_type)
        items = library.list_items(search=search, media_type=media_type, sort=sort)

    render_media_grid(library, items, total_matches)


def render_media_grid(
    library: MediaLibrary,
    items: tuple[MediaItem, ...],
    total_matches: int,
    active_playlist_id: int | None = None,
) -> None:
    if not items:
        st.info("No matching media found in this collection.")
        return

    playlists = library.playlists()
    favorite_paths = library.favorite_paths()
    shown = len(items)
    st.caption(f"Showing {shown} of {total_matches} matching item(s).")
    for start in range(0, shown, 3):
        columns = st.columns(3)
        for column, item in zip(columns, items[start : start + 3], strict=False):
            with column:
                render_library_item(
                    library,
                    item,
                    favorite_paths,
                    playlists,
                    active_playlist_id,
                )


def render_library_item(
    library: MediaLibrary,
    item: MediaItem,
    favorite_paths: set[str],
    playlists: tuple[Playlist, ...],
    active_playlist_id: int | None = None,
) -> None:
    relative_path = library.relative_path(item.path)
    item_key = hashlib.sha256(relative_path.encode()).hexdigest()[:12]
    with st.container(border=True):
        st.markdown('<span class="sf-library-card-marker"></span>', unsafe_allow_html=True)
        render_media_art(item)

        title = html.escape(item.title)
        artist = html.escape(item.artist)
        album = html.escape(item.album)
        st.markdown(
            f'<div class="sf-media-title">{title}</div>'
            f'<div class="sf-media-artist">{artist}</div>'
            f'<div class="sf-media-album">{album}</div>',
            unsafe_allow_html=True,
        )
        details = [item.format, item.media_type.upper(), human_size(item.size_bytes)]
        if item.duration_seconds:
            details.append(format_duration(int(item.duration_seconds)).removeprefix(" — "))
        st.caption(" · ".join(details))

        play_col, favorite_col = st.columns(2)
        if play_col.button("▶ Play", key=f"play_{item_key}", width="stretch"):
            select_media(library, item)
        favorite_label = "♥ Saved" if relative_path in favorite_paths else "♡ Favorite"
        if favorite_col.button(
            favorite_label,
            key=f"favorite_{item_key}",
            width="stretch",
        ):
            library.toggle_favorite(item.path)
            st.rerun()
        if st.button("＋ Add to queue", key=f"queue_{item_key}", width="stretch"):
            library.enqueue(item.path)
            st.toast(f"Added {item.title} to the queue.")
            st.rerun()

        if playlists:
            with st.expander("Add to playlist"):
                playlist_names = {playlist.id: playlist.name for playlist in playlists}
                playlist_id = st.selectbox(
                    "Playlist",
                    list(playlist_names),
                    format_func=playlist_names.get,
                    key=f"playlist_select_{item_key}",
                )
                if st.button("Add", key=f"playlist_add_{item_key}", width="stretch"):
                    library.add_to_playlist(playlist_id, item.path)
                    st.toast(f"Added {item.title} to {playlist_names[playlist_id]}.")
                    st.rerun()
        if active_playlist_id is not None and st.button(
            "Remove from playlist",
            key=f"playlist_remove_{active_playlist_id}_{item_key}",
            width="stretch",
        ):
            library.remove_from_playlist(active_playlist_id, item.path)
            st.rerun()

        modified = datetime.fromtimestamp(item.modified_at).strftime("%Y-%m-%d %H:%M")
        with st.expander("File details"):
            st.caption(f"Modified {modified}")
            st.code(str(item.path), language=None)


def render_media_art(item: MediaItem) -> None:
    if item.cover_path and item.cover_path.exists():
        st.image(str(item.cover_path), width="stretch")
        return
    icon = "♫" if item.media_type == "audio" else "▶"
    st.markdown(
        f'<div class="sf-cover-placeholder"><span>{icon}</span></div>',
        unsafe_allow_html=True,
    )


def select_media(library: MediaLibrary, item: MediaItem) -> None:
    library.set_current_item(item.path)
    library.record_play(item.path)
    st.session_state.player_autoplay = True
    st.rerun()


def render_player(library: MediaLibrary) -> None:
    current = library.current_item()
    queue = library.queue()
    if current is None:
        st.info("Choose an item from the library to start the local player.")
        if queue and st.button("Play first queued item", type="primary"):
            item = library.take_queue_entry()
            if item:
                select_media(library, item)
        return

    with st.container(border=True):
        st.markdown('<span class="sf-player-marker"></span>', unsafe_allow_html=True)
        art_col, player_col = st.columns([1, 3])
        with art_col:
            render_media_art(current)
        with player_col:
            st.markdown('<div class="sf-player-kicker">Now playing</div>', unsafe_allow_html=True)
            st.subheader(current.title)
            st.caption(f"{current.artist} · {current.album}")
            autoplay = st.session_state.pop("player_autoplay", False)
            if current.media_type == "audio":
                st.audio(
                    str(current.path),
                    format=AUDIO_MIME_TYPES.get(current.format, "audio/mpeg"),
                    autoplay=autoplay,
                    alt=f"{current.title} by {current.artist}",
                    width="stretch",
                )
            else:
                st.video(str(current.path), autoplay=autoplay)

            previous = library.previous_item(current.path)
            controls = st.columns(3)
            if controls[0].button(
                "← Previous",
                disabled=previous is None,
                width="stretch",
                key="player_previous",
            ) and previous:
                select_media(library, previous)
            if controls[1].button(
                "Next →",
                disabled=not queue,
                width="stretch",
                key="player_next",
            ):
                next_item = library.take_queue_entry()
                if next_item:
                    select_media(library, next_item)
            current_is_favorite = library.relative_path(current.path) in library.favorite_paths()
            favorite_label = "♥ Saved" if current_is_favorite else "♡ Favorite"
            if controls[2].button(favorite_label, width="stretch", key="player_favorite"):
                library.toggle_favorite(current.path)
                st.rerun()

        with st.expander(f"Queue · {len(queue)} item(s)"):
            if not queue:
                st.caption("Your queue is empty.")
            for entry in queue:
                title_col, play_col, remove_col = st.columns([3, 1, 1])
                title_col.write(f"{entry.item.title} — {entry.item.artist}")
                if play_col.button("Play", key=f"queue_play_{entry.id}"):
                    item = library.take_queue_entry(entry.id)
                    if item:
                        select_media(library, item)
                if remove_col.button("Remove", key=f"queue_remove_{entry.id}"):
                    library.remove_queue_entry(entry.id)
                    st.rerun()
            if queue and st.button("Clear queue", key="queue_clear"):
                library.clear_queue()
                st.rerun()


def render_playlists(library: MediaLibrary) -> None:
    create_col, button_col = st.columns([3, 1])
    playlist_name = create_col.text_input(
        "New playlist",
        placeholder="Road trip, Focus, Favorites…",
        key="new_playlist_name",
    )
    if button_col.button("Create", type="primary", width="stretch"):
        try:
            playlist = library.create_playlist(playlist_name)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state.selected_playlist_id = playlist.id
            st.rerun()

    playlists = library.playlists()
    if not playlists:
        st.info("Create your first playlist, then add tracks from Browse or Favorites.")
        return

    playlist_names = {
        playlist.id: f"{playlist.name} · {playlist.item_count} item(s)" for playlist in playlists
    }
    valid_ids = set(playlist_names)
    selected_id = st.session_state.get("selected_playlist_id")
    if selected_id not in valid_ids:
        selected_id = playlists[0].id
    selected_id = st.selectbox(
        "Playlist",
        list(playlist_names),
        index=list(playlist_names).index(selected_id),
        format_func=playlist_names.get,
        key="playlist_browser",
    )
    st.session_state.selected_playlist_id = selected_id

    delete_col, _ = st.columns([1, 3])
    if delete_col.button("Delete playlist", width="stretch"):
        library.delete_playlist(selected_id)
        st.session_state.pop("selected_playlist_id", None)
        st.rerun()

    items = filter_collection(
        library.playlist_items(selected_id),
        st.session_state.library_search,
        st.session_state.library_media_type,
        st.session_state.library_sort,
    )
    render_media_grid(library, items, len(items), active_playlist_id=selected_id)


def render_history(library: MediaLibrary) -> None:
    entries = library.history()
    if not entries:
        st.info("Play something and it will appear here.")
        return
    st.caption(f"Your latest {len(entries)} play action(s).")
    for entry in entries:
        with st.container(border=True):
            st.markdown('<span class="sf-history-marker"></span>', unsafe_allow_html=True)
            text_col, time_col, play_col = st.columns([3, 2, 1])
            text_col.markdown(f"**{entry.item.title}**  \n{entry.item.artist}")
            played = datetime.fromtimestamp(entry.played_at).strftime("%Y-%m-%d %H:%M")
            time_col.caption(f"Played {played}")
            if play_col.button("Play", key=f"history_play_{entry.id}", width="stretch"):
                select_media(library, entry.item)


def filter_collection(
    items: tuple[MediaItem, ...],
    search: str,
    media_type: str,
    sort: str,
) -> tuple[MediaItem, ...]:
    query = search.strip().casefold()
    filtered = [
        item
        for item in items
        if (media_type == "all" or item.media_type == media_type)
        and (
            not query
            or query
            in " ".join((item.title, item.artist, item.album, str(item.path))).casefold()
        )
    ]
    if sort == "artist":
        filtered.sort(key=lambda item: (item.artist.casefold(), item.title.casefold()))
    elif sort == "largest":
        filtered.sort(key=lambda item: item.size_bytes, reverse=True)
    elif sort == "oldest":
        filtered.sort(key=lambda item: item.modified_at)
    elif sort == "title":
        filtered.sort(key=lambda item: item.title.casefold())
    else:
        filtered.sort(key=lambda item: item.modified_at, reverse=True)
    return tuple(filtered[:120])


def main() -> None:
    render_header()
    st.markdown('<div class="sf-nav-label">Choose your workspace</div>', unsafe_allow_html=True)
    workspace = st.radio(
        "Workspace",
        ["Download", "Library"],
        horizontal=True,
        label_visibility="collapsed",
        key="workspace",
    )
    if workspace == "Library":
        render_library_view()
    else:
        render_download_view()


def analyze(raw_urls: str) -> None:
    try:
        urls = parse_urls(raw_urls)
        downloader = Downloader()
        with st.spinner("Reading source information…"):
            st.session_state.previews = [downloader.inspect(url) for url in urls]
    except (ValidationError, DownloaderError) as exc:
        st.error(str(exc))


def download(raw_urls: str) -> None:
    try:
        urls = parse_urls(raw_urls)
        request = build_request(urls)
    except ValidationError as exc:
        st.error(str(exc))
        return
    if shutil.which("ffmpeg") is None:
        st.error("FFmpeg was not found. Install FFmpeg and restart the app before downloading.")
        return

    progress = st.progress(0.0, text="Preparing download…")
    current_file = st.empty()

    def on_progress(event: ProgressEvent) -> None:
        if event.progress is not None:
            progress.progress(event.progress, text=event.message)
        else:
            progress.progress(0.0, text=event.message)
        if event.filename:
            current_file.caption(Path(event.filename).name)

    try:
        with st.status("Download in progress", expanded=True) as status:
            result = Downloader().download(request, on_progress)
            status.update(label="Download complete", state="complete", expanded=False)
    except DownloaderError as exc:
        progress.empty()
        st.error(str(exc))
        return

    progress.progress(1.0, text="Complete")
    st.success(
        f"Created {len(result.files)} file(s) in {result.elapsed_seconds:.1f} seconds. "
        f"Saved under {result.output_dir}"
    )
    st.session_state.pop("library_scanned_root", None)
    if result.files:
        st.markdown(RESULT_LABEL_HTML, unsafe_allow_html=True)
        rows = [
            {
                "File": str(path.relative_to(result.output_dir)),
                "Size": human_size(path.stat().st_size),
            }
            for path in result.files
        ]
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.info("No new files were created. They may already be listed in the download archive.")


if __name__ == "__main__":
    main()
