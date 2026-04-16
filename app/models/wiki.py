"""Wiki system models for LLM-maintained knowledge bases."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, Text, ForeignKey, Index, UniqueConstraint, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.source import InputSource, Dataset


class WikiPageType(str, enum.Enum):
    entity = "entity"
    concept = "concept"
    source_summary = "source_summary"
    topic_summary = "topic_summary"
    comparison = "comparison"
    analysis = "analysis"
    index = "index"
    overview = "overview"


class WikiLogOperation(str, enum.Enum):
    ingest = "ingest"
    query = "query"
    lint = "lint"
    transform = "transform"
    update = "update"
    create_page = "create_page"
    delete_page = "delete_page"


class WikiTransformationType(str, enum.Enum):
    concept_map = "concept_map"
    qa_exercises = "qa_exercises"
    story = "story"
    podcast_transcript = "podcast_transcript"
    video_script = "video_script"
    flashcards = "flashcards"
    quiz = "quiz"
    slide_deck = "slide_deck"
    mind_map = "mind_map"
    character_story = "character_story"
    advanced_summary = "advanced_summary"
    comparison_table = "comparison_table"


class WikiTransformationStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    error = "error"


# ── Junction table ──────────────────────────────────────────────────

class WikiSourcePage(Base):
    """Junction: which input sources contributed to which wiki pages."""

    __tablename__ = "wiki_source_pages"

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("input_sources.id", ondelete="CASCADE"),
        primary_key=True,
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wiki_pages.id", ondelete="CASCADE"),
        primary_key=True,
    )


# ── Core models ─────────────────────────────────────────────────────

class Wiki(Base):
    """A wiki attached to a dataset — the persistent knowledge layer."""

    __tablename__ = "wikis"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
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
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    stats: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="wikis")
    dataset: Mapped["Dataset"] = relationship("Dataset", back_populates="wiki")
    pages: Mapped[list["WikiPage"]] = relationship(
        "WikiPage", back_populates="wiki", cascade="all, delete-orphan"
    )
    logs: Mapped[list["WikiLog"]] = relationship(
        "WikiLog", back_populates="wiki", cascade="all, delete-orphan"
    )
    transformations: Mapped[list["WikiTransformation"]] = relationship(
        "WikiTransformation", back_populates="wiki", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("user_id", "dataset_id", name="uq_wikis_user_dataset"),
        Index("idx_wikis_user_id", "user_id"),
    )


class WikiPage(Base):
    """A single wiki page — markdown content owned and maintained by the LLM."""

    __tablename__ = "wiki_pages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    wiki_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wikis.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    page_type: Mapped[WikiPageType] = mapped_column(
        Enum(WikiPageType, name="wiki_page_type", create_type=False),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    frontmatter: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    wiki: Mapped["Wiki"] = relationship("Wiki", back_populates="pages")
    outbound_links: Mapped[list["WikiPageLink"]] = relationship(
        "WikiPageLink",
        foreign_keys="WikiPageLink.source_page_id",
        back_populates="source_page",
        cascade="all, delete-orphan",
    )
    inbound_links: Mapped[list["WikiPageLink"]] = relationship(
        "WikiPageLink",
        foreign_keys="WikiPageLink.target_page_id",
        back_populates="target_page",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("wiki_id", "slug", name="uq_wiki_pages_wiki_slug"),
        Index("idx_wiki_pages_wiki_id", "wiki_id"),
        Index("idx_wiki_pages_type", "page_type"),
    )


class WikiPageLink(Base):
    """A directional cross-reference between two wiki pages."""

    __tablename__ = "wiki_page_links"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wiki_pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wiki_pages.id", ondelete="CASCADE"),
        nullable=False,
    )
    link_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    # Relationships
    source_page: Mapped["WikiPage"] = relationship(
        "WikiPage", foreign_keys=[source_page_id], back_populates="outbound_links"
    )
    target_page: Mapped["WikiPage"] = relationship(
        "WikiPage", foreign_keys=[target_page_id], back_populates="inbound_links"
    )

    __table_args__ = (
        UniqueConstraint("source_page_id", "target_page_id", name="uq_wiki_page_links_src_tgt"),
        Index("idx_wiki_page_links_source", "source_page_id"),
        Index("idx_wiki_page_links_target", "target_page_id"),
    )


class WikiLog(Base):
    """Chronological record of wiki operations."""

    __tablename__ = "wiki_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    wiki_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wikis.id", ondelete="CASCADE"),
        nullable=False,
    )
    operation: Mapped[WikiLogOperation] = mapped_column(
        Enum(WikiLogOperation, name="wiki_log_operation", create_type=False),
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )

    # Relationships
    wiki: Mapped["Wiki"] = relationship("Wiki", back_populates="logs")

    __table_args__ = (
        Index("idx_wiki_logs_wiki_created", "wiki_id", "created_at"),
    )


class WikiTransformation(Base):
    """A content transformation generated from wiki pages."""

    __tablename__ = "wiki_transformations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    wiki_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wikis.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    transformation_type: Mapped[WikiTransformationType] = mapped_column(
        Enum(WikiTransformationType, name="wiki_transformation_type", create_type=False),
        nullable=False,
    )
    scope: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[WikiTransformationStatus] = mapped_column(
        Enum(WikiTransformationStatus, name="wiki_transformation_status", create_type=False),
        nullable=False,
        default=WikiTransformationStatus.pending,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    wiki: Mapped["Wiki"] = relationship("Wiki", back_populates="transformations")

    __table_args__ = (
        Index("idx_wiki_transformations_wiki_type", "wiki_id", "transformation_type"),
    )
