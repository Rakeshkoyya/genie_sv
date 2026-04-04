"""Prompt-related models."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, Boolean, Integer, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.generation import Generation


class ResponseFormat(Base):
    """Response format template model."""
    
    __tablename__ = "response_formats"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True  # Null for default formats
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
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
    prompts: Mapped[list["Prompt"]] = relationship(
        "Prompt", back_populates="response_format"
    )
    prompt_chain_steps: Mapped[list["PromptChainStep"]] = relationship(
        "PromptChainStep", back_populates="response_format"
    )


class PromptFolder(Base):
    """Folder for organizing prompts."""
    
    __tablename__ = "prompt_folders"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True  # Null for default folders
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )
    
    # Relationships
    user: Mapped["User | None"] = relationship("User", back_populates="prompt_folders")
    prompts: Mapped[list["Prompt"]] = relationship(
        "Prompt", back_populates="folder", cascade="all, delete-orphan"
    )


class Prompt(Base):
    """Saved prompt template model."""
    
    __tablename__ = "prompts"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True  # Null for default prompts
    )
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompt_folders.id", ondelete="SET NULL"),
        nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    response_format_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("response_formats.id", ondelete="SET NULL"),
        nullable=True
    )
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
    user: Mapped["User | None"] = relationship("User", back_populates="prompts")
    folder: Mapped["PromptFolder | None"] = relationship("PromptFolder", back_populates="prompts")
    response_format: Mapped["ResponseFormat | None"] = relationship(
        "ResponseFormat", back_populates="prompts"
    )
    prompt_chain_steps: Mapped[list["PromptChainStep"]] = relationship(
        "PromptChainStep", back_populates="prompt"
    )


class PromptChain(Base):
    """Multi-step prompt chain model."""
    
    __tablename__ = "prompt_chains"
    
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
    user: Mapped["User"] = relationship("User", back_populates="prompt_chains")
    steps: Mapped[list["PromptChainStep"]] = relationship(
        "PromptChainStep",
        back_populates="chain",
        cascade="all, delete-orphan",
        order_by="PromptChainStep.step_order"
    )
    generations: Mapped[list["Generation"]] = relationship(
        "Generation", back_populates="prompt_chain"
    )


class PromptChainStep(Base):
    """Individual step in a prompt chain."""
    
    __tablename__ = "prompt_chain_steps"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    chain_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompt_chains.id", ondelete="CASCADE"),
        nullable=False
    )
    prompt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompts.id", ondelete="CASCADE"),
        nullable=False
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    response_format_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("response_formats.id", ondelete="SET NULL"),
        nullable=True
    )
    
    # Relationships
    chain: Mapped["PromptChain"] = relationship("PromptChain", back_populates="steps")
    prompt: Mapped["Prompt"] = relationship("Prompt", back_populates="prompt_chain_steps")
    response_format: Mapped["ResponseFormat | None"] = relationship(
        "ResponseFormat", back_populates="prompt_chain_steps"
    )
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("chain_id", "step_order", name="uq_chain_step_order"),
        Index("idx_chain_steps_chain_id", "chain_id"),
    )
