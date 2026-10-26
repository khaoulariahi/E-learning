"""Performance tab: demo job, live job progress, metrics and cache statistics."""

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from assistant.app.common import job_panel
from assistant.core.notebooks import Notebook
from assistant.core.runtime import metrics
from assistant.core.runtime.cache import cache_stats
from assistant.core.runtime.progress import notebook_jobs
from assistant.core.runtime.queue import get_queue


def render(notebook: Notebook | None) -> None:
    st.subheader("Demo job")
    st.caption("Runs N small tasks in the background worker to check parallelism, rate limits, progress, resume and caching.")
    with st.form("demo_job"):
        c1, c2 = st.columns(2)
        n = c1.number_input("Tasks", min_value=1, max_value=1000, value=100, step=10)
        mode = c2.radio("Mode", ["Real LLM calls (fast model)", "Fake tasks (no API)"], horizontal=True)
        if st.form_submit_button("Run demo job"):
            job_id = get_queue().enqueue(
                "demo", {"n": int(n), "fake": mode.startswith("Fake")},
                notebook_id=notebook.id if notebook else None,
            )
            st.toast(f"Job {job_id[:8]} queued")

    jobs_section()

    st.subheader("Metrics (last 24 h)")
    rows = metrics.summary(hours=24)
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        st.caption("No metrics yet.")

    st.subheader("Cache")
    stats = cache_stats()
    if stats:
        st.dataframe(pd.DataFrame(stats), hide_index=True, width="stretch")
    else:
        st.caption("Cache is empty.")


@st.fragment(run_every="2s")
def jobs_section() -> None:
    st.subheader("Jobs")
    jobs = notebook_jobs(None, limit=8)
    if not jobs:
        st.caption("No jobs yet.")
        return
    waiting = [p for p in jobs if p.status == "queued" and _age_s(p.created_at) > 5]
    if waiting and not any(p.status == "running" for p in jobs):
        st.warning("Jobs are waiting. Is the worker running?  `python -m assistant.worker`")
    for p in jobs:
        with st.container(border=True):
            job_panel(p, key_prefix="perf-")


def _age_s(iso: str) -> float:
    return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds()
