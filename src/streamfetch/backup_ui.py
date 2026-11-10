"""Workspace backup and side-by-side recovery controls."""

import sqlite3
from pathlib import Path

import streamlit as st

from streamfetch.backup import (
    create_workspace_backup,
    inspect_workspace_backup,
    restore_workspace_backup,
)


def render_workspace_backup(libraries, t):
    with st.expander(t("Workspace backup and recovery")):
        st.caption(t("Save library metadata and optionally copy the original files."))
        destination = st.text_input(t("New backup folder"), key="backup_destination")
        originals = st.checkbox(t("Include original media files"), key="backup_originals")
        if st.button(t("Create workspace backup"), disabled=not destination.strip()):
            try:
                with st.spinner(t("Creating workspace backup…")):
                    created = create_workspace_backup(
                        libraries, Path(destination.strip()), include_originals=originals
                    )
                st.success(t("Backup created"))
                st.text(str(created))
            except (OSError, ValueError, sqlite3.Error) as exc:
                st.error(str(exc))
        source = st.text_input(t("Existing backup folder"), key="backup_source")
        restore_to = st.text_input(t("New recovery folder"), key="backup_restore_to")
        if st.button(t("Verify and preview backup"), disabled=not source.strip()):
            try:
                names, has_originals, count = inspect_workspace_backup(Path(source.strip()))
                st.session_state.backup_preview = (source, names, has_originals, count)
            except (OSError, ValueError, sqlite3.Error) as exc:
                st.session_state.pop("backup_preview", None)
                st.error(str(exc))
        preview = st.session_state.get("backup_preview")
        if preview and preview[0] == source:
            _, names, has_originals, count = preview
            st.text(", ".join(names))
            st.caption(t("Files verified: {count}", count=count))
            st.caption(t("Originals included") if has_originals else t("Metadata only"))
            if st.button(t("Restore into new folder"), disabled=not restore_to.strip()):
                try:
                    with st.spinner(t("Restoring workspace backup…")):
                        restored = restore_workspace_backup(
                            Path(source.strip()), Path(restore_to.strip())
                        )
                    st.success(t("Recovery complete. Open these folders in Library."))
                    for root in restored:
                        st.text(str(root))
                except (OSError, ValueError, sqlite3.Error) as exc:
                    st.error(str(exc))
