"""Source and dataset schemas."""

from datetime import datetime
from uuid import UUID
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from app.models.source import SourceType


class SourceBase(BaseModel):
    """Base source schema."""
    name: str
    type: SourceType


class SourceCreate(SourceBase):
    """Schema for creating a source."""
    dataset_id: UUID | None = None
    original_filename: str | None = None
    extracted_text: str | None = None
    file_size: int | None = None
    file_metadata: dict[str, Any] | None = Field(None, alias="metadata")


class SourceRead(SourceBase):
    """Schema for reading a source."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    
    id: UUID
    user_id: UUID
    dataset_id: UUID | None
    original_filename: str | None
    storage_path: str | None
    extracted_text: str | None
    file_size: int | None
    file_metadata: dict[str, Any] | None = Field(None, serialization_alias="metadata")
    created_at: datetime
    updated_at: datetime | None = None


class SourceListResponse(BaseModel):
    """Response schema for listing sources."""
    sources: list[SourceRead]
    total: int


# Dataset schemas

class DatasetBase(BaseModel):
    """Base dataset schema."""
    name: str
    description: str | None = None


class DatasetCreate(DatasetBase):
    """Schema for creating a dataset."""
    pass


class DatasetRead(DatasetBase):
    """Schema for reading a dataset."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
    sources_count: int | None = None
    input_sources: list[SourceRead] | None = None


class DatasetUpdate(BaseModel):
    """Schema for updating a dataset."""
    name: str | None = None
    description: str | None = None


class DatasetListResponse(BaseModel):
    """Response schema for listing datasets."""
    datasets: list[DatasetRead]
    total: int
