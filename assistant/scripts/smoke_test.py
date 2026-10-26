"""Checks that config, database, NVIDIA models and Qdrant all work.

Run from the repo root:  python -m assistant.scripts.smoke_test
"""

import asyncio
import sys
import time

from pydantic import BaseModel
from qdrant_client import QdrantClient

from assistant.core.config import get_settings
from assistant.core.db import init_db
from assistant.core.providers import embeddings, llm, rerank
from assistant.core.runtime import metrics

QUESTION = [{"role": "user", "content": "Réponds en une phrase : qu'est-ce que la photosynthèse ?"}]


class Capital(BaseModel):
    country: str
    capital: str


results: list[tuple[bool, str, str]] = []


async def check(name: str, coro_or_fn):
    t0 = time.perf_counter()
    try:
        out = coro_or_fn() if callable(coro_or_fn) else await coro_or_fn
        if asyncio.iscoroutine(out):
            out = await out
        ok, detail = True, str(out)
    except Exception as e:
        ok, detail = False, f"{type(e).__name__}: {e}"
    ms = int((time.perf_counter() - t0) * 1000)
    results.append((ok, name, detail))
    print(f"{'OK  ' if ok else 'FAIL'} {name} ({ms} ms)\n     {detail[:300]}")
    return ok


async def main() -> int:
    s = get_settings()
    await check("config + API key", lambda: f"chat={s.model('chat').id}, key=...{s.api_key[-4:]}")
    await check("sqlite init", lambda: (init_db(), str(s.data_dir / "app.db"))[1])
    await check("llm chat (role chat)", llm.chat(QUESTION, role="chat", max_tokens=200))
    await check("llm chat (role fast)", llm.chat(QUESTION, role="fast", max_tokens=200))
    await check("llm chat_json", llm.chat_json(
        [{"role": "user", "content": "Quelle est la capitale du Maroc ?"}], Capital, role="fast"))
    await check("embed_query + dimension", embeddings.embedding_dim())
    await check("embed_passages (FR + EN)", lambda: _passages())
    await check("rerank", lambda: _rerank())
    await check("qdrant reachable", lambda: QdrantClient(url=s.qdrant_url).get_collections())
    t0 = time.perf_counter()
    await check("cache hit on repeated chat", llm.chat(QUESTION, role="fast", max_tokens=200))
    cached_ms = (time.perf_counter() - t0) * 1000
    print(f"     repeated call took {cached_ms:.0f} ms (a cache hit should be a few ms)")
    metrics.flush()

    failed = [n for ok, n, _ in results if not ok]
    print("\nAll checks passed." if not failed else f"\n{len(failed)} check(s) failed: {', '.join(failed)}")
    return 1 if failed else 0


async def _passages() -> str:
    vecs = await embeddings.embed_passages([
        "La photosynthèse transforme l'énergie lumineuse en énergie chimique.",
        "Photosynthesis converts light energy into chemical energy.",
        "Le théorème de Pythagore relie les côtés d'un triangle rectangle.",
    ])
    return f"{len(vecs)} vectors of dim {len(vecs[0])}"


async def _rerank() -> str:
    hits = await rerank.rerank(
        "What does photosynthesis produce?",
        [
            "Le théorème de Pythagore relie les côtés d'un triangle rectangle.",
            "La photosynthèse produit du glucose et libère du dioxygène.",
            "La Révolution française commence en 1789.",
        ],
    )
    best = hits[0]
    if best.index != 1:
        raise AssertionError(f"expected passage 1 first, got {hits}")
    return f"best=passage {best.index} (score {best.score:.2f}); order={[h.index for h in hits]}"


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
