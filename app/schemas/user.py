"""User schemas."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr, ConfigDict

from app.models.user import UserRole, AuthProvider


class UserBase(BaseModel):
    """Base user schema."""
    email: str  # Can be email or username for credentials login
    name: str | None = None
    avatar_url: str | None = None


class UserCreate(UserBase):
    """Schema for creating a user."""
    password: str | None = None
    auth_provider: AuthProvider = AuthProvider.credentials


class UserRead(UserBase):
    """Schema for reading a user."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    role: UserRole
    is_approved: bool
    auth_provider: AuthProvider
    created_at: datetime
    updated_at: datetime


class UserUpdate(BaseModel):
    """Schema for updating a user."""
    name: str | None = None
    avatar_url: str | None = None
    is_approved: bool | None = None
    role: UserRole | None = None


class UserListResponse(BaseModel):
    """Response schema for listing users."""
    users: list[UserRead]
    total: int
