"""Provider logic with a fake OpenAI client (no network)."""

from types import SimpleNamespace

import httpx
import openai
import pytest
from pydantic import BaseModel

from assistant.core.providers import embeddings, llm
from assistant.core.providers.base import ProviderError


def _status_error(cls, code: int):
    req = httpx.Request("POST", "https://x/v1/chat/completions")
    return cls(f"HTTP {code}", response=httpx.Response(code, request=req), body=None)


class FakeCompletions:
    def __init__(self, script):
        self.script = list(script)   # items: str reply, Exception, or (model, str) / (model, Exception)
        self.calls: list[dict] = []

    async def create(self, **kw):
        self.calls.append(kw)
        item = self.script.pop(0)
        if isinstance(item, tuple):
            expected_model, item = item
            assert kw["model"] == expected_model
        if isinstance(item, Exception):
            raise item
        if kw.get("stream"):
            return _stream(item)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=item))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )


async def _stream(chunks):
    for c in chunks:
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=c))])


class FakeEmbeddings:
    def __init__(self):
        self.batches: list[list[str]] = []

    async def create(self, *, model, input, encoding_format, extra_body):
        self.batches.append(list(input))
        return SimpleNamespace(
            data=[SimpleNamespace(index=i, embedding=[float(len(t)), 1.0]) for i, t in enumerate(input)],
            usage=SimpleNamespace(prompt_tokens=len(input)),
        )


@pytest.fixture
def fake(monkeypatch):
    def install(script=(), emb=None):
        client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(script)),
                                 embeddings=emb or FakeEmbeddings())
        monkeypatch.setattr(llm, "openai_client", lambda: client)
        monkeypatch.setattr(embeddings, "openai_client", lambda: client)
        return client
    return install


MSG = [{"role": "user", "content": "Bonjour"}]


def test_strip_think_and_extract_json():
    assert llm.strip_think("<think>hmm\nok</think>\n Réponse") == "Réponse"
    assert llm.strip_think("Réponse <think>unfinished") == "Réponse"
    assert llm.extract_json('Voici :\n```json\n{"a": [1, 2]}\n```') == '{"a": [1, 2]}'
    assert llm.extract_json('Sure! {"a": 1} hope it helps') == '{"a": 1}'


async def test_chat_strips_think_and_caches(fake):
    client = fake(["<think>reasoning</think>La photosynthèse."])
    assert await llm.chat(MSG, role="fast") == "La photosynthèse."
    assert await llm.chat(MSG, role="fast") == "La photosynthèse."      # served from cache
    assert len(client.chat.completions.calls) == 1


async def test_system_prefix_is_added(fake):
    client = fake(["ok"])
    await llm.chat([{"role": "system", "content": "Tu es un tuteur."}, *MSG], role="chat")
    sent = client.chat.completions.calls[0]["messages"]
    assert sent[0]["role"] == "system" and sent[0]["content"].startswith("/no_think\n")


async def test_retries_on_429_then_succeeds(fake):
    client = fake([_status_error(openai.RateLimitError, 429), "ok"])
    assert await llm.chat(MSG, role="fast", cache=False) == "ok"
    assert len(client.chat.completions.calls) == 2


async def test_falls_back_when_primary_model_is_gone(fake):
    from assistant.core.config import get_settings
    chat_cfg = get_settings().model("chat")
    client = fake([(chat_cfg.id, _status_error(openai.NotFoundError, 404)), (chat_cfg.fallbacks[0], "fallback ok")])
    assert await llm.chat(MSG, role="chat", cache=False) == "fallback ok"
    assert len(client.chat.completions.calls) == 2


async def test_does_not_retry_on_400(fake):
    client = fake([_status_error(openai.BadRequestError, 400)])
    with pytest.raises(openai.BadRequestError):
        await llm.chat(MSG, role="fast", cache=False)
    assert len(client.chat.completions.calls) == 1


class Capital(BaseModel):
    country: str
    capital: str


async def test_chat_json_repairs_invalid_json(fake):
    client = fake(['{"country": "Maroc"}', '```json\n{"country": "Maroc", "capital": "Rabat"}\n```'])
    out = await llm.chat_json(MSG, Capital)
    assert out == Capital(country="Maroc", capital="Rabat")
    repair_msgs = client.chat.completions.calls[1]["messages"]
    assert "invalid" in repair_msgs[-1]["content"]


async def test_chat_json_gives_up_after_two_invalid_replies(fake):
    fake(["pas du json", "toujours pas"])
    with pytest.raises(ProviderError):
        await llm.chat_json(MSG, Capital)


@pytest.mark.parametrize("chunks, expected", [
    (["Bon", "jour", " !"], "Bonjour !"),
    (["<thi", "nk>je réfléchis", "</think>", "\nRéponse", " finale"], "Réponse finale"),
    (["  ", "<", "Hello"], "  <Hello"),
])
async def test_stream_hides_think_block(fake, chunks, expected):
    fake([chunks])
    out = "".join([t async for t in llm.stream(MSG, role="fast")])
    assert out == expected


async def test_embeddings_batch_and_cache_per_text(fake, monkeypatch):
    from assistant.core.config import get_settings
    monkeypatch.setattr(get_settings().model("embed"), "batch_size", 4)
    client = fake()
    texts = [f"texte {i}" for i in range(10)]
    vecs = await embeddings.embed_passages(texts)
    assert len(vecs) == 10 and vecs[3] == [float(len("texte 3")), 1.0]
    assert [len(b) for b in client.embeddings.batches] == [4, 4, 2]

    client.embeddings.batches.clear()
    await embeddings.embed_passages(texts[:5] + ["nouveau"])
    assert client.embeddings.batches == [["nouveau"]]    # only the new text is sent
