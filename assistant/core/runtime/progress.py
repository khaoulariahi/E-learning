"""Job progress and time-left estimates, read by the UI."""

from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from assistant.core.db import connect

THROUGHPUT_WINDOW_S = 60


class JobProgress(BaseModel):
    job_id: str
    type: str
    notebook_id: str | None
    status: str
    total: int
    done: int
    failed: int
    running: int
    current_stages: list[str]
    eta_s: float | None
    error: str | None
    created_at: str


def job_progress(job_id: str) -> JobProgress | None:
    conn = connect()
    job = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if job is None:
        return None
    counts = {r["status"]: r["n"] for r in conn.execute(
        "SELECT status, COUNT(*) AS n FROM tasks WHERE job_id=? GROUP BY status", (job_id,))}
    total = sum(counts.values())
    done = counts.get("done", 0) + counts.get("skipped", 0)
    stages = [r["stage"] for r in conn.execute(
        "SELECT DISTINCT stage FROM tasks WHERE job_id=? AND status='running' AND stage IS NOT NULL", (job_id,))]
    return JobProgress(
        job_id=job_id, type=job["type"], notebook_id=job["notebook_id"], status=job["status"],
        total=total, done=done, failed=counts.get("failed", 0), running=counts.get("running", 0),
        current_stages=stages, eta_s=_eta(job_id, total - done) if job["status"] == "running" else None,
        error=job["error"], created_at=job["created_at"],
    )


def _eta(job_id: str, remaining: int) -> float | None:
    """Remaining tasks ÷ recent throughput. Falls back to mean task duration when nothing finished recently."""
    if remaining <= 0:
        return 0.0
    conn = connect()
    since = (datetime.now(timezone.utc) - timedelta(seconds=THROUGHPUT_WINDOW_S)).isoformat()
    recent = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE job_id=? AND status='done' AND updated_at >= ?", (job_id, since)
    ).fetchone()[0]
    if recent:
        return remaining / (recent / THROUGHPUT_WINDOW_S)
    row = conn.execute(
        "SELECT AVG(duration_ms), SUM(status='running') FROM tasks WHERE job_id=?", (job_id,)
    ).fetchone()
    avg_ms, running = row[0], row[1] or 0
    if not avg_ms:
        return None
    return remaining * (avg_ms / 1000) / max(running, 1)


def notebook_jobs(notebook_id: str | None, active_only: bool = False, limit: int = 20) -> list[JobProgress]:
    sql, args = "SELECT id FROM jobs WHERE 1=1", []
    if notebook_id is not None:
        sql += " AND notebook_id=?"
        args.append(notebook_id)
    if active_only:
        sql += " AND status IN ('queued','running')"
    sql += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    ids = [r["id"] for r in connect().execute(sql, args)]
    return [p for p in (job_progress(i) for i in ids) if p is not None]
