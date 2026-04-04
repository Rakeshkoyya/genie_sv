"""Workflow models for batch processing."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING
import enum

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.source import Dataset
    from app.models.prompt import PromptChain


class WorkflowStatus(str, enum.Enum):
    """Status of a workflow run."""
    pending = "pending"
    running = "running"
    completed = "completed"
    error = "error"
    cancelled = "cancelled"


class WorkflowRun(Base):
    """A background workflow run that processes multiple files through a prompt chain."""

    __tablename__ = "workflow_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
    )
    chain_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompt_chains.id", ondelete="CASCADE"),
        nullable=False,
    )
    output_format: Mapped[str] = mapped_column(String(10), nullable=False)  # "docx" or "txt"
    filename_prefix: Mapped[str] = mapped_column(String(200), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[WorkflowStatus] = mapped_column(
        String(50),
        default=WorkflowStatus.pending,
        nullable=False,
    )
    # JSON list of source IDs to process
    source_ids: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Progress tracking
    total_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_file_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_step_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_file_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Results: list of {source_id, filename, export_id, status, error?}
    results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User")
    dataset: Mapped["Dataset"] = relationship("Dataset")
    chain: Mapped["PromptChain"] = relationship("PromptChain")

    __table_args__ = (
        Index("idx_workflow_runs_user_id", "user_id"),
        Index("idx_workflow_runs_status", "status"),
    )
