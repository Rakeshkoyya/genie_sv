"""Export schemas."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict

from app.models.export import ExportFormat


class ExportCreate(BaseModel):
    """Schema for creating an export."""
    generation_id: UUID | None = None
    dataset_id: UUID | None = None
    format: ExportFormat
    filename: str


class ExportRead(BaseModel):
    """Schema for reading an export."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    user_id: UUID
    dataset_id: UUID | None
    dataset_name: str | None = None
    generation_id: UUID | None
    format: ExportFormat
    storage_path: str
    filename: str
    file_size: int | None
    created_at: datetime


class ExportListResponse(BaseModel):
    """Response schema for listing exports."""
    exports: list[ExportRead]
    total: int


class ExportDocxRequest(BaseModel):
    """Request schema for DOCX export."""
    title: str
    results: list[dict]  # List of {name, content} objects
    generation_id: UUID | None = None
    dataset_id: UUID | None = None


class ExportTxtRequest(BaseModel):
    """Request schema for TXT export."""
    title: str
    content: str
    generation_id: UUID | None = None
    dataset_id: UUID | None = None
