"""Embeddings: batched, cached per text. The embed role has no fallbacks on purpose:
vectors from different models can't be mixed in one collection."""

import asyncio
import time
from typing import Literal

from assistant.core.config import get_settings
from assistant.core.providers.base import openai_client, with_retries
from assistant.core.runtime import limiter, metrics
from assistant.core.runtime.cache import get_cache, make_key

VERSION = "v1"
InputType = Literal["passage", "query"]

_dim: int | None = None


def _extra_body(input_type: InputType) -> dict | None:
    cfg = get_settings().model("embed")
    if not cfg.extra.get("input_type"):
        return None
    return {"input_type": input_type, "truncate": "END"}


async def _embed_batch(texts: list[str], input_type: InputType, job_id: str | None) -> list[list[float]]:
    model_id = get_settings().model("embed").id

    async def attempt() -> list[list[float]]:
        async with limiter.slot("embed"):
            t0 = time.perf_counter()
            resp = await openai_client().embeddings.create(
                model=model_id, input=texts, encoding_format="float", extra_body=_extra_body(input_type),
            )
        metrics.record("embed.request", model=model_id, job_id=job_id,
                       duration_ms=int((time.perf_counter() - t0) * 1000),
                       tokens_in=resp.usage.prompt_tokens if resp.usage else None)
        return [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]

    return await with_retries(attempt, stage="embed.request", model=model_id)


async def _embed(texts: list[str], input_type: InputType, job_id: str | None) -> list[list[float]]:
    cfg = get_settings().model("embed")
    cache = get_cache()
    keys = [make_key("embed", cfg.id, VERSION, {"t": t, "it": input_type}) for t in texts]
    out: list[list[float] | None] = [cache.get(k) for k in keys]
    hits = sum(v is not None for v in out)
    if hits:
        metrics.record("embed", model=cfg.id, cache_hit=True, duration_ms=0, job_id=job_id)

    missing = [i for i, v in enumerate(out) if v is None]
    size = cfg.batch_size or 32
    batches = [missing[i:i + size] for i in range(0, len(missing), size)]

    async def run(batch: list[int]) -> None:
        vectors = await _embed_batch([texts[i] for i in batch], input_type, job_id)
        for i, vec in zip(batch, vectors):
            out[i] = vec
            cache.set(keys[i], vec, kind="embed", model=cfg.id, version=VERSION)

    await asyncio.gather(*(run(b) for b in batches))
    return [v for v in out if v is not None]


async def embed_passages(texts: list[str], *, job_id: str | None = None) -> list[list[float]]:
    return await _embed(texts, "passage", job_id)


async def embed_query(text: str) -> list[float]:
    return (await _embed([text], "query", None))[0]


async def embedding_dim() -> int:
    global _dim
    if _dim is None:
        _dim = len(await embed_query("dimension probe"))
    return _dim
