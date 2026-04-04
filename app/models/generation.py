"""Generation and generation-source junction models."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING
import enum

from sqlalchemy import String, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.source import InputSource
    from app.models.prompt import PromptChain
    from app.models.export import ExportedDocument


class GenerationStatus(str, enum.Enum):
    """Status of a generation."""
    pending = "pending"
    processing = "processing"
    completed = "completed"
    error = "error"


class Generation(Base):
    """LLM generation record model."""
    
    __tablename__ = "generations"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_format_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    response_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[GenerationStatus] = mapped_column(
        String(50),
        default=GenerationStatus.pending,
        nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_chain_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompt_chains.id", ondelete="SET NULL"),
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="generations")
    prompt_chain: Mapped["PromptChain | None"] = relationship(
        "PromptChain", back_populates="generations"
    )
    generation_sources: Mapped[list["GenerationSource"]] = relationship(
        "GenerationSource", back_populates="generation", cascade="all, delete-orphan"
    )
    exported_documents: Mapped[list["ExportedDocument"]] = relationship(
        "ExportedDocument", back_populates="generation", cascade="all, delete-orphan"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_generations_user_id", "user_id"),
        Index("idx_generations_status", "status"),
    )


class GenerationSource(Base):
    """Junction table linking generations to input sources."""
    
    __tablename__ = "generation_sources"
    
    generation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generations.id", ondelete="CASCADE"),
        primary_key=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("input_sources.id", ondelete="CASCADE"),
        primary_key=True
    )
    
    # Relationships
    generation: Mapped["Generation"] = relationship(
        "Generation", back_populates="generation_sources"
    )
    source: Mapped["InputSource"] = relationship(
        "InputSource", back_populates="generation_sources"
    )
