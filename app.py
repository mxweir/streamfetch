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
from streamfetch.jobs import DownloadJobManager, JobStatus
from streamfetch.library import MediaItem, MediaLibrary, Playlist
from streamfetch.models import DownloadRequest, MediaType
from streamfetch.player import build_player_data, render_continuous_player
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
    if (
        st.session_state.use_clip_range
        and st.session_state.clip_end <= st.session_state.clip_start
    ):
        raise ValidationError("The clip end must be after its start.")
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
        concurrent_fragments=st.session_state.concurrent_fragments,
        rate_limit=(
            int(st.session_state.rate_limit_mbps * 1024 * 1024)
            if st.session_state.use_rate_limit
            else None
        ),
        download_sections=(
            (f"{st.session_state.clip_start}-{st.session_state.clip_end}",)
            if st.session_state.use_clip_range
            else ()
        ),
        split_chapters=st.session_state.split_chapters,
        sponsorblock_remove=tuple(st.session_state.sponsorblock_remove),
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
            st.slider(
                "Concurrent fragments",
                min_value=1,
                max_value=16,
                value=4,
                key="concurrent_fragments",
            )
            st.checkbox("Limit bandwidth", key="use_rate_limit")
            st.number_input(
                "Bandwidth limit (MB/s)",
                min_value=0.1,
                max_value=1000.0,
                value=5.0,
                step=0.5,
                disabled=not st.session_state.use_rate_limit,
                key="rate_limit_mbps",
            )
            st.checkbox("Download a time range only", key="use_clip_range")
            clip_start, clip_end = st.columns(2)
            clip_start.number_input(
                "Start (seconds)",
                min_value=0.0,
                value=0.0,
                disabled=not st.session_state.use_clip_range,
                key="clip_start",
            )
            clip_end.number_input(
                "End (seconds)",
                min_value=0.1,
                value=60.0,
                disabled=not st.session_state.use_clip_range,
                key="clip_end",
            )
            st.checkbox("Split files by chapters", key="split_chapters")
            st.multiselect(
                "Remove YouTube segments with SponsorBlock",
                ["sponsor", "intro", "outro", "selfpromo", "interaction", "filler"],
                key="sponsorblock_remove",
                help="Applied only where SponsorBlock data is available.",
            )


def render_library_sidebar() -> None:
    with st.sidebar:
        st.markdown(LIBRARY_SIDEBAR_HTML, unsafe_allow_html=True)
        default_dir = st.session_state.get("output_dir", default_download_dir())
        st.text_input("Library folder", value=default_dir, key="library_dir")
        st.divider()
        st.text_input(
            "Search",
            placeholder="Title, artist, album, tag, or path",
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
    manager = get_download_manager()

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
        enqueue_download(raw_urls, manager)
    render_download_jobs(manager)


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
        render_library_import(library)
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
        ["Browse", "Discover", "Favorites", "Playlists", "History"],
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
    if section == "Discover":
        render_discover(library)
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
    caption_col, play_col = st.columns([3, 1])
    caption_col.caption(f"Showing {shown} of {total_matches} matching item(s).")
    if play_col.button(
        "▶ Play collection",
        key=f"play_collection_{active_playlist_id}_{shown}",
        width="stretch",
    ):
        library.replace_queue([item.path for item in items[1:]])
        select_media(library, items[0])
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
        if item.rating or item.tags:
            annotations = []
            if item.rating:
                annotations.append("★" * item.rating + "☆" * (5 - item.rating))
            if item.tags:
                annotations.append(" · ".join(f"#{tag}" for tag in item.tags))
            st.caption("  ".join(annotations))

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
        next_col, queue_col = st.columns(2)
        if next_col.button("Play next", key=f"next_{item_key}", width="stretch"):
            library.enqueue(item.path, play_next=True)
            st.toast(f"{item.title} will play next.")
            st.rerun()
        if queue_col.button("Add to queue", key=f"queue_{item_key}", width="stretch"):
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
        render_metadata_editor(library, item, item_key)


def render_metadata_editor(library: MediaLibrary, item: MediaItem, item_key: str) -> None:
    with st.expander("Edit metadata"):
        st.caption("Edits are stored in the local library database; the media file is unchanged.")
        with st.form(f"metadata_{item_key}"):
            title = st.text_input("Title", value=item.title)
            artist = st.text_input("Artist", value=item.artist)
            album = st.text_input("Album", value=item.album)
            rating = st.select_slider(
                "Rating",
                options=[0, 1, 2, 3, 4, 5],
                value=item.rating,
                format_func=lambda value: "Unrated" if value == 0 else "★" * value,
            )
            tags = st.text_input(
                "Tags",
                value=", ".join(item.tags),
                placeholder="focus, live, workout",
            )
            submitted = st.form_submit_button("Save metadata", width="stretch")
        if submitted:
            try:
                library.update_metadata(
                    item.path,
                    title=title,
                    artist=artist,
                    album=album,
                    rating=rating,
                    tags=[tag for tag in tags.split(",")],
                )
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.toast("Metadata saved.")
                st.rerun()


def render_library_import(library: MediaLibrary) -> None:
    with st.expander("Import a local media folder"):
        st.caption(
            "Supported audio and video files are copied into Imported/ while preserving folders."
        )
        source = st.text_input(
            "Folder to import",
            placeholder="/Users/you/Music",
            key="library_import_source",
        )
        if st.button("Import folder", key="library_import_button", width="stretch"):
            try:
                with st.spinner("Copying media into the library…"):
                    summary = library.import_folder(source)
                    library.scan()
            except (OSError, ValueError, sqlite3.Error) as exc:
                st.error(f"Import failed: {exc}")
            else:
                st.success(
                    f"Imported {summary.imported} file(s), skipped {summary.skipped}; "
                    f"saved under {summary.destination}."
                )


def render_discover(library: MediaLibrary) -> None:
    mode = st.selectbox(
        "Explore your library",
        [
            "Recently added",
            "Most played",
            "Highly rated",
            "Unplayed",
            "Artists",
            "Albums",
            "Duplicates",
        ],
        key="library_discover_mode",
    )
    search = st.session_state.library_search
    media_type = st.session_state.library_media_type
    sort = st.session_state.library_sort

    if mode == "Artists":
        facets = library.artists()
        if not facets:
            st.info("No artists found yet.")
            return
        names = {facet.name: f"{facet.name} · {facet.item_count} item(s)" for facet in facets}
        selected = st.selectbox("Artist", list(names), format_func=names.get)
        items = library.items_for_artist(selected)
    elif mode == "Albums":
        facets = library.albums()
        if not facets:
            st.info("No albums found yet.")
            return
        names = {facet.name: f"{facet.name} · {facet.item_count} item(s)" for facet in facets}
        selected = st.selectbox("Album", list(names), format_func=names.get)
        items = library.items_for_album(selected)
    elif mode == "Duplicates":
        render_duplicates(library)
        return
    else:
        items = {
            "Recently added": library.recently_added,
            "Most played": library.most_played,
            "Highly rated": library.highly_rated,
            "Unplayed": library.unplayed,
        }[mode]()

    collection_sort = sort if sort != "newest" else "collection"
    items = filter_collection(items, search, media_type, collection_sort)
    render_media_grid(library, items, len(items))


def render_duplicates(library: MediaLibrary) -> None:
    st.caption("Files are compared by size and SHA-256 content hash. Nothing is deleted.")
    if st.button("Scan for exact duplicates", type="primary", key="scan_duplicates"):
        with st.spinner("Hashing files with matching sizes…"):
            groups = library.duplicate_groups()
        st.session_state.library_duplicate_groups = [
            [library.relative_path(item.path) for item in group] for group in groups
        ]

    stored_groups = st.session_state.get("library_duplicate_groups")
    if stored_groups is None:
        st.info("Start a scan to look for byte-identical files.")
        return
    groups = [
        tuple(item for path in paths if (item := library.item_for_path(path)) is not None)
        for paths in stored_groups
    ]
    groups = [group for group in groups if len(group) > 1]
    if not groups:
        st.success("No exact duplicates found.")
        return
    st.warning(f"Found {len(groups)} duplicate group(s). Review the paths before cleanup.")
    for index, group in enumerate(groups, start=1):
        with st.expander(
            f"Duplicate group {index} · {human_size(group[0].size_bytes)}",
            expanded=index == 1,
        ):
            for item in group:
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
            autoplay = st.session_state.pop("player_autoplay", False)
            previous = library.previous_item(current.path)
            current_is_favorite = library.relative_path(current.path) in library.favorite_paths()
            player_data = build_player_data(
                current,
                queue,
                favorite=current_is_favorite,
                can_previous=previous is not None,
                autoplay=autoplay,
                repeat_mode=library.player_setting("repeat", "off"),
                crossfade_seconds=int(library.player_setting("crossfade", "0")),
                resume_position=library.playback_position(current.path),
            )
            result = render_continuous_player(player_data)
            handle_player_action(library, result, previous)

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
            if queue:
                shuffle_col, clear_col = st.columns(2)
                if shuffle_col.button("Shuffle queue", key="queue_shuffle"):
                    library.shuffle_queue()
                    st.rerun()
                if clear_col.button("Clear queue", key="queue_clear"):
                    library.clear_queue()
                    st.rerun()


def handle_player_action(library: MediaLibrary, result, previous: MediaItem | None) -> None:
    action = getattr(result, "action", None)
    if not isinstance(action, dict):
        return
    nonce = action.get("nonce")
    if not nonce or nonce == st.session_state.get("processed_player_action"):
        return
    st.session_state.processed_player_action = nonce

    action_type = action.get("type")
    if action_type == "favorite":
        current = library.current_item()
        if current:
            library.toggle_favorite(current.path)
        st.rerun()
    if action_type == "previous" and previous:
        select_media(library, previous)
    if action_type == "advance":
        entry_id = action.get("entry_id")
        if isinstance(entry_id, int):
            current = library.current_item()
            if current:
                library.set_playback_position(current.path, 0)
                if library.player_setting("repeat", "off") == "all":
                    library.enqueue(current.path)
            next_item = library.take_queue_entry(entry_id)
            if next_item:
                select_media(library, next_item)
    if action_type == "jump":
        entry_id = action.get("entry_id")
        if isinstance(entry_id, int):
            next_item = library.take_queue_entry(entry_id)
            if next_item:
                select_media(library, next_item)
    if action_type == "reorder":
        entry_ids = action.get("entry_ids")
        if isinstance(entry_ids, list) and all(isinstance(value, int) for value in entry_ids):
            library.reorder_queue(entry_ids)
            st.rerun()
    if action_type == "repeat" and action.get("mode") in {"off", "all", "one"}:
        library.set_player_setting("repeat", action["mode"])
        st.rerun()
    if action_type == "crossfade" and action.get("seconds") in {0, 2, 4, 6}:
        library.set_player_setting("crossfade", str(action["seconds"]))
        st.rerun()
    if action_type == "position" and isinstance(action.get("position"), (int, float)):
        current = library.current_item()
        if current:
            library.set_playback_position(current.path, float(action["position"]))
    if action_type == "replay":
        current = library.current_item()
        if current:
            library.set_playback_position(current.path, 0)
            library.record_play(current.path)


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
            in " ".join(
                (item.title, item.artist, item.album, *item.tags, str(item.path))
            ).casefold()
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
    elif sort == "newest":
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


def get_download_manager() -> DownloadJobManager:
    if "download_job_manager" not in st.session_state:
        st.session_state.download_job_manager = DownloadJobManager(max_workers=2)
    return st.session_state.download_job_manager


def enqueue_download(raw_urls: str, manager: DownloadJobManager) -> None:
    try:
        urls = parse_urls(raw_urls)
        request = build_request(urls)
    except ValidationError as exc:
        st.error(str(exc))
        return
    if shutil.which("ffmpeg") is None:
        st.error("FFmpeg was not found. Install FFmpeg and restart the app before downloading.")
        return
    job_ids = manager.submit(request)
    st.success(f"Queued {len(job_ids)} background download job(s).")


@st.fragment(run_every=1.0)
def render_download_jobs(manager: DownloadJobManager) -> None:
    jobs = manager.snapshots()
    if not jobs:
        return

    st.markdown(RESULT_LABEL_HTML, unsafe_allow_html=True)
    heading_col, clear_col = st.columns([3, 1])
    heading_col.caption("Downloads continue while you browse this app session.")
    if clear_col.button("Clear finished", width="stretch", key="jobs_clear_finished"):
        manager.remove_finished()
        st.rerun(scope="fragment")

    for job in jobs:
        with st.container(border=True):
            title_col, status_col = st.columns([3, 1])
            title_col.markdown(f"**{job.url}**")
            status_col.caption(job.status.value.upper())
            st.progress(job.progress, text=job.message)

            details = []
            if job.filename:
                details.append(Path(job.filename).name)
            if job.speed_bytes_per_second:
                details.append(f"{human_size(int(job.speed_bytes_per_second))}/s")
            if job.eta_seconds is not None:
                details.append(f"ETA {int(job.eta_seconds)}s")
            if details:
                st.caption(" · ".join(details))
            if job.error:
                st.error(job.error)

            action_col, files_col = st.columns([1, 3])
            if job.status in {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.PAUSING}:
                if action_col.button("Pause", key=f"pause_{job.id}", width="stretch"):
                    manager.pause(job.id)
                    st.rerun(scope="fragment")
            elif job.status is JobStatus.PAUSED:
                if action_col.button("Resume", key=f"resume_{job.id}", width="stretch"):
                    manager.resume(job.id)
                    st.rerun(scope="fragment")
            elif job.status is JobStatus.FAILED and action_col.button(
                "Retry", key=f"retry_{job.id}", width="stretch"
            ):
                manager.retry(job.id)
                st.rerun(scope="fragment")

            if job.files:
                files_col.caption(
                    "Created: " + ", ".join(path.name for path in job.files[:4])
                )
                st.session_state.pop("library_scanned_root", None)


if __name__ == "__main__":
    main()
