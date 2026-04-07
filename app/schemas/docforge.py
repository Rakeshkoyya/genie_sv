"""DocForge schemas for templates, folders, and generated documents."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


# ── Placeholder definition ──

class PlaceholderDef(BaseModel):
    """A single placeholder inside a template."""
    name: str
    label: str
    original_text: str
    default_value: str = ""


# ── Template schemas ──

class TemplateCreate(BaseModel):
    """Metadata sent alongside the uploaded DOCX file (multipart form)."""
    name: str
    description: str | None = None


class TemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str
    description: str | None
    original_filename: str
    html_preview: str | None
    placeholders: list[PlaceholderDef]
    created_at: datetime
    updated_at: datetime


class TemplateListResponse(BaseModel):
    templates: list[TemplateRead]
    total: int


# ── Folder schemas ──

class FolderCreate(BaseModel):
    name: str


class FolderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    name: str
    document_count: int = 0
    created_at: datetime


class FolderListResponse(BaseModel):
    folders: list[FolderRead]
    total: int


# ── Document schemas ──

class GenerateDocumentRequest(BaseModel):
    """Request to fill a template and save the generated document."""
    template_id: UUID
    placeholder_values: dict[str, str]
    filename: str
    folder_id: UUID | None = None
    folder_name: str | None = None  # Create or find folder by name


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    template_id: UUID | None
    folder_id: UUID | None
    folder_name: str | None = None
    template_name: str | None = None
    name: str
    placeholder_values: dict[str, str]
    file_size: int | None
    created_at: datetime


class DocumentListResponse(BaseModel):
    documents: list[DocumentRead]
    total: int


class PreviewRequest(BaseModel):
    """Request body for HTML preview with placeholder values."""
    placeholder_values: dict[str, str] = {}
