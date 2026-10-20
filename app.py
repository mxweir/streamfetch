"""Streamlit entry point for StreamFetch."""

from __future__ import annotations

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
from streamfetch.library import MediaItem, MediaLibrary
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
        search = st.session_state.library_search
        media_type = st.session_state.library_media_type
        total_matches = library.count_items(search, media_type)
        items = library.list_items(
            search=search,
            media_type=media_type,
            sort=st.session_state.library_sort,
        )
    except (OSError, sqlite3.Error) as exc:
        st.error(f"The library could not be opened: {exc}")
        return

    metric_columns = st.columns(5)
    metric_columns[0].metric("Items", stats.total)
    metric_columns[1].metric("Audio", stats.audio)
    metric_columns[2].metric("Video", stats.video)
    metric_columns[3].metric("Artists", stats.artists)
    metric_columns[4].metric("Storage", human_size(stats.size_bytes))

    if not items:
        st.info(
            "No matching media found. Download something first or choose another library folder."
        )
        return

    shown = len(items)
    st.caption(f"Showing {shown} of {total_matches} matching item(s).")
    for start in range(0, shown, 3):
        columns = st.columns(3)
        for column, item in zip(columns, items[start : start + 3], strict=False):
            with column:
                render_library_item(item)


def render_library_item(item: MediaItem) -> None:
    with st.container(border=True):
        st.markdown('<span class="sf-library-card-marker"></span>', unsafe_allow_html=True)
        if item.cover_path and item.cover_path.exists():
            st.image(str(item.cover_path), width="stretch")
        else:
            icon = "♫" if item.media_type == "audio" else "▶"
            st.markdown(
                f'<div class="sf-cover-placeholder"><span>{icon}</span></div>',
                unsafe_allow_html=True,
            )

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
        modified = datetime.fromtimestamp(item.modified_at).strftime("%Y-%m-%d %H:%M")
        with st.expander("File details"):
            st.caption(f"Modified {modified}")
            st.code(str(item.path), language=None)


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
