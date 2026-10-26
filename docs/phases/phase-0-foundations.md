# Phase 0: Foundations + runtime

**Goal:** build the skeleton that every later phase plugs into: project layout, config, database, async model providers, cache, rate limiter, a background worker with jobs and progress, and an empty Streamlit app. Performance infrastructure is built **here**, not added later.

**Estimate:** ~1 week · **Depends on:** nothing

**Phase done when:** a demo job of 100 LLM tasks runs in parallel within the rate limits, shows live progress in Streamlit, survives a worker restart (only unfinished tasks rerun), and a second run is served 100% from cache.

---

## Task list

| ID | Task | Est. |
|----|------|------|
| P0-T01 | Repository layout + virtual environment | 0.5 d |
| P0-T02 | Config (`config.yaml` + `.env`) | 0.5 d |
| P0-T03 | SQLite database + migrations | 0.5 d |
| P0-T04 | Core Pydantic models | 0.5 d |
| P0-T05 | Call cache | 0.5 d |
| P0-T06 | Rate limiter with budgets | 0.5 d |
| P0-T07 | Metrics | 0.25 d |
| P0-T08 | LLM provider (async, streaming, JSON) | 1 d |
| P0-T09 | Embeddings + reranker providers | 0.5 d |
| P0-T10 | Async ↔ sync bridge for Streamlit | 0.25 d |
| P0-T11 | Job queue + tasks + progress | 1 d |
| P0-T12 | Worker process | 0.5 d |
| P0-T13 | Smoke test script | 0.25 d |
| P0-T14 | Streamlit skeleton (notebooks, demo job, performance tab) | 0.5 d |
| P0-T15 | Test setup | 0.25 d |

---

### P0-T01: Repository layout + virtual environment

**Goal:** a clean, runnable project that follows the structure in plan §4.

**Files:**
```
.gitignore
assistant/__init__.py
assistant/requirements.txt
assistant/.env.example
assistant/config.yaml
assistant/core/__init__.py
assistant/core/{config.py, db.py, models.py}
assistant/core/migrations/001_runtime.sql
assistant/core/runtime/{__init__.py, aio.py, cache.py, limiter.py, metrics.py, queue.py, progress.py}
assistant/core/providers/{__init__.py, base.py, llm.py, embeddings.py, rerank.py}
assistant/worker.py
assistant/scripts/{__init__.py, smoke_test.py}
assistant/app/streamlit_app.py
assistant/tests/{__init__.py, conftest.py}
pytest.ini
```

**Steps:**
1. Create the folders and empty `__init__.py` files.
2. Create the venv at the repo root:
   ```powershell
   & "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -m venv .venv   # Python 3.13
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   ```
3. `assistant/requirements.txt` for Phase 0 only (add packages in the phase that needs them):
   ```
   streamlit>=1.37
   openai
   pydantic>=2
   pydantic-settings
   python-dotenv
   pyyaml
   tenacity
   aiolimiter
   httpx
   qdrant-client
   pytest
   pytest-asyncio
   ```
4. `pip install -r assistant\requirements.txt`, then **pin versions**: `pip freeze > assistant\requirements.lock.txt`.
5. `.gitignore`:
   ```
   .venv/
   .env
   data/
   __pycache__/
   *.pyc
   .pytest_cache/
   ```
6. Start Qdrant: `docker compose up -d` (see `docker-compose.yml`; storage is a Docker named volume, because bind-mounting Windows folders can corrupt Qdrant data), or download `qdrant-x86_64-pc-windows-msvc.zip` from Qdrant's GitHub releases and run `qdrant.exe`.

**Done when:** `python -c "import assistant"` works from the repo root, and `http://localhost:6333/dashboard` opens.

---

### P0-T02: Config (`config.yaml` + `.env`)

**Goal:** one place for every model ID, limit, threshold and path. Code never hard-codes them.

**Files:** `assistant/config.yaml`, `assistant/.env.example`, `assistant/core/config.py`

**`.env.example`:**
```
NVIDIA_API_KEY=nvapi-xxxxxxxx
```

**`config.yaml` (initial; later phases add sections):**
```yaml
paths:
  data_dir: data

nvidia:
  base_url: https://integrate.api.nvidia.com/v1     # OpenAI-compatible (chat, embeddings)
  ai_base_url: https://ai.api.nvidia.com/v1         # NIM-specific endpoints (rerank, OCR, ...)
  grpc_server: grpc.nvcf.nvidia.com:443             # Riva speech (Phase 4, 6)
  timeout_s: 120

limits:
  background_share: 0.8      # share of each model's rpm the worker may use; the UI gets the rest

models:
  chat:
    id: nvidia/llama-3.3-nemotron-super-49b-v1.5
    fallbacks: [meta/llama-3.3-70b-instruct]
    rpm: 35
    max_in_flight: 6
    max_tokens: 4096
    temperature: 0.2
  fast:
    id: meta/llama-3.1-8b-instruct
    fallbacks: []
    rpm: 35
    max_in_flight: 8
    max_tokens: 2048
    temperature: 0.1
  embed:
    id: nvidia/llama-3.2-nv-embedqa-1b-v2
    fallbacks: [baai/bge-m3]
    rpm: 35
    max_in_flight: 4
    batch_size: 32
  rerank:
    id: nvidia/llama-3.2-nv-rerankqa-1b-v2
    endpoint: retrieval/nvidia/llama-3_2-nv-rerankqa-1b-v2/reranking   # check the model page
    rpm: 35
    max_in_flight: 4

qdrant:
  url: http://localhost:6333
  collection: chunks

cache:
  enabled: true
```

> ⚠️ Before you fill in the IDs, open each model on `build.nvidia.com`, check it exists and that your key can call it, and note its **real rate limit**. Some models (for example Nemotron Super) have a **reasoning on/off switch** in the system prompt (`/think` / `/no_think` or `detailed thinking on/off`, depending on the version). Read the model card. Turn reasoning **off** for extraction and cleanup tasks, and strip any `<think>…</think>` text from outputs.

**Code sketch (`core/config.py`):**
```python
from functools import lru_cache
from pathlib import Path
import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]        # repo root
PKG = ROOT / "assistant"

class ModelCfg(BaseModel):
    id: str
    fallbacks: list[str] = []
    rpm: int = 30
    max_in_flight: int = 4
    max_tokens: int | None = None
    temperature: float | None = None
    batch_size: int | None = None
    endpoint: str | None = None
    function_id: str | None = None   # Riva (Phase 4, 6)
    extra: dict = {}

class Secrets(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    nvidia_api_key: str

class Settings(BaseModel):
    raw: dict
    models: dict[str, ModelCfg]
    secrets: Secrets

    @property
    def data_dir(self) -> Path:
        return ROOT / self.raw["paths"]["data_dir"]

    def section(self, name: str) -> dict:
        return self.raw.get(name, {})

@lru_cache
def get_settings() -> Settings:
    raw = yaml.safe_load((PKG / "config.yaml").read_text(encoding="utf-8"))
    models = {k: ModelCfg(**v) for k, v in raw["models"].items()}
    return Settings(raw=raw, models=models, secrets=Secrets())
```

**Done when:** `get_settings().models["chat"].id` returns the configured ID, and a missing `NVIDIA_API_KEY` raises a clear error.

**Tests:** load the config; check every `models.*` entry has `id`, `rpm` and `max_in_flight`.

---

### P0-T03: SQLite database + migrations

**Goal:** a durable store for metadata, jobs, tasks, cache and metrics. WAL mode lets the worker write while Streamlit reads.

**Files:** `core/db.py`, `core/migrations/001_runtime.sql`

**`001_runtime.sql`:**
```sql
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);

CREATE TABLE notebooks (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE jobs (
  id TEXT PRIMARY KEY,
  notebook_id TEXT REFERENCES notebooks(id),
  type TEXT NOT NULL,                 -- 'demo', 'ingest_file', 'resume', 'podcast', ...
  params_json TEXT NOT NULL,
  status TEXT NOT NULL,               -- queued | running | done | failed | cancelled
  priority INTEGER NOT NULL DEFAULT 0,
  worker_id TEXT,
  heartbeat_at TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  error TEXT,
  result_json TEXT
);
CREATE INDEX idx_jobs_status ON jobs(status, priority DESC, created_at);

CREATE TABLE tasks (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(id),
  key TEXT NOT NULL,                  -- stable key, e.g. 'page:12', 'chunk:3'
  kind TEXT NOT NULL,                 -- 'ocr_page', 'embed_batch', ...
  stage TEXT,
  status TEXT NOT NULL,               -- pending | running | done | failed | skipped
  attempts INTEGER NOT NULL DEFAULT 0,
  duration_ms INTEGER,
  error TEXT,
  result_json TEXT,
  updated_at TEXT NOT NULL,
  UNIQUE(job_id, key)
);
CREATE INDEX idx_tasks_job ON tasks(job_id, status);

CREATE TABLE call_cache (
  key TEXT PRIMARY KEY,               -- sha256 of (kind, model, version, input)
  kind TEXT NOT NULL,                 -- 'llm', 'embed', 'ocr', 'asr', ...
  model TEXT,
  pipeline_version TEXT,
  value TEXT NOT NULL,                -- JSON
  created_at TEXT NOT NULL,
  hits INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  stage TEXT NOT NULL,
  model TEXT,
  duration_ms INTEGER,
  cache_hit INTEGER,
  status TEXT,                        -- ok | error | rate_limited
  tokens_in INTEGER,
  tokens_out INTEGER,
  job_id TEXT
);
CREATE INDEX idx_metrics_ts ON metrics(ts);
```

**Code sketch (`core/db.py`):**
```python
import sqlite3, threading
from datetime import datetime, timezone
from pathlib import Path
from assistant.core.config import get_settings, PKG

_local = threading.local()

def now() -> str:
    return datetime.now(timezone.utc).isoformat()

def connect() -> sqlite3.Connection:
    """One connection per thread; WAL; foreign keys on."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        path = get_settings().data_dir / "app.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, timeout=30, isolation_level=None)  # autocommit; use BEGIN explicitly
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        _local.conn = conn
    return conn

def init_db() -> None:
    conn = connect()
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
    applied = {r[0] for r in conn.execute("SELECT version FROM schema_version")}
    for f in sorted((PKG / "core" / "migrations").glob("*.sql")):
        v = int(f.name.split("_")[0])
        if v not in applied:
            conn.executescript(f.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_version VALUES (?, ?)", (v, now()))
```

> **Note:** `executescript` commits automatically. Keep each migration idempotent where you can (`IF NOT EXISTS`).

**Done when:** `init_db()` creates `data/app.db` and running it twice changes nothing.

**Tests:** use a temporary data directory (fixture overrides `paths.data_dir`) → `init_db()` twice → `schema_version` has one row per file.

---

### P0-T04: Core Pydantic models

**Goal:** shared types for the whole project. Define them now, even if later phases fill them.

**File:** `core/models.py`

```python
from typing import Literal
from pydantic import BaseModel, Field

Lang = Literal["fr", "en", "mixed", "unknown"]
BlockType = Literal["heading", "paragraph", "list", "table", "formula",
                    "figure_description", "image_text", "transcript_segment", "code"]

class Block(BaseModel):
    id: str
    type: BlockType
    text: str
    level: int | None = None
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    start_s: float | None = None
    end_s: float | None = None
    extractor: str
    confidence: float | None = None
    verified_by: list[str] = []
    important: bool = False
    language: Lang = "unknown"
    section_path: list[str] = []

class PageReport(BaseModel):
    page: int
    page_class: Literal["TEXT", "MIXED", "SCANNED", "COMPLEX"] | None = None
    text_chars: int = 0
    image_coverage: float = 0.0
    images_total: int = 0
    images_processed: int = 0
    extractors: list[str] = []
    rerouted_by_missed_text: bool = False
    duration_ms: int = 0
    warnings: list[str] = []

class DocumentIR(BaseModel):
    doc_id: str
    notebook_id: str
    filename: str
    kind: Literal["pdf", "image", "audio", "text", "markdown", "docx", "pptx"]
    language: Lang = "unknown"
    title: str | None = None
    blocks: list[Block] = []
    page_reports: list[PageReport] = []
    warnings: list[str] = []
    pipeline_version: str = "1"

class Chunk(BaseModel):
    id: str                      # uuid5 string (Qdrant point id)
    key: str                     # f"{doc_id}:c{n}"
    notebook_id: str
    doc_id: str
    filename: str
    kind: str
    order: int
    text: str                    # text shown to the LLM
    embed_text: str              # text with contextual header (what gets embedded)
    section_path: list[str] = []
    page_start: int | None = None
    page_end: int | None = None
    start_s: float | None = None
    end_s: float | None = None
    language: Lang = "unknown"
    important: bool = False
    block_ids: list[str] = []
    min_confidence: float | None = None
    concept_ids: list[str] = []

class Citation(BaseModel):
    n: int
    chunk_id: str
    doc_id: str
    filename: str
    page: int | None = None
    start_s: float | None = None
    snippet: str
```

**Done when:** these models import cleanly and round-trip through `model_dump_json()` / `model_validate_json()`.

---

### P0-T05: Call cache

**Goal:** never pay twice for the same model call. This is the main speed-up during development.

**File:** `core/runtime/cache.py`

**Design:**
- Key = `sha256(json.dumps({"kind", "model", "version", "input"}, sort_keys=True, ensure_ascii=False))`.
- `input` is anything JSON-serializable. For images and audio, pass their **content hash** instead of the bytes.
- An interface (`CallCache` protocol) with a SQLite implementation, so Redis can be plugged in later (Phase 8).

```python
from typing import Protocol, Any
import hashlib, json

def make_key(kind: str, model: str, version: str, payload: Any) -> str:
    raw = json.dumps({"k": kind, "m": model, "v": version, "p": payload},
                     sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

class CallCache(Protocol):
    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, *, kind: str, model: str | None, version: str) -> None: ...

class SqliteCallCache:
    def get(self, key):
        row = connect().execute("SELECT value FROM call_cache WHERE key=?", (key,)).fetchone()
        if row is None:
            return None
        connect().execute("UPDATE call_cache SET hits = hits + 1 WHERE key=?", (key,))
        return json.loads(row["value"])

    def set(self, key, value, *, kind, model, version):
        connect().execute(
            "INSERT OR REPLACE INTO call_cache(key, kind, model, pipeline_version, value, created_at, hits)"
            " VALUES (?,?,?,?,?,?,0)",
            (key, kind, model, version, json.dumps(value, ensure_ascii=False), now()))

def get_cache() -> CallCache: ...   # returns a singleton; a no-op cache when config cache.enabled is false
```

Also add a helper decorator or function used by every provider:

```python
async def cached_call(kind, model, version, payload, fn):
    key = make_key(kind, model, version, payload)
    if (hit := cache.get(key)) is not None:
        metrics.record(stage=kind, model=model, cache_hit=True, duration_ms=0)
        return hit
    value = await fn()
    cache.set(key, value, kind=kind, model=model, version=version)
    return value
```

**Done when:** calling the same LLM prompt twice makes only one HTTP request.

**Tests:** set → get round-trip; a different version gives a different key; non-ASCII French text works.

---

### P0-T06: Rate limiter with budgets

**Goal:** stay under each model's rate limit, and keep some capacity for interactive use (chat, quizzes) so background work never blocks the student.

**File:** `core/runtime/limiter.py`

**Design:**
- One limiter **per model role** (`chat`, `fast`, `embed`, ...).
- `aiolimiter.AsyncLimiter(max_rate=rpm_budget, time_period=60)` + `asyncio.Semaphore(max_in_flight)`.
- **Budget split between processes:** the worker process uses `rpm × background_share`, and the Streamlit process uses `rpm × (1 − background_share)`. Each process sets its "process kind" at startup: `limiter.configure(process="worker" | "ui")`. This needs no cross-process coordination, which is fine on one machine. Phase 8 replaces it with a Redis limiter.

```python
import asyncio
from contextlib import asynccontextmanager
from aiolimiter import AsyncLimiter

_PROCESS = "ui"
_limiters: dict[str, tuple[AsyncLimiter, asyncio.Semaphore]] = {}

def configure(process: str) -> None:
    global _PROCESS
    _PROCESS = process

def _get(role: str):
    if role not in _limiters:
        cfg = get_settings().models[role]
        share = get_settings().section("limits").get("background_share", 0.8)
        rpm = cfg.rpm * (share if _PROCESS == "worker" else 1 - share)
        _limiters[role] = (AsyncLimiter(max(1, int(rpm)), 60), asyncio.Semaphore(cfg.max_in_flight))
    return _limiters[role]

@asynccontextmanager
async def slot(role: str):
    limiter, sem = _get(role)
    async with sem:
        await limiter.acquire()
        yield
```

> **Event loop gotcha:** `asyncio.Semaphore` objects belong to the loop they're first used on. Create the limiters lazily inside the running loop (as above), and use a single long-lived loop per process (P0-T10, P0-T12).

**Done when:** firing 100 calls with `rpm=30` takes about 3+ minutes and never gets a 429.

**Tests:** with a fake async function and `rpm=60, max_in_flight=2`, at most 2 run at the same time.

---

### P0-T07: Metrics

**Goal:** know where time goes from day one.

**File:** `core/runtime/metrics.py`

```python
def record(stage: str, *, model: str | None = None, duration_ms: int | None = None,
           cache_hit: bool | None = None, status: str = "ok",
           tokens_in: int | None = None, tokens_out: int | None = None, job_id: str | None = None) -> None: ...

class timer:  # context manager: `with metrics.timer("pdf.analyze", job_id=...)`
    ...

def summary(since: str | None = None) -> list[dict]:
    """Aggregates per stage/model: count, p50, p95, cache hit rate, errors, 429s."""
```

Write metrics in a batch (keep a small in-memory buffer and flush every ~2 s or 50 rows) so hot loops don't hit SQLite on every call.

**Done when:** the Performance tab (P0-T14) shows per-stage counts and timings.

---

### P0-T08: LLM provider (async, streaming, JSON)

**Goal:** a single function set for every chat-model call in the project.

**Files:** `core/providers/base.py`, `core/providers/llm.py`

**Features:**
- `AsyncOpenAI(base_url=nvidia.base_url, api_key=...)` created once per process.
- **Roles**, not model IDs: `chat(messages, role="chat")` looks up `models[role]`.
- Retries with `tenacity`: on `RateLimitError`, `APITimeoutError`, `APIConnectionError` and 5xx errors, use exponential backoff with jitter, 5 attempts. Record `status="rate_limited"` in metrics on 429.
- **Fallbacks**: if the primary model still fails after retries (or returns 404), try `fallbacks` in order and log which one answered.
- Cache through `cached_call` (kind `"llm"`). Payload = model + messages + temperature + max_tokens + prompt version.
- Strip `<think>...</think>` from outputs.
- `chat_json(messages, schema: type[BaseModel])`: ask for JSON. Use `response_format={"type": "json_object"}` if the model supports it, otherwise only the instructions. Parse with `schema.model_validate_json`. On failure, retry **once** with the validation error added to the conversation ("Your JSON was invalid: … Return only valid JSON matching this schema").
- `stream(messages, role="chat")` is an async generator of text deltas. **Not cached.** It records time to first token in metrics.

```python
async def chat(messages: list[dict], *, role: str = "chat", temperature: float | None = None,
               max_tokens: int | None = None, prompt_version: str = "v1", cache: bool = True) -> str: ...

async def chat_json(messages: list[dict], schema: type[T], *, role: str = "fast",
                    prompt_version: str = "v1") -> T: ...

async def stream(messages: list[dict], *, role: str = "chat") -> AsyncIterator[str]: ...
```

**Helper for extracting JSON** (models sometimes wrap it in ```json fences):
```python
def extract_json(text: str) -> str:
    text = strip_think(text).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    start = min([i for i in (text.find("{"), text.find("[")) if i != -1], default=0)
    return text[start:]
```

**Done when:** `chat`, `chat_json` (with a small Pydantic schema) and `stream` all work against NVIDIA. Repeating the `chat` call is a cache hit.

**Tests:** unit tests with a fake client (monkeypatch) for retry, fallback, JSON repair and think-stripping. Plus a `@pytest.mark.live` test with the real API.

---

### P0-T09: Embeddings + reranker providers

**Files:** `core/providers/embeddings.py`, `core/providers/rerank.py`

**Embeddings:**
- Use the OpenAI-compatible `/embeddings` endpoint. NVIDIA retrieval embedding models need an **input type**: `extra_body={"input_type": "passage" | "query", "truncate": "END"}`. Check the model card.
- `embed_passages(texts)` splits into batches of `batch_size`, runs batches concurrently (through the limiter), and caches **per text** (key = model + input_type + text) so only new texts are sent.
- `embed_query(text)` is a single call, cached.
- Record the **vector dimension** at first call. The Qdrant collection is created with it (Phase 1).

```python
async def embed_passages(texts: list[str]) -> list[list[float]]: ...
async def embed_query(text: str) -> list[float]: ...
async def embedding_dim() -> int: ...
```

**Reranker:**
- A NIM endpoint, not OpenAI-compatible: `POST {ai_base_url}/{models.rerank.endpoint}` with
  ```json
  {"model": "<id>", "query": {"text": "..."}, "passages": [{"text": "..."}, ...], "truncate": "END"}
  ```
  The response contains `rankings: [{"index": i, "logit": x}, ...]`. **Check the exact URL and shape on the model page.**
- Use `httpx.AsyncClient` with an `Authorization: Bearer` header, the same retry policy, the limiter and the cache.

```python
class RerankHit(BaseModel):
    index: int
    score: float

async def rerank(query: str, passages: list[str], top_n: int | None = None) -> list[RerankHit]: ...
```

**Done when:** embedding 100 short texts takes ≤ 4 requests (batch 32). Rerank orders an obviously relevant passage first.

**Tests:** batching splits correctly, and per-text cache hits skip requests (fake client).

---

### P0-T10: Async ↔ sync bridge for Streamlit

**Goal:** Streamlit scripts are synchronous and rerun often. Async providers need one long-lived event loop.

**File:** `core/runtime/aio.py`

```python
import asyncio, threading, queue
from typing import AsyncIterator, Iterator, TypeVar, Awaitable

_loop: asyncio.AbstractEventLoop | None = None

def _ensure_loop() -> asyncio.AbstractEventLoop:
    global _loop
    if _loop is None:
        _loop = asyncio.new_event_loop()
        threading.Thread(target=_loop.run_forever, daemon=True, name="aio-loop").start()
    return _loop

def run_sync(coro: Awaitable[T], timeout: float | None = None) -> T:
    return asyncio.run_coroutine_threadsafe(coro, _ensure_loop()).result(timeout)

def iter_sync(agen: AsyncIterator[str]) -> Iterator[str]:
    """Bridge an async generator into a sync generator (for st.write_stream)."""
    q: queue.Queue = queue.Queue()
    DONE = object()
    async def pump():
        try:
            async for item in agen:
                q.put(item)
        except Exception as e:
            q.put(e)
        finally:
            q.put(DONE)
    asyncio.run_coroutine_threadsafe(pump(), _ensure_loop())
    while (item := q.get()) is not DONE:
        if isinstance(item, Exception):
            raise item
        yield item
```

In Streamlit, call `limiter.configure("ui")` once, and keep the loop alive across reruns. The module-level global already does that within one Streamlit server process.

**Done when:** `st.write_stream(iter_sync(llm.stream(messages)))` streams tokens.

---

### P0-T11: Job queue + tasks + progress

**Goal:** submit slow work from the UI, run it in the worker, see progress, and resume after crashes.

**Files:** `core/runtime/queue.py`, `core/runtime/progress.py`

**JobQueue interface (SQLite implementation now, Redis later):**
```python
class Job(BaseModel):
    id: str; notebook_id: str | None; type: str; params: dict; status: str

class JobQueue(Protocol):
    def enqueue(self, type: str, params: dict, notebook_id: str | None = None, priority: int = 0) -> str: ...
    def claim(self, worker_id: str) -> Job | None: ...
    def heartbeat(self, job_id: str) -> None: ...
    def complete(self, job_id: str, result: dict | None = None) -> None: ...
    def fail(self, job_id: str, error: str) -> None: ...
    def cancel(self, job_id: str) -> None: ...
    def requeue_stale(self, older_than_s: int = 120) -> int: ...
```

**Claiming safely in SQLite** (one atomic statement; needs SQLite ≥ 3.35 for `RETURNING`, which Python 3.13 ships):
```sql
UPDATE jobs SET status='running', worker_id=?, started_at=COALESCE(started_at, ?), heartbeat_at=?
WHERE id = (SELECT id FROM jobs WHERE status='queued' ORDER BY priority DESC, created_at LIMIT 1)
RETURNING id, notebook_id, type, params_json, status;
```

**Tasks API** (inside a running job):
```python
class TaskRef(BaseModel):
    job_id: str
    key: str
    kind: str

def ensure_tasks(job_id: str, items: list[tuple[str, str]]) -> None:
    """Insert (key, kind) as 'pending' if not present (INSERT OR IGNORE) → enables resume."""

def pending_tasks(job_id: str) -> list[TaskRef]: ...
def task_done(job_id: str, key: str, result: dict | None, duration_ms: int) -> None: ...
def task_failed(job_id: str, key: str, error: str) -> None: ...
def task_result(job_id: str, key: str) -> dict | None: ...
def set_stage(job_id: str, key: str, stage: str) -> None: ...
```

**Resume rule:** when a job restarts, `ensure_tasks` is idempotent, and only tasks that aren't `done` are run again. Task results are saved in `tasks.result_json` (small) or on disk (large, with the path in `result_json`).

**Progress (`progress.py`):**
```python
class JobProgress(BaseModel):
    job_id: str
    status: str
    total: int
    done: int
    failed: int
    running: int
    current_stages: list[str]
    eta_s: float | None          # avg duration of done tasks × remaining / effective concurrency
    error: str | None

def job_progress(job_id: str) -> JobProgress: ...
def notebook_jobs(notebook_id: str, active_only: bool = False) -> list[JobProgress]: ...
```

**Done when:** you can enqueue a job, the worker claims it, tasks show up with statuses, and `job_progress` reports correct counts.

**Tests:** two concurrent `claim` calls never return the same job; `ensure_tasks` twice doesn't duplicate; `requeue_stale` requeues a job whose heartbeat is older than the limit.

---

### P0-T12: Worker process

**Goal:** the long-running process that executes jobs.

**File:** `assistant/worker.py`

**Design:**
- `python -m assistant.worker [--concurrency 2]`
- At startup: `init_db()`, `limiter.configure("worker")`, `queue.requeue_stale()`.
- A **handler registry**: `@handler("demo")`, `@handler("ingest_file")`, ... Each phase registers its handlers in its own module, and the worker imports `assistant.core.handlers` so all of them are registered.
- Main loop: run up to `concurrency` jobs concurrently. Poll `claim()` every 1 s when idle. Send a heartbeat every 15 s per running job.
- Each handler runs its tasks with `asyncio.gather` (or `asyncio.TaskGroup`). Concurrency per model is controlled by the limiter, not by the handler.
- Catch exceptions per task, so one failed page doesn't fail the whole document. The job fails only if the handler raises.
- Graceful stop on Ctrl+C: finish or abandon tasks; unfinished jobs are requeued on the next start.

```python
HANDLERS: dict[str, Callable[[Job, "JobContext"], Awaitable[dict | None]]] = {}

def handler(name: str):
    def deco(fn):
        HANDLERS[name] = fn
        return fn
    return deco

class JobContext:
    job: Job
    async def run_tasks(self, items: list[tuple[str, str]], fn, *, stage: str) -> dict[str, Any]:
        """ensure_tasks + run pending ones concurrently with fn(key) + record results/progress.
        Returns {key: result} for all tasks (including those done in a previous run)."""
```

**Demo handler** (for the phase acceptance test):
```python
@handler("demo")
async def demo(job, ctx):
    n = job.params.get("n", 100)
    async def one(key):
        i = int(key.split(":")[1])
        return {"answer": await llm.chat([{"role": "user", "content": f"Give one word for number {i}."}], role="fast")}
    await ctx.run_tasks([(f"q:{i}", "demo_llm") for i in range(n)], one, stage="llm")
```

**Done when:** the phase acceptance criteria pass (kill the worker mid-job → restart → only the remaining tasks run).

---

### P0-T13: Smoke test script

**File:** `assistant/scripts/smoke_test.py` → run with `python -m assistant.scripts.smoke_test`

**Checks** (print ✅ / ❌ with timings for each):
1. Config loads and the API key is present.
2. SQLite init.
3. `llm.chat` with role `chat` and role `fast`, in French: "Réponds en une phrase : qu'est-ce que la photosynthèse ?"
4. `llm.chat_json` with a tiny schema.
5. `embed_query` + `embed_passages` (prints the dimension).
6. `rerank` with 3 passages.
7. Qdrant reachable (`client.get_collections()`).
8. Second run of step 3 is a cache hit.

**Done when:** all checks are green.

---

### P0-T14: Streamlit skeleton

**File:** `assistant/app/streamlit_app.py` (split into `assistant/app/pages_*.py` modules as it grows)

**Contents now:**
- At startup: `init_db()`, `limiter.configure("ui")`.
- **Sidebar**: notebook selector + "New notebook" form, and a live list of active jobs for the notebook.
- **Tabs** (empty placeholders for later phases): Sources · Chat · Résumé · Podcast · Learn · Eval · Performance · Settings.
- **Performance tab**: a button "Run demo job (100 tasks)" → `queue.enqueue("demo", {"n": 100})`. A progress section uses `@st.fragment(run_every="2s")` to read `job_progress` and show a progress bar, counts and ETA. A metrics table comes from `metrics.summary()`: stage, model, count, p50, p95, cache-hit %, errors, 429s.
- **Settings tab**: read-only view of `config.yaml` (model IDs and limits).

```python
@st.fragment(run_every="2s")
def job_panel(job_id: str):
    p = job_progress(job_id)
    st.progress(p.done / max(p.total, 1), text=f"{p.done}/{p.total} · ETA {fmt(p.eta_s)}")
    if p.failed:
        st.warning(f"{p.failed} tasks failed")
```

**Done when:** the phase acceptance test can be run entirely from the UI.

---

### P0-T15: Test setup

**Files:** `pytest.ini`, `assistant/tests/conftest.py`

```ini
[pytest]
testpaths = assistant/tests
asyncio_mode = auto
markers =
    live: calls the real NVIDIA API (deselected by default)
addopts = -m "not live"
```

`conftest.py` fixtures:
- `tmp_settings`: points `paths.data_dir` to `tmp_path`, clears the `get_settings` cache, and calls `init_db()`.
- `fake_llm`: monkeypatches the OpenAI client to return scripted responses.
- `qdrant_mem`: `QdrantClient(":memory:")` for store tests (Phase 1).

Run all: `pytest`. Run live tests: `pytest -m live`.

---

## Phase 0 checklist

- [x] P0-T01 layout + venv + Qdrant running (Python 3.13; Qdrant via `docker-compose.yml`; optional Dockerfile for worker + UI)
- [x] P0-T02 config
- [x] P0-T03 SQLite + migrations
- [x] P0-T04 models
- [x] P0-T05 cache
- [x] P0-T06 limiter
- [x] P0-T07 metrics
- [x] P0-T08 LLM provider (tested with a fake client; ⏳ not yet against the real API)
- [x] P0-T09 embeddings + rerank (tested with a fake client; ⏳ reranker endpoint not yet verified live)
- [x] P0-T10 async bridge
- [x] P0-T11 queue + tasks + progress
- [x] P0-T12 worker (hard-kill + restart verified: only unfinished tasks reran)
- [ ] P0-T13 smoke test green ⏳ needs `.env` with a real `NVIDIA_API_KEY`
- [x] P0-T14 Streamlit skeleton
- [x] P0-T15 tests (31 passing)
- [ ] **Acceptance:** 100-task demo job (parallel, within limits, live progress, survives restart, second run fully cached). Restart/resume already verified with fake tasks; ⏳ the real-API run remains.
