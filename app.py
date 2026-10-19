"""Streamlit entry point for StreamFetch."""

from __future__ import annotations

import shutil
from pathlib import Path

import streamlit as st

from streamfetch.config import ValidationError, human_size, parse_subtitle_languages, parse_urls
from streamfetch.downloader import Downloader, DownloaderError
from streamfetch.models import DownloadRequest, MediaType, ProgressEvent

st.set_page_config(page_title="StreamFetch", page_icon="⬇️", layout="wide")


def render_header() -> None:
    st.title("⬇️ StreamFetch")
    st.caption("A local, open-source GUI for permitted YouTube downloads")
    st.info(
        "Only download media you created, that is in the public domain, or that you have "
        "permission to download. Respect copyright, platform terms, and local law.",
        icon="⚖️",
    )


def render_preview(preview) -> None:
    with st.container(border=True):
        left, right = st.columns([1, 3])
        with left:
            if preview.thumbnail:
                st.image(preview.thumbnail, use_container_width=True)
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
    return DownloadRequest(
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


def render_sidebar() -> None:
    with st.sidebar:
        st.header("Download settings")
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
        st.checkbox("Process playlists and channels", value=True, key="allow_playlists")
        st.checkbox("Limit playlist/channel size", value=True, key="use_limit")
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


def main() -> None:
    render_header()
    render_sidebar()

    default_dir = str((Path.cwd() / "downloads").resolve())
    st.text_input("Output directory", value=default_dir, key="output_dir")
    raw_urls = st.text_area(
        "YouTube URLs",
        height=150,
        placeholder=(
            "One URL per line:\n"
            "https://www.youtube.com/watch?v=...\n"
            "https://www.youtube.com/playlist?list=...\n"
            "https://www.youtube.com/@channel/videos"
        ),
    )
    accepted = st.checkbox(
        "I have permission to download these items and accept responsibility for their use."
    )

    analyze_col, download_col, _ = st.columns([1, 1, 3])
    analyze_clicked = analyze_col.button("Analyze", use_container_width=True)
    download_clicked = download_col.button(
        "Start download", type="primary", use_container_width=True, disabled=not accepted
    )

    if analyze_clicked:
        analyze(raw_urls)
    if st.session_state.get("previews"):
        st.subheader("Preview")
        for preview in st.session_state.previews:
            render_preview(preview)
    if download_clicked:
        download(raw_urls)


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
    if result.files:
        rows = [
            {
                "File": str(path.relative_to(result.output_dir)),
                "Size": human_size(path.stat().st_size),
            }
            for path in result.files
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No new files were created. They may already be listed in the download archive.")


if __name__ == "__main__":
    main()
