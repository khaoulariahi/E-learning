# Implementation Phases: Index

These files break [the project plan](../study-assistant-plan.md) into **tasks you can implement one by one**. The plan explains *why*. These files explain *what to build, where, and how to know it's done*.

| Phase | File | Est. | Depends on |
|-------|------|------|------------|
| 0 | [Foundations + runtime](phase-0-foundations.md) | ~1 week | none |
| 1 | [TXT/MD + full PDF pipeline → chat](phase-1-pdf-and-chat.md) | ~2 weeks | 0 |
| 2 | [Accuracy + evaluation](phase-2-accuracy-eval.md) | ~1 week | 1 |
| 3 | [Images + Office documents](phase-3-images-office.md) | ~1 week | 1 (2 recommended) |
| 4 | [Audio (teacher recordings)](phase-4-audio.md) | ~1 week | 1 (2 recommended) |
| 5 | [Verified résumé + concepts](phase-5-verified-resume.md) | ~2 weeks | 2 |
| 6 | [Podcast](phase-6-podcast.md) | ~1 week | 5 |
| 7 | [Learning intelligence](phase-7-learning.md) | ~2 weeks | 5 |
| 8 | [Platform integration](phase-8-integration.md) | later | 0–7 |

Phases 3 and 4 are independent of each other, so you can do them in either order.

---

## How each task is written

```
### P1-T06: Short title
Goal         what this task achieves and why
Files        files to create or change
Steps        what to implement, in order
Code sketch  signatures / key snippets (a starting point, not final code)
Done when    acceptance criteria you can check
Tests        what to put in tests/
```

Task IDs (`P<phase>-T<nn>`) are stable, so use them in commit messages: `P1-T06: page analysis`.

## Definition of done (applies to every task)

- [ ] Code is in the file(s) listed, with type hints, using the shared interfaces (`providers/`, `runtime/`, `db.py`). No direct `openai` calls outside `providers/`.
- [ ] Every new model ID, threshold or limit lives in `config.yaml`, not in code.
- [ ] Every API call goes through the **cache** and the **rate limiter**.
- [ ] `pytest` passes. Tests that need the NVIDIA API are marked `@pytest.mark.live` and skipped by default.
- [ ] The result is **visible in Streamlit**, at least in a debug expander.
- [ ] Timings are recorded with `metrics.record(...)` for anything slower than ~100 ms.

## Conventions used in all phases

| Topic | Convention |
|-------|-----------|
| Working directory | Always the repo root `D:\Khoula\E-learning`. Run modules with `python -m assistant.<module>`. |
| Package | `assistant/` is a Python package (has `__init__.py`). Imports look like `from assistant.core.providers.llm import chat`. |
| Data | Everything generated goes into `data/` (git-ignored): `data/app.db`, `data/files/`, `data/ir/`, `data/pages/`, `data/audio/`, `data/artifacts/`. |
| IDs | `uuid4().hex` for notebooks, documents, jobs. Block IDs: `"{doc_id}:p{page}:b{n}"` or `"{doc_id}:t{n}"` for audio. Qdrant point IDs: `uuid5(NAMESPACE_URL, chunk_key)`. |
| Async | Providers are `async`. Streamlit uses the sync bridge `runtime.aio.run_sync()` / `iter_sync()` (Phase 0). |
| LLM JSON output | Always validated with a Pydantic model (`chat_json(schema=...)`), with one automatic repair retry. |
| Prompts | Live in `prompts.py` files as module-level constants with `{placeholders}`. Each prompt has a version string included in the cache key. |
| Language codes | `"fr"`, `"en"`, `"mixed"`, `"unknown"` |
| Logging | Standard `logging`, one logger per module: `log = logging.getLogger(__name__)` |

## Database migrations by phase

Each phase adds a numbered SQL file in `assistant/core/migrations/`. `db.init_db()` applies the missing ones in order.

| File | Phase | Tables |
|------|-------|--------|
| `001_runtime.sql` | 0 | `schema_version`, `notebooks`, `jobs`, `tasks`, `call_cache`, `metrics` |
| `002_documents.sql` | 1 | `documents`, `pages`, `chunks`, `chat_messages` |
| `003_eval_summaries.sql` | 2 | `summaries`, `eval_runs`, `eval_results` |
| `004_parts.sql` | 3 | adds `documents.parts_json` (multi-photo documents) |
| `005_audio.sql` | 4 | adds `documents.audio_path`, `documents.playback_path` |
| `006_resume_concepts.sql` | 5 | `concepts`, `concept_edges`, `concept_chunks`, `inventory_items`, `resume_items`, `resumes` |
| `007_podcast.sql` | 6 | `podcasts`, `podcast_lines` |
| `008_learning.sql` | 7 | `students`, `questions`, `attempts`, `mastery`, `flashcards`, `study_plans`, `grade_contests` |

If you do Phase 4 before Phase 3, keep the numbers anyway. Migrations are applied by number, and both are independent.

## Test material to collect before starting

Put it in `assistant/tests/fixtures/` (small files) or `data/samples/` (large files, git-ignored):

- [ ] French course PDF with normal digital text (10–30 pages)
- [ ] PDF with **screenshots/images that contain text** (slides pasted as pictures, code screenshots)
- [ ] Scanned PDF (photocopied handout)
- [ ] PDF with many formulas and at least one table
- [ ] 5–10 phone photos: board, handwritten notes, printed page
- [ ] One DOCX and one PPTX with speaker notes
- [ ] One teacher recording (ideally 30–60 min, French)
- [ ] One English course document
