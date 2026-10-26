# E-learning: Study Assistant

A NotebookLM-style study assistant for the E-learning platform. Students upload their course material (PDFs, including scanned ones and ones with text inside images; photos of notes; text and Markdown; DOCX/PPTX; teacher recordings) and then:

- **chat** with it in French or English, with answers grounded in their documents and citing the page or timestamp,
- get a **verified exam-night summary** ("résumé"), where definitions and formulas are checked against the source,
- listen to a **two-host podcast** summary,
- **practice** with quizzes and flashcards that track which concepts they've mastered.

All AI models are free endpoints from **NVIDIA Build** (`build.nvidia.com`).

## Documentation

| Read | What it is |
|------|-----------|
| [docs/study-assistant-plan.md](docs/study-assistant-plan.md) | The full plan: architecture, pipelines, design decisions and their reasons |
| [docs/phases/README.md](docs/phases/README.md) | Implementation guide, phase by phase and task by task, with conventions |
| [AGENTS.md](AGENTS.md) | Rules for coding agents (and humans) working in this repo |
| [FIRST_PROMPT.md](FIRST_PROMPT.md) | The first message to give a coding agent that starts on this project |

## Status

| Phase | State |
|-------|-------|
| 0 Foundations + runtime | ✅ Code done, 31 tests pass. ⏳ Live checks with a real API key still to run (see [phase 0 checklist](docs/phases/phase-0-foundations.md#phase-0-checklist)). |
| Student interface | ✅ Clickable demo on a sample notebook (chat, résumé, podcast, quiz, flashcards, mind map, progress); features become real phase by phase |
| 1–8 | Not started |

## Requirements

- Windows, macOS or Linux
- **Python 3.13** (for the venv workflow)
- **Docker** (Qdrant always runs in Docker; the app can too)
- An **NVIDIA API key** from [build.nvidia.com](https://build.nvidia.com)

## Setup (venv workflow, recommended for development)

Run everything from the repo root.

```powershell
# 1. Virtual environment (Windows PowerShell; on macOS/Linux use python3.13 and .venv/bin/activate)
python -m venv .venv                      # must be Python 3.13
.\.venv\Scripts\Activate.ps1               # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
python -m pip install --upgrade pip
pip install -r assistant\requirements.lock.txt

# 2. API key
copy assistant\.env.example .env           # then put your key in NVIDIA_API_KEY

# 3. Qdrant (vector database)
docker compose up -d                       # dashboard: http://localhost:6333/dashboard

# 4. Check everything works
pytest                                     # unit tests (no API calls)
python -m assistant.scripts.smoke_test     # real calls to NVIDIA + Qdrant

# 5. Run (separate terminals)
python -m assistant.worker                 # background jobs
streamlit run assistant\app\streamlit_app.py                                           # developer UI  → http://localhost:8501
streamlit run assistant\app\student_app.py --theme.base=dark --server.port=8502       # student interface → http://localhost:8502
```

**Two interfaces.** The **developer UI** is for testing every stage (debug data, metrics, evaluation). The **student interface** is the NotebookLM-style product (Sources · Chat · Studio) used for demos and validation with the teacher. It currently runs on a sample notebook (`assistant/app/demo_data.py`); its chat uses the real model over those sample sources when an API key is set, otherwise prepared answers. Each phase replaces the sample data with the real pipeline through `assistant/app/student_backend.py`.

**VS Code:** open the repo folder and install the **Python** extension (Microsoft). The repo's `.vscode/settings.json` points it at `.venv`, so every new terminal activates the venv automatically (you'll see `(.venv)` at the start of the prompt). If it doesn't, press `Ctrl+Shift+P` → "Python: Select Interpreter" → choose `.venv`, then open a new terminal.

## Setup (everything in Docker)

```powershell
copy assistant\.env.example .env           # put your key in NVIDIA_API_KEY
docker compose --profile app up -d --build # Qdrant + worker + UI at http://localhost:8501
docker compose --profile app logs -f worker
docker compose --profile app down          # stop (data is kept in Docker volumes)
```

The Docker setup keeps its data in Docker volumes (`app_data`, `qdrant_storage`), separate from the venv workflow's `./data` folder. Rebuild the image (`--build`) after changing code or requirements.

## Project layout

```
assistant/
  config.yaml            model IDs, rate limits, thresholds (never hard-code these)
  core/
    config.py db.py models.py notebooks.py
    migrations/          numbered SQL files, applied in order by db.init_db()
    runtime/             cache, rate limiter, job queue, progress, metrics, async bridge
    providers/           every model call goes through here (llm, embeddings, rerank, ...)
    handlers/            background job handlers (registered with @handler)
  worker.py              background worker: python -m assistant.worker
  app/                   Streamlit dev UI
  scripts/               smoke_test and other tools
  tests/                 pytest (pytest -m live for tests that call the real API)
docs/                    plan + phase guides
docker-compose.yml       Qdrant (+ worker and UI with --profile app)
Dockerfile               image for the worker and the UI
```
