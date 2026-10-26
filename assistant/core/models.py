"""Shared types for the whole project. Later phases fill them; they are defined now so every module agrees."""

from typing import Literal

from pydantic import BaseModel

Lang = Literal["fr", "en", "mixed", "unknown"]
BlockType = Literal[
    "heading", "paragraph", "list", "table", "formula",
    "figure_description", "image_text", "transcript_segment", "code",
]


class Block(BaseModel):
    id: str
    type: BlockType
    text: str                                   # Markdown (LaTeX for math)
    level: int | None = None                    # heading level
    page: int | None = None                     # PDF/office page or slide number
    bbox: tuple[float, float, float, float] | None = None
    start_s: float | None = None                # audio timestamps
    end_s: float | None = None
    extractor: str
    confidence: float | None = None
    verified_by: list[str] = []                 # second extractor that agreed (formulas)
    important: bool = False                     # teacher emphasis, "à retenir" boxes
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
    id: str                                     # uuid5 string (Qdrant point id)
    key: str                                    # f"{doc_id}:c{n}"
    notebook_id: str
    doc_id: str
    filename: str
    kind: str
    order: int
    text: str                                   # text shown to the LLM
    embed_text: str                             # text with contextual header (what gets embedded)
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
