"""DocForge models for document templates and generated documents."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Integer, DateTime, Text, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class DocForgeTemplate(Base):
    """Reusable document template with placeholder definitions."""

    __tablename__ = "docforge_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    original_storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    template_storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    html_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    placeholders: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="docforge_templates")
    documents: Mapped[list["DocForgeDocument"]] = relationship(
        "DocForgeDocument", back_populates="template", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_docforge_templates_user_id", "user_id"),
    )


class DocForgeFolder(Base):
    """Folder for organising generated DocForge documents."""

    __tablename__ = "docforge_folders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="docforge_folders")
    documents: Mapped[list["DocForgeDocument"]] = relationship(
        "DocForgeDocument", back_populates="folder"
    )

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_docforge_folders_user_name"),
        Index("idx_docforge_folders_user_id", "user_id"),
    )


class DocForgeDocument(Base):
    """A generated document from a DocForge template."""

    __tablename__ = "docforge_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("docforge_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("docforge_folders.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    placeholder_values: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="docforge_documents")
    template: Mapped["DocForgeTemplate | None"] = relationship(
        "DocForgeTemplate", back_populates="documents"
    )
    folder: Mapped["DocForgeFolder | None"] = relationship(
        "DocForgeFolder", back_populates="documents"
    )

    __table_args__ = (
        Index("idx_docforge_documents_user_id", "user_id"),
        Index("idx_docforge_documents_template_id", "template_id"),
        Index("idx_docforge_documents_folder_id", "folder_id"),
    )
