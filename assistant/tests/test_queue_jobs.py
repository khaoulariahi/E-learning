import asyncio
from concurrent.futures import ThreadPoolExecutor

from assistant.core import db
from assistant.core.runtime import queue as q
from assistant.core.runtime.jobs import JobContext
from assistant.core.runtime.progress import job_progress
from assistant.worker import run_job


def test_claim_is_exclusive():
    queue = q.get_queue()
    ids = {queue.enqueue("demo", {"i": i}) for i in range(20)}

    def claim_all(worker):
        got = []
        while (job := q.get_queue().claim(worker)) is not None:
            got.append(job.id)
        return got

    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(claim_all, ["w1", "w2", "w3", "w4"]))
    claimed = [j for r in results for j in r]
    assert len(claimed) == len(set(claimed)) == 20
    assert set(claimed) == ids


def test_priority_then_age():
    queue = q.get_queue()
    low = queue.enqueue("demo", {})
    high = queue.enqueue("demo", {}, priority=5)
    assert queue.claim("w").id == high
    assert queue.claim("w").id == low


def test_ensure_tasks_is_idempotent():
    job_id = q.get_queue().enqueue("demo", {})
    q.ensure_tasks(job_id, [("a", "k"), ("b", "k")])
    q.ensure_tasks(job_id, [("a", "k"), ("b", "k"), ("c", "k")])
    assert sorted(t.key for t in q.pending_tasks(job_id)) == ["a", "b", "c"]


def test_requeue_stale_resets_running_tasks():
    queue = q.get_queue()
    job_id = queue.enqueue("demo", {})
    queue.claim("dead-worker")
    q.ensure_tasks(job_id, [("a", "k")])
    q.task_started(job_id, "a")
    db.connect().execute("UPDATE jobs SET heartbeat_at='2000-01-01T00:00:00+00:00' WHERE id=?", (job_id,))
    assert queue.requeue_stale(120) == 1
    assert queue.get(job_id).status == "queued"
    assert q.pending_tasks(job_id)[0].status == "pending"


async def test_run_tasks_resumes_only_unfinished():
    queue = q.get_queue()
    job_id = queue.enqueue("demo", {})
    job = queue.claim("w")
    calls: list[str] = []
    fail_once = {"k3", "k7"}

    async def fn(key):
        calls.append(key)
        if key in fail_once:
            raise RuntimeError("boom")
        await asyncio.sleep(0)
        return {"v": key}

    items = [(f"k{i}", "t") for i in range(10)]
    first = await JobContext(job).run_tasks(items, fn, stage="s")
    assert len(first) == 8 and len(calls) == 10

    fail_once.clear()
    calls.clear()
    second = await JobContext(job).run_tasks(items, fn, stage="s")
    assert sorted(calls) == ["k3", "k7"]          # only the failed tasks ran again
    assert len(second) == 10 and second["k3"] == {"v": "k3"}


async def test_fake_demo_job_end_to_end():
    import assistant.core.handlers  # noqa: F401

    queue = q.get_queue()
    job_id = queue.enqueue("demo", {"n": 12, "fake": True})
    job = queue.claim("w")
    await run_job(job)
    p = job_progress(job_id)
    assert p.status == "done" and p.total == p.done == 12 and p.failed == 0
    assert queue.get(job_id).result == {"done": 12, "failed": 0}


async def test_cancelled_job_stops():
    import assistant.core.handlers  # noqa: F401

    queue = q.get_queue()
    job_id = queue.enqueue("demo", {"n": 5, "fake": True})
    job = queue.claim("w")
    queue.cancel(job_id)
    await run_job(job)
    assert queue.get(job_id).status == "cancelled"
    assert job_progress(job_id).done == 0


async def test_unknown_job_type_fails():
    queue = q.get_queue()
    job_id = queue.enqueue("nope", {})
    await run_job(queue.claim("w"))
    assert "No handler" in queue.get(job_id).error
