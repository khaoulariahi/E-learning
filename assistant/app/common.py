"""Shared UI pieces: one-time init, notebook sidebar, job progress panel."""

import streamlit as st

from assistant.core.db import init_db
from assistant.core.notebooks import Notebook, create_notebook, list_notebooks
from assistant.core.runtime import limiter
from assistant.core.runtime.progress import JobProgress, notebook_jobs
from assistant.core.runtime.queue import get_queue


@st.cache_resource
def _init() -> bool:
    init_db()
    limiter.configure("ui")
    return True


def init_once() -> None:
    _init()


def fmt_seconds(s: float | None) -> str:
    if s is None:
        return "?"
    s = int(s)
    return f"{s // 60} min {s % 60:02d} s" if s >= 60 else f"{s} s"


def sidebar() -> Notebook | None:
    with st.sidebar:
        st.header("📚 Notebooks")
        notebooks = list_notebooks()
        selected = None
        if notebooks:
            ids = [n.id for n in notebooks]
            current = st.session_state.get("notebook_id")
            index = ids.index(current) if current in ids else 0
            selected = st.selectbox("Notebook", notebooks, index=index, format_func=lambda n: n.name)
            st.session_state["notebook_id"] = selected.id
        with st.form("new_notebook", clear_on_submit=True):
            name = st.text_input("New notebook", placeholder="ex. Biologie — Semestre 1")
            if st.form_submit_button("Create") and name.strip():
                nb = create_notebook(name)
                st.session_state["notebook_id"] = nb.id
                st.rerun()
        active_jobs(selected.id if selected else None)
        return selected


@st.fragment(run_every="3s")
def active_jobs(notebook_id: str | None) -> None:
    jobs = notebook_jobs(None, active_only=True)
    st.divider()
    st.caption(f"Background jobs running or queued: {len(jobs)}")
    for p in jobs[:5]:
        st.progress(p.done / max(p.total, 1), text=f"{p.type} · {p.done}/{p.total}")


def job_panel(p: JobProgress, *, key_prefix: str = "") -> None:
    icon = {"queued": "⏳", "running": "⚙️", "done": "✅", "failed": "❌", "cancelled": "🚫"}.get(p.status, "•")
    label = f"{icon} **{p.type}** · {p.status} · {p.done}/{p.total} tasks"
    if p.failed:
        label += f" · {p.failed} failed"
    if p.status == "running":
        label += f" · time left ≈ {fmt_seconds(p.eta_s)}"
    st.markdown(label)
    st.progress(p.done / max(p.total, 1))
    if p.current_stages:
        st.caption("Stage: " + ", ".join(p.current_stages))
    cols = st.columns(6)
    if p.status in ("queued", "running") and cols[0].button("Cancel", key=f"{key_prefix}cancel-{p.job_id}"):
        get_queue().cancel(p.job_id)
        st.rerun()
    if p.status in ("failed", "cancelled") and cols[0].button("Retry", key=f"{key_prefix}retry-{p.job_id}"):
        get_queue().retry(p.job_id)
        st.rerun()
    if p.error:
        with st.expander("Error"):
            st.code(p.error)
