# Phase 6: Podcast

**Goal:** generate a natural, two-host audio podcast (French or English) that summarizes the notebook. It's built from the **verified items** of Phase 5, so it adds no invented facts. A short (~5 min) and a deep-dive (~15 min) format are available, plus a "my weak points" option once Phase 7 exists.

**Estimate:** ~1 week · **Depends on:** Phase 5

**Phase done when:** a natural-sounding 5-minute French podcast is generated from a real notebook, the fact review finds **no claim outside the sources**, editing one script line re-renders only that line, and the MP3 has chapter markers and a transcript.

---

## Task list

| ID | Task | Est. |
|----|------|------|
| P6-T01 | Migration `007_podcast.sql` | 0.25 d |
| P6-T02 | TTS provider (Riva Magpie) + voice discovery | 1 d |
| P6-T03 | Local TTS fallback (Piper) | 0.5 d |
| P6-T04 | Podcast input pack | 0.25 d |
| P6-T05 | Outline generation | 0.25 d |
| P6-T06 | Script generation (dialogue JSON) | 0.75 d |
| P6-T07 | Speech normalization (numbers, formulas, symbols) | 0.5 d |
| P6-T08 | Script fact review | 0.5 d |
| P6-T09 | Synthesis per line (parallel, cached) | 0.25 d |
| P6-T10 | Audio assembly + chapters + transcript | 0.5 d |
| P6-T11 | Podcast job | 0.25 d |
| P6-T12 | UI: Podcast tab with script editor | 0.5 d |
| P6-T13 | Podcast eval + tests | 0.25 d |

**New requirements:**
```
num2words        # numbers → words in FR/EN
pydub            # audio assembly (uses ffmpeg)
mutagen          # MP3 chapter (ID3 CHAP) tags
piper-tts        # optional local TTS fallback
```

**New config:**
```yaml
models:
  tts:
    id: nvidia/magpie-tts-multilingual
    function_id: "<copy from the model page>"
    rpm: 30
    max_in_flight: 4
    sample_rate: 44100            # check supported rates on the model page

podcast:
  words_per_minute: 150
  lengths: {short: 5, deep: 15}   # minutes
  max_words_per_line: 40
  pause_ms_same_speaker: 250
  pause_ms_turn: 450
  pause_ms_segment: 1200
  voices:                         # fill after running voice discovery (P6-T02)
    fr: {A: "<voice name>", B: "<voice name>"}
    en: {A: "<voice name>", B: "<voice name>"}
  local_voices:                   # Piper fallback voice models
    fr: {A: fr_FR-siwis-medium, B: fr_FR-upmc-medium}
    en: {A: en_US-lessac-medium, B: en_US-ryan-medium}

pipeline_versions:
  podcast_script: "1"
  tts: "1"
```

---

### P6-T01: Migration `007_podcast.sql`

```sql
CREATE TABLE podcasts (
  id TEXT PRIMARY KEY,
  notebook_id TEXT NOT NULL,
  options_json TEXT NOT NULL,       -- language, length, scope, focus_weak, voices
  content_hash TEXT NOT NULL,
  status TEXT NOT NULL,             -- scripting | review | synthesizing | done | failed
  outline_json TEXT,
  review_json TEXT,
  audio_path TEXT,
  transcript_path TEXT,
  duration_s REAL,
  created_at TEXT NOT NULL
);

CREATE TABLE podcast_lines (
  podcast_id TEXT NOT NULL REFERENCES podcasts(id) ON DELETE CASCADE,
  idx INTEGER NOT NULL,
  segment INTEGER NOT NULL,
  speaker TEXT NOT NULL,            -- A | B
  text TEXT NOT NULL,               -- display text (may contain symbols)
  spoken TEXT NOT NULL,             -- normalized text sent to TTS
  item_ids_json TEXT,               -- verified items this line is based on
  audio_path TEXT,
  audio_hash TEXT,                  -- hash(spoken + voice + tts version) → re-render only when changed
  duration_ms INTEGER,
  PRIMARY KEY (podcast_id, idx)
);
```

---

### P6-T02: TTS provider (Riva Magpie) + voice discovery

**File:** `core/providers/tts.py`

Same gRPC pattern as ASR (P4-T04):
```python
import riva.client

def _service() -> riva.client.SpeechSynthesisService:
    auth = riva.client.Auth(uri=grpc_server, use_ssl=True,
                            metadata_args=[["function-id", cfg.function_id],
                                           ["authorization", f"Bearer {api_key}"]])
    return riva.client.SpeechSynthesisService(auth)

async def synthesize(text: str, *, language: Lang, voice: str) -> bytes:
    """Returns WAV bytes. Runs synthesize() in a thread under limiter.slot('tts').
    Cached by hash(text + voice + language + model + version) → files in data/audio/tts/<hash>.wav"""
    def call():
        resp = _service().synthesize(
            text, voice_name=voice,
            language_code="fr-FR" if language == "fr" else "en-US",
            sample_rate_hz=cfg.sample_rate,
            encoding=riva.client.AudioEncoding.LINEAR_PCM)
        return pcm_to_wav(resp.audio, cfg.sample_rate)
```

**Voice discovery script** `python -m assistant.scripts.list_voices`:
- Check the model page for the list of voices (names like `Magpie-Multilingual.FR-FR.<Name>`; recent Riva clients may also offer a "get config" call that lists them).
- Synthesize the same French and English test sentence with each candidate voice into `data/audio/voice_samples/`, so you can listen and pick **two clearly different voices per language** (for example one female, one male).
- Write the chosen names into `podcast.voices`.

Notes:
- Keep each TTS request to **one line** (≤ 40 words). Long inputs sound flatter and may hit request limits.
- If the model supports SSML or emotion tags, keep them out of v1. Plain text is more predictable.

---

### P6-T03: Local TTS fallback (Piper)

**File:** `core/providers/tts_local.py`

- Piper runs locally on CPU, fast, with FR and EN voices. Download the `.onnx` + `.json` voice files once into `data/models/piper/`.
- Same interface: `synthesize_local(text, language, voice) -> bytes` (WAV).
- Used when Magpie fails after retries, or when `podcast.provider: local` is set (offline development).
- Don't mix providers inside one podcast. If more than 10% of lines fail on Magpie, re-render the whole podcast locally so the voices stay consistent.

---

### P6-T04: Podcast input pack

**File:** `core/artifacts/podcast/inputs.py`

Build a compact, **verified-only** input for the script writer:

```python
class PodcastPack(BaseModel):
    title: str
    language: Lang
    overview: str                      # notebook overview (P2-T10)
    topics: list[TopicPack]            # in course order (P5-T12 topics)
    emphasis: list[ItemRef]            # teacher emphasis items
    weak_concepts: list[str] = []      # Phase 7 (focus_weak)

class TopicPack(BaseModel):
    title: str
    items: list[ItemRef]               # verified + needs_check items, highest importance first

class ItemRef(BaseModel):
    id: str
    type: str
    term: str | None
    content: str                       # quote (definitions/theorems) or explanation (others)
    latex: str | None
    status: str
```

- Size: limit to what fits the target length: about `minutes × words_per_minute / 25` items in total, chosen by concept importance (and weakness, with `focus_weak`).
- Items with status `needs_check` can be included, but the script must **not** state them as certain (see the script rules).

---

### P6-T05: Outline generation

**File:** `core/artifacts/podcast/script.py`

One `chat` call → JSON:
```json
{"title": "…",
 "segments": [
   {"n": 0, "kind": "intro", "goal": "hook + what we'll cover", "item_ids": [], "target_words": 120},
   {"n": 1, "kind": "topic", "title": "La phase lumineuse", "item_ids": ["i12", "i15"], "target_words": 220},
   {"n": 5, "kind": "recap", "item_ids": ["i12", "i30"], "target_words": 150},
   {"n": 6, "kind": "exam_tips", "item_ids": ["..."], "target_words": 120}]}
```
Rules: 4–7 segments for short, 8–14 for deep. Total target words ≈ minutes × `words_per_minute`. Every high-importance item and every emphasis item appears in at least one segment.

Validate: the item IDs exist; the word budget is within ±15%.

---

### P6-T06: Script generation (dialogue JSON)

**Same file.** One call per segment, **in parallel** (each segment also receives the outline and the previous segment's title for continuity).

```python
class Line(BaseModel):
    speaker: Literal["A", "B"]
    text: str
    item_ids: list[str] = []

class SegmentScript(BaseModel):
    lines: list[Line]
```

**Hosts:**
- **A** = a curious student: asks questions, rephrases, says what's confusing, connects to the exam.
- **B** = a tutor: explains clearly, with examples from the course.

**Prompt rules:**
- Use **only** the provided items. Every factual line lists the `item_ids` it relies on.
- Definitions and formulas: B states them **faithfully** (wording close to the quote). Then A or B explains them in simpler words.
- `needs_check` items: say it cautiously ("vérifie dans ton cours, mais il me semble que…" / "check your notes, but I think…").
- Natural spoken style: short sentences, occasional reactions ("Ah d'accord !", "Exactement."), no Markdown, no lists, no symbols.
- Lines ≤ `max_words_per_line`. Alternate speakers, with at most 2 consecutive lines from the same speaker.
- No greetings to a named audience, no invented anecdotes, statistics or examples that aren't in the items.

Post-check: split lines that are too long at sentence boundaries; drop empty lines; check speaker alternation.

---

### P6-T07: Speech normalization

**File:** `core/artifacts/podcast/speech.py`

TTS reads symbols badly. Every line gets a `spoken` version:

1. **Formulas**: an LLM pass (`fast`, batched per segment) rewrites LaTeX or symbols in words, in the target language: `E = mc^2` → "E égale m c au carré"; `\frac{a}{b}` → "a sur b"; `x_i` → "x indice i". Validate: the output has no `$`, `\`, `^` or `_`.
2. **Numbers** (`num2words(n, lang="fr"|"en")`): integers, decimals (`3,5` → "trois virgule cinq" in FR), years ("1789" → "mille sept cent quatre-vingt-neuf"), percentages, ordinals (`XVIIe` → "dix-septième").
3. **Units** (dictionary): `°C` → "degrés Celsius", `km/h` → "kilomètres par heure", `mol` → "moles", ...
4. **Abbreviations** (dictionary + notebook glossary): `ex.` → "par exemple", `cf.` → "voir"; acronyms that are read letter by letter ("ADN" → "A D N") vs as a word ("UNESCO"), with a small editable list in config.
5. Remove any leftover Markdown (`*`, `#`, backticks).

**Tests:** a table of input → expected spoken text for FR and EN (at least 20 cases).

---

### P6-T08: Script fact review

**File:** `core/artifacts/podcast/review.py`

- Role `verifier`, per segment, temperature 0. Input: the segment lines + the full content of the items they cite.
- Output JSON: `[{"line_idx": 3, "problem": "unsupported" | "distorted" | "wrong_formula", "fix": "corrected line text"}]`.
- Apply the fixes. If a fixed line still fails a second review, **delete** the line (and fix the dialogue flow if needed by asking for a bridging line from the same items).
- **Deterministic check** as well: numbers in `text` must appear in the cited items (same as P5-T10 `numbers_match`).
- Save the review results in `podcasts.review_json` and show them in the UI.

---

### P6-T09: Synthesis per line

**File:** `core/artifacts/podcast/synth.py`

- One task per line: `tts:{idx}`, in parallel under the TTS limiter.
- `audio_hash = hash(spoken + voice + tts model + version)`. If the hash is unchanged, reuse the file. This is how **editing one line re-renders only that line**.
- Post-process each WAV: trim leading and trailing silence (pydub `detect_leading_silence`), then normalize to about −16 LUFS (or pydub `normalize` with headroom).

---

### P6-T10: Audio assembly + chapters + transcript

**File:** `core/artifacts/podcast/assemble.py`

- Concatenate with pauses: `pause_ms_same_speaker` between lines of the same speaker, `pause_ms_turn` between speakers, and `pause_ms_segment` between segments. Optional: a short intro/outro jingle (royalty-free, stored in `assistant/assets/`).
- Export MP3 (`pydub ... export(format="mp3", bitrate="96k")`).
- **Chapters**: compute the start time of each segment, and write ID3 `CHAP` / `CTOC` frames with `mutagen` (segment titles). Also store them in `outline_json` for the UI.
- **Transcript**: a Markdown file with `[mm:ss] **Host A**: text`, where each line links to the item sources (`[cours.pdf p.4]`).
- Store `duration_s`.

---

### P6-T11: Podcast job

**File:** `core/artifacts/podcast/job.py` → `@handler("podcast")`

Stages: `pack` → `outline` → `script:{segment}` (parallel) → `speech` → `review:{segment}` → status `review` → **stop here if the user chose "review the script before audio"** → `tts:{line}` (parallel) → `assemble` → `done`.

A second handler, `@handler("podcast_render")`, renders the audio of an existing (possibly edited) script. It only re-synthesizes lines whose `audio_hash` changed.

`content_hash` = hash(item IDs and contents used + options + versions) → reuse an identical existing podcast.

---

### P6-T12: UI: Podcast tab

**File:** `assistant/app/tab_podcast.py`

- **Options**: language, length (short / deep), scope (documents), "focus on my weak points" (disabled until Phase 7), "review the script before generating the audio" (checkbox), voice preview buttons.
- **Script editor** (status `review`): lines grouped by segment, with speaker, text (editable), the `spoken` version (editable, shown under the text), source chips, review flags, and add / delete / move line actions. A "Generate audio" button.
- **Player**: `st.audio(mp3)`, chapter list (clicking one plays from that time), transcript, MP3 and transcript downloads.
- **Progress**: script segments, then lines synthesized (`n/N`).

---

### P6-T13: Podcast eval + tests

**Eval (manual, documented in `assistant/eval/podcast_review.md`):**
- Generate one FR short, one FR deep and one EN short podcast.
- Check: no unsupported facts (spot-check 20 lines against the sources), formulas spoken correctly, numbers and units read correctly, voices distinct, natural pacing, actual duration within ±20% of the target.

**Tests:**
- Speech normalization table (P6-T07).
- Script validators: line length, speaker alternation, unknown item IDs.
- Assembly: chapter times match segment boundaries (using synthetic silent WAVs of known lengths).
- Re-render: changing one line's `spoken` only re-synthesizes that line (fake TTS that counts calls).

---

## Phase 6 checklist

- [ ] P6-T01 migration
- [ ] P6-T02 Magpie TTS + voices chosen
- [ ] P6-T03 Piper fallback
- [ ] P6-T04 input pack
- [ ] P6-T05 outline
- [ ] P6-T06 script
- [ ] P6-T07 speech normalization
- [ ] P6-T08 fact review
- [ ] P6-T09 per-line synthesis + cache
- [ ] P6-T10 assembly + chapters + transcript
- [ ] P6-T11 job
- [ ] P6-T12 UI
- [ ] P6-T13 eval + tests
- [ ] **Acceptance:** natural 5-min FR podcast, no unsupported facts, single-line re-render works
