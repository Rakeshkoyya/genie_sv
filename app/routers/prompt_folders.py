"""Prompt folder management router."""

from uuid import UUID
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, or_

from app.dependencies import DbSession, ApprovedUser
from app.models.prompt import PromptFolder
from app.schemas.prompt import PromptFolderRead, PromptFolderCreate, PromptFolderUpdate

router = APIRouter(prefix="/api/prompt-folders", tags=["Prompt Folders"])


@router.get("", response_model=list[PromptFolderRead])
async def list_folders(user: ApprovedUser, db: DbSession):
    """List user's prompt folders and default folders."""
    result = await db.execute(
        select(PromptFolder)
        .where(or_(PromptFolder.user_id == user.id, PromptFolder.is_default == True))
        .order_by(PromptFolder.is_default.desc(), PromptFolder.created_at.desc())
    )
    folders = result.scalars().all()
    return list(folders)


@router.post("", response_model=PromptFolderRead, status_code=status.HTTP_201_CREATED)
async def create_folder(
    data: PromptFolderCreate,
    user: ApprovedUser,
    db: DbSession
):
    """Create a new prompt folder."""
    folder = PromptFolder(
        user_id=user.id,
        name=data.name,
        is_default=False
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return folder


@router.patch("/{folder_id}", response_model=PromptFolderRead)
async def update_folder(
    folder_id: UUID,
    data: PromptFolderUpdate,
    user: ApprovedUser,
    db: DbSession
):
    """Update a prompt folder (user's folders only)."""
    result = await db.execute(
        select(PromptFolder).where(
            PromptFolder.id == folder_id,
            PromptFolder.user_id == user.id,
            PromptFolder.is_default == False
        )
    )
    folder = result.scalar_one_or_none()
    
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folder not found or cannot be edited"
        )
    
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(folder, field, value)
    
    await db.commit()
    await db.refresh(folder)
    return folder


@router.delete("/{folder_id}")
async def delete_folder(
    folder_id: UUID,
    user: ApprovedUser,
    db: DbSession
):
    """Delete a prompt folder (user's folders only)."""
    result = await db.execute(
        select(PromptFolder).where(
            PromptFolder.id == folder_id,
            PromptFolder.user_id == user.id,
            PromptFolder.is_default == False
        )
    )
    folder = result.scalar_one_or_none()
    
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Folder not found or cannot be deleted"
        )
    
    await db.delete(folder)
    await db.commit()
    
    return {"success": True}
