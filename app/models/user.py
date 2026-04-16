"""User model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base

if TYPE_CHECKING:
    from app.models.source import InputSource, Dataset
    from app.models.prompt import Prompt, PromptFolder, PromptChain
    from app.models.generation import Generation
    from app.models.export import ExportedDocument
    from app.models.docforge import DocForgeTemplate, DocForgeFolder, DocForgeDocument
    from app.models.wiki import Wiki


class UserRole(str, enum.Enum):
    """User role enum."""
    admin = "admin"
    user = "user"


class AuthProvider(str, enum.Enum):
    """Authentication provider enum."""
    google = "google"
    credentials = "credentials"


class User(Base):
    """User model for authentication and authorization."""
    
    __tablename__ = "users"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[UserRole] = mapped_column(
        String(50),
        default=UserRole.user,
        nullable=False
    )
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auth_provider: Mapped[AuthProvider] = mapped_column(
        String(50),
        default=AuthProvider.credentials,
        nullable=False
    )
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    input_sources: Mapped[list["InputSource"]] = relationship(
        "InputSource", back_populates="user", cascade="all, delete-orphan"
    )
    datasets: Mapped[list["Dataset"]] = relationship(
        "Dataset", back_populates="user", cascade="all, delete-orphan"
    )
    prompts: Mapped[list["Prompt"]] = relationship(
        "Prompt", back_populates="user", cascade="all, delete-orphan"
    )
    prompt_folders: Mapped[list["PromptFolder"]] = relationship(
        "PromptFolder", back_populates="user", cascade="all, delete-orphan"
    )
    prompt_chains: Mapped[list["PromptChain"]] = relationship(
        "PromptChain", back_populates="user", cascade="all, delete-orphan"
    )
    generations: Mapped[list["Generation"]] = relationship(
        "Generation", back_populates="user", cascade="all, delete-orphan"
    )
    exported_documents: Mapped[list["ExportedDocument"]] = relationship(
        "ExportedDocument", back_populates="user", cascade="all, delete-orphan"
    )
    docforge_templates: Mapped[list["DocForgeTemplate"]] = relationship(
        "DocForgeTemplate", back_populates="user", cascade="all, delete-orphan"
    )
    docforge_folders: Mapped[list["DocForgeFolder"]] = relationship(
        "DocForgeFolder", back_populates="user", cascade="all, delete-orphan"
    )
    docforge_documents: Mapped[list["DocForgeDocument"]] = relationship(
        "DocForgeDocument", back_populates="user", cascade="all, delete-orphan"
    )
    wikis: Mapped[list["Wiki"]] = relationship(
        "Wiki", back_populates="user", cascade="all, delete-orphan"
    )
