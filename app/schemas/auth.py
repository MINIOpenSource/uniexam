from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime

class LoginRequest(BaseModel):
    username: str
    password: str
