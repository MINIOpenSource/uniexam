from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional
from app.db.models import UserRole


class UserBase(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    role: UserRole = UserRole.USER
    is_active: bool = True


class UserCreate(UserBase):
    password: str = Field(..., min_length=6, max_length=128)


class UserRegister(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)


class PasswordChangeRequest(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=6, max_length=128)


class UserUpdate(BaseModel):
    password: Optional[str] = Field(None, min_length=6, max_length=128)
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
