"""Password hashing (Argon2 via pwdlib) and JWT access tokens (PyJWT)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import cache

import jwt
from pwdlib import PasswordHash

from app.core.config import Settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


@cache
def dummy_hash() -> str:
    """Checked against when the email is unknown, so login takes as long as with a real user."""
    return hash_password("not-a-real-password")


def create_access_token(user_id: int, settings: Settings, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    claims = {
        "sub": str(user_id),  # JWT requires a string subject
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> int:
    """User id from a valid token. Raises jwt.InvalidTokenError (bad signature, expired, malformed)."""
    claims = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["sub", "exp"]},
    )
    try:
        return int(claims["sub"])
    except ValueError as error:
        raise jwt.InvalidTokenError("subject is not a user id") from error
