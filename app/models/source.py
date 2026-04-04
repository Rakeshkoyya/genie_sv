"""Input source and dataset models."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any
import enum

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.generation import GenerationSource
    from app.models.export import ExportedDocument


class SourceType(str, enum.Enum):
    """Type of input source."""
    pdf = "pdf"
    image = "image"
    text = "text"
    excel = "excel"
    csv = "csv"
    document = "document"
    other = "other"


class Dataset(Base):
    """Dataset model for grouping input sources."""
    
    __tablename__ = "datasets"
    
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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="datasets")
    input_sources: Mapped[list["InputSource"]] = relationship(
        "InputSource", back_populates="dataset", cascade="all, delete-orphan"
    )
    exported_documents: Mapped[list["ExportedDocument"]] = relationship(
        "ExportedDocument", back_populates="dataset"
    )


class InputSource(Base):
    """Input source model for uploaded files and text content."""
    
    __tablename__ = "input_sources"
    
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
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="SET NULL"),
        nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[SourceType] = mapped_column(
        String(50),
        nullable=False
    )
    original_filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, name="metadata"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=True
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="input_sources")
    dataset: Mapped["Dataset | None"] = relationship("Dataset", back_populates="input_sources")
    generation_sources: Mapped[list["GenerationSource"]] = relationship(
        "GenerationSource", back_populates="source", cascade="all, delete-orphan"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_input_sources_user_id", "user_id"),
        Index("idx_input_sources_user_dataset", "user_id", "dataset_id"),
    )
