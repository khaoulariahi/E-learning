# Working rules for this repository

These rules apply to every coding agent and every person working on the study assistant. The full context is in [docs/study-assistant-plan.md](docs/study-assistant-plan.md) and [docs/phases/](docs/phases/README.md).

## How work is organized
- Work follows the phase guides in `docs/phases/`, **one task at a time**, by task ID (`P1-T06`). Don't start a phase before the previous phase's acceptance test passes.
- Each task's "Code sketch" is a starting point, not final code. Adapt it if something doesn't fit, and say why.
- When a task is done, tick its box in the phase file's checklist. If you made a design decision that differs from the guide, record it in `docs/decisions/NNN-title.md` (context, options, decision, consequences).

## Definition of done (every task)
- Code is in the files the task lists, with type hints, using the shared interfaces: `core/providers/` for **every** model call, `core/runtime/` for cache, limiter, jobs and metrics, and `core/db.py` for SQL.
- Model IDs, thresholds and limits live in `assistant/config.yaml`, never in code.
- Every API call goes through the **cache** (`cached_call`) and the **rate limiter** (`limiter.slot(role)`).
- `pytest` passes. Tests that need the real NVIDIA API are marked `@pytest.mark.live` (skipped by default; run with `pytest -m live`).
- The result is visible in the **developer UI** (`assistant/app/streamlit_app.py`), at least in a debug expander.
- Student-facing features are also wired into the **student interface** (`assistant/app/student_app.py`) by replacing the matching function in `assistant/app/student_backend.py` with the real pipeline, keeping its signature. The student interface is shown to the teacher for validation, so it must always run: never leave it broken, and keep the demo content in `demo_data.py` until the real feature replaces it. Each phase file has a `P<n>-UI` checklist item for this.
- Slow work (> ~1 s) runs as a background job with tasks (`JobContext.run_tasks`) so it shows progress and resumes after a crash.

## Conventions
- Run everything from the repo root: `python -m assistant.<module>`.
- Python 3.13, venv in `.venv`, dependencies in `assistant/requirements.txt` (ranges) and `assistant/requirements.lock.txt` (exact pins; regenerate with `pip freeze > assistant/requirements.lock.txt` after adding a package).
- Database changes: add a new numbered file in `assistant/core/migrations/` (numbers are reserved per phase in `docs/phases/README.md`). Never edit an applied migration.
- Async providers. From synchronous code (Streamlit, scripts) use `runtime.aio.run_sync()` / `iter_sync()`.
- LLM JSON output is always validated with a Pydantic model through `llm.chat_json(...)`.
- Prompts live in `prompts.py` files as constants, and each has a version string that is part of its cache key. Bump the version when you change a prompt.
- Language codes: `"fr"`, `"en"`, `"mixed"`, `"unknown"`. The app must work in French and English, so test with French text (accents, `’`, `«  »`).
- Logging: `log = logging.getLogger(__name__)`. Never log student content or secrets.

## Things to know
- **NVIDIA API details in the docs are unverified.** Model IDs, endpoint paths and request/response shapes (reranker, OCR, page parsing, Riva speech `function-id`s) come from the plan, not from a live check. Before relying on one, check the model's page on build.nvidia.com and prove it with a live test or the smoke test.
- The `openai` package is version 3.x. It's the same client API as 1.x (`AsyncOpenAI`, `chat.completions.create`), pointed at NVIDIA's OpenAI-compatible base URL.
- Rate limits are the main bottleneck (about 40 requests/min per model on the free tier). Concurrency comes from async calls under `limiter.slot`, never from unbounded loops.
- Qdrant runs in Docker (`docker compose up -d`). Data lives in Docker named volumes; don't bind-mount Windows folders for Qdrant or SQLite.
- Secrets live in `.env` at the repo root (git-ignored). Never commit keys.
