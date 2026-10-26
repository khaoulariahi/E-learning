"""Demo job used to check the runtime: parallel tasks, rate limits, progress, resume and caching."""

import asyncio
import random

from assistant.core.providers import llm
from assistant.core.runtime.jobs import JobContext, handler
from assistant.core.runtime.queue import Job


@handler("demo")
async def demo(job: Job, ctx: JobContext) -> dict:
    """params: n (number of tasks), fake (sleep instead of calling the API), role (model role)."""
    n = int(job.params.get("n", 100))
    fake = bool(job.params.get("fake", False))
    role = job.params.get("role", "fast")

    async def one(key: str) -> dict:
        i = int(key.split(":")[1])
        if fake:
            await asyncio.sleep(random.uniform(0.2, 1.0))
            return {"answer": f"fake-{i}"}
        answer = await llm.chat(
            [{"role": "user", "content": f"Réponds par un seul mot : un fruit qui commence par la lettre numéro {i % 26 + 1} de l'alphabet."}],
            role=role, max_tokens=10, job_id=job.id,
        )
        return {"answer": answer}

    results = await ctx.run_tasks([(f"q:{i}", "demo_llm") for i in range(n)], one, stage="llm")
    return {"done": len(results), "failed": len(ctx.failed)}
