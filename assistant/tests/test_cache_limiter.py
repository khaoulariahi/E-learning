import asyncio
import time

from assistant.core.config import get_settings
from assistant.core.runtime import limiter, metrics
from assistant.core.runtime.cache import SqliteCallCache, cached_call, make_key


def test_cache_round_trip_with_french_text():
    cache = SqliteCallCache()
    key = make_key("llm", "m", "v1", {"q": "Qu'est-ce que la photosynthèse ? « œ »"})
    assert cache.get(key) is None
    cache.set(key, {"a": "énergie lumineuse"}, kind="llm", model="m", version="v1")
    assert cache.get(key) == {"a": "énergie lumineuse"}


def test_version_changes_the_key():
    assert make_key("llm", "m", "v1", "x") != make_key("llm", "m", "v2", "x")
    assert make_key("llm", "m", "v1", {"a": 1, "b": 2}) == make_key("llm", "m", "v1", {"b": 2, "a": 1})


async def test_cached_call_runs_once():
    calls = 0

    async def fn():
        nonlocal calls
        calls += 1
        return [1, 2, 3]

    assert await cached_call("test", "m", "v1", "p", fn) == [1, 2, 3]
    assert await cached_call("test", "m", "v1", "p", fn) == [1, 2, 3]
    assert calls == 1
    stages = {r["stage"]: r for r in metrics.summary()}
    assert stages["test"]["cache_hit_%"] == 50.0


async def test_limiter_bounds_calls_in_flight(monkeypatch):
    cfg = get_settings().model("fast")
    monkeypatch.setattr(cfg, "max_in_flight", 2)
    monkeypatch.setattr(cfg, "rpm", 6000)
    limiter.configure("worker")
    current = peak = 0

    async def call():
        nonlocal current, peak
        async with limiter.slot("fast"):
            current += 1
            peak = max(peak, current)
            await asyncio.sleep(0.02)
            current -= 1

    await asyncio.gather(*(call() for _ in range(10)))
    assert peak == 2


async def test_limiter_respects_rpm(monkeypatch):
    cfg = get_settings().model("fast")
    monkeypatch.setattr(cfg, "max_in_flight", 1)
    monkeypatch.setattr(cfg, "rpm", 600)  # worker budget 480/min = one call every 0.125 s
    limiter.configure("worker")
    t0 = time.perf_counter()
    for _ in range(5):
        async with limiter.slot("fast"):
            pass
    assert time.perf_counter() - t0 >= 0.4


def test_budget_split_between_worker_and_ui():
    rpm = get_settings().model("chat").rpm
    share = get_settings().section("limits")["background_share"]
    limiter.configure("worker")
    assert limiter.budget_rpm("chat") == rpm * share
    limiter.configure("ui")
    assert abs(limiter.budget_rpm("chat") - rpm * (1 - share)) < 1e-9
