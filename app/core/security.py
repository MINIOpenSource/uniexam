import secrets
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError, VerificationError

_ph = PasswordHasher()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against the Argon2 hashed password."""
    if not plain_password or not hashed_password:
        return False
    try:
        return _ph.verify(hashed_password, plain_password)
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False


def get_password_hash(password: str) -> str:
    """Hashes a password using Argon2."""
    return _ph.hash(password)


def generate_opaque_token(length: int = 128) -> str:
    """Generates a high-entropy random opaque token (128 random bytes -> ~171 urlsafe chars)."""
    return secrets.token_urlsafe(length)


def generate_reset_token() -> str:
    """Generates a token for password reset."""
    return secrets.token_urlsafe(64)
