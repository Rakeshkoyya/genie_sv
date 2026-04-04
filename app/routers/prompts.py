"""Prompt management router."""

from uuid import UUID
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload

from app.dependencies import DbSession, ApprovedUser
from app.models.prompt import Prompt, PromptFolder
from app.schemas.prompt import (
    PromptRead, PromptCreate, PromptUpdate, PromptListResponse,
    PromptFolderRead
)

router = APIRouter(prefix="/api/prompts", tags=["Prompts"])


@router.get("", response_model=PromptListResponse)
async def list_prompts(user: ApprovedUser, db: DbSession):
    """List user's prompts and default prompts."""
    # Get prompts (user's + defaults)
    result = await db.execute(
        select(Prompt)
        .options(selectinload(Prompt.response_format))
        .where(or_(Prompt.user_id == user.id, Prompt.is_default == True))
        .order_by(Prompt.is_default.desc(), Prompt.created_at.desc())
    )
    prompts = result.scalars().all()
    
    # Get folders (user's + defaults)
    folder_result = await db.execute(
        select(PromptFolder)
        .where(or_(PromptFolder.user_id == user.id, PromptFolder.is_default == True))
        .order_by(PromptFolder.is_default.desc(), PromptFolder.created_at.desc())
    )
    folders = folder_result.scalars().all()
    
    return PromptListResponse(
        prompts=list(prompts),
        folders=list(folders)
    )


@router.post("", response_model=PromptRead, status_code=status.HTTP_201_CREATED)
async def create_prompt(
    data: PromptCreate,
    user: ApprovedUser,
    db: DbSession
):
    """Create a new prompt."""
    prompt = Prompt(
        user_id=user.id,
        name=data.name,
        text=data.text,
        folder_id=data.folder_id,
        response_format_id=data.response_format_id,
        is_default=False
    )
    db.add(prompt)
    await db.commit()
    await db.refresh(prompt)
    
    # Load relationships
    result = await db.execute(
        select(Prompt)
        .options(selectinload(Prompt.response_format))
        .where(Prompt.id == prompt.id)
    )
    prompt = result.scalar_one()
    
    return prompt


@router.get("/{prompt_id}", response_model=PromptRead)
async def get_prompt(
    prompt_id: UUID,
    user: ApprovedUser,
    db: DbSession
):
    """Get a specific prompt."""
    result = await db.execute(
        select(Prompt)
        .options(selectinload(Prompt.response_format))
        .where(
            Prompt.id == prompt_id,
            or_(Prompt.user_id == user.id, Prompt.is_default == True)
        )
    )
    prompt = result.scalar_one_or_none()
    
    if not prompt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found")
    
    return prompt


@router.patch("/{prompt_id}", response_model=PromptRead)
async def update_prompt(
    prompt_id: UUID,
    data: PromptUpdate,
    user: ApprovedUser,
    db: DbSession
):
    """Update a prompt (user's prompts only, not defaults)."""
    result = await db.execute(
        select(Prompt).where(
            Prompt.id == prompt_id,
            Prompt.user_id == user.id,
            Prompt.is_default == False
        )
    )
    prompt = result.scalar_one_or_none()
    
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prompt not found or cannot be edited"
        )
    
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(prompt, field, value)
    
    await db.commit()
    
    # Reload with relationships
    result = await db.execute(
        select(Prompt)
        .options(selectinload(Prompt.response_format))
        .where(Prompt.id == prompt_id)
    )
    prompt = result.scalar_one()
    
    return prompt


@router.delete("/{prompt_id}")
async def delete_prompt(
    prompt_id: UUID,
    user: ApprovedUser,
    db: DbSession
):
    """Delete a prompt (user's prompts only, not defaults)."""
    result = await db.execute(
        select(Prompt).where(
            Prompt.id == prompt_id,
            Prompt.user_id == user.id,
            Prompt.is_default == False
        )
    )
    prompt = result.scalar_one_or_none()
    
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prompt not found or cannot be deleted"
        )
    
    await db.delete(prompt)
    await db.commit()
    
    return {"success": True}
