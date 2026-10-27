"""Explicit multi-page library selection and portable offline collections."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from .collections import MAX_COLLECTION_TRACKS, Collections
from .library import MediaLibrary


def render_collections(library: MediaLibrary, t) -> None:
    st.subheader(t("Collections"))
    st.caption(t("Curate together. Take your originals anywhere."))
    scope = str(library.root)
    if st.session_state.get("collections_library") != scope:
        previous = st.session_state.pop("collections_export_artifact", None)
        if previous is not None:
            previous.remove()
        st.session_state["collections_library"] = scope
        st.session_state["collections_selected"] = []
    selected = list(st.session_state.get("collections_selected", []))
    search = st.text_input(t("Search title, artist, album or tag"), key="collections_search")
    filters = st.columns(3)
    media_type = filters[0].selectbox(
        t("Media type"), ("all", "audio", "video"), format_func=t, key="collections_type"
    )
    sort = filters[1].selectbox(
        t("Sort"),
        ("newest", "title", "artist", "largest", "oldest"),
        format_func=t,
        key="collections_sort",
    )
    count = library.count_items(search=search, media_type=media_type)
    pages = max(1, (count + 24) // 25)
    page = filters[2].selectbox(t("Page"), range(1, pages + 1), key="collections_page")
    items = library.list_items(
        search=search, media_type=media_type, sort=sort, limit=25, offset=(page - 1) * 25
    )
    st.caption(
        f"{t('Matching tracks')}: {count} · "
        f"{t('Selected across pages')}: {len(selected)}/{MAX_COLLECTION_TRACKS}"
    )
    controls = st.columns(2)
    if controls[0].button(t("Select this page"), key="collections_select_page"):
        requested = list(
            dict.fromkeys([*selected, *(library.relative_path(i.path) for i in items)])
        )
        if len(requested) > MAX_COLLECTION_TRACKS:
            st.warning(t("Select at most 200 tracks per collection."))
        else:
            selected = requested
    if controls[1].button(t("Clear selection"), key="collections_clear"):
        selected = []
    current_keys = [library.relative_path(item.path) for item in items]
    if items:
        table = [
            {
                t("Select"): key in selected,
                t("Title"): item.title,
                t("Artist"): item.artist,
                t("Album"): item.album,
                t("Format"): item.format,
                t("Added"): datetime.fromtimestamp(item.added_at).strftime("%Y-%m-%d"),
            }
            for key, item in zip(current_keys, items, strict=True)
        ]
        # A changing key resets the editor when selection controls or filters change.
        key = f"collections_editor_{scope}_{search}_{media_type}_{sort}_{page}_{','.join(selected)}"
        edited = st.data_editor(
            table,
            hide_index=True,
            key=key,
            width="stretch",
            disabled=[t("Title"), t("Artist"), t("Album"), t("Format"), t("Added")],
        )
        checked = {path for path, row in zip(current_keys, edited, strict=True) if row[t("Select")]}
        selected = [path for path in selected if path not in current_keys or path in checked]
        selected.extend(path for path in current_keys if path in checked and path not in selected)
    else:
        st.info(t("No matching tracks. Download or import media, then refresh the library."))
    st.session_state["collections_selected"] = selected
    st.caption(
        t("Selection stays explicit across filters and pages. Originals are never modified.")
    )
    service = Collections(library)
    actions = st.columns(3)
    for column, label, action in (
        (actions[0], "Add favorites", "favorite"),
        (actions[1], "Remove favorites", "unfavorite"),
        (actions[2], "Add to queue", "queue"),
    ):
        if column.button(t(label), disabled=not selected, key=f"collections_{action}"):
            try:
                changed = service.apply(selected, action)
                st.success(f"{t('Tracks updated')}: {changed}")
            except (ValueError, OSError) as exc:
                st.error(t(str(exc)))
    playlists = library.playlists()
    playlist_ids = [None, *(playlist.id for playlist in playlists)]
    playlist_names = {playlist.id: playlist.name for playlist in playlists}
    playlist_id = st.selectbox(
        t("Destination playlist"),
        playlist_ids,
        format_func=lambda value: playlist_names.get(value, t("New playlist")),
        key="collections_playlist",
    )
    name = (
        st.text_input(t("Playlist name"), key="collections_playlist_name")
        if playlist_id is None
        else ""
    )
    if st.button(
        t("Save selection to playlist"), disabled=not selected, key="collections_save_playlist"
    ):
        try:
            changed = service.apply(
                selected, "playlist", playlist_id=playlist_id, playlist_name=name
            )
            st.success(f"{t('Tracks updated')}: {changed}")
        except (ValueError, OSError) as exc:
            st.error(t(str(exc)))
    st.markdown(f"### {t('Offline collection')}")
    st.caption(t("ZIP with untouched originals, a relative M3U8 playlist and portable metadata."))
    st.caption(t("Up to 200 tracks / 200 MiB including archive metadata."))
    st.caption(t("Embedded original-file metadata is preserved."))
    if st.button(t("Build offline ZIP"), disabled=not selected, key="collections_export"):
        previous = st.session_state.get("collections_export_artifact")
        try:
            with st.spinner(t("Preparing original files…")):
                st.session_state["collections_export_artifact"] = service.export(selected)
            if previous is not None:
                previous.remove()
        except (ValueError, OSError) as exc:
            st.error(t(str(exc)))
    artifact = st.session_state.get("collections_export_artifact")
    if artifact is not None and artifact.path.is_file():
        st.caption(
            f"{artifact.item_count} {t('tracks')} · {artifact.size_bytes / 1024 / 1024:.1f} MiB"
        )
        if artifact.path.stat().st_size <= 200 * 1024 * 1024:
            with artifact.path.open("rb") as handle:
                st.download_button(
                    t("Download offline collection"),
                    handle,
                    file_name="StreamFetch-collection.zip",
                    mime="application/zip",
                    key="collections_download",
                )
        if st.button(t("Remove prepared ZIP"), key="collections_remove_export"):
            artifact.remove()
            st.session_state.pop("collections_export_artifact", None)
            st.rerun()
