"""Offline download inbox. The callback opens the existing confirmation workflow."""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from .inbox import InboxStore

STATUS_LABELS = {"ready": "Ready", "handed_off": "Sent to Downloads", "archived": "Archived"}


def render_inbox(t: Callable, open_download_callback: Callable[[tuple[str, ...]], None]) -> None:
    """Render offline inbox; callback receives URLs, never starts jobs itself.

    Entries are marked handed_off before the callback, so a callback can safely
    trigger st.rerun(). On the download screen, let users review options and
    permissions before submitting to the existing job manager. A handoff is not
    proof of a submitted or successful download. ``restore`` is always explicit.
    """
    store = InboxStore()
    st.markdown(f"## {t('Capture now. Download when ready.')}")
    st.caption(t("Save links privately on this device. "
                 "Nothing downloads until you confirm in Downloads."))
    with st.form("inbox_capture", clear_on_submit=True):
        raw = st.text_area(t("YouTube or SoundCloud links"), key="inbox_links",
                           placeholder="https://www.youtube.com/watch?v=…", height=110)
        note = st.text_input(t("Note (optional)"), max_chars=2000, key="inbox_new_note")
        saved = st.form_submit_button(t("Save to inbox"), type="primary")
    if saved:
        try:
            inserted, duplicates = store.add_batch(raw, note)
            st.success(t("Saved {count} links. {duplicates} duplicates kept unchanged.",
                         count=inserted, duplicates=duplicates))
        except (ValueError, OSError) as exc:
            st.error(t(str(exc)))

    filters = st.columns((1, 2))
    status = filters[0].selectbox(t("Inbox status"), ["ready", "handed_off", "archived", "all"],
                                 format_func=lambda value: t(STATUS_LABELS.get(value, "All")),
                                 key="inbox_status")
    search = filters[1].text_input(t("Search links and notes"), max_chars=200, key="inbox_search")
    entries = store.list_entries(status=None if status == "all" else status, search=search)
    if not entries:
        st.info(t("Your inbox is clear. Save a link to plan your next download."))
        return
    st.caption(t("Showing up to 200 entries. Select up to 100 links per action."))
    choices = {entry.id: entry for entry in entries}
    selected = st.multiselect(t("Select inbox entries"), list(choices),
                              format_func=lambda i: f"#{i} · {choices[i].url}",
                              max_selections=100, key="inbox_selected")
    actions = st.columns(3)
    if actions[0].button(t("Review in Downloads"), disabled=not selected, key="inbox_handoff"):
        try:
            urls = store.handoff(selected)
        except ValueError as exc:
            st.error(t(str(exc)))
        else:
            st.session_state.inbox_handoff_ids = tuple(selected)
            st.session_state.pop("inbox_selected", None)
            open_download_callback(urls)
            st.rerun()
    if actions[1].button(t("Archive selected"), disabled=not selected, key="inbox_archive"):
        store.archive(selected)
        st.session_state.pop("inbox_selected", None)
        st.rerun()
    if actions[2].button(t("Make ready again"), disabled=not selected, key="inbox_restore"):
        store.restore(selected)
        st.session_state.pop("inbox_selected", None)
        st.rerun()
    st.caption(t("Sent to Downloads means opened for review, not started or completed."))
    for entry in entries:
        with st.expander(f"#{entry.id} · {t(STATUS_LABELS[entry.status])} · {entry.url}"):
            st.text(entry.url)
            st.caption(t("Saved: {created} · Updated: {updated}",
                         created=entry.created_at, updated=entry.updated_at))
            with st.form(f"inbox_note_form_{entry.id}"):
                edited = st.text_area(t("Note"), value=entry.note, max_chars=2000,
                                      key=f"inbox_note_{entry.id}")
                if st.form_submit_button(t("Save note")):
                    store.update_note(entry.id, edited)
                    st.rerun()
            if entry.job_ids:
                st.caption(t("Linked jobs: {jobs}", jobs=", ".join(entry.job_ids)))
