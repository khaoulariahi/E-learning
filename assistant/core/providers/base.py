"""Shared plumbing for model providers: clients, retries with backoff, model fallbacks."""

import asyncio
import logging
from typing import Awaitable, Callable, TypeVar

import httpx
import openai
from openai import AsyncOpenAI
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception, stop_after_attempt, wait_random_exponential

from assistant.core.config import get_settings
from assistant.core.runtime import metrics

log = logging.getLogger(__name__)
T = TypeVar("T")

MAX_ATTEMPTS = 5
RETRY_WAIT_MULTIPLIER = 1.0   # seconds; tests set it to 0
RETRY_WAIT_MAX = 30.0

# Clients hold connections bound to an event loop, so keep one per loop.
_openai_clients: dict[int, AsyncOpenAI] = {}
_http_clients: dict[int, httpx.AsyncClient] = {}


class ProviderError(RuntimeError):
    pass


def openai_client() -> AsyncOpenAI:
    key = id(asyncio.get_running_loop())
    if key not in _openai_clients:
        s = get_settings()
        nv = s.section("nvidia")
        _openai_clients[key] = AsyncOpenAI(
            base_url=nv["base_url"], api_key=s.api_key, timeout=nv.get("timeout_s", 120), max_retries=0,
        )
    return _openai_clients[key]


def http_client() -> httpx.AsyncClient:
    key = id(asyncio.get_running_loop())
    if key not in _http_clients:
        s = get_settings()
        _http_clients[key] = httpx.AsyncClient(
            timeout=s.section("nvidia").get("timeout_s", 120),
            headers={"Authorization": f"Bearer {s.api_key}", "Accept": "application/json"},
        )
    return _http_clients[key]


def status_code(e: BaseException) -> int | None:
    if isinstance(e, openai.APIStatusError):
        return e.status_code
    if isinstance(e, httpx.HTTPStatusError):
        return e.response.status_code
    return None


def is_retryable(e: BaseException) -> bool:
    if isinstance(e, (openai.APITimeoutError, openai.APIConnectionError, httpx.TransportError)):
        return True
    code = status_code(e)
    return code is not None and (code == 429 or code >= 500)


def is_model_unavailable(e: BaseException) -> bool:
    return status_code(e) in (404, 410)


async def with_retries(fn: Callable[[], Awaitable[T]], *, stage: str, model: str) -> T:
    """Run fn with exponential backoff on 429, 5xx, timeouts and connection errors."""

    def before_sleep(state: RetryCallState) -> None:
        e = state.outcome.exception() if state.outcome else None
        rate_limited = status_code(e) == 429
        metrics.record(stage, model=model, status="rate_limited" if rate_limited else "error")
        log.info("%s %s attempt %d failed (%s); retrying", stage, model, state.attempt_number, e)

    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(MAX_ATTEMPTS),
        wait=wait_random_exponential(multiplier=RETRY_WAIT_MULTIPLIER, max=RETRY_WAIT_MAX),
        retry=retry_if_exception(is_retryable),
        before_sleep=before_sleep,
        reraise=True,
    ):
        with attempt:
            return await fn()
    raise AssertionError("unreachable")


async def with_fallbacks(role: str, call: Callable[[str], Awaitable[T]]) -> tuple[T, str]:
    """Try the role's model, then its fallbacks. Returns (result, model id that answered).

    Moves to the next model only when retries are exhausted on a retryable error, or the model is gone (404).
    """
    cfg = get_settings().model(role)
    last: BaseException | None = None
    for model_id in [cfg.id, *cfg.fallbacks]:
        try:
            return await call(model_id), model_id
        except Exception as e:
            if not (is_retryable(e) or is_model_unavailable(e)):
                raise
            log.warning("model %s failed for role %s: %s", model_id, role, e)
            last = e
    raise ProviderError(f"All models failed for role '{role}': {last}") from last
