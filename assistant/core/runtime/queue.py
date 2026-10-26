"""Job queue and per-job tasks in SQLite.

Jobs are what the UI submits ("ingest this file"). Tasks are the units inside a job ("page 12"). Task
results are stored as soon as they finish, so a restarted job only reruns unfinished tasks.
JobQueue is a protocol so a Redis-backed queue can replace this later (Phase 8).
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from pydantic import BaseModel

from assistant.core.db import connect, now

ACTIVE = ("queued", "running")


class Job(BaseModel):
    id: str
    notebook_id: str | None
    type: str
    params: dict
    status: str
    priority: int = 0
    worker_id: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    result: dict | None = None


class TaskRef(BaseModel):
    job_id: str
    key: str
    kind: str
    status: str
    attempts: int = 0


def _job(row) -> Job:
    d = dict(row)
    return Job(
        id=d["id"], notebook_id=d.get("notebook_id"), type=d["type"],
        params=json.loads(d.get("params_json") or "{}"), status=d["status"],
        priority=d.get("priority") or 0, worker_id=d.get("worker_id"), created_at=d.get("created_at"),
        started_at=d.get("started_at"), finished_at=d.get("finished_at"), error=d.get("error"),
        result=json.loads(d["result_json"]) if d.get("result_json") else None,
    )


def _ago(seconds: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


class JobQueue(Protocol):
    def enqueue(self, type: str, params: dict, notebook_id: str | None = None, priority: int = 0) -> str: ...
    def claim(self, worker_id: str) -> Job | None: ...
    def heartbeat(self, job_id: str) -> None: ...
    def complete(self, job_id: str, result: dict | None = None) -> None: ...
    def fail(self, job_id: str, error: str) -> None: ...
    def cancel(self, job_id: str) -> None: ...
    def requeue_stale(self, older_than_s: int = 120) -> int: ...


class SqliteJobQueue:
    def enqueue(self, type: str, params: dict, notebook_id: str | None = None, priority: int = 0) -> str:
        job_id = uuid.uuid4().hex
        connect().execute(
            "INSERT INTO jobs(id, notebook_id, type, params_json, status, priority, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (job_id, notebook_id, type, json.dumps(params, ensure_ascii=False), "queued", priority, now()),
        )
        return job_id

    def claim(self, worker_id: str) -> Job | None:
        ts = now()
        row = connect().execute(
            "UPDATE jobs SET status='running', worker_id=?, started_at=COALESCE(started_at, ?), heartbeat_at=?"
            " WHERE id = (SELECT id FROM jobs WHERE status='queued' ORDER BY priority DESC, created_at LIMIT 1)"
            " RETURNING *",
            (worker_id, ts, ts),
        ).fetchone()
        return _job(row) if row else None

    def heartbeat(self, job_id: str) -> None:
        connect().execute("UPDATE jobs SET heartbeat_at=? WHERE id=? AND status='running'", (now(), job_id))

    def complete(self, job_id: str, result: dict | None = None) -> None:
        connect().execute(
            "UPDATE jobs SET status='done', finished_at=?, error=NULL, result_json=? WHERE id=? AND status='running'",
            (now(), json.dumps(result, ensure_ascii=False) if result is not None else None, job_id),
        )

    def fail(self, job_id: str, error: str) -> None:
        connect().execute(
            "UPDATE jobs SET status='failed', finished_at=?, error=? WHERE id=? AND status='running'",
            (now(), error[:4000], job_id),
        )

    def cancel(self, job_id: str) -> None:
        connect().execute(
            "UPDATE jobs SET status='cancelled', finished_at=? WHERE id=? AND status IN ('queued','running')",
            (now(), job_id),
        )

    def retry(self, job_id: str) -> None:
        """Requeue a failed or cancelled job; its done tasks are kept."""
        connect().execute(
            "UPDATE jobs SET status='queued', worker_id=NULL, finished_at=NULL, error=NULL"
            " WHERE id=? AND status IN ('failed','cancelled')",
            (job_id,),
        )

    def requeue_stale(self, older_than_s: int = 120) -> int:
        """Requeue running jobs whose worker stopped sending heartbeats (crash, kill)."""
        conn = connect()
        rows = conn.execute(
            "UPDATE jobs SET status='queued', worker_id=NULL"
            " WHERE status='running' AND (heartbeat_at IS NULL OR heartbeat_at < ?) RETURNING id",
            (_ago(older_than_s),),
        ).fetchall()
        for r in rows:
            _reset_running_tasks(r["id"])
        return len(rows)

    def requeue_worker(self, worker_id: str) -> int:
        """On graceful shutdown: put this worker's running jobs back in the queue."""
        rows = connect().execute(
            "UPDATE jobs SET status='queued', worker_id=NULL WHERE status='running' AND worker_id=? RETURNING id",
            (worker_id,),
        ).fetchall()
        for r in rows:
            _reset_running_tasks(r["id"])
        return len(rows)

    def get(self, job_id: str) -> Job | None:
        row = connect().execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return _job(row) if row else None

    def status(self, job_id: str) -> str | None:
        row = connect().execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
        return row["status"] if row else None

    def list(self, notebook_id: str | None = None, *, active_only: bool = False, limit: int = 50) -> list[Job]:
        sql, args = "SELECT * FROM jobs WHERE 1=1", []
        if notebook_id is not None:
            sql += " AND notebook_id=?"
            args.append(notebook_id)
        if active_only:
            sql += " AND status IN ('queued','running')"
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        return [_job(r) for r in connect().execute(sql, args).fetchall()]


def get_queue() -> SqliteJobQueue:
    return SqliteJobQueue()


# ---- tasks -----------------------------------------------------------------------------------------

def _reset_running_tasks(job_id: str) -> None:
    connect().execute("UPDATE tasks SET status='pending', updated_at=? WHERE job_id=? AND status='running'",
                      (now(), job_id))


def ensure_tasks(job_id: str, items: list[tuple[str, str]]) -> None:
    """Insert (key, kind) pairs as pending unless they already exist. Idempotent, which enables resume."""
    ts = now()
    connect().executemany(
        "INSERT OR IGNORE INTO tasks(id, job_id, key, kind, status, attempts, updated_at)"
        " VALUES (?,?,?,?, 'pending', 0, ?)",
        [(uuid.uuid4().hex, job_id, key, kind, ts) for key, kind in items],
    )


def pending_tasks(job_id: str, keys: list[str] | None = None) -> list[TaskRef]:
    """Tasks that still need to run (pending, failed, or left running by a crash)."""
    rows = connect().execute(
        "SELECT job_id, key, kind, status, attempts FROM tasks WHERE job_id=? AND status NOT IN ('done','skipped')",
        (job_id,),
    ).fetchall()
    tasks = [TaskRef(**dict(r)) for r in rows]
    if keys is not None:
        wanted = set(keys)
        tasks = [t for t in tasks if t.key in wanted]
    return tasks


def task_started(job_id: str, key: str, stage: str | None = None) -> None:
    connect().execute(
        "UPDATE tasks SET status='running', stage=COALESCE(?, stage), attempts=attempts+1, updated_at=?"
        " WHERE job_id=? AND key=?",
        (stage, now(), job_id, key),
    )


def task_done(job_id: str, key: str, result: Any, duration_ms: int) -> None:
    connect().execute(
        "UPDATE tasks SET status='done', result_json=?, duration_ms=?, error=NULL, updated_at=? WHERE job_id=? AND key=?",
        (json.dumps(result, ensure_ascii=False) if result is not None else None, duration_ms, now(), job_id, key),
    )


def task_failed(job_id: str, key: str, error: str, duration_ms: int | None = None) -> None:
    connect().execute(
        "UPDATE tasks SET status='failed', error=?, duration_ms=?, updated_at=? WHERE job_id=? AND key=?",
        (error[:4000], duration_ms, now(), job_id, key),
    )


def set_stage(job_id: str, key: str, stage: str) -> None:
    connect().execute("UPDATE tasks SET stage=?, updated_at=? WHERE job_id=? AND key=?", (stage, now(), job_id, key))


def task_results(job_id: str, keys: list[str] | None = None) -> dict[str, Any]:
    """Results of done tasks, by key."""
    rows = connect().execute(
        "SELECT key, result_json FROM tasks WHERE job_id=? AND status='done'", (job_id,)
    ).fetchall()
    out = {r["key"]: json.loads(r["result_json"]) if r["result_json"] else None for r in rows}
    if keys is not None:
        wanted = set(keys)
        out = {k: v for k, v in out.items() if k in wanted}
    return out


def task_rows(job_id: str) -> list[dict]:
    rows = connect().execute(
        "SELECT key, kind, stage, status, attempts, duration_ms, error, updated_at FROM tasks WHERE job_id=?"
        " ORDER BY rowid",
        (job_id,),
    ).fetchall()
    return [dict(r) for r in rows]
