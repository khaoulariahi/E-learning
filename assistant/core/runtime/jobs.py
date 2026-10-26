"""Job handler registry and the context handlers use to run their tasks.

Each phase registers handlers with @handler("name") in its own module, imported by
assistant.core.handlers.
"""

import asyncio
import logging
import time
import traceback
from typing import Any, Awaitable, Callable

from assistant.core.runtime import queue as q
from assistant.core.runtime.queue import Job

log = logging.getLogger(__name__)

Handler = Callable[[Job, "JobContext"], Awaitable[dict | None]]
HANDLERS: dict[str, Handler] = {}

CANCEL_CHECK_S = 2.0


def handler(name: str):
    def deco(fn: Handler) -> Handler:
        HANDLERS[name] = fn
        return fn
    return deco


class JobCancelled(Exception):
    pass


class JobContext:
    def __init__(self, job: Job):
        self.job = job
        self.failed: dict[str, str] = {}
        self._cancel_checked = 0.0
        self._cancelled = False

    def cancelled(self) -> bool:
        if not self._cancelled and time.monotonic() - self._cancel_checked > CANCEL_CHECK_S:
            self._cancel_checked = time.monotonic()
            self._cancelled = q.get_queue().status(self.job.id) == "cancelled"
        return self._cancelled

    async def run_tasks(
        self,
        items: list[tuple[str, str]],
        fn: Callable[[str], Awaitable[Any]],
        *,
        stage: str,
    ) -> dict[str, Any]:
        """Register (key, kind) tasks, run the unfinished ones concurrently with fn(key), store each result.

        Concurrency is bounded by the model limiters inside fn, not here. A failing task is recorded and
        does not stop the others. Returns {key: result} for every done task, including those finished in
        a previous run of this job.
        """
        job_id = self.job.id
        q.ensure_tasks(job_id, items)
        keys = [k for k, _ in items]

        async def one(key: str) -> None:
            if self.cancelled():
                return
            q.task_started(job_id, key, stage)
            t0 = time.perf_counter()
            try:
                result = await fn(key)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                ms = int((time.perf_counter() - t0) * 1000)
                log.warning("task %s/%s failed: %s", job_id[:8], key, e)
                self.failed[key] = f"{type(e).__name__}: {e}"
                q.task_failed(job_id, key, f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=5)}", ms)
                return
            q.task_done(job_id, key, result, int((time.perf_counter() - t0) * 1000))

        await asyncio.gather(*(one(t.key) for t in q.pending_tasks(job_id, keys)))
        if self.cancelled():
            raise JobCancelled()
        return q.task_results(job_id, keys)
