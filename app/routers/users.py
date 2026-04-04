"""User management router."""

from uuid import UUID
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, func

from app.dependencies import DbSession, CurrentUser, AdminUser
from app.models.user import User
from app.schemas.user import UserRead, UserUpdate, UserListResponse

router = APIRouter(prefix="/api", tags=["Users"])


@router.get("/users/me", response_model=UserRead)
async def get_current_user_profile(user: CurrentUser):
    """Get current user's profile."""
    return user


@router.get("/admin/users", response_model=UserListResponse)
async def list_all_users(admin: AdminUser, db: DbSession):
    """List all users (admin only)."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    
    count_result = await db.execute(select(func.count(User.id)))
    total = count_result.scalar() or 0
    
    return UserListResponse(users=list(users), total=total)


@router.patch("/admin/users/{user_id}", response_model=UserRead)
async def update_user(
    user_id: UUID,
    data: UserUpdate,
    admin: AdminUser,
    db: DbSession
):
    """Update a user (admin only)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)
    
    await db.commit()
    await db.refresh(user)
    
    return user
