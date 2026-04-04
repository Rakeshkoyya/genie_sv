"""Response format management router."""

from uuid import UUID
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, or_

from app.dependencies import DbSession, ApprovedUser
from app.models.prompt import ResponseFormat
from app.schemas.prompt import ResponseFormatRead, ResponseFormatCreate, ResponseFormatUpdate

router = APIRouter(prefix="/api/formats", tags=["Response Formats"])


@router.get("", response_model=list[ResponseFormatRead])
async def list_formats(user: ApprovedUser, db: DbSession):
    """List user's response formats and default formats."""
    result = await db.execute(
        select(ResponseFormat)
        .where(or_(ResponseFormat.user_id == user.id, ResponseFormat.is_default == True))
        .order_by(ResponseFormat.is_default.desc(), ResponseFormat.created_at.desc())
    )
    formats = result.scalars().all()
    return list(formats)


@router.post("", response_model=ResponseFormatRead, status_code=status.HTTP_201_CREATED)
async def create_format(
    data: ResponseFormatCreate,
    user: ApprovedUser,
    db: DbSession
):
    """Create a new response format."""
    format_obj = ResponseFormat(
        user_id=user.id,
        name=data.name,
        description=data.description,
        template_text=data.template_text,
        is_default=False
    )
    db.add(format_obj)
    await db.commit()
    await db.refresh(format_obj)
    return format_obj


@router.get("/{format_id}", response_model=ResponseFormatRead)
async def get_format(
    format_id: UUID,
    user: ApprovedUser,
    db: DbSession
):
    """Get a specific response format."""
    result = await db.execute(
        select(ResponseFormat).where(
            ResponseFormat.id == format_id,
            or_(ResponseFormat.user_id == user.id, ResponseFormat.is_default == True)
        )
    )
    format_obj = result.scalar_one_or_none()
    
    if not format_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Format not found")
    
    return format_obj


@router.patch("/{format_id}", response_model=ResponseFormatRead)
async def update_format(
    format_id: UUID,
    data: ResponseFormatUpdate,
    user: ApprovedUser,
    db: DbSession
):
    """Update a response format (user's formats only)."""
    result = await db.execute(
        select(ResponseFormat).where(
            ResponseFormat.id == format_id,
            ResponseFormat.user_id == user.id,
            ResponseFormat.is_default == False
        )
    )
    format_obj = result.scalar_one_or_none()
    
    if not format_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Format not found or cannot be edited"
        )
    
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(format_obj, field, value)
    
    await db.commit()
    await db.refresh(format_obj)
    return format_obj


@router.delete("/{format_id}")
async def delete_format(
    format_id: UUID,
    user: ApprovedUser,
    db: DbSession
):
    """Delete a response format (user's formats only)."""
    result = await db.execute(
        select(ResponseFormat).where(
            ResponseFormat.id == format_id,
            ResponseFormat.user_id == user.id,
            ResponseFormat.is_default == False
        )
    )
    format_obj = result.scalar_one_or_none()
    
    if not format_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Format not found or cannot be deleted"
        )
    
    await db.delete(format_obj)
    await db.commit()
    
    return {"success": True}
