"""Streamlit entry point for StreamFetch."""

from __future__ import annotations

import hashlib
import html
import shutil
import sqlite3
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import streamlit as st

from streamfetch import __version__
from streamfetch.config import (
    ValidationError,
    human_size,
    parse_subtitle_languages,
    parse_urls,
    validate_request,
)
from streamfetch.connected import playback_hub
from streamfetch.download_errors import classify_download_error, safe_error_detail
from streamfetch.downloader import (
    Downloader,
    DownloaderError,
    estimate_download_bytes,
    resolve_selected_urls,
)
from streamfetch.engine_updates import engine_status, ensure_engine
from streamfetch.i18n import LANGUAGES, default_language, player_labels, translate
from streamfetch.jobs import DownloadJobManager, JobStatus, default_job_state_path
from streamfetch.library import MediaItem, MediaLibrary, Playlist
from streamfetch.listening import ListeningLibrary
from streamfetch.loudness import loudness_service
from streamfetch.models import DownloadRequest, MediaType
from streamfetch.player import build_player_data, render_continuous_player
from streamfetch.presets import PresetStore
from streamfetch.settings import AppSettings, default_state_dir, load_settings, save_settings
from streamfetch.studio_ui import folder_watcher, render_studio
from streamfetch.subscription_ui import render_subscriptions
from streamfetch.subscriptions import SubscriptionService, SubscriptionStore
from streamfetch.system import HealthStatus, diagnostics_archive, run_health_checks
from streamfetch.theme import (
    APP_CSS,
    hero_html,
    legal_html,
    library_sidebar_html,
    sidebar_header_html,
    system_sidebar_html,
)
from streamfetch.updates import (
    ReleaseInfo,
    apply_update,
    cached_update_check,
    launch_downloaded_update,
)

_source_favicon = Path(__file__).resolve().parent / "docs" / "assets" / "streamfetch-mark.svg"
_package_favicon = Path(__file__).resolve().parent / "assets" / "streamfetch-mark.svg"
_favicon = next(
    (str(path) for path in (_source_favicon, _package_favicon) if path.exists()),
    "🎵",
)
st.set_page_config(page_title="StreamFetch", page_icon=_favicon, layout="wide")

if "app_settings" not in st.session_state:
    stored_settings = load_settings()
    if not stored_settings.first_run_completed and stored_settings.language == "English":
        stored_settings = replace(stored_settings, language=default_language())
    st.session_state.app_settings = stored_settings
if "ui_language" not in st.session_state:
    st.session_state.ui_language = st.session_state.app_settings.language


def t(text: str, **values: object) -> str:
    return translate(text, st.session_state.get("ui_language"), **values)


def render_language_picker() -> None:
    st.selectbox(
        t("Language"),
        list(LANGUAGES),
        key="ui_language",
        on_change=persist_language,
    )


def persist_language() -> None:
    settings = replace(st.session_state.app_settings, language=st.session_state.ui_language)
    save_settings(settings)
    st.session_state.app_settings = settings


def section_label(text: str) -> str:
    return f'<div class="sf-section-label">{html.escape(t(text))}</div>'


def render_header() -> None:
    st.markdown(APP_CSS, unsafe_allow_html=True)
    st.markdown(hero_html(t), unsafe_allow_html=True)
    st.markdown(legal_html(t), unsafe_allow_html=True)


def current_health_checks(*, force: bool = False):
    if force or "health_checks" not in st.session_state:
        output = Path(st.session_state.get("output_dir", st.session_state.app_settings.media_dir))
        st.session_state.health_checks = run_health_checks(output)
    return st.session_state.health_checks


def check_for_updates(*, force: bool = False) -> ReleaseInfo | None:
    settings = st.session_state.app_settings
    if not settings.check_updates and not force:
        return None
    try:
        release = cached_update_check(
            __version__,
            default_state_dir(),
            force=force,
        )
    except RuntimeError as exc:
        st.session_state.update_error = str(exc)
        return None
    st.session_state.latest_release = release
    st.session_state.pop("update_error", None)
    return release


def initialize_startup_services() -> None:
    ensure_engine()
    current_health_checks()
    get_subscription_service()
    settings = st.session_state.app_settings
    if "update_checked" not in st.session_state and settings.check_updates:
        st.session_state.update_checked = True
        release = check_for_updates()
        if (
            release
            and settings.auto_update
            and "automatic_update_attempted" not in st.session_state
        ):
            st.session_state.automatic_update_attempted = True
            st.session_state.update_result = apply_update(
                release,
                state_dir=default_state_dir(),
                library_root=settings.media_dir,
                project_root=Path(__file__).resolve().parent,
            )


def open_system_workspace() -> None:
    st.session_state.workspace = "System"


def render_startup_notices() -> None:
    engine = engine_status()
    if engine.error:
        st.warning(t(engine.error))
    if engine.pending_version:
        st.info(t("yt-dlp {version} is ready. Restart StreamFetch to activate it safely.",
                  version=engine.pending_version))
    missing = [
        check
        for check in current_health_checks()
        if check.required and check.status == HealthStatus.MISSING
    ]
    if missing:
        notice_col, action_col = st.columns([4, 1])
        notice_col.warning(
            t(
                "Setup needs attention: {names}. Open System for the exact installation steps.",
                names=", ".join(check.name for check in missing),
            )
        )
        action_col.button(
            t("Open System"),
            on_click=open_system_workspace,
            width="stretch",
            key="open_system_health",
        )
    release = st.session_state.get("latest_release")
    if release:
        update_col, action_col = st.columns([4, 1])
        update_col.info(
            t(
                "StreamFetch {version} is available. Your library and settings are "
                "backed up before installation.",
                version=release.version,
            )
        )
        action_col.button(
            t("View update"),
            on_click=open_system_workspace,
            width="stretch",
            key="open_system_update",
        )


@st.dialog("Welcome to StreamFetch", width="large")
def render_first_run_dialog() -> None:
    st.markdown(f"## {t('Let’s get your media workspace ready')}")
    st.caption(
        t(
            "StreamFetch checks its local tools first and shows platform-specific help "
            "for anything missing."
        )
    )
    language = st.selectbox(
        t("Language"),
        list(LANGUAGES),
        index=list(LANGUAGES).index(st.session_state.ui_language),
        key="setup_language",
    )
    suggested_media_dir = st.session_state.app_settings.download_dir or "~/Downloads/StreamFetch"
    media_dir = st.text_input(
        t("Media folder"),
        value=suggested_media_dir,
        key="setup_media_dir",
    )
    checks = run_health_checks(Path(media_dir))
    st.markdown(f"### {t('System check')}")
    for check in checks:
        icon = (
            "✅"
            if check.status == HealthStatus.READY
            else "⚠️"
            if check.status == HealthStatus.WARNING
            else "❌"
        )
        st.markdown(f"{icon} **{t(check.name)}** — {t(check.detail)}")
        if check.guidance and check.status != HealthStatus.READY:
            st.code(t(check.guidance), language=None)
    check_updates = st.checkbox(
        t("Automatically check GitHub for StreamFetch updates"),
        value=True,
        key="setup_check_updates",
    )
    if st.button(t("Finish setup"), type="primary", width="stretch"):
        try:
            Path(media_dir).expanduser().mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            st.error(t("The media folder could not be created: {error}", error=exc))
            return
        settings = AppSettings(
            first_run_completed=True,
            language=language,
            download_dir=media_dir,
            check_updates=check_updates,
            auto_update=False,
        )
        save_settings(settings)
        st.session_state.app_settings = settings
        st.session_state.ui_language = language
        st.session_state.output_dir = media_dir
        st.session_state.library_dir = media_dir
        st.session_state.health_checks = checks
        st.rerun()


def preview_selection_key(source_url: str) -> str:
    digest = hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:12]
    return f"preview_selection_{digest}"


def preview_editor_key(source_url: str) -> str:
    return preview_selection_key(source_url).replace("selection", "editor")


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
                selectable = [entry for entry in preview.entries if entry.webpage_url]
                if selectable:
                    selection_key = preview_selection_key(preview.source_url)
                    current = set(
                        st.session_state.get(
                            selection_key,
                            [entry.webpage_url for entry in selectable],
                        )
                    )
                    rows = [
                        {
                            "Selected": entry.webpage_url in current,
                            "Title": entry.title,
                            "Duration": format_duration(entry.duration).removeprefix(" — "),
                            "URL": entry.webpage_url,
                        }
                        for entry in selectable
                    ]
                    with st.expander(t("Select items"), expanded=True):
                        edited = st.data_editor(
                            rows,
                            column_config={
                                "Selected": st.column_config.CheckboxColumn(t("Selected")),
                                "Title": st.column_config.TextColumn(t("Title")),
                                "Duration": st.column_config.TextColumn(t("Duration")),
                            },
                            column_order=("Selected", "Title", "Duration"),
                            disabled=("Title", "Duration", "URL"),
                            hide_index=True,
                            height=min(420, 36 * len(rows) + 38),
                            width="stretch",
                            key=preview_editor_key(preview.source_url),
                        )
                    selected = tuple(row["URL"] for row in edited if row["Selected"])
                    st.session_state[selection_key] = selected
                    st.caption(
                        t(
                            "{count} of {total} selected",
                            count=len(selected),
                            total=len(selectable),
                        )
                    )
                elif preview.entries:
                    with st.expander(t("First {count} entries", count=len(preview.entries))):
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
    return str(st.session_state.app_settings.media_dir)


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
    if st.session_state.use_clip_range and st.session_state.clip_end <= st.session_state.clip_start:
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
        conflict_policy=st.session_state.conflict_policy,
    )
    validate_request(request)
    return request


DOWNLOAD_PRESETS = {
    "Music MP3": {
        "media_type": "audio",
        "audio_format": "mp3",
        "audio_quality": "192K",
        "embed_metadata": True,
        "embed_thumbnail": True,
    },
    "Lossless audio": {
        "media_type": "audio",
        "audio_format": "flac",
        "audio_quality": "0",
        "embed_metadata": True,
        "embed_thumbnail": True,
    },
    "Video 1080p": {
        "media_type": "video",
        "video_format": "mp4",
        "video_quality": "1080p",
        "embed_metadata": True,
        "embed_thumbnail": True,
    },
    "Archive quality": {
        "media_type": "video",
        "video_format": "mkv",
        "video_quality": "best",
        "embed_metadata": True,
        "embed_thumbnail": True,
        "embed_subtitles": True,
    },
}


def apply_download_preset() -> None:
    preset = st.session_state.get("download_preset")
    options = (PresetStore().load().get(preset.removeprefix("saved:"), {})
               if preset and preset.startswith("saved:") else DOWNLOAD_PRESETS.get(preset, {}))
    for key, value in options.items():
        st.session_state[key] = value


def save_user_preset() -> None:
    try:
        name = st.session_state.get("preset_name", "").strip()
        PresetStore().save(name, dict(st.session_state))
        st.session_state.download_preset = f"saved:{name}"
        st.session_state.preset_notice = (
            "Preset saved. Your paths and browser cookies are excluded."
        )
    except (ValueError, OSError) as exc:
        st.session_state.preset_notice = str(exc)


def delete_user_preset() -> None:
    selected = st.session_state.get("download_preset", "")
    if selected.startswith("saved:"):
        try:
            PresetStore().delete(selected.removeprefix("saved:"))
            st.session_state.download_preset = "Custom"
            st.session_state.preset_notice = (
                "Preset deleted. Current download settings are unchanged."
            )
        except OSError:
            st.session_state.preset_notice = (
                "The preset could not be saved. Check folder permissions."
            )


def render_download_sidebar() -> None:
    with st.sidebar:
        st.markdown(sidebar_header_html(t), unsafe_allow_html=True)
        render_language_picker()
        preset_col, apply_col = st.columns([2, 1])
        saved_presets = PresetStore().load()
        preset_choices = ["Custom", *DOWNLOAD_PRESETS, *(f"saved:{name}" for name in saved_presets)]
        if st.session_state.get("download_preset", "Custom") not in preset_choices:
            st.session_state.download_preset = "Custom"
        preset_col.selectbox(
            t("Preset"),
            preset_choices,
            format_func=lambda name: f"★ {name.removeprefix('saved:')}"
            if name.startswith("saved:") else t(name),
            key="download_preset",
        )
        if apply_col.button(t("Apply"), key="apply_download_preset", width="stretch"):
            apply_download_preset()
            st.rerun()
        with st.expander(t("My download presets")):
            st.caption(t(
                "Save the current format and options. Links, folders and cookies stay out."
            ))
            st.text_input(t("Preset name"), max_chars=48, key="preset_name")
            st.button(t("Save / update preset"), on_click=save_user_preset, width="stretch")
            st.button(t("Delete selected preset"), on_click=delete_user_preset,
                      disabled=not st.session_state.download_preset.startswith("saved:"),
                      width="stretch")
            if st.session_state.get("preset_notice"):
                st.caption(t(st.session_state.preset_notice))
        st.radio(
            t("Media type"),
            ["video", "audio"],
            horizontal=True,
            format_func=t,
            key="media_type",
        )

        if st.session_state.media_type == "video":
            st.selectbox(t("Container"), ["mp4", "mkv", "webm"], key="video_format")
            st.selectbox(
                t("Maximum resolution"),
                ["best", "2160p", "1440p", "1080p", "720p", "480p", "360p"],
                index=3,
                key="video_quality",
            )
        else:
            st.selectbox(
                t("Audio format"),
                ["mp3", "m4a", "opus", "flac", "wav"],
                key="audio_format",
            )
            st.selectbox(
                t("Audio quality"),
                ["0", "320K", "256K", "192K", "128K"],
                index=3,
                key="audio_quality",
                help="0 is yt-dlp/FFmpeg's best variable-bitrate setting.",
            )

        st.divider()
        st.checkbox(
            t("Process playlists, channels, sets, and profiles"),
            value=True,
            key="allow_playlists",
        )
        st.checkbox(t("Limit collection size"), value=True, key="use_limit")
        st.number_input(
            t("Maximum items per source"),
            min_value=1,
            max_value=10_000,
            value=50,
            disabled=not st.session_state.use_limit,
            key="max_items",
        )
        st.divider()
        st.checkbox(t("Embed metadata"), value=True, key="embed_metadata")
        st.checkbox(t("Embed thumbnail"), value=True, key="embed_thumbnail")
        st.checkbox(
            t("Embed subtitles"),
            value=False,
            disabled=st.session_state.media_type == "audio",
            key="embed_subtitles",
        )
        st.text_input(
            t("Subtitle languages"),
            value="en,de",
            disabled=not st.session_state.embed_subtitles,
            help="Comma-separated yt-dlp language codes.",
            key="subtitle_languages",
        )

        with st.expander(t("Advanced")):
            st.selectbox(
                t("If a file already exists"),
                ["resume", "skip", "overwrite"],
                format_func=t,
                key="conflict_policy",
            )
            st.selectbox(
                t("Use cookies from browser"),
                ["None", "Chrome", "Firefox", "Edge", "Safari", "Brave"],
                key="cookie_browser",
                help=(
                    "Useful for age-restricted or signed-in content. Cookies stay on this computer."
                ),
            )
            st.slider(
                t("Concurrent fragments"),
                min_value=1,
                max_value=16,
                value=4,
                key="concurrent_fragments",
            )
            st.checkbox(t("Limit bandwidth"), key="use_rate_limit")
            st.number_input(
                t("Bandwidth limit (MB/s)"),
                min_value=0.1,
                max_value=1000.0,
                value=5.0,
                step=0.5,
                disabled=not st.session_state.use_rate_limit,
                key="rate_limit_mbps",
            )
            st.checkbox(t("Download a time range only"), key="use_clip_range")
            clip_start, clip_end = st.columns(2)
            clip_start.number_input(
                t("Start (seconds)"),
                min_value=0.0,
                value=0.0,
                disabled=not st.session_state.use_clip_range,
                key="clip_start",
            )
            clip_end.number_input(
                t("End (seconds)"),
                min_value=0.1,
                value=60.0,
                disabled=not st.session_state.use_clip_range,
                key="clip_end",
            )
            st.checkbox(t("Split files by chapters"), key="split_chapters")
            st.multiselect(
                t("Remove YouTube segments with SponsorBlock"),
                ["sponsor", "intro", "outro", "selfpromo", "interaction", "filler"],
                key="sponsorblock_remove",
                help="Applied only where SponsorBlock data is available.",
            )


def render_library_sidebar() -> None:
    with st.sidebar:
        st.markdown(library_sidebar_html(t), unsafe_allow_html=True)
        render_language_picker()
        default_dir = st.session_state.get("output_dir", default_download_dir())
        st.text_input(t("Library folder"), value=default_dir, key="library_dir")
        st.divider()
        st.text_input(
            t("Search"),
            placeholder=t("Title, artist, album, tag, or path"),
            key="library_search",
        )
        st.selectbox(
            t("Media type"),
            ["all", "audio", "video"],
            format_func=t,
            key="library_media_type",
        )
        st.selectbox(
            t("Sort by"),
            ["newest", "title", "artist", "largest", "oldest"],
            format_func=t,
            key="library_sort",
        )


def render_system_sidebar() -> None:
    with st.sidebar:
        st.markdown(system_sidebar_html(t), unsafe_allow_html=True)
        render_language_picker()
        st.caption(t("StreamFetch {version}", version=__version__))
        st.caption(t(
            "Engine updates use PyPI. App update checks use GitHub. Other checks are local."
        ))


def render_system_view() -> None:
    render_system_sidebar()
    st.markdown(section_label("System"), unsafe_allow_html=True)
    st.markdown(
        '<div class="sf-view-heading">'
        f"<h2>{html.escape(t('System health'))}</h2>"
        f"<p>{html.escape(t('Dependencies, safe updates, and privacy-friendly diagnostics.'))}</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    heading_col, refresh_col = st.columns([3, 1])
    heading_col.markdown(f"### {t('Startup check')}")
    refresh_health = refresh_col.button(
        t("Run checks again"),
        width="stretch",
        key="refresh_health_checks",
    )
    checks = current_health_checks(force=refresh_health)
    columns = st.columns(2)
    for index, check in enumerate(checks):
        with columns[index % 2].container(border=True):
            icon = (
                "✅"
                if check.status == HealthStatus.READY
                else "⚠️"
                if check.status == HealthStatus.WARNING
                else "❌"
            )
            st.markdown(f"### {icon} {t(check.name)}")
            st.caption(t(check.detail))
            if check.guidance and check.status != HealthStatus.READY:
                st.code(t(check.guidance), language=None)

    st.markdown(section_label("Defaults"), unsafe_allow_html=True)
    with st.container(border=True):
        default_media = st.text_input(
            t("Default media folder"),
            value=str(st.session_state.app_settings.media_dir),
            key="system_default_media_dir",
        )
        if st.button(t("Save default folder"), width="stretch"):
            try:
                Path(default_media).expanduser().mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                st.error(t("The media folder could not be created: {error}", error=exc))
            else:
                updated = replace(st.session_state.app_settings, download_dir=default_media)
                save_settings(updated)
                st.session_state.app_settings = updated
                st.session_state.output_dir = default_media
                st.session_state.library_dir = default_media
                st.session_state.pop("health_checks", None)
                st.success(t("Default media folder saved."))

    st.markdown(section_label("Updates"), unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("### yt-dlp")
        st.caption(t("The downloader engine updates automatically from PyPI every six hours, "
                     "independently of StreamFetch releases. Your media stays untouched."))
        if st.button(t("Check engine updates now"), width="stretch"):
            with st.spinner(t("Checking downloader engine…")):
                ensure_engine(force=True)
            st.session_state.pop("health_checks", None)
        engine = engine_status()
        st.caption(t("Active engine: {version}", version=engine.version))
        if engine.error:
            st.warning(t(engine.error))
        elif engine.pending_version:
            st.info(t("yt-dlp {version} is ready. Restart StreamFetch to activate it safely.",
                      version=engine.pending_version))
        elif engine.checked_at:
            st.success(t("Downloader engine is up to date as of the last successful check."))
    settings = st.session_state.app_settings
    with st.container(border=True):
        check_updates = st.checkbox(
            t("Automatically check GitHub for StreamFetch updates"),
            value=settings.check_updates,
            key="system_check_updates",
        )
        auto_update = st.checkbox(
            t("Install updates automatically when it is safe"),
            value=settings.auto_update,
            disabled=not check_updates,
            help=t(
                "Before every installation StreamFetch backs up settings, job state, and "
                "the library database. Media files are never changed."
            ),
            key="system_auto_update",
        )
        settings_col, check_col = st.columns(2)
        if settings_col.button(t("Save update settings"), width="stretch"):
            updated = replace(
                settings,
                check_updates=check_updates,
                auto_update=auto_update,
            )
            save_settings(updated)
            st.session_state.app_settings = updated
            st.toast(t("Update settings saved."))
        if check_col.button(t("Check for updates now"), width="stretch"):
            with st.spinner(t("Checking GitHub releases…")):
                check_for_updates(force=True)

        release = st.session_state.get("latest_release")
        if release:
            st.success(
                t(
                    "Version {version} is ready. A backup is created before installation.",
                    version=release.version,
                )
            )
            install_col, notes_col = st.columns(2)
            if install_col.button(t("Back up and install"), type="primary", width="stretch"):
                with st.spinner(t("Backing up your data and installing the update…")):
                    st.session_state.update_result = apply_update(
                        release,
                        state_dir=default_state_dir(),
                        library_root=Path(
                            st.session_state.get("library_dir", settings.media_dir)
                        ).expanduser(),
                        project_root=Path(__file__).resolve().parent,
                    )
            notes_col.link_button(t("Release notes"), release.url, width="stretch")
        elif not st.session_state.get("update_error"):
            if "latest_release" in st.session_state:
                st.info(t("You are running the latest available version."))
            else:
                st.info(t("App update checks are disabled." if not settings.check_updates
                          else "App updates have not been checked yet."))
        if st.session_state.get("update_error"):
            st.warning(st.session_state.update_error)
        result = st.session_state.get("update_result")
        if result:
            if result.success:
                st.success(t(result.message))
            else:
                st.error(t(result.message))
            if result.backup_file:
                st.caption(t("Backup: {path}", path=result.backup_file))
            if result.downloaded_file:
                st.caption(t("Downloaded update: {path}", path=result.downloaded_file))
                if st.button(
                    t("Open downloaded update"), width="stretch"
                ) and not launch_downloaded_update(result.downloaded_file):
                    st.error(t("The downloaded update could not be opened automatically."))

    st.markdown(section_label("Diagnostics"), unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown(f"### {t('Privacy-safe support bundle')}")
        st.caption(
            t(
                "Contains versions, dependency results, and job counts — never URLs, cookies, "
                "media filenames, or absolute media paths."
            )
        )
        manager = get_download_manager()
        archive = diagnostics_archive(
            checks,
            language=st.session_state.ui_language,
            jobs=manager.snapshots(),
        )
        st.download_button(
            t("Download diagnostics"),
            data=archive,
            file_name=f"streamfetch-diagnostics-{__version__}.zip",
            mime="application/zip",
            width="stretch",
        )


def render_download_view() -> None:
    render_download_sidebar()
    manager = get_download_manager()
    download_description = t(
        "Paste one or more permitted links, choose a format, and let the queue run."
    )

    st.markdown(
        '<div class="sf-view-heading">'
        f"<h2>{html.escape(t('Download studio'))}</h2>"
        f"<p>{html.escape(download_description)}</p>"
        "</div>",
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.markdown(section_label("New download"), unsafe_allow_html=True)
        st.text_input(t("Output directory"), value=default_download_dir(), key="output_dir")
        raw_urls = st.text_area(
            t("YouTube or SoundCloud URLs"),
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
            st.info(t("SoundCloud sources are audio-only. Select **Audio** in the sidebar."))
        accepted = st.checkbox(
            t("I have permission to download these items and accept responsibility for their use.")
        )

        analyze_col, download_col, _ = st.columns([1, 1, 2])
        analyze_clicked = analyze_col.button(t("Analyze"), width="stretch")
        download_clicked = download_col.button(
            t("Start download"), type="primary", width="stretch", disabled=not accepted
        )

    if analyze_clicked:
        analyze(raw_urls)
    if st.session_state.get("previews"):
        st.markdown(section_label("Source preview"), unsafe_allow_html=True)
        for preview in st.session_state.previews:
            render_preview(preview)
        try:
            selected = selected_download_urls(raw_urls)
            media_type = st.session_state.media_type
            quality = (
                st.session_state.audio_quality
                if media_type == "audio"
                else st.session_state.video_quality
            )
            estimate = estimate_download_bytes(
                st.session_state.previews,
                selected,
                media_type,
                quality,
            )
        except ValidationError:
            estimate = None
        if estimate:
            output = Path(st.session_state.output_dir).expanduser()
            existing = output
            while not existing.exists() and existing != existing.parent:
                existing = existing.parent
            try:
                available = shutil.disk_usage(existing).free
            except OSError:
                available = 0
            message = t(
                "Estimated download: about {size} · {available} available",
                size=human_size(estimate),
                available=human_size(available),
            )
            if available and estimate > available:
                st.error(t("Not enough free space. {message}", message=message))
            else:
                st.caption(message)
    if download_clicked:
        enqueue_download(raw_urls, manager)
    render_download_jobs(manager)


def render_library_view() -> None:
    if "pending_library_root" in st.session_state:
        st.session_state.library_dir = st.session_state.pop("pending_library_root")
    render_library_sidebar()
    root = Path(st.session_state.library_dir).expanduser().resolve()
    library = MediaLibrary(root)

    st.markdown(section_label("Local library"), unsafe_allow_html=True)
    st.markdown(
        '<div class="sf-view-heading">'
        f"<h2>{html.escape(t('Your library'))}</h2>"
        f"<p>{html.escape(t('Everything downloaded, imported, organized, and ready to play.'))}</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    refresh_col, path_col = st.columns([1, 3])
    refresh_clicked = refresh_col.button(
        t("Refresh library"),
        type="primary",
        width="stretch",
    )
    path_col.caption(t("Watching {path}", path=root))

    scan_needed = not library.database_path.exists() or st.session_state.get(
        "library_scanned_root"
    ) != str(root)
    try:
        if scan_needed or refresh_clicked:
            with st.spinner(t("Scanning local media…")):
                summary = library.scan()
            st.session_state.library_scanned_root = str(root)
            if refresh_clicked or summary.added or summary.updated or summary.removed:
                st.success(
                    t(
                        "Library refreshed — {added} added, {updated} updated, {removed} removed.",
                        added=summary.added,
                        updated=summary.updated,
                        removed=summary.removed,
                    )
                )
        render_library_import(library)
        stats = library.stats()
    except (OSError, sqlite3.Error) as exc:
        st.error(t("The library could not be opened: {error}", error=exc))
        return

    render_player(library)

    st.markdown(
        '<div class="sf-stats">'
        f'<div class="sf-stat"><span>{html.escape(t("Items"))}</span>'
        f"<strong>{stats.total}</strong></div>"
        f'<div class="sf-stat"><span>{html.escape(t("Audio"))}</span>'
        f"<strong>{stats.audio}</strong></div>"
        f'<div class="sf-stat"><span>{html.escape(t("Video"))}</span>'
        f"<strong>{stats.video}</strong></div>"
        f'<div class="sf-stat"><span>{html.escape(t("Artists"))}</span>'
        f"<strong>{stats.artists}</strong></div>"
        f'<div class="sf-stat"><span>{html.escape(t("Storage"))}</span>'
        f"<strong>{human_size(stats.size_bytes)}</strong></div>"
        "</div>",
        unsafe_allow_html=True,
    )

    section = st.segmented_control(
        t("Library section"),
        ["Home", "Browse", "Discover", "Favorites", "Playlists", "History", "Studio"],
        default="Home",
        selection_mode="single",
        format_func=t,
        key="library_section",
    )
    if section == "Home":
        render_library_home(library)
        return
    if section == "History":
        render_history(library)
        return
    if section == "Playlists":
        render_playlists(library)
        return
    if section == "Discover":
        render_discover(library)
        return
    if section == "Studio":
        render_studio(library, t, render_media_grid)
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

    render_media_grid(library, items, total_matches, key_prefix=section.lower())


def render_library_home(library: MediaLibrary) -> None:
    recent = library.recently_added(limit=6)
    if not recent:
        st.info(t("Your library is ready. Download something or import a media folder to begin."))
        return

    st.markdown(f"### {t('Fresh in your library')}")
    st.caption(t("The newest additions, ready for a first listen."))
    render_media_grid(
        library,
        recent,
        len(recent),
        key_prefix="home_recent",
    )

    most_played = library.most_played(limit=6)
    if most_played:
        st.markdown(f"### {t('Back on repeat')}")
        st.caption(t("Your most-played tracks and videos."))
        render_media_grid(
            library,
            most_played,
            len(most_played),
            key_prefix="home_most_played",
        )


def render_media_grid(
    library: MediaLibrary,
    items: tuple[MediaItem, ...],
    total_matches: int,
    active_playlist_id: int | None = None,
    key_prefix: str = "library",
) -> None:
    if not items:
        st.info(t("No matching media found in this collection."))
        return

    playlists = library.playlists()
    favorite_paths = library.favorite_paths()
    shown = len(items)
    caption_col, play_col = st.columns([3, 1])
    caption_col.caption(
        t("Showing {shown} of {total} matching item(s).", shown=shown, total=total_matches)
    )
    if play_col.button(
        f"▶ {t('Play collection')}",
        key=f"play_collection_{key_prefix}_{active_playlist_id}_{shown}",
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
                    key_prefix,
                )


def render_library_item(
    library: MediaLibrary,
    item: MediaItem,
    favorite_paths: set[str],
    playlists: tuple[Playlist, ...],
    active_playlist_id: int | None = None,
    key_prefix: str = "library",
) -> None:
    relative_path = library.relative_path(item.path)
    digest = hashlib.sha256(relative_path.encode()).hexdigest()[:12]
    item_key = f"{key_prefix}_{digest}"
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

        play_col, favorite_col, more_col = st.columns([2, 1, 1])
        if play_col.button(f"▶ {t('Play')}", key=f"play_{item_key}", width="stretch"):
            select_media(library, item)
        favorite_label = "♥" if relative_path in favorite_paths else "♡"
        if favorite_col.button(
            favorite_label,
            key=f"favorite_{item_key}",
            width="stretch",
            help="Remove favorite" if relative_path in favorite_paths else "Add favorite",
        ):
            library.toggle_favorite(item.path)
            st.rerun()
        with more_col.popover(
            "•••",
            key=f"more_{item_key}",
            help=t("More actions"),
            width="stretch",
        ):
            st.markdown(f"**{item.title}**")
            next_col, queue_col = st.columns(2)
            if next_col.button(t("Play next"), key=f"next_{item_key}", width="stretch"):
                library.enqueue(item.path, play_next=True)
                st.toast(t("{title} will play next.", title=item.title))
                st.rerun()
            if queue_col.button(t("Queue"), key=f"queue_{item_key}", width="stretch"):
                library.enqueue(item.path)
                st.toast(t("Added {title} to the queue.", title=item.title))
                st.rerun()

            if playlists:
                playlist_names = {playlist.id: playlist.name for playlist in playlists}
                playlist_id = st.selectbox(
                    t("Add to playlist"),
                    list(playlist_names),
                    format_func=playlist_names.get,
                    key=f"playlist_select_{item_key}",
                )
                if st.button(t("Add"), key=f"playlist_add_{item_key}", width="stretch"):
                    library.add_to_playlist(playlist_id, item.path)
                    st.toast(
                        t(
                            "Added {title} to {playlist}.",
                            title=item.title,
                            playlist=playlist_names[playlist_id],
                        )
                    )
                    st.rerun()
            if active_playlist_id is not None and st.button(
                t("Remove from playlist"),
                key=f"playlist_remove_{active_playlist_id}_{item_key}",
                width="stretch",
            ):
                library.remove_from_playlist(active_playlist_id, item.path)
                st.rerun()

            st.divider()
            modified = datetime.fromtimestamp(item.modified_at).strftime("%Y-%m-%d %H:%M")
            st.caption(t("{format} · Modified {modified}", format=item.format, modified=modified))
            st.code(str(item.path), language=None)
            st.divider()
            render_metadata_editor(library, item, item_key)


def render_metadata_editor(library: MediaLibrary, item: MediaItem, item_key: str) -> None:
    st.markdown(f"**{t('Edit display metadata')}**")
    st.caption(t("Saved locally; the media file stays unchanged."))
    with st.form(f"metadata_{item_key}"):
        title = st.text_input(t("Title"), value=item.title)
        artist = st.text_input(t("Artist"), value=item.artist)
        album = st.text_input(t("Album"), value=item.album)
        rating = st.select_slider(
            t("Rating"),
            options=[0, 1, 2, 3, 4, 5],
            value=item.rating,
            format_func=lambda value: t("Unrated") if value == 0 else "★" * value,
        )
        tags = st.text_input(
            t("Tags"),
            value=", ".join(item.tags),
            placeholder="focus, live, workout",
        )
        submitted = st.form_submit_button(t("Save metadata"), width="stretch")
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
            st.error(t(str(exc)))
        else:
            st.toast(t("Metadata saved."))
            st.rerun()


def render_library_import(library: MediaLibrary) -> None:
    with st.expander(t("Import a local media folder")):
        st.caption(
            t("Supported audio and video files are copied into Imported/ while preserving folders.")
        )
        source = st.text_input(
            t("Folder to import"),
            placeholder="/Users/you/Music",
            key="library_import_source",
        )
        if st.button(t("Import folder"), key="library_import_button", width="stretch"):
            try:
                with st.spinner(t("Copying media into the library…")):
                    summary = library.import_folder(source)
                    library.scan()
            except (OSError, ValueError, sqlite3.Error) as exc:
                st.error(t("Import failed: {error}", error=exc))
            else:
                st.success(
                    t(
                        "Imported {imported} file(s), skipped {skipped}; "
                        "saved under {destination}.",
                        imported=summary.imported,
                        skipped=summary.skipped,
                        destination=summary.destination,
                    )
                )


def render_discover(library: MediaLibrary) -> None:
    mode = st.selectbox(
        t("Explore your library"),
        [
            "Recently added",
            "Most played",
            "Highly rated",
            "Unplayed",
            "Artists",
            "Albums",
            "Duplicates",
        ],
        format_func=t,
        key="library_discover_mode",
    )
    search = st.session_state.library_search
    media_type = st.session_state.library_media_type
    sort = st.session_state.library_sort

    if mode == "Artists":
        facets = library.artists()
        if not facets:
            st.info(t("No artists found yet."))
            return
        names = {facet.name: f"{facet.name} · {facet.item_count} item(s)" for facet in facets}
        selected = st.selectbox(t("Artist"), list(names), format_func=names.get)
        items = library.items_for_artist(selected)
    elif mode == "Albums":
        facets = library.albums()
        if not facets:
            st.info(t("No albums found yet."))
            return
        names = {facet.name: f"{facet.name} · {facet.item_count} item(s)" for facet in facets}
        selected = st.selectbox(t("Album"), list(names), format_func=names.get)
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
    render_media_grid(
        library,
        items,
        len(items),
        key_prefix=f"discover_{mode.lower().replace(' ', '_')}",
    )


def render_duplicates(library: MediaLibrary) -> None:
    st.caption(t("Files are compared by size and SHA-256 content hash. Nothing is deleted."))
    if st.button(t("Scan for exact duplicates"), type="primary", key="scan_duplicates"):
        with st.spinner(t("Hashing files with matching sizes…")):
            groups = library.duplicate_groups()
        st.session_state.library_duplicate_groups = [
            [library.relative_path(item.path) for item in group] for group in groups
        ]

    stored_groups = st.session_state.get("library_duplicate_groups")
    if stored_groups is None:
        st.info(t("Start a scan to look for byte-identical files."))
        return
    groups = [
        tuple(item for path in paths if (item := library.item_for_path(path)) is not None)
        for paths in stored_groups
    ]
    groups = [group for group in groups if len(group) > 1]
    if not groups:
        st.success(t("No exact duplicates found."))
        return
    st.warning(
        t(
            "Found {count} duplicate group(s). Review the paths before cleanup.",
            count=len(groups),
        )
    )
    for index, group in enumerate(groups, start=1):
        with st.expander(
            t(
                "Duplicate group {index} · {size}",
                index=index,
                size=human_size(group[0].size_bytes),
            ),
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


@st.fragment
def render_player(library: MediaLibrary) -> None:
    hub = playback_hub(library.root)
    owner = st.session_state.setdefault("desktop_owner", uuid4().hex)
    command = hub.take(owner)
    if command:
        if command.get("path"):
            item = library.item_for_path(command["path"])
            if item and item.path.is_file():
                library.set_current_item(item.path)
        elif command["action"] in {"next", "previous"}:
            current = library.current_item()
            item = (
                library.take_queue_entry()
                if command["action"] == "next"
                else library.previous_item(current.path)
                if current
                else None
            )
            if item:
                library.set_current_item(item.path)
            else:
                available = library.list_items(limit=100000)
                if available:
                    index = next((i for i, entry in enumerate(available)
                                  if current and entry.path == current.path), 0)
                    offset = 1 if command["action"] == "next" else -1
                    library.set_current_item(available[(index + offset) % len(available)].path)
            command = {**command, "action": "play", "position": 0}
        st.session_state.desktop_command = command
        st.session_state.desktop_command_root = str(library.root)
    current = library.current_item()
    queue = library.queue()
    if current is None:
        st.info(t("Choose an item to open the floating player."))
        if queue and st.button(t("Play first queued item"), type="primary"):
            item = library.take_queue_entry()
            if item:
                select_media(library, item)
        return

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
        visualizer_mode=library.player_setting("visualizer", "off"),
        labels=dict(player_labels(st.session_state.get("ui_language"))),
        playback_speed=float(library.player_setting("speed", "1")),
        seek_request=st.session_state.get("player_seek_request"),
        library_key=str(library.root),
    )
    player_data["remote_command"] = st.session_state.get("desktop_command") if (
        st.session_state.get("desktop_command_root") == str(library.root)) else None
    player_data["current"]["gain_db"] = (
        loudness_service(library.root).gain(current)
        if (library.player_setting("normalize", "off") == "on")
        else None
    )
    if queue and player_data["next"]:
        player_data["next"]["gain_db"] = loudness_service(library.root).gain(queue[0].item) if (
            library.player_setting("normalize", "off") == "on") else None
    result = render_continuous_player(player_data)
    handle_player_action(library, result, previous)


def handle_player_action(library: MediaLibrary, result, previous: MediaItem | None) -> None:
    action = getattr(result, "action", None)
    if not isinstance(action, dict):
        return
    nonce = action.get("nonce")
    if not nonce or nonce == st.session_state.get("processed_player_action"):
        return
    st.session_state.processed_player_action = nonce

    action_type = action.get("type")
    if action_type in {"telemetry", "remote_ack"}:
        item = library.item_for_path(action.get("path", ""))
        if item:
            hub = playback_hub(library.root)
            before = hub.snapshot()
            published = hub.publish(
                st.session_state.desktop_owner,
                item.path,
                position=action.get("position", 0),
                paused=action.get("paused", True),
                volume=action.get("volume", 1),
                blocked=action.get("blocked", False),
                ack=action.get("ack"),
            )
            if published and (not action.get("paused", True) or
                              before.get("paused") is False or action.get("ack")):
                library.set_playback_position(item.path, float(action.get("position", 0)))
        return
    if action_type == "speed" and action.get("speed") in {0.75, 1, 1.25, 1.5, 2}:
        library.set_player_setting("speed", str(action["speed"]))
        st.rerun()
    if action_type == "bookmark" and isinstance(action.get("position"), (int, float)):
        current = library.current_item()
        if current:
            seconds = float(action["position"])
            ListeningLibrary(library).add_bookmark(current.path, seconds, t("Quick bookmark"))
            st.toast(t("Bookmark saved"))
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
    if action_type == "remove" and isinstance(action.get("entry_id"), int):
        library.remove_queue_entry(action["entry_id"])
        st.rerun()
    if action_type == "shuffle":
        library.shuffle_queue()
        st.rerun()
    if action_type == "clear":
        library.clear_queue()
        st.rerun()
    if action_type == "repeat" and action.get("mode") in {"off", "all", "one"}:
        library.set_player_setting("repeat", action["mode"])
        st.rerun()
    if action_type == "crossfade" and action.get("seconds") in {0, 2, 4, 6}:
        library.set_player_setting("crossfade", str(action["seconds"]))
        st.rerun()
    if action_type == "visualization" and action.get("mode") in {
        "off",
        "spectrum",
        "waveform",
    }:
        library.set_player_setting("visualizer", action["mode"])
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
        t("New playlist"),
        placeholder=t("Road trip, Focus, Favorites…"),
        key="new_playlist_name",
    )
    if button_col.button(t("Create"), type="primary", width="stretch"):
        try:
            playlist = library.create_playlist(playlist_name)
        except ValueError as exc:
            st.error(t(str(exc)))
        else:
            st.session_state.selected_playlist_id = playlist.id
            st.rerun()

    playlists = library.playlists()
    if not playlists:
        st.info(t("Create your first playlist, then add tracks from Browse or Favorites."))
        return

    playlist_names = {
        playlist.id: f"{playlist.name} · {playlist.item_count} item(s)" for playlist in playlists
    }
    valid_ids = set(playlist_names)
    selected_id = st.session_state.get("selected_playlist_id")
    if selected_id not in valid_ids:
        selected_id = playlists[0].id
    selected_id = st.selectbox(
        t("Playlist"),
        list(playlist_names),
        index=list(playlist_names).index(selected_id),
        format_func=playlist_names.get,
        key="playlist_browser",
    )
    st.session_state.selected_playlist_id = selected_id

    delete_col, _ = st.columns([1, 3])
    if delete_col.button(t("Delete playlist"), width="stretch"):
        library.delete_playlist(selected_id)
        st.session_state.pop("selected_playlist_id", None)
        st.rerun()

    items = filter_collection(
        library.playlist_items(selected_id),
        st.session_state.library_search,
        st.session_state.library_media_type,
        st.session_state.library_sort,
    )
    render_media_grid(
        library,
        items,
        len(items),
        active_playlist_id=selected_id,
        key_prefix=f"playlist_{selected_id}",
    )


def render_history(library: MediaLibrary) -> None:
    entries = library.history()
    if not entries:
        st.info(t("Play something and it will appear here."))
        return
    st.caption(t("Your latest {count} play action(s).", count=len(entries)))
    for entry in entries:
        with st.container(border=True):
            st.markdown('<span class="sf-history-marker"></span>', unsafe_allow_html=True)
            text_col, time_col, play_col = st.columns([3, 2, 1])
            text_col.markdown(f"**{entry.item.title}**  \n{entry.item.artist}")
            played = datetime.fromtimestamp(entry.played_at).strftime("%Y-%m-%d %H:%M")
            time_col.caption(t("Played {time}", time=played))
            if play_col.button(t("Play"), key=f"history_play_{entry.id}", width="stretch"):
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
    folder_watcher(str(default_state_dir()))
    initialize_startup_services()
    if not st.session_state.app_settings.first_run_completed:
        render_first_run_dialog()
    render_startup_notices()
    workspace = st.segmented_control(
        t("Workspace"),
        ["Download", "Library", "Subscriptions", "System"],
        default="Library",
        selection_mode="single",
        format_func=t,
        key="workspace",
    )
    if workspace == "Library":
        render_library_view()
    elif workspace == "System":
        render_system_view()
    elif workspace == "Subscriptions":
        render_subscriptions(
            get_subscription_service(), default_download_dir(), t, render_language_picker
        )
    else:
        render_download_view()


def analyze(raw_urls: str) -> None:
    st.session_state.pop("previews", None)
    try:
        urls = parse_urls(raw_urls)
        downloader = Downloader()
        configured_limit = (
            int(st.session_state.max_items) if st.session_state.get("use_limit") else 200
        )
        preview_limit = min(configured_limit, 500)
        with st.spinner(t("Reading source information…")):
            for url in urls:
                st.session_state.pop(preview_selection_key(url), None)
                st.session_state.pop(preview_editor_key(url), None)
            st.session_state.previews = [
                downloader.inspect(url, limit=preview_limit) for url in urls
            ]
    except ValidationError as exc:
        st.error(t(str(exc)))
    except DownloaderError as exc:
        render_download_failure(str(exc))


def selected_download_urls(raw_urls: str) -> tuple[str, ...]:
    urls = parse_urls(raw_urls)
    previews = tuple(st.session_state.get("previews", ()))
    selections: dict[str, tuple[str, ...]] = {}
    for url in urls:
        preview = next((item for item in previews if item.source_url == url), None)
        selectable = (
            tuple(entry.webpage_url for entry in preview.entries if entry.webpage_url)
            if preview
            else ()
        )
        if selectable:
            selections[url] = tuple(st.session_state.get(preview_selection_key(url), selectable))
    unique = resolve_selected_urls(urls, previews, selections)
    if not unique:
        raise ValidationError("Select at least one item from the analyzed collection.")
    return unique


@st.cache_resource
def shared_download_manager(state_path: str) -> DownloadJobManager:
    return DownloadJobManager(max_workers=2, state_path=Path(state_path))


def get_download_manager() -> DownloadJobManager:
    return shared_download_manager(str(default_job_state_path()))


@st.cache_resource
def shared_subscription_service(state_dir: str) -> SubscriptionService:
    return SubscriptionService(
        SubscriptionStore(Path(state_dir) / "subscriptions.db"), get_download_manager()
    )


def get_subscription_service() -> SubscriptionService:
    return shared_subscription_service(str(default_state_dir()))


def enqueue_download(raw_urls: str, manager: DownloadJobManager) -> None:
    try:
        urls = selected_download_urls(raw_urls)
        request = build_request(urls)
    except ValidationError as exc:
        st.error(t(str(exc)))
        return
    if shutil.which("ffmpeg") is None:
        st.error(t("FFmpeg was not found. Install FFmpeg and restart the app before downloading."))
        return
    job_ids = manager.submit(request)
    st.success(t("Queued {count} background download job(s).", count=len(job_ids)))


def render_download_failure(error: str) -> None:
    failure = classify_download_error(error)
    st.error(t(failure.title))
    st.caption(t(failure.guidance))
    with st.expander(t("Technical details")):
        st.code(safe_error_detail(error), language=None)


@st.fragment(run_every=1.0)
def render_download_jobs(manager: DownloadJobManager) -> None:
    jobs = manager.snapshots()
    if not jobs:
        return

    st.markdown(section_label("Download activity"), unsafe_allow_html=True)
    heading_col, clear_col = st.columns([3, 1])
    heading_col.caption(t("Downloads are saved locally and survive full app restarts."))
    if clear_col.button(t("Clear finished"), width="stretch", key="jobs_clear_finished"):
        manager.remove_finished()
        st.rerun(scope="fragment")

    for job in jobs:
        with st.container(border=True):
            title_col, status_col = st.columns([3, 1])
            title_col.markdown(f"**{job.url}**")
            status_col.caption(t(job.status.value).upper())
            st.progress(job.progress, text=t(job.message))

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
                render_download_failure(job.error)

            action_col, cancel_col, files_col = st.columns([1, 1, 2])
            if job.status in {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.PAUSING}:
                if action_col.button(t("Pause"), key=f"pause_{job.id}", width="stretch"):
                    manager.pause(job.id)
                    st.rerun(scope="fragment")
            elif job.status is JobStatus.PAUSED:
                if action_col.button(t("Resume"), key=f"resume_{job.id}", width="stretch"):
                    manager.resume(job.id)
                    st.rerun(scope="fragment")
            elif job.status is JobStatus.FAILED and action_col.button(
                t("Retry"), key=f"retry_{job.id}", width="stretch"
            ):
                manager.retry(job.id)
                st.rerun(scope="fragment")

            if job.status in {
                JobStatus.QUEUED,
                JobStatus.RUNNING,
                JobStatus.PAUSING,
                JobStatus.PAUSED,
                JobStatus.FAILED,
            } and cancel_col.button(
                t("Cancel"),
                key=f"cancel_{job.id}",
                help=t("Stop this job and remove only its temporary partial files."),
                width="stretch",
            ):
                manager.cancel(job.id, cleanup_partial=True)
                st.rerun(scope="fragment")

            if job.files:
                files_col.caption(
                    t("Created: {files}", files=", ".join(path.name for path in job.files[:4]))
                )
                st.session_state.pop("library_scanned_root", None)


if __name__ == "__main__":
    main()
