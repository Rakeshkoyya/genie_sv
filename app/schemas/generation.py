"""Generation schemas."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict

from app.models.generation import GenerationStatus
from app.schemas.source import SourceRead


class GenerationBase(BaseModel):
    """Base generation schema."""
    title: str | None = None
    prompt_text: str
    response_format_text: str | None = None
    model: str = "anthropic/claude-3.5-sonnet"


class GenerationCreate(GenerationBase):
    """Schema for creating a generation."""
    source_ids: list[UUID] = []
    chain_id: UUID | None = None


class GenerationSourceRead(BaseModel):
    """Schema for reading a generation source link."""
    model_config = ConfigDict(from_attributes=True)
    
    source_id: UUID
    source: SourceRead | None = None


class GenerationRead(BaseModel):
    """Schema for reading a generation."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    user_id: UUID
    title: str | None
    prompt_text: str
    response_format_text: str | None
    model_used: str
    response_content: str | None
    status: GenerationStatus
    error_message: str | None
    prompt_chain_id: UUID | None
    created_at: datetime
    sources: list[SourceRead] = []


class GenerationListResponse(BaseModel):
    """Response schema for listing generations."""
    generations: list[GenerationRead]
    total: int


class GenerateRequest(BaseModel):
    """Request schema for the generate endpoint."""
    source_ids: list[UUID] = []
    prompt_text: str
    format_text: str | None = None
    model: str = "anthropic/claude-3.5-sonnet"
    title: str | None = None
    chain_id: UUID | None = None


class GenerateResponse(BaseModel):
    """Response schema for the generate endpoint."""
    content: str
    generation_id: UUID
