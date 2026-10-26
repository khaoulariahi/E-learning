"""Chat models: plain text, validated JSON, and streaming. All calls go through roles defined in config.yaml."""

import json
import re
import time
from typing import AsyncIterator, TypeVar

from pydantic import BaseModel, ValidationError

from assistant.core.config import get_settings
from assistant.core.providers.base import ProviderError, openai_client, with_fallbacks, with_retries
from assistant.core.runtime import limiter, metrics
from assistant.core.runtime.cache import cached_call

T = TypeVar("T", bound=BaseModel)

THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_think(text: str) -> str:
    text = THINK_RE.sub("", text)
    if "<think>" in text:  # unclosed reasoning block: drop it
        text = text.split("<think>", 1)[0]
    return text.strip()


def extract_json(text: str) -> str:
    """Pull the JSON value out of a model reply (handles ```json fences and leading prose)."""
    text = strip_think(text)
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if starts:
        text = text[min(starts):]
    end = max(text.rfind("}"), text.rfind("]"))
    return text[: end + 1] if end != -1 else text


def _with_system_prefix(role: str, messages: list[dict]) -> list[dict]:
    prefix = get_settings().model(role).system_prefix
    if not prefix:
        return messages
    if messages and messages[0]["role"] == "system":
        return [{"role": "system", "content": f"{prefix}\n{messages[0]['content']}"}, *messages[1:]]
    return [{"role": "system", "content": prefix}, *messages]


async def _complete(role: str, messages: list[dict], temperature: float, max_tokens: int | None,
                    job_id: str | None) -> str:
    async def call(model_id: str) -> str:
        async def attempt() -> str:
            async with limiter.slot(role):
                t0 = time.perf_counter()
                resp = await openai_client().chat.completions.create(
                    model=model_id, messages=messages, temperature=temperature, max_tokens=max_tokens,
                )
            usage = resp.usage
            metrics.record("llm.request", model=model_id, job_id=job_id,
                           duration_ms=int((time.perf_counter() - t0) * 1000),
                           tokens_in=usage.prompt_tokens if usage else None,
                           tokens_out=usage.completion_tokens if usage else None)
            content = resp.choices[0].message.content
            if content is None:
                raise ProviderError(f"{model_id} returned an empty message")
            return content

        return await with_retries(attempt, stage="llm.request", model=model_id)

    text, _ = await with_fallbacks(role, call)
    return strip_think(text)


async def chat(
    messages: list[dict],
    *,
    role: str = "chat",
    temperature: float | None = None,
    max_tokens: int | None = None,
    prompt_version: str = "v1",
    cache: bool = True,
    job_id: str | None = None,
) -> str:
    cfg = get_settings().model(role)
    messages = _with_system_prefix(role, messages)
    temperature = cfg.temperature if temperature is None else temperature
    temperature = 0.2 if temperature is None else temperature
    max_tokens = max_tokens or cfg.max_tokens

    async def run() -> str:
        return await _complete(role, messages, temperature, max_tokens, job_id)

    if not cache:
        return await run()
    payload = {"messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    return await cached_call("llm", cfg.id, prompt_version, payload, run, job_id=job_id)


async def chat_json(
    messages: list[dict],
    schema: type[T],
    *,
    role: str = "fast",
    prompt_version: str = "v1",
    job_id: str | None = None,
) -> T:
    """Ask for JSON matching `schema`, validate it, and retry once with the validation error if it is invalid."""
    instruction = (
        "Return ONLY valid JSON (no prose, no code fences) matching this JSON schema:\n"
        + json.dumps(schema.model_json_schema(), ensure_ascii=False)
    )
    msgs = [*messages, {"role": "user", "content": instruction}]
    reply = await chat(msgs, role=role, prompt_version=prompt_version, job_id=job_id)
    try:
        return schema.model_validate_json(extract_json(reply))
    except (ValidationError, ValueError) as e:
        repair = [
            *msgs,
            {"role": "assistant", "content": reply},
            {"role": "user", "content": f"Your JSON was invalid: {e}\nReturn only the corrected JSON."},
        ]
        reply = await chat(repair, role=role, prompt_version=prompt_version, job_id=job_id)
        try:
            return schema.model_validate_json(extract_json(reply))
        except (ValidationError, ValueError) as e2:
            raise ProviderError(f"Model returned invalid JSON twice: {e2}") from e2


async def stream(
    messages: list[dict],
    *,
    role: str = "chat",
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> AsyncIterator[str]:
    """Yield text deltas. Not cached. Hides a leading <think>…</think> block. Fallbacks apply before the first token."""
    cfg = get_settings().model(role)
    messages = _with_system_prefix(role, messages)
    temperature = cfg.temperature if temperature is None else temperature
    max_tokens = max_tokens or cfg.max_tokens

    async def open_stream(model_id: str):
        async def attempt():
            return await openai_client().chat.completions.create(
                model=model_id, messages=messages, temperature=temperature, max_tokens=max_tokens, stream=True,
            )
        return await with_retries(attempt, stage="llm.stream", model=model_id)

    async with limiter.slot(role):
        t0 = time.perf_counter()
        response, model_id = await with_fallbacks(role, open_stream)
        first = True
        pending = ""          # text held back while we may be inside a <think> block
        thinking = None       # None = undecided, True = inside think block, False = normal output
        after_think = False   # drop whitespace right after </think>
        async for event in response:
            if not event.choices:
                continue
            delta = event.choices[0].delta.content or ""
            if not delta:
                continue
            if thinking is not False:
                pending += delta
                if thinking is None:
                    stripped = pending.lstrip()
                    if stripped.startswith("<think>"):
                        thinking = True
                    elif len(stripped) >= len("<think>") or not "<think>".startswith(stripped):
                        thinking = False
                        delta, pending = pending, ""
                    else:
                        continue
                if thinking:
                    if "</think>" not in pending:
                        continue
                    delta = pending.split("</think>", 1)[1]
                    pending, thinking, after_think = "", False, True
            if after_think:
                delta = delta.lstrip()
                if not delta:
                    continue
                after_think = False
            if first:
                metrics.record("llm.first_token", model=model_id,
                               duration_ms=int((time.perf_counter() - t0) * 1000))
                first = False
            yield delta
        if pending and thinking is None:
            yield pending
        metrics.record("llm.stream", model=model_id, duration_ms=int((time.perf_counter() - t0) * 1000))
