"""Pydantic schemas for the Wiki system."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


# ── Wiki ────────────────────────────────────────────────────────────

class WikiCreate(BaseModel):
    dataset_id: UUID
    name: str
    description: str | None = None
    schema_config: dict | None = None


class WikiUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    schema_config: dict | None = None


class WikiRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    dataset_id: UUID
    name: str
    description: str | None
    schema_config: dict
    stats: dict
    created_at: datetime
    updated_at: datetime


class WikiListResponse(BaseModel):
    wikis: list[WikiRead]
    total: int


# ── Wiki Pages ──────────────────────────────────────────────────────

class WikiPageCreate(BaseModel):
    title: str
    slug: str
    page_type: str
    content: str = ""
    frontmatter: dict | None = None


class WikiPageUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    frontmatter: dict | None = None


class WikiPageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    wiki_id: UUID
    title: str
    slug: str
    page_type: str
    content: str
    frontmatter: dict
    created_at: datetime
    updated_at: datetime


class WikiPageListResponse(BaseModel):
    pages: list[WikiPageRead]
    total: int


# ── Graph ───────────────────────────────────────────────────────────

class WikiGraphNode(BaseModel):
    id: str
    title: str
    slug: str
    page_type: str
    link_count: int = 0


class WikiGraphEdge(BaseModel):
    source: str
    target: str
    link_text: str | None = None


class WikiGraphResponse(BaseModel):
    nodes: list[WikiGraphNode]
    edges: list[WikiGraphEdge]


# ── Agent Operations ────────────────────────────────────────────────

class WikiIngestRequest(BaseModel):
    source_id: UUID
    model: str | None = None


class WikiQueryRequest(BaseModel):
    question: str
    model: str | None = None
    file_as_page: bool = False


class WikiQueryResponse(BaseModel):
    answer: str
    cited_pages: list[WikiPageRead] = []
    filed_page: WikiPageRead | None = None


class WikiLintIssue(BaseModel):
    type: str  # orphan_page, broken_link, contradiction, missing_page, knowledge_gap
    severity: str  # info, warning, error
    message: str
    page_id: str | None = None
    page_title: str | None = None
    suggestion: str | None = None


class WikiLintReport(BaseModel):
    issues: list[WikiLintIssue]
    summary: str
    page_count: int
    link_count: int
    orphan_count: int


# ── Transformations ─────────────────────────────────────────────────

class WikiTransformRequest(BaseModel):
    transformation_type: str
    title: str | None = None
    scope: dict | None = None  # {page_ids: [], tags: [], query: ""}
    config: dict | None = None  # style, tone, detail_level, etc.
    model: str | None = None


class WikiTransformationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    wiki_id: UUID
    title: str
    transformation_type: str
    scope: dict
    content: str
    config: dict
    status: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class WikiTransformationListResponse(BaseModel):
    transformations: list[WikiTransformationRead]
    total: int


# ── Logs ────────────────────────────────────────────────────────────

class WikiLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    wiki_id: UUID
    operation: str
    summary: str
    details: dict
    created_at: datetime


class WikiLogListResponse(BaseModel):
    logs: list[WikiLogRead]
    total: int
