# First prompt for a coding agent

Copy everything below the line and send it as the first message to the coding agent (Claude Code, Cursor, Codex, ...) opened in this repository.

---

You're joining an existing project as its coding agent. Before writing any code, read the documentation and check the environment, as described below.

## What we're building

A **NotebookLM-style study assistant** for an E-learning platform. Students upload their course material and get help studying it:

- **Inputs:** PDFs (digital, scanned, and digital PDFs with text inside images), photos (board, handwritten notes), TXT/Markdown, DOCX/PPTX, and teacher audio recordings. Content can be in **French or English**.
- **Chat:** grounded answers in the student's language that cite the file and page or the audio timestamp, and say clearly when the answer isn't in the documents.
- **Exam-night summary ("résumé"):** complete and verified. Definitions and formulas are quoted verbatim, checked by code and by a second model, and inserted by code, never retyped by an LLM.
- **Podcast:** two hosts, built only from verified content.
- **Learning intelligence:** quizzes, flashcards (FSRS), a mastery score per concept, a tutor mode, and a study plan.
- **Constraints:** all AI models are **free NVIDIA Build endpoints** (`build.nvidia.com`); Python 3.13 with a venv; a Streamlit app is the developer's test UI; Qdrant (in Docker) is the vector database; SQLite holds metadata, jobs and the cache for now. Performance (parallelism under rate limits, caching, progress, resume after crashes) is built in from the start.

## Read these first, in this order

1. `README.md`: setup and project layout.
2. `AGENTS.md`: the rules for working in this repo (definition of done, conventions, known pitfalls). Follow them in everything you do.
3. `docs/study-assistant-plan.md`: architecture, every pipeline, and the reasons behind the design decisions. Don't change a decision recorded there without discussing it with me first.
4. `docs/phases/README.md`: how the implementation guide is organized, shared conventions, and the database migration numbering.
5. The phase file we're working on (start with `docs/phases/phase-0-foundations.md`, then `phase-1-pdf-and-chat.md`).

Then look at the existing code in `assistant/`, especially `core/runtime/` (cache, limiter, queue, jobs, progress, metrics), `core/providers/` (LLM, embeddings, rerank) and `worker.py`. Every new feature must use these instead of creating its own.

## Current state

- **Phase 0 (foundations) is implemented**, and its 31 unit tests pass (`pytest`). It was checked without an API key, including a real crash-and-resume test of the worker.
- **Not yet done in Phase 0:** the live checks with a real NVIDIA key: `python -m assistant.scripts.smoke_test`, then the 100-task demo job with real calls from the Streamlit Performance tab (it should stay within rate limits, and a second run should come fully from the cache). The model IDs and the reranker endpoint have **never been tested against the real API**, so expect to fix some of them.
- Phases 1–8 haven't started.

## How I want you to work

- **One task at a time**, by its ID in the phase guide (for example `P1-T06`). For each task: summarize what you'll do and which files you'll touch, implement it, write the tests listed in the task, run `pytest`, and show me the result. Then tick the task's box in the phase file.
- Treat each task's "Code sketch" as a starting point. If something doesn't fit, adapt it and tell me why. For a real design change, write a short decision record in `docs/decisions/`.
- **Verify NVIDIA API details** (model IDs, endpoints, request and response formats) on the model's page on build.nvidia.com, and prove them with a live test (`@pytest.mark.live`) before building on them.
- Test with **French** text and real course files, not only English examples.
- Ask me before: adding a large dependency, changing the architecture, or deleting data.

## Your first steps now

1. Read the documents listed above.
2. Check the environment and report what you find: Python version in `.venv`, `pytest` result, `docker compose ps` (Qdrant should be running; start it with `docker compose up -d`), and whether `.env` with `NVIDIA_API_KEY` exists.
3. If the key is present, run `python -m assistant.scripts.smoke_test` and fix whatever fails (most likely a model ID or an endpoint). Then help me run the Phase 0 acceptance test.
4. Then give me a short plan for Phase 1, starting with `P1-T01`, and wait for my go-ahead before you start implementing.
