"""FastAPI dependencies for authentication and common operations."""

from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.database import get_db
from app.models.user import User

settings = get_settings()
security = HTTPBearer()


class TokenPayload:
    """Decoded JWT token payload."""
    def __init__(self, user_id: str, email: str, role: str, is_approved: bool):
        self.user_id = user_id
        self.email = email
        self.role = role
        self.is_approved = is_approved


async def decode_token(token: str) -> TokenPayload:
    """Decode and validate NextAuth JWT token."""
    try:
        # NextAuth uses HS256 by default
        payload = jwt.decode(
            token,
            settings.nextauth_secret,
            algorithms=["HS256"],
            options={"verify_aud": False}
        )
        
        # Extract user info from NextAuth token structure
        # NextAuth stores user data in the 'user' or root level
        user_data = payload.get("user", payload)
        
        user_id = user_data.get("id") or payload.get("sub")
        email = user_data.get("email", "")
        role = user_data.get("role", "user")
        is_approved = user_data.get("is_approved", False)
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID"
            )
        
        return TokenPayload(
            user_id=user_id,
            email=email,
            role=role,
            is_approved=is_approved
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)]
) -> User:
    """Get the current authenticated user from JWT token."""
    token_payload = await decode_token(credentials.credentials)
    
    # Fetch user from database to get latest data
    result = await db.execute(
        select(User).where(User.id == token_payload.user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    return user


async def get_approved_user(
    user: Annotated[User, Depends(get_current_user)]
) -> User:
    """Get current user and verify they are approved."""
    if not user.is_approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not approved"
        )
    return user


async def get_admin_user(
    user: Annotated[User, Depends(get_current_user)]
) -> User:
    """Get current user and verify they are admin."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user


# Type aliases for cleaner dependency injection
CurrentUser = Annotated[User, Depends(get_current_user)]
ApprovedUser = Annotated[User, Depends(get_approved_user)]
AdminUser = Annotated[User, Depends(get_admin_user)]
DbSession = Annotated[AsyncSession, Depends(get_db)]
