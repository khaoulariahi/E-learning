"""Per-model rate limits (requests/min + calls in flight) with a budget split between processes.

The worker gets `rpm × background_share` and the Streamlit UI gets the rest, so background work never
starves interactive use. Each process calls configure() once at startup. Phase 8 replaces this with a
limiter shared through Redis.
"""

import asyncio
from contextlib import asynccontextmanager

from aiolimiter import AsyncLimiter

from assistant.core.config import get_settings

_process = "ui"
# Keyed by (role, id(loop)): asyncio primitives belong to the loop they were created on.
_limiters: dict[tuple[str, int], tuple[AsyncLimiter, asyncio.Semaphore]] = {}


def configure(process: str) -> None:
    global _process
    if process not in ("worker", "ui"):
        raise ValueError("process must be 'worker' or 'ui'")
    _process = process
    _limiters.clear()


def budget_rpm(role: str) -> float:
    cfg = get_settings().model(role)
    share = get_settings().section("limits").get("background_share", 0.8)
    return max(1.0, cfg.rpm * (share if _process == "worker" else 1 - share))


def _get(role: str) -> tuple[AsyncLimiter, asyncio.Semaphore]:
    key = (role, id(asyncio.get_running_loop()))
    if key not in _limiters:
        cfg = get_settings().model(role)
        # Spread requests evenly: a bucket of max_in_flight requests refilled at the rpm budget,
        # instead of allowing the whole minute's budget in one burst.
        rpm = budget_rpm(role)
        burst = max(1, min(cfg.max_in_flight, int(rpm)))
        _limiters[key] = (AsyncLimiter(burst, 60 * burst / rpm), asyncio.Semaphore(cfg.max_in_flight))
    return _limiters[key]


@asynccontextmanager
async def slot(role: str):
    """`async with limiter.slot("chat"):` waits for a free request slot for that model role."""
    rate, in_flight = _get(role)
    async with in_flight:
        await rate.acquire()
        yield
