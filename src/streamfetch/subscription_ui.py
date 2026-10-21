"""Streamlit workspace for source subscriptions."""

from __future__ import annotations

import hashlib
import html
import sqlite3
from datetime import datetime

import streamlit as st

from streamfetch.subscriptions import PROFILES, SubscriptionService
from streamfetch.theme import LOGO_SVG


def render_subscriptions(service: SubscriptionService, media_root: str, t, language_picker):
    with st.sidebar:
        st.markdown(
            '<div class="sf-sidebar-brand"><div class="sf-sidebar-brand__top">'
            f'<span class="sf-logo">{LOGO_SVG}</span><strong>{t("Your sources.")}</strong>'
            f"</div><span>{t('Follow · preview · sync')}</span></div>",
            unsafe_allow_html=True,
        )
        st.caption(t("Checks discover new items. You choose what to download."))
        st.caption(t("Scheduled checks run only while StreamFetch is running."))
        st.caption(t("Downloads appear in the library of each source’s media folder."))
        language_picker()
    st.markdown(
        '<div class="sf-section-label">STREAMFETCH 1.3</div>'
        f'<div class="sf-view-heading"><h2>{html.escape(t("Subscriptions"))}</h2>'
        f"<p>{html.escape(t('Your favorite sources. Just the new arrivals.'))}</p></div>",
        unsafe_allow_html=True,
    )
    with st.expander(t("Add a source"), expanded=not service.store.sources(), key="add_source"):
        source_form(service, media_root, t)
    sources = service.store.sources()
    if not sources:
        st.info(t("Save a YouTube channel, playlist, or SoundCloud profile to get started."))
        return
    labels = {source["id"]: source["name"] for source in sources}
    source_id = st.selectbox(
        t("Source"), list(labels), format_func=labels.get, key="subscription_selected"
    )
    source = service.store.source(source_id)
    with st.expander(t("Source settings"), key=f"source_settings_{source_id}"):
        source_form(service, media_root, t, source)
        enabled = st.checkbox(
            t("Enable scheduled checks"),
            value=bool(source["enabled"]),
            key=f"source_enabled_{source_id}",
        )
        if enabled != bool(source["enabled"]):
            service.store.toggle(source_id, enabled)
        st.caption(t("Removing a source keeps its downloaded files and local playlist."))
        confirmed = st.checkbox(t("Remove this subscription"), key=f"remove_confirm_{source_id}")
        if st.button(t("Remove source"), disabled=not confirmed or service.busy(source_id)):
            try:
                service.store.delete(source_id)
            except ValueError as exc:
                st.error(t(str(exc)))
            else:
                st.rerun()
    source_activity(service, source_id, t)


def source_form(service, media_root, t, source=None):
    suffix = source["id"] if source else "new"
    value = source or {}
    with st.form(f"source_form_{suffix}"):
        name = st.text_input(t("Source name"), value=value.get("name", ""), max_chars=60)
        url = st.text_input(
            t("Source URL"),
            value=value.get("url", ""),
            placeholder="https://www.youtube.com/@creator/videos",
            disabled=source is not None,
        )
        profile = st.selectbox(
            t("Preset"),
            list(PROFILES),
            format_func=t,
            index=list(PROFILES).index(value.get("profile", "Music MP3")),
        )
        root = st.text_input(
            t("Media folder"), value=value.get("root", media_root), disabled=source is not None
        )
        left, right = st.columns(2)
        batch = left.number_input(
            t("Maximum new downloads per sync"),
            min_value=1,
            max_value=100,
            value=value.get("batch_limit", 20),
        )
        scan = right.number_input(
            t("Items to inspect per check"),
            min_value=1,
            max_value=500,
            value=value.get("scan_limit", 200),
        )
        st.caption(
            t("Each check inspects this source window; older items outside it are retained.")
        )
        startup = st.checkbox(
            t("Check this source when StreamFetch starts"),
            value=bool(value.get("check_on_start", False)),
        )
        intervals = {
            0: t("Manual only"),
            15: t("Every 15 minutes"),
            30: t("Every 30 minutes"),
            60: t("Hourly"),
            360: t("Every 6 hours"),
            1440: t("Daily"),
        }
        interval = st.selectbox(
            t("Check interval"),
            list(intervals),
            format_func=intervals.get,
            index=list(intervals).index(value.get("interval_minutes", 0)),
        )
        playlist = st.checkbox(
            t("Maintain a local playlist in source order"),
            value=bool(value.get("make_playlist", True)),
        )
        if st.form_submit_button(t("Save source"), type="primary", width="stretch"):
            try:
                service.store.save(
                    name=name,
                    url=url,
                    profile=profile,
                    root=root,
                    batch_limit=int(batch),
                    scan_limit=int(scan),
                    check_on_start=startup,
                    interval_minutes=interval,
                    make_playlist=playlist,
                    source_id=source["id"] if source else None,
                )
            except (ValueError, OSError, sqlite3.Error) as exc:
                st.error(t(str(exc)))
            else:
                st.rerun()


@st.fragment(run_every=3)
def source_activity(service, source_id, t):
    source = service.store.source(source_id)
    items = service.store.items(source_id)
    candidates = [item for item in items if item["status"] in {"new", "failed", "cancelled"}]
    pending = [item for item in items if item["status"] == "queued"]
    complete = [item for item in items if item["status"] == "downloaded"]
    busy = service.busy(source_id)
    a, b, c = st.columns(3)
    a.metric(t("Ready to sync"), len(candidates))
    b.metric(t("In progress"), len(pending))
    c.metric(t("In your library"), len(complete))
    st.caption(f"{source['profile']} · {source['url']}")
    checked = (
        datetime.fromtimestamp(source["checked_at"]).strftime("%Y-%m-%d %H:%M")
        if source["checked_at"]
        else t("Not checked yet")
    )
    st.caption(f"{t('Last checked')}: {checked}")
    if source["error"]:
        st.error(source["error"])
    if busy:
        st.info(t("Checking source… You can keep using the app."))
    if st.button(t("Check for new items"), disabled=busy, width="stretch"):
        service.request_check(source_id)
        st.rerun(scope="fragment")
    if candidates:
        st.markdown(f"### {t('New arrivals')}")
        item_labels = {item["key"]: f"{item['title']} · {t(item['status'])}" for item in candidates}
        revision = hashlib.sha256("|".join(item_labels.values()).encode()).hexdigest()[:12]
        chosen = st.multiselect(
            t("Choose items to sync"),
            list(item_labels),
            default=list(item_labels)[: source["batch_limit"]],
            format_func=item_labels.get,
            key=f"sync_items_{source_id}_{revision}",
        )
        st.caption(
            t("At most {count} selected items are queued per sync.", count=source["batch_limit"])
        )
        for item in candidates:
            if item["error"]:
                st.caption(f"{item['title']}: {item['error']}")
        accepted = st.checkbox(
            t("I have permission to download these items and accept responsibility for their use."),
            key=f"sync_permission_{source_id}",
        )
        if st.button(
            t("Sync selected"),
            type="primary",
            disabled=busy or not chosen or not accepted,
            width="stretch",
        ):
            try:
                count = service.queue(source_id, chosen)
            except (ValueError, OSError) as exc:
                st.error(t(str(exc)))
            else:
                st.toast(t("Queued {count} background download job(s).", count=count))
                st.rerun(scope="fragment")
    elif source["checked_at"] and not busy and not pending:
        st.success(t("You’re up to date. Check again for new arrivals."))
    if pending:
        snapshots = {job.id: job for job in service.jobs.snapshots()}
        with st.expander(t("Sync activity"), expanded=True, key=f"sync_activity_{source_id}"):
            for item in pending:
                job = snapshots.get(item["job_id"])
                if job:
                    st.progress(job.progress, text=f"{item['title']} · {t(job.status.value)}")
                    if job.status.value == "paused" and st.button(
                        t("Resume"), key=f"sync_resume_{job.id}"
                    ):
                        service.jobs.resume(job.id)
                    if st.button(t("Cancel"), key=f"sync_cancel_{job.id}"):
                        service.jobs.cancel(job.id, cleanup_partial=True)
    with st.expander(t("Sync history"), expanded=not candidates, key=f"sync_history_{source_id}"):
        history = service.store.history(source_id)
        if history:
            st.dataframe(
                [
                    {
                        t("Time"): datetime.fromtimestamp(row["created_at"]).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                        t("Activity"): t(row["kind"]),
                        t("Details"): row["detail"],
                    }
                    for row in history
                ],
                hide_index=True,
                width="stretch",
            )
        else:
            st.caption(t("Your first source check will appear here."))
