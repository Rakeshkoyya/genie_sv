"""Workflow schemas."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict

from app.models.workflow import WorkflowStatus


class WorkflowRunCreate(BaseModel):
    """Request to start a workflow run."""
    dataset_id: UUID
    source_ids: list[UUID]
    chain_id: UUID
    output_format: str  # "docx" or "txt"
    filename_prefix: str
    model: str = "anthropic/claude-3.5-sonnet"


class WorkflowRunRead(BaseModel):
    """Full workflow run response."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    dataset_id: UUID
    chain_id: UUID
    output_format: str
    filename_prefix: str
    model: str
    status: WorkflowStatus
    source_ids: list[UUID] | dict  # JSONB stores list
    total_files: int
    completed_files: int
    current_file_index: int
    current_step_index: int
    total_steps: int
    current_file_name: str | None
    error_message: str | None
    results: list[dict] | dict | None
    created_at: datetime
    updated_at: datetime


class WorkflowRunListResponse(BaseModel):
    """List response."""
    workflows: list[WorkflowRunRead]
    total: int
