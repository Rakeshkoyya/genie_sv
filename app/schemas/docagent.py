"""Pydantic schemas for DocAgent."""

from __future__ import annotations
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict


# ── Request Schemas ──

class DocAgentCreateRequest(BaseModel):
    """Request to start a DocAgent job."""
    user_prompt: str
    model: str = "anthropic/claude-sonnet-4"
    title: str | None = None


class DocAgentFromSourceRequest(BaseModel):
    """Request to start a DocAgent job from an existing source."""
    source_id: UUID
    user_prompt: str
    model: str = "anthropic/claude-sonnet-4"
    title: str | None = None


# ── Document Structure Schema (JSON contract between LLM and formatter) ──

class TextRun(BaseModel):
    """A run of text with formatting."""
    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: str | None = None
    font_size: int | None = None
    highlight: str | None = None


class TableCell(BaseModel):
    """A table cell with optional formatting."""
    text: str
    bold: bool = False
    color: str | None = None
    bg_color: str | None = None
    alignment: str = "left"


class DocumentBlock(BaseModel):
    """A single block in the document structure."""
    type: str  # heading, paragraph, table, bullet_list, numbered_list, page_break, horizontal_rule, spacer
    # For headings
    level: int | None = None
    text: str | None = None
    color: str | None = None
    alignment: str | None = None
    underline: bool = False
    # For paragraphs
    runs: list[TextRun] | None = None
    # For tables
    headers: list[TableCell] | None = None
    rows: list[list[TableCell]] | None = None
    header_bg_color: str | None = None
    striped: bool = False
    border_color: str | None = None
    # For lists
    items: list[TextRun] | None = None
    # For spacer
    lines: int = 1


class DocumentSchema(BaseModel):
    """Full document structure output by the LLM."""
    title: TextRun | None = None
    subtitle: TextRun | None = None
    page_margin_inches: float = 1.0
    blocks: list[DocumentBlock]


# ── Agent Step Result Schemas ──

class AnalysisResult(BaseModel):
    """Result of the analysis step."""
    document_type: str
    key_topics: list[str]
    structure_summary: str
    content_density: str
    recommended_sections: list[str]
    total_length_estimate: str


class PlanSection(BaseModel):
    """A planned section for the document."""
    section_number: float | int | str
    heading: str
    description: str
    content_type: str  # narrative, table, list, mixed
    estimated_blocks: int | float


class PlanResult(BaseModel):
    """Result of the planning step."""
    document_title: str
    document_subtitle: str | None = None
    color_scheme: dict[str, str]
    sections: list[PlanSection]
    design_notes: str


# ── Response Schemas ──

class DocAgentJobRead(BaseModel):
    """Read schema for a DocAgent job."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    title: str | None
    user_prompt: str
    model_used: str
    source_filename: str | None
    status: str
    error_message: str | None
    output_filename: str | None
    file_size: int | None
    analysis_result: dict | None
    plan_result: dict | None
    created_at: datetime


class DocAgentJobListResponse(BaseModel):
    """Paginated list of DocAgent jobs."""
    jobs: list[DocAgentJobRead]
    total: int
