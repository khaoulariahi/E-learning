"""Reranker (NVIDIA NIM retrieval endpoint, not OpenAI-compatible)."""

import time

from pydantic import BaseModel

from assistant.core.config import get_settings
from assistant.core.providers.base import ProviderError, http_client, with_retries
from assistant.core.runtime import limiter, metrics
from assistant.core.runtime.cache import cached_call

VERSION = "v1"


class RerankHit(BaseModel):
    index: int          # position in the passages list given to rerank()
    score: float        # model logit: higher is more relevant; scale is model-specific


async def rerank(query: str, passages: list[str], top_n: int | None = None,
                 *, job_id: str | None = None) -> list[RerankHit]:
    """Return passages ordered by relevance (best first), cut to top_n."""
    if not passages:
        return []
    s = get_settings()
    cfg = s.model("rerank")
    url = f"{s.section('nvidia')['ai_base_url'].rstrip('/')}/{cfg.endpoint}"
    body = {
        "model": cfg.id,
        "query": {"text": query},
        "passages": [{"text": p} for p in passages],
        "truncate": "END",
    }

    async def request() -> list[dict]:
        async def attempt() -> list[dict]:
            async with limiter.slot("rerank"):
                t0 = time.perf_counter()
                resp = await http_client().post(url, json=body)
                resp.raise_for_status()
            metrics.record("rerank.request", model=cfg.id, job_id=job_id,
                           duration_ms=int((time.perf_counter() - t0) * 1000))
            data = resp.json()
            if "rankings" not in data:
                raise ProviderError(f"Unexpected rerank response: {str(data)[:300]}")
            return data["rankings"]

        return await with_retries(attempt, stage="rerank.request", model=cfg.id)

    rankings = await cached_call("rerank", cfg.id, VERSION, body, request, job_id=job_id)
    hits = sorted((RerankHit(index=r["index"], score=r["logit"]) for r in rankings),
                  key=lambda h: h.score, reverse=True)
    return hits[:top_n] if top_n else hits
