"""
Security utilities — JWT tokens, password hashing, and auth dependencies.

All authentication flows go through this module.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import bcrypt
import structlog
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from parikrama.config import settings
from parikrama.core.exceptions import AuthenticationError
from parikrama.db.session import get_db

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from parikrama.models.user import User

logger = structlog.get_logger()

# bearer token extractor
security_scheme = HTTPBearer(auto_error=False)


# ── Password Hashing ──────────────────────────────────────────────────

import hashlib


def hash_password(password: str) -> str:
    """Hash a plain-text password with bcrypt. Pre-hashes with SHA256 to bypass 72-byte limit."""
    pre_hashed = hashlib.sha256(password.encode("utf-8")).hexdigest().encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pre_hashed, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against its hash."""
    try:
        pre_hashed = hashlib.sha256(plain_password.encode("utf-8")).hexdigest().encode("utf-8")
        return bcrypt.checkpw(pre_hashed, hashed_password.encode("utf-8"))
    except ValueError:
        return False


# ── JWT Token Creation ────────────────────────────────────────────────


def create_access_token(user_id: str, role: str = "user") -> str:
    """Create a short-lived JWT access token."""
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> tuple[str, str]:
    """
    Create a long-lived refresh token.
    Returns (raw_token, token_hash) — store the hash, send the raw token.
    """
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        "jti": str(uuid.uuid4()),
    }
    raw_token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    token_hash = hash_password(raw_token)
    return raw_token, token_hash


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises AuthenticationError on failure."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError as e:
        raise AuthenticationError(f"Invalid token: {e}") from e


# ── FastAPI Dependencies ──────────────────────────────────────────────


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> str:
    """
    FastAPI dependency — extract and validate user ID from Bearer token.

    Usage in routes:
        @router.get("/me")
        async def me(user_id: str = Depends(get_current_user_id)):
    """
    if credentials is None:
        raise AuthenticationError("Missing authorization header")

    payload = decode_token(credentials.credentials)

    if payload.get("type") != "access":
        raise AuthenticationError("Invalid token type")

    user_id = payload.get("sub")
    if not user_id:
        raise AuthenticationError("Token missing user ID")

    return user_id


async def require_admin(user_id: str = Depends(get_current_user_id)) -> str:
    """Dependency that requires the user to be an admin."""
    # Note: in production, look up the user's role from the DB or token
    # For now, we trust the role claim in the JWT
    # This will be enhanced in Phase 1 implementation
    return user_id


async def get_current_user(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency — return the full User ORM object for the authenticated user.

    Uses standard FastAPI Depends for database session injection. Used by endpoints that
    need user.email, user.fcm_token, or other profile fields
    (e.g. ApprovalService, NotificationService).
    """
    from sqlalchemy import select

    from parikrama.models.user import User

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise AuthenticationError("User not found")
    return user
