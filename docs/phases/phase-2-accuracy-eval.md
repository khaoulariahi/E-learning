# Phase 2: Accuracy + evaluation

**Goal:** measure accuracy instead of guessing, then improve it. Build evaluation sets (extraction + Q&A, FR + EN, cross-language, "not in documents"), an eval runner, history-aware query rewriting, multi-query retrieval, a calibrated "not found" threshold, data-driven model choices, and hierarchical summaries with a notebook guide.

**Estimate:** ~1 week · **Depends on:** Phase 1

**Phase done when:** on your eval sets, **retrieval hit@8 ≥ 90%**, **answer correctness ≥ 85%**, **refusal correctness ≥ 90%** (adjust to your data), and model choices in `config.yaml` are backed by a saved eval run.

---

## Task list

| ID | Task | Est. |
|----|------|------|
| P2-T01 | Migration `003_eval_summaries.sql` | 0.25 d |
| P2-T02 | Eval dataset format + question authoring helper | 1 d |
| P2-T03 | Extraction accuracy eval (CER per page class) | 0.5 d |
| P2-T04 | Eval runner: retrieval metrics | 0.5 d |
| P2-T05 | Eval runner: answer metrics (LLM judge) | 0.5 d |
| P2-T06 | Query rewrite with history + FR↔EN variants | 0.5 d |
| P2-T07 | Multi-query retrieval + RRF | 0.25 d |
| P2-T08 | "Not found" threshold calibration | 0.25 d |
| P2-T09 | Model comparison runs | 0.5 d |
| P2-T10 | Hierarchical summaries job | 0.75 d |
| P2-T11 | Intent routing (summarize / compare / QA) | 0.25 d |
| P2-T12 | Notebook guide | 0.25 d |
| P2-T13 | Eval tab | 0.5 d |

**New requirements:** `jiwer` (character/word error rate)

**New config:**
```yaml
retrieval:
  top_k: 30
  rerank_top_n: 8
  variants: 3                    # standalone + translation + 1 paraphrase
  history_turns: 6
  not_found_threshold: null      # set by P2-T08
  include_summaries: true

summaries:
  section_min_tokens: 150        # smaller sections are merged with the next one
  section_bullets: [3, 6]
  role_section: fast
  role_document: chat

eval:
  judge_role: verifier           # a different model family from 'chat'

models:
  verifier:
    id: meta/llama-3.3-70b-instruct    # pick a different family than models.chat
    rpm: 30
    max_in_flight: 4
    temperature: 0.0
```

---

### P2-T01: Migration `003_eval_summaries.sql`

```sql
CREATE TABLE summaries (
  id TEXT PRIMARY KEY,
  notebook_id TEXT NOT NULL,
  level TEXT NOT NULL,             -- section | document | notebook
  doc_id TEXT,                     -- null for notebook level
  section_path TEXT,               -- JSON list, for section level
  block_ids TEXT,                  -- JSON list of source blocks
  language TEXT NOT NULL,
  text TEXT NOT NULL,
  extra_json TEXT,                 -- e.g. suggested questions for the notebook level
  content_hash TEXT NOT NULL,      -- hash of the source text → regenerate only when it changes
  created_at TEXT NOT NULL
);
CREATE INDEX idx_summaries_nb ON summaries(notebook_id, level);

CREATE TABLE eval_runs (
  id TEXT PRIMARY KEY,
  dataset TEXT NOT NULL,
  config_json TEXT NOT NULL,       -- models, chunking, retrieval params at run time
  git_commit TEXT,
  metrics_json TEXT,               -- aggregated metrics
  created_at TEXT NOT NULL,
  notes TEXT
);

CREATE TABLE eval_results (
  run_id TEXT NOT NULL REFERENCES eval_runs(id),
  item_id TEXT NOT NULL,
  result_json TEXT NOT NULL,       -- retrieved chunks, answer, judge outputs, scores
  PRIMARY KEY (run_id, item_id)
);
```

---

### P2-T02: Eval dataset format + authoring helper

**Files:** `assistant/eval/datasets/<name>/qa.jsonl`, `assistant/eval/datasets/<name>/notebook.yaml`, `assistant/eval/authoring.py`

**`notebook.yaml`** lists the source files the dataset expects:
```yaml
name: bio-fr
files:
  - data/samples/bio/cours_photosynthese.pdf
  - data/samples/bio/td_scanne.pdf
language: fr
```

**`qa.jsonl`** has one item per line:
```json
{"id": "bio-fr-001",
 "question": "Quelle est l'équation bilan de la photosynthèse ?",
 "lang": "fr",
 "type": "formula",
 "expected_answer": "6CO2 + 6H2O → C6H12O6 + 6O2 (en présence de lumière)",
 "must_include": ["6CO2", "C6H12O6", "6O2"],
 "sources": [{"filename": "cours_photosynthese.pdf", "page": 4}]}
```

`type` ∈ `factual | definition | formula | list | multi_hop | cross_lang | image_text | unanswerable`.
- `cross_lang`: the question is in the other language from the source.
- `image_text`: the answer exists only inside an image (tests Phase 1's key feature).
- `unanswerable`: plausible, on-topic, but **not** in the documents (`sources: []`, `expected_answer: null`).

**Target per dataset:** ~50 items: 15 factual, 8 definition, 6 formula, 4 list, 4 multi_hop, 5 cross_lang, 3 image_text, 5 unanswerable. Build **two datasets**: one mostly French, one mostly English.

**Authoring helper** (it saves time, but **you must review every item**):
- `python -m assistant.eval.authoring --notebook <id> --n 60 --out draft.jsonl` samples chunks (spread across documents and page classes) and asks the `chat` model to propose a question, a short expected answer and `must_include` terms. It records the source chunk's filename and page.
- A Streamlit review screen (in the Eval tab): accept / edit / reject each draft, then save to `qa.jsonl`.
- **Write the `unanswerable` and `cross_lang` items by hand.** Generated ones are too easy.

---

### P2-T03: Extraction accuracy eval

**Files:** `assistant/eval/extraction/<name>/page_<n>.txt` (your hand transcriptions), `assistant/eval/run_extraction_eval.py`

**Steps:**
1. Pick ~20 pages across your test PDFs: 6 TEXT, 6 MIXED, 5 SCANNED, 3 COMPLEX.
2. Type the **exact** text of each page by hand. For images with text, include that text where it appears.
3. The script loads the IR, joins the blocks of the page (header/footer removed), normalizes both sides (`normalize_text` + collapse whitespace), and computes `jiwer.cer` and `jiwer.wer`.
4. Report per page class: mean CER, worst pages, plus **"missing content"**: the share of reference words not found in the extraction (catches dropped images).

**Targets:** TEXT CER < 2%, MIXED < 5%, SCANNED < 8% (adjust after the first run). Missing content < 3%.

---

### P2-T04: Eval runner: retrieval metrics

**File:** `assistant/eval/run_eval.py`

```
python -m assistant.eval.run_eval --dataset bio-fr --notebook <id> [--notes "rerank top 10"]
```

For each item (concurrently, through the limiter):
1. Run the **same retrieval** the chat uses (rewrite → multi-query → rerank).
2. A chunk is **relevant** if its filename matches and `page_start ≤ page ≤ page_end` for any expected source.
3. Metrics:
   - `hit@k` for k = 1, 3, 8: at least one relevant chunk in the top k
   - `MRR`: 1 / rank of the first relevant chunk
   - `candidate_recall@30`: was a relevant chunk in the pre-rerank candidates? (separates "search missed it" from "reranker dropped it")
4. Skip `unanswerable` items for retrieval metrics.

Save the run config (models, chunking, retrieval params, git commit) to `eval_runs`.

---

### P2-T05: Eval runner: answer metrics

**Same file**, with `--answers` (default on).

For each item: generate the answer with the real chat engine (non-streaming mode), then judge it with the **verifier** model (temperature 0, JSON output):

| Metric | How |
|--------|-----|
| **Correctness** (0 / 0.5 / 1) | Judge compares the answer with `expected_answer`: correct, partially correct, or wrong |
| **must_include** | Deterministic: share of `must_include` terms present after `fold()` |
| **Faithfulness** | Judge splits the answer into claims; for each claim, is it supported by the **cited** chunks? Score = supported / total |
| **Citation validity** | Deterministic: share of `[n]` that point to a retrieved chunk that is relevant |
| **Refusal correctness** | `unanswerable` → the answer must say it's not in the documents; answerable → it must **not** refuse |
| **Language correctness** | `detect_language(answer) == item.lang` (or the requested language) |
| **Latency** | Time to first token, total |

**Judge prompt (correctness)**, in short: "Question / expected answer / student-facing answer. Is the answer correct and complete relative to the expected answer? Ignore style and language. Return JSON `{verdict: correct|partial|wrong, reason}`."

**Output:** aggregated metrics per item type and overall, saved in `eval_runs.metrics_json`, plus a CSV row appended to `assistant/eval/history.csv` (date, dataset, commit, key settings, metrics).

---

### P2-T06: Query rewrite with history + FR↔EN variants

**File:** `core/chat/rewrite.py`

```python
class Rewrite(BaseModel):
    standalone: str            # question made self-contained using history, original language
    translation: str           # same question in the other language (FR↔EN)
    paraphrase: str | None     # keywords / alternative phrasing (helps BM25)
    language: Lang

async def rewrite(question: str, history: list[dict], doc_languages: set[Lang]) -> Rewrite:
    """One 'fast' LLM call, JSON output. Uses the last history_turns messages.
    Skip the translation if every document in the notebook is in the question's language."""
```

Prompt rules: keep technical terms, variable names and acronyms unchanged. Resolve pronouns from history ("et sa formule ?" → "Quelle est la formule de la photosynthèse ?"). Don't answer the question.

**Tests:** a follow-up with a pronoun is resolved; the translation of a French question is in English.

---

### P2-T07: Multi-query retrieval + RRF

**File:** `core/chat/retriever.py` (extend)

1. Run `hybrid_search` for each variant **concurrently** (`asyncio.gather`).
2. Fuse across variants with RRF: `score(c) = Σ 1 / (60 + rank_v(c))`, and keep the top `top_k`.
3. Include **summaries** (P2-T10) as candidates when `include_summaries` (they're stored in Qdrant with `payload.kind = "summary"`).
4. Rerank the fused candidates with the **standalone** question → top `rerank_top_n`.
5. Record per-variant results in the debug output.

---

### P2-T08: "Not found" threshold calibration

**File:** `assistant/eval/calibrate.py`

1. From an eval run, collect the **best rerank score** of each item, labelled answerable / unanswerable.
2. Choose the threshold that maximizes balanced accuracy (or F1 on "unanswerable"), with a bias toward **not** refusing answerable questions (a false "not found" frustrates students more than a cautious answer).
3. Print the score distributions (or plot them in the Eval tab) and the chosen value. Write it to `config.yaml → retrieval.not_found_threshold` by hand.

**Engine behaviour** (`core/chat/engine.py`):
- If the best rerank score < threshold → skip the main LLM call and answer with a template: *"Je ne trouve pas cette information dans tes documents."* ("I can't find this information in your documents.") Then list the 3 closest sections (filename, page, section) as "you might want to look at:".
- The system prompt still tells the LLM to refuse when the sources don't answer. That's the second line of defence for scores just above the threshold.

> Rerank scores are model-specific logits. **Recalibrate whenever you change the reranker.**

---

### P2-T09: Model comparison runs

**File:** `assistant/eval/compare_models.py`

- **Chat LLMs**: for 2–3 candidates (e.g. Nemotron Super, Llama 3.3 70B, Mistral Large), run the answer eval with retrieval fixed. Override the model with `--set models.chat.id=...`. Compare correctness, faithfulness, French quality and latency.
- **Embedding models**: each embedding model needs its **own collection** (vector sizes differ). Collection name = `chunks__<embed-model-slug>`. Re-index the eval notebooks into it (chunk texts are the same, so only the embedding calls run), then compare retrieval metrics.
- **French quality check**: have the judge also rate fluency on French answers (1–5), and read 10 answers yourself.

**Output:** a decision record `docs/decisions/002-model-choice.md` with the results table, and updated `config.yaml`.

---

### P2-T10: Hierarchical summaries job

**Files:** `core/indexing/summaries.py`, handler `@handler("summaries")`, enqueued automatically after a document is `indexed`

**Steps:**
1. **Sections**: group the document's blocks by `section_path` at heading level ≤ 2. Merge sections shorter than `section_min_tokens` with the next one. Split sections larger than the model context into parts, summarize each part, then merge.
2. **Section summary** (`fast` model, parallel): 3–6 bullets in the document's language, covering the main ideas and naming key terms. No outside knowledge.
3. **Document summary** (`chat` model) from the section summaries: ~150–250 words + the list of main topics.
4. **Notebook overview** (`chat` model) from the document summaries: a short overview, the main themes, and **5 suggested questions** (stored in `extra_json`). Regenerated when documents are added or removed.
5. **Skip unchanged**: `content_hash` = hash of the source block texts. If it matches the stored row, keep the existing summary.
6. **Index** section and document summaries in Qdrant as extra points with `payload.kind="summary"`, `level`, `doc_id`, `section_path`. They help with broad questions.

---

### P2-T11: Intent routing

**File:** `core/chat/intents.py`

The rewrite call (P2-T06) also returns `intent` ∈ `qa | summarize | compare | quiz`, plus `targets` (document/section names, or the two things to compare).

| Intent | Handling |
|--------|----------|
| `qa` | Normal RAG |
| `summarize` | Find the matching document/section (fuzzy match on filenames and section titles). Answer from the **stored summaries** + the top chunks of that section. Cite the section's pages. |
| `compare` | Retrieve separately for each target (in parallel), merge the sources, and use a prompt asking for a structured comparison (similarities / differences, table if useful) |
| `quiz` | Phase 7. For now, reply that quizzes are coming and suggest 3 questions from the notebook guide. |

---

### P2-T12: Notebook guide

In the Chat tab, when a conversation is empty, show:
- The notebook overview (summary + main themes).
- The **suggested questions** as buttons; clicking one sends it.
- Per document: a one-line summary, expandable to the document summary.

---

### P2-T13: Eval tab

**File:** `assistant/app/tab_eval.py`

- **Datasets**: list them, show item counts by type, open the authoring/review screen (P2-T02).
- **Run**: pick a dataset and a notebook, add notes, click Run. The run executes as a worker job (`@handler("eval")`) with live progress.
- **Results**: a metrics table per item type; a table of failed items with question, expected answer, answer, judge reason, retrieved sources and the relevant rank. Click an item to see full details.
- **History**: chart key metrics over runs (from `eval_runs`), with notes as labels, so you can see whether a change helped.
- **Calibration**: the rerank-score histogram for answerable vs unanswerable, with the current threshold drawn on it.
- **Extraction eval**: CER per page class, worst pages, and a link to the IR viewer for each.

---

## Phase 2 checklist

- [ ] P2-T01 migration
- [ ] P2-T02 datasets (2 × ~50 items, reviewed)
- [ ] P2-T03 extraction eval (~20 hand-transcribed pages)
- [ ] P2-T04 retrieval metrics
- [ ] P2-T05 answer metrics
- [ ] P2-T06 query rewrite
- [ ] P2-T07 multi-query + RRF
- [ ] P2-T08 threshold calibrated
- [ ] P2-T09 model comparison + decision record
- [ ] P2-T10 summaries
- [ ] P2-T11 intents
- [ ] P2-T12 notebook guide
- [ ] P2-T13 Eval tab
- [ ] **Acceptance:** hit@8 ≥ 90%, correctness ≥ 85%, refusal correctness ≥ 90%
