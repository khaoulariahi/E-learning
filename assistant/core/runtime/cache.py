"""Call cache: never pay twice for the same model call.

The key covers the kind of call, the model, a version string and the input. Images and audio are passed
as content hashes, not bytes. CallCache is a protocol so Redis can replace SQLite later (Phase 8).
"""

import hashlib
import json
import time
from typing import Any, Awaitable, Callable, Protocol

from assistant.core.config import get_settings
from assistant.core.db import connect, now
from assistant.core.runtime import metrics


def make_key(kind: str, model: str, version: str, payload: Any) -> str:
    raw = json.dumps({"k": kind, "m": model, "v": version, "p": payload},
                     sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class CallCache(Protocol):
    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, *, kind: str, model: str | None, version: str) -> None: ...


class SqliteCallCache:
    def get(self, key: str) -> Any | None:
        conn = connect()
        row = conn.execute("SELECT value FROM call_cache WHERE key=?", (key,)).fetchone()
        if row is None:
            return None
        conn.execute("UPDATE call_cache SET hits = hits + 1 WHERE key=?", (key,))
        return json.loads(row["value"])

    def set(self, key: str, value: Any, *, kind: str, model: str | None, version: str) -> None:
        connect().execute(
            "INSERT OR REPLACE INTO call_cache(key, kind, model, pipeline_version, value, created_at, hits)"
            " VALUES (?,?,?,?,?,?,0)",
            (key, kind, model, version, json.dumps(value, ensure_ascii=False), now()),
        )


class NullCache:
    def get(self, key: str) -> Any | None:
        return None

    def set(self, key: str, value: Any, *, kind: str, model: str | None, version: str) -> None:
        pass


def get_cache() -> CallCache:
    enabled = get_settings().section("cache").get("enabled", True)
    return SqliteCallCache() if enabled else NullCache()


async def cached_call(
    kind: str,
    model: str,
    version: str,
    payload: Any,
    fn: Callable[[], Awaitable[Any]],
    *,
    job_id: str | None = None,
) -> Any:
    """Return the cached value for this call, or run `fn`, store its (JSON-serializable) result and return it."""
    cache = get_cache()
    key = make_key(kind, model, version, payload)
    hit = cache.get(key)
    if hit is not None:
        metrics.record(kind, model=model, cache_hit=True, duration_ms=0, job_id=job_id)
        return hit
    t0 = time.perf_counter()
    value = await fn()
    cache.set(key, value, kind=kind, model=model, version=version)
    metrics.record(kind, model=model, cache_hit=False, job_id=job_id,
                   duration_ms=int((time.perf_counter() - t0) * 1000))
    return value


def cache_stats() -> list[dict]:
    rows = connect().execute(
        "SELECT kind, model, COUNT(*) AS entries, SUM(hits) AS hits FROM call_cache GROUP BY kind, model"
    ).fetchall()
    return [dict(r) for r in rows]
