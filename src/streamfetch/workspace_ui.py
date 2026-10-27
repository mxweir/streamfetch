"""Focused home and offline search surfaces for StreamFetch 2.0."""

import re

import streamlit as st

from streamfetch.workspace import overview, search


def _time(seconds):
    seconds = max(0, int(seconds or 0))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _item(item, t, play, key, seconds=None, detail=""):
    with st.container(border=True):
        # Source titles are untrusted text, not Markdown image/link instructions.
        title = re.sub(r"([\\`*_{}\[\]<>()#+.!|~-])", r"\\\1", item.title)
        st.markdown(f"**{title}**")
        detail_line = f"{item.artist} · {item.format.upper()}"
        detail_line += f" · {_time(seconds)}" if seconds is not None else ""
        st.caption(re.sub(r"([\\`*_{}\[\]<>()#+.!|~-])", r"\\\1", detail_line))
        if detail:
            st.text(detail)
        if st.button(
            t("Resume") if seconds is not None else t("Play"), key=key, use_container_width=True
        ):
            play(item, seconds)


def render_overview(library, manager, t, navigate, play):
    data = overview(library)
    st.header(t("Your media, ready when you are"))
    st.caption(t("Continue listening, find a moment, or bring something new into your library."))
    actions = [
        ("Download", "download", None),
        ("Inbox", "inbox", None),
        ("Library", "library", None),
        ("Home network", "studio", "sharing"),
        ("System", "system", None),
    ]
    for column, (label, workspace, section) in zip(st.columns(len(actions)), actions, strict=True):
        if column.button(t(label), key=f"overview-go-{workspace}", use_container_width=True):
            navigate(workspace, section)
    columns = st.columns(3)
    for column, label, value in zip(
        columns,
        ("Indexed media", "Audio", "Video"),
        (data.total, data.audio, data.video),
        strict=True,
    ):
        column.metric(t(label), value)
    jobs = manager.snapshots() if manager is not None else ()
    active = [
        job for job in jobs if str(job.status) in {"queued", "running", "pausing", "cancelling"}
    ]
    failed = [job for job in jobs if str(job.status) == "failed"]
    if active or failed:
        st.subheader(t("Downloads at a glance"))
        st.caption(f"{t('Active')}: {len(active)} · {t('Failed')}: {len(failed)}")
        for job in (active + failed)[:5]:
            with st.container(border=True):
                st.write(job.filename or job.url)
                st.caption(t(str(job.status).capitalize()))
                if job in active:
                    st.progress(min(1.0, max(0.0, float(job.progress or 0))))
        if st.button(t("Open downloads"), key="overview-downloads"):
            navigate("download", None)
    if data.resume:
        st.subheader(t("Continue listening"))
        columns = st.columns(min(3, len(data.resume)))
        for index, entry in enumerate(data.resume):
            with columns[index % len(columns)]:
                _item(entry.item, t, play, f"overview-resume-{index}", entry.seconds)
    if data.recent:
        st.subheader(t("Recently added"))
        columns = st.columns(min(3, len(data.recent)))
        for index, item in enumerate(data.recent):
            with columns[index % len(columns)]:
                _item(item, t, play, f"overview-recent-{index}")
    else:
        st.info(
            t(
                "Your library starts here. Download permitted media "
                "or import your existing collection in Library."
            )
        )


def render_search(library, t, play):
    st.header(t("Find a track. Discover a moment."))
    st.caption(
        t(
            "Search your library, bookmarks and saved transcripts. "
            "Entirely local, no AI download required."
        )
    )
    query = st.text_input(t("Search your media"), max_chars=200, key="workspace-query")
    kinds = {
        t("Everything"): "all",
        t("Tracks & videos"): "metadata",
        t("Bookmarks"): "bookmark",
        t("Transcript moments"): "transcript",
    }
    selected = st.radio(t("Search in"), list(kinds), horizontal=True, key="workspace-kind")
    fingerprint = (str(library.root), query, kinds[selected])
    if st.session_state.get("workspace-search-fingerprint") != fingerprint:
        st.session_state["workspace-search-fingerprint"] = fingerprint
        st.session_state["workspace-search-offset"] = 0
        st.session_state["workspace-search-history"] = []
    if not query.strip():
        st.info(t("Try a title, artist, bookmark label or a phrase from a saved transcript."))
        return
    cursor = st.session_state.get("workspace-search-offset", 0)
    page = search(library, query, kind=kinds[selected], offset=cursor)
    if not page.hits:
        st.info(t("No matching media on this page. Try another phrase or category."))
    labels = {
        "metadata": "Tracks & videos",
        "bookmark": "Bookmarks",
        "transcript": "Transcript moments",
    }
    for hit in page.hits:
        st.caption(t(labels[hit.kind]))
        _item(hit.item, t, play, f"search-{hit.identity}", hit.seconds, hit.text)
    previous, following = st.columns(2)
    history = st.session_state.get("workspace-search-history", [])
    if previous.button(t("Previous page"), disabled=not history, key="search-previous"):
        st.session_state["workspace-search-offset"] = history[-1]
        st.session_state["workspace-search-history"] = history[:-1]
        st.rerun()
    if following.button(t("Next page"), disabled=page.next_offset is None, key="search-next"):
        st.session_state["workspace-search-history"] = history + [cursor]
        st.session_state["workspace-search-offset"] = page.next_offset
        st.rerun()
