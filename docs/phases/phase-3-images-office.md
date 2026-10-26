# Phase 3: Images + Office documents

**Goal:** ingest photos (board, handwritten notes, printed pages), screenshots and diagrams, as well as DOCX and PPTX files. Add **formula double extraction** so OCR mistakes in formulas are caught, for both PDFs and images.

**Estimate:** ~1 week · **Depends on:** Phase 1 (Phase 2 recommended, so you can measure)

**Phase done when:** phone photos of handwritten notes produce readable IR (CER measured in the extraction eval), a photo of a printed page is as good as a scanned PDF page, a PPTX's speaker notes are searchable, and formula disagreements between two extractors show up as warnings.

---

## Task list

| ID | Task | Est. |
|----|------|------|
| P3-T01 | Router: image, DOCX, PPTX kinds (incl. HEIC) | 0.25 d |
| P3-T02 | Image preprocessing | 0.75 d |
| P3-T03 | VLM image classification | 0.25 d |
| P3-T04 | Image routes (OCR / handwriting / figure / mixed) | 0.75 d |
| P3-T05 | Guarded OCR cleanup | 0.25 d |
| P3-T06 | Multi-photo documents ("lesson batch") | 0.5 d |
| P3-T07 | Formula double extraction | 1 d |
| P3-T08 | DOCX pipeline | 0.5 d |
| P3-T09 | PPTX pipeline | 0.5 d |
| P3-T10 | Ingest job integration | 0.25 d |
| P3-T11 | UI updates | 0.25 d |
| P3-T12 | Photo / handwriting eval + tests | 0.5 d |

**New requirements:**
```
opencv-python-headless
pillow-heif          # iPhone HEIC photos
python-docx
python-pptx
sympy
antlr4-python3-runtime==4.11   # needed by sympy.parsing.latex; check the version sympy expects
```

**New config:**
```yaml
upload:
  allowed_kinds: [pdf, text, markdown, image, docx, pptx]

image:
  max_side_px: 2048
  deskew: true
  perspective_correction: true   # flatten photographed pages
  min_ocr_conf_for_skip_cleanup: 0.9

formulas:
  double_extraction: true
  second_extractor: vision       # role used for the second opinion

pipeline_versions:
  image: "1"
  office: "1"
  formula_check: "1"
```

---

### P3-T01: Router: image, DOCX, PPTX

**File:** `core/ingestion/router.py` (extend)

- Images: JPEG, PNG, WEBP, BMP, TIFF, **HEIC/HEIF**. Call `pillow_heif.register_heif_opener()` once at startup so Pillow can open HEIC.
- Multi-page TIFF → treat each frame as a page.
- DOCX / PPTX: zip-based. Check the extension, and confirm with the zip content (`word/document.xml` or `ppt/presentation.xml`).
- Old `.doc` / `.ppt` formats: reject with a message ("Enregistre le fichier en .docx / .pptx" / "Save the file as .docx / .pptx"), or convert with LibreOffice if it's installed (see P3-T09).

---

### P3-T02: Image preprocessing

**File:** `core/ingestion/image_prep.py`

```python
class PreparedImage(BaseModel, arbitrary_types_allowed=True):
    image: Image.Image
    original_size: tuple[int, int]
    steps: list[str]          # e.g. ["exif_rotate", "perspective", "deskew:-2.1°", "clahe"]

def prepare(img: Image.Image, *, is_photo: bool) -> PreparedImage:
```

Steps, in order:
1. `ImageOps.exif_transpose` (phone orientation), convert to RGB.
2. **Perspective correction** (photos of a page): OpenCV grayscale → blur → Canny → largest 4-point contour covering > 40% of the image → `getPerspectiveTransform` → warp to a rectangle. Skip it if no clear page outline is found. Never crop a whiteboard photo by accident: require a 4-point contour with plausible proportions.
3. **Deskew**: estimate the angle from text lines (`cv2.minAreaRect` on thresholded text pixels, or the median angle of RapidOCR boxes). Rotate if |angle| > 0.5°.
4. **Contrast** for photos: CLAHE on the L channel (LAB). Helps with shadows and uneven lighting.
5. Resize so the longest side ≤ `max_side_px`.

How to decide `is_photo`: EXIF camera fields present, or the image has no pure-white background (low share of near-white pixels).

**Done when:** a skewed phone photo of a printed page comes out flat and straight (visible in the IR viewer as "processed image").

---

### P3-T03: VLM image classification

**File:** `core/ingestion/image.py`

```python
class ImageClass(BaseModel):
    type: Literal["text_document", "handwritten", "slide", "diagram", "photo", "mixed"]
    language: Lang
    has_formulas: bool
    readable: Literal["good", "medium", "poor"]
    rotation_needed: Literal[0, 90, 180, 270] = 0

async def classify_image(img) -> ImageClass:
    """One small VLM call on a downscaled copy (≤ 1024 px). JSON output."""
```

If `rotation_needed` ≠ 0, rotate and continue. If `readable == "poor"`, still process, but add an IR warning shown to the student ("Photo peu lisible : vérifie le résultat" / "Photo hard to read: check the result").

---

### P3-T04: Image routes

**File:** `core/ingestion/image.py`

| Class | Route | Output blocks |
|-------|-------|---------------|
| `text_document`, `slide` | `ocr_nvidia` → lines grouped into paragraphs by vertical gaps → guarded cleanup (P3-T05) → headings from large-text lines (OCR box height) | `paragraph`, `heading`, `list`, `image_text` |
| `handwritten` | VLM `transcribe_page` with a handwriting prompt (below) | Markdown → blocks (`extractor="vlm"`) |
| `diagram`, `photo` | VLM `describe_figure` (all labels, arrows, values) | `figure_description` |
| `mixed` | OCR **and** VLM: the VLM gets the OCR text as a hint and returns structured Markdown with figure descriptions inline | Markdown → blocks |

**Handwriting prompt essentials:**
- "Transcribe the handwritten notes exactly as written, in the original language. Keep the structure (titles, bullet points, arrows → '→'). Write math in LaTeX. If a word is unreadable, write `[illisible]`. Don't correct the student's content, and don't add explanations."
- Set the temperature to 0.

**Optional accuracy boost** for handwriting (enable if the eval shows errors): a **second pass** where a different vision model gets the image + the first transcription and returns only corrections as JSON (`[{"original": "...", "corrected": "...", "reason": "..."}]`). Apply corrections only when both agree that the image shows the corrected text.

Every block gets `page = photo index` (1-based) and `bbox` when OCR provides it.

---

### P3-T05: Guarded OCR cleanup

**File:** `core/ingestion/cleanup.py` (also used by PDF image text and audio later)

LLM cleanup can "fix" text by adding content. Guard it with a deterministic check:

```python
async def guarded_cleanup(raw: str, *, lang: Lang) -> tuple[str, bool]:
    cleaned = await llm.chat(cleanup_prompt(raw, lang), role="fast")
    ratio = rapidfuzz.fuzz.ratio(fold(raw), fold(cleaned))
    len_ok = 0.85 <= len(cleaned) / max(len(raw), 1) <= 1.15
    if ratio >= 85 and len_ok:
        return cleaned, True
    return raw, False          # reject the cleanup, keep raw OCR, log it
```

Skip cleanup when the mean OCR confidence ≥ `min_ocr_conf_for_skip_cleanup`.

(Add `rapidfuzz` to requirements now if it isn't there yet. It's needed again in Phase 5.)

---

### P3-T06: Multi-photo documents ("lesson batch")

**Goal:** a student photographs 8 pages of notes. They should become **one document with 8 pages**, not 8 separate documents.

- **UI**: in the Sources tab, when several images are selected, a checkbox "Regrouper ces images en un seul document" ("Group these images as one document"), a name field, and drag-to-reorder (or a sort by filename / EXIF date, with up/down buttons).
- **Storage**: each image file is stored by its own sha256. The document's `sha256` = hash of the ordered list of image hashes. The document row stores the ordered list in a new column added by migration `004_parts.sql`: `ALTER TABLE documents ADD COLUMN parts_json TEXT;`.
- **Processing**: one task per photo (in parallel). Merge in order and set `page = index`.

---

### P3-T07: Formula double extraction

**File:** `core/ingestion/formulas.py`

**Goal:** catch OCR mistakes in formulas (a wrong exponent, sign, index or fraction), which are very costly for exam prep.

**Which blocks:** every `formula` block (and any block with inline `$…$`) whose extractor is **not** the PDF text layer: OCR, parse, or VLM output.

**Steps:**
1. **Crop the formula region**: use the block's `bbox` on the rendered page or photo, with ~10 px padding. If there's no bbox (whole-page VLM transcription), ask the second extractor for "all formulas on this page, in order, as LaTeX" and align them by order and similarity.
2. **Second extraction** with a **different extractor** from the first (if the first was `nemoretriever-parse`, use the VLM; if the first was the VLM, use a different VLM model or `parse`). Prompt: "Transcribe this formula exactly as LaTeX. Output only the LaTeX."
3. **Normalize both** (`normalize_latex`):
   - remove `\displaystyle`, `\left`, `\right`, `\,`, `\;`, `\!`, spaces
   - `\cdot` / `\times` kept distinct (they can differ in meaning), `\dfrac` → `\frac`, `^{2}` → `^2` (single-character braces removed)
   - unify `\text{…}` / `\mathrm{…}`
4. **Compare:**
   - equal after normalization → **agree**
   - else try `sympy.parsing.latex.parse_latex` on both. For equations (`=`), compare `simplify(lhs - rhs)` of both sides, or check that their difference is zero. If they're symbolically equal → **agree**.
   - else → **disagree**
5. **Result:**
   - agree → `block.verified_by.append(second_extractor)`, `confidence = max(confidence, 0.95)`
   - disagree → `confidence = min(confidence, 0.5)`, IR warning `"page 7: formula uncertain"`, and store both versions in the block's debug data. The IR viewer shows both side by side. The résumé (Phase 5) marks the formula "⚠️ vérifie dans ton cours" ("check this in your course notes").

`parse_latex` fails on many real formulas (units, text, unusual notation). That's expected. When it fails, rely on the normalized string comparison.

**Tests:** `normalize_latex` cases; `x^{2}+1` vs `x^2 + 1` → agree; `x^2` vs `x^3` → disagree; `\frac{a}{b}` vs `\dfrac{a}{b}` → agree.

---

### P3-T08: DOCX pipeline

**File:** `core/ingestion/office.py`

(If the Phase 1 Docling decision was positive, you can use Docling for DOCX/PPTX instead. Keep the same IR output.)

Using `python-docx`:
- Walk the body elements **in order** (paragraphs and tables are interleaved; iterate `document.element.body` children to keep that order).
- Paragraph style `Heading 1..6` / `Titre 1..6` (French Word) / `Title` → `heading` with level. Otherwise → `paragraph`.
- List paragraphs (`w:numPr` present, or a list style) → merge consecutive ones into `list` blocks.
- Tables → Markdown (merged cells: repeat the value).
- **Inline images** (`w:drawing` → relationship ID → image part bytes) → image sub-pipeline (P1-T15: OCR → text or VLM description), inserted at their position.
- **Equations (OMML)**: python-docx doesn't convert them. Extract the `m:oMath` text content as a raw fallback block of type `formula` with low confidence, and mark it for double extraction only if you render the document (see P3-T09 LibreOffice note).
- **Page numbers** don't exist in DOCX. Use `page = None` and cite by section (`section_path`) plus the paragraph order. The citation UI shows "section X" instead of "p. N".

---

### P3-T09: PPTX pipeline

**File:** `core/ingestion/office.py`

Using `python-pptx`:
- One slide = one page (`page = slide index`).
- Title placeholder → `heading` (level 1 for slides; a section-header layout → level 1, others → level 2).
- Text frames sorted by position (top, then left), with bullet levels from `paragraph.level` → `list` / `paragraph`.
- Tables → Markdown.
- Pictures → image sub-pipeline. Group shapes: recurse into them.
- **Speaker notes** (`slide.notes_slide.notes_text_frame.text`) → a `paragraph` block prefixed with "Notes : ", marked `important=False`, but always included. Notes often hold the actual explanations.
- **Previews (optional)**: if LibreOffice is installed (`soffice` on PATH), convert to PDF (`soffice --headless --convert-to pdf`) and render page previews for the IR viewer. The PDF also lets you run the Phase 1 missed-text detector on slides. Without LibreOffice, skip the previews.

---

### P3-T10: Ingest job integration

**File:** `core/ingestion/jobs.py` (extend the `ingest_file` handler)

- `image` → tasks: `prep:p{n}` (CPU pool) → `classify:p{n}` → `extract:p{n}` → `formula:p{n}:b{k}` → merge → chunk → index.
- `docx` / `pptx` → `parse` (local) → `img:{k}` tasks for embedded images → `formula:*` → merge → chunk → index.
- Progressive indexing works the same as for PDFs: index the local text first (DOCX/PPTX text, slide notes), then re-index after the image tasks.
- Formula checks also run for **PDF** documents now: add `formula:*` tasks to the PDF enrich stage.

---

### P3-T11: UI updates

- IR viewer: for images, show **original vs preprocessed** (toggle) next to the blocks, and the image class + readability.
- Formula blocks: a ✅ badge when verified; ⚠️ when uncertain, with both versions rendered.
- DOCX citations show section names; PPTX citations show "diapo N" / "slide N".
- Sources tab: the multi-photo grouping UI (P3-T06).

---

### P3-T12: Photo / handwriting eval + tests

- Add to the extraction eval (P2-T03): 5 photos of printed pages, 5 photos of handwritten notes, and 2 diagrams (for diagrams, check that `must_include` labels appear in the description rather than computing CER).
- Add Q&A items of type `image_text` / `handwritten` to the Q&A datasets.
- Unit tests: perspective correction on a synthetic warped image (a rectangle drawn then warped → corners recovered within a tolerance); deskew of a rotated synthetic text image; DOCX order (heading, table, paragraph, image in the right order) using a DOCX built in the test with python-docx; PPTX notes extracted.

---

## Phase 3 checklist

- [ ] P3-T01 router
- [ ] P3-T02 preprocessing
- [ ] P3-T03 classification
- [ ] P3-T04 routes
- [ ] P3-T05 guarded cleanup
- [ ] P3-T06 lesson batches
- [ ] P3-T07 formula double extraction (images + PDFs)
- [ ] P3-T08 DOCX
- [ ] P3-T09 PPTX
- [ ] P3-T10 job integration
- [ ] P3-T11 UI
- [ ] P3-T12 eval + tests
- [ ] **Acceptance:** readable handwritten notes IR, measured CER, formula disagreements flagged, PPTX notes searchable
