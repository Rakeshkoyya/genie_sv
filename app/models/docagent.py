"""DocAgent models for agentic document generation."""

import uuid
import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, DateTime, ForeignKey, Index, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class DocAgentStatus(str, enum.Enum):
    """Status of a DocAgent job."""
    pending = "pending"
    analyzing = "analyzing"
    planning = "planning"
    generating = "generating"
    formatting = "formatting"
    completed = "completed"
    error = "error"


class DocAgentJob(Base):
    """A DocAgent document generation job."""

    __tablename__ = "docagent_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    user_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model_used: Mapped[str] = mapped_column(String(200), nullable=False)

    # Uploaded source document info
    source_filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Agent step outputs (stored as JSON)
    analysis_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    plan_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    content_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Final output
    output_storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[DocAgentStatus] = mapped_column(
        String(50), default=DocAgentStatus.pending, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        Index("idx_docagent_jobs_user_id", "user_id"),
        Index("idx_docagent_jobs_status", "status"),
    )
