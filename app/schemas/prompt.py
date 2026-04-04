"""Prompt, folder, format, and chain schemas."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


# Response Format schemas

class ResponseFormatBase(BaseModel):
    """Base response format schema."""
    name: str
    description: str | None = None
    template_text: str


class ResponseFormatCreate(ResponseFormatBase):
    """Schema for creating a response format."""
    pass


class ResponseFormatRead(ResponseFormatBase):
    """Schema for reading a response format."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    user_id: UUID | None
    is_default: bool
    created_at: datetime
    updated_at: datetime


class ResponseFormatUpdate(BaseModel):
    """Schema for updating a response format."""
    name: str | None = None
    description: str | None = None
    template_text: str | None = None


# Prompt Folder schemas

class PromptFolderBase(BaseModel):
    """Base prompt folder schema."""
    name: str


class PromptFolderCreate(PromptFolderBase):
    """Schema for creating a prompt folder."""
    pass


class PromptFolderRead(PromptFolderBase):
    """Schema for reading a prompt folder."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    user_id: UUID | None
    is_default: bool
    created_at: datetime


class PromptFolderUpdate(BaseModel):
    """Schema for updating a prompt folder."""
    name: str | None = None


# Prompt schemas

class PromptBase(BaseModel):
    """Base prompt schema."""
    name: str
    text: str


class PromptCreate(PromptBase):
    """Schema for creating a prompt."""
    folder_id: UUID | None = None
    response_format_id: UUID | None = None


class PromptRead(PromptBase):
    """Schema for reading a prompt."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    user_id: UUID | None
    folder_id: UUID | None
    is_default: bool
    response_format_id: UUID | None
    response_format: ResponseFormatRead | None = None
    created_at: datetime
    updated_at: datetime


class PromptUpdate(BaseModel):
    """Schema for updating a prompt."""
    name: str | None = None
    text: str | None = None
    folder_id: UUID | None = None
    response_format_id: UUID | None = None


class PromptListResponse(BaseModel):
    """Response schema for listing prompts."""
    prompts: list[PromptRead]
    folders: list[PromptFolderRead]


# Prompt Chain schemas

class PromptChainStepCreate(BaseModel):
    """Schema for creating a prompt chain step."""
    prompt_id: UUID
    step_order: int
    response_format_id: UUID | None = None


class PromptChainStepRead(BaseModel):
    """Schema for reading a prompt chain step."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    chain_id: UUID
    prompt_id: UUID
    step_order: int
    response_format_id: UUID | None
    prompt: PromptRead | None = None
    response_format: ResponseFormatRead | None = None


class PromptChainBase(BaseModel):
    """Base prompt chain schema."""
    name: str
    description: str | None = None


class PromptChainCreate(PromptChainBase):
    """Schema for creating a prompt chain."""
    steps: list[PromptChainStepCreate] = []


class PromptChainRead(PromptChainBase):
    """Schema for reading a prompt chain."""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    user_id: UUID
    steps: list[PromptChainStepRead] = []
    created_at: datetime
    updated_at: datetime


class PromptChainUpdate(BaseModel):
    """Schema for updating a prompt chain."""
    name: str | None = None
    description: str | None = None
    steps: list[PromptChainStepCreate] | None = None
