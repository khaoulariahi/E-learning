"""Timing and usage metrics, buffered and written to SQLite in batches."""

import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from assistant.core.db import connect, now

FLUSH_EVERY_ROWS = 50
FLUSH_EVERY_S = 2.0

_lock = threading.Lock()
_buffer: list[tuple] = []
_last_flush = time.monotonic()


def record(
    stage: str,
    *,
    model: str | None = None,
    duration_ms: int | None = None,
    cache_hit: bool | None = None,
    status: str = "ok",
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    job_id: str | None = None,
) -> None:
    global _last_flush
    row = (now(), stage, model, duration_ms, None if cache_hit is None else int(cache_hit),
           status, tokens_in, tokens_out, job_id)
    with _lock:
        _buffer.append(row)
        due = len(_buffer) >= FLUSH_EVERY_ROWS or time.monotonic() - _last_flush >= FLUSH_EVERY_S
    if due:
        flush()


def flush() -> None:
    global _last_flush
    with _lock:
        rows = list(_buffer)
        _buffer.clear()
        _last_flush = time.monotonic()
    if rows:
        connect().executemany(
            "INSERT INTO metrics(ts, stage, model, duration_ms, cache_hit, status, tokens_in, tokens_out, job_id)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            rows,
        )


class timer:
    """`with metrics.timer("pdf.analyze", job_id=...):` records the block's duration."""

    def __init__(self, stage: str, **fields):
        self.stage = stage
        self.fields = fields

    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        status = "error" if exc_type else self.fields.pop("status", "ok")
        record(self.stage, duration_ms=int((time.perf_counter() - self.t0) * 1000), status=status, **self.fields)
        return False


def _pct(values: list[int], p: float) -> int | None:
    if not values:
        return None
    values = sorted(values)
    return values[min(len(values) - 1, int(round(p * (len(values) - 1))))]


def summary(hours: float = 24) -> list[dict]:
    """Per stage/model: count, p50, p95, cache hit rate, errors and 429s over the last `hours`."""
    flush()
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rows = connect().execute(
        "SELECT stage, model, duration_ms, cache_hit, status, tokens_in, tokens_out FROM metrics WHERE ts >= ?",
        (since,),
    ).fetchall()
    groups: dict[tuple, list] = defaultdict(list)
    for r in rows:
        groups[(r["stage"], r["model"] or "")].append(r)
    out = []
    for (stage, model), rs in sorted(groups.items()):
        durations = [r["duration_ms"] for r in rs if r["duration_ms"] is not None and not r["cache_hit"]]
        hits = [r["cache_hit"] for r in rs if r["cache_hit"] is not None]
        out.append({
            "stage": stage,
            "model": model,
            "count": len(rs),
            "p50_ms": _pct(durations, 0.5),
            "p95_ms": _pct(durations, 0.95),
            "cache_hit_%": round(100 * sum(hits) / len(hits), 1) if hits else None,
            "errors": sum(1 for r in rs if r["status"] == "error"),
            "rate_limited": sum(1 for r in rs if r["status"] == "rate_limited"),
            "tokens_in": sum(r["tokens_in"] or 0 for r in rs),
            "tokens_out": sum(r["tokens_out"] or 0 for r in rs),
        })
    return out
