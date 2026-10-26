"""Background worker: claims jobs from the queue and runs them concurrently.

Run from the repo root:  python -m assistant.worker [--concurrency 2]
"""

import argparse
import asyncio
import logging
import os
import socket
import traceback

from assistant.core.config import get_settings
from assistant.core.db import init_db
from assistant.core.runtime import limiter, metrics
from assistant.core.runtime.jobs import HANDLERS, JobCancelled, JobContext
from assistant.core.runtime.queue import Job, get_queue

log = logging.getLogger("assistant.worker")


async def run_job(job: Job) -> None:
    queue = get_queue()
    fn = HANDLERS.get(job.type)
    if fn is None:
        queue.fail(job.id, f"No handler registered for job type '{job.type}'")
        return
    ctx = JobContext(job)
    log.info("job %s (%s) started", job.id[:8], job.type)
    try:
        result = await fn(job, ctx)
    except JobCancelled:
        log.info("job %s cancelled", job.id[:8])
        return
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.exception("job %s failed", job.id[:8])
        queue.fail(job.id, f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=8)}")
        return
    finally:
        metrics.flush()
    queue.complete(job.id, result)
    log.info("job %s done: %s", job.id[:8], result)


async def _heartbeats(running: dict[str, asyncio.Task], every_s: float) -> None:
    queue = get_queue()
    while True:
        await asyncio.sleep(every_s)
        for job_id in list(running):
            queue.heartbeat(job_id)


async def main(concurrency: int) -> None:
    import assistant.core.handlers  # noqa: F401  (registers handlers)

    cfg = get_settings().section("worker")
    init_db()
    limiter.configure("worker")
    queue = get_queue()
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    stale = queue.requeue_stale(cfg.get("stale_after_s", 120))
    if stale:
        log.info("requeued %d stale job(s)", stale)
    log.info("worker %s ready (concurrency=%d, handlers=%s)", worker_id, concurrency, sorted(HANDLERS))

    running: dict[str, asyncio.Task] = {}
    hb = asyncio.create_task(_heartbeats(running, cfg.get("heartbeat_s", 15)))
    try:
        while True:
            for job_id, task in list(running.items()):
                if task.done():
                    running.pop(job_id)
            if len(running) < concurrency and (job := queue.claim(worker_id)):
                running[job.id] = asyncio.create_task(run_job(job))
                continue
            await asyncio.sleep(cfg.get("poll_s", 1.0))
    finally:
        hb.cancel()
        for task in running.values():
            task.cancel()
        await asyncio.gather(*running.values(), return_exceptions=True)
        requeued = queue.requeue_worker(worker_id)
        metrics.flush()
        log.info("worker stopped; %d running job(s) requeued", requeued)


def cli() -> None:
    parser = argparse.ArgumentParser(description="Study assistant background worker")
    parser.add_argument("--concurrency", type=int, default=None, help="jobs running at the same time")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    concurrency = args.concurrency or get_settings().section("worker").get("concurrency", 2)
    try:
        asyncio.run(main(concurrency))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cli()
