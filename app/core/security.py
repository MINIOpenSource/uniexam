from passlib.context import CryptContext
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against the hashed password."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hashes a password using Argon2."""
    return pwd_context.hash(password)

def generate_opaque_token(length: int = 48) -> str:
    """Generates a secure, random opaque token."""
    return secrets.token_urlsafe(length)

def generate_reset_token() -> str:
    """Generates a token for password reset."""
    return secrets.token_urlsafe(32)
