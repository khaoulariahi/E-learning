"""Bridge between synchronous code (Streamlit, scripts) and the async providers.

One long-lived event loop runs in a daemon thread, so limiters and HTTP clients stay valid across
Streamlit reruns.
"""

import asyncio
import queue
import threading
from typing import AsyncIterator, Awaitable, Iterator, TypeVar

T = TypeVar("T")

_loop: asyncio.AbstractEventLoop | None = None
_lock = threading.Lock()


def _ensure_loop() -> asyncio.AbstractEventLoop:
    global _loop
    with _lock:
        if _loop is None:
            _loop = asyncio.new_event_loop()
            threading.Thread(target=_loop.run_forever, daemon=True, name="aio-loop").start()
    return _loop


def run_sync(coro: Awaitable[T], timeout: float | None = None) -> T:
    return asyncio.run_coroutine_threadsafe(coro, _ensure_loop()).result(timeout)


def iter_sync(agen: AsyncIterator[T]) -> Iterator[T]:
    """Turn an async generator into a sync generator (for st.write_stream)."""
    q: queue.Queue = queue.Queue()
    done = object()

    async def pump():
        try:
            async for item in agen:
                q.put(item)
        except Exception as e:  # re-raised in the consumer thread
            q.put(e)
        finally:
            q.put(done)

    asyncio.run_coroutine_threadsafe(pump(), _ensure_loop())
    while (item := q.get()) is not done:
        if isinstance(item, Exception):
            raise item
        yield item
