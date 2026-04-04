"""Exported document model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING
import enum

from sqlalchemy import String, Integer, DateTime, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.generation import Generation
    from app.models.source import Dataset


class ExportFormat(str, enum.Enum):
    """Export document format."""
    docx = "docx"
    txt = "txt"
    pdf = "pdf"
    png = "png"


class ExportedDocument(Base):
    """Exported document model for generated files."""
    
    __tablename__ = "exported_documents"
    
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
    generation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generations.id", ondelete="SET NULL"),
        nullable=True
    )
    format: Mapped[ExportFormat] = mapped_column(
        String(50),
        nullable=False
    )
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="exported_documents")
    dataset: Mapped["Dataset | None"] = relationship("Dataset", back_populates="exported_documents")
    generation: Mapped["Generation | None"] = relationship(
        "Generation", back_populates="exported_documents"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_exported_documents_user_id", "user_id"),
        Index("idx_exported_documents_dataset_id", "dataset_id"),
        Index("idx_exported_documents_generation_id", "generation_id"),
    )
