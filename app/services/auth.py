from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.base import get_db
from app.db.models import User, Token, UserRole
from app.core.security import verify_password, generate_opaque_token, get_password_hash
from app.core.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def authenticate_user(self, username: str, password: str) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.username == username))
        user = result.scalars().first()
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    async def create_user_token(self, user_id: str) -> Token:
        token_str = generate_opaque_token()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

        token = Token(
            token=token_str,
            user_id=user_id,
            expires_at=expires_at
        )
        self.db.add(token)
        await self.db.commit()
        await self.db.refresh(token)
        return token

    async def logout(self, token_str: str):
        await self.db.execute(delete(Token).where(Token.token == token_str))
        await self.db.commit()

    async def get_user_by_token(self, token_str: str) -> Optional[User]:
        # Perform a join to fetch user eagerly if needed, or just select token then user
        result = await self.db.execute(select(Token).where(Token.token == token_str))
        token = result.scalars().first()

        if not token:
            return None

        # Ensure timezone awareness for comparison
        now = datetime.now(timezone.utc)
        expires_at = token.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at < now:
            # Cleanup expired token
            await self.db.delete(token)
            await self.db.commit()
            return None

        # Get user
        user_result = await self.db.execute(select(User).where(User.id == token.user_id))
        user = user_result.scalars().first()
        return user

# Dependencies
async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    auth_service = AuthService(db)
    user = await auth_service.get_user_by_token(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user

async def get_current_active_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise HTTPException(
            status_code=400, detail="The user doesn't have enough privileges"
        )
    return current_user
