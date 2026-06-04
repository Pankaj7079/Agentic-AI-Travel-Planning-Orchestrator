# Phase 1: Backend Core + Authentication

## Overview

Phase 1 builds the **spine of the entire application** — the FastAPI backend with production-grade authentication, database models, and the layered architecture pattern (Router → Service → Repository) that every subsequent phase plugs into. This is the most important phase for code quality because every agent, every API, every notification flows through these patterns.

### Why This Phase is Critical
- **Authentication gates everything** — no feature is usable without auth
- **Database models define the data contract** — changing them later requires migrations
- **The layered pattern prevents spaghetti code** — agents, RAG, and voice all use the same service layer
- **Rate limiting prevents abuse from day one** — not something to bolt on later

---

## Architecture Decisions

### Decision 1: Router → Service → Repository Pattern
```
API Router (thin)  →  Service (business logic)  →  Repository (data access)
    ↓                       ↓                            ↓
 Validation           Authorization,              SQLAlchemy queries,
 Serialization        Orchestration               Transactions
```

**Why this over a flat architecture:**
| Approach | Pros | Cons |
|----------|------|------|
| **Layered (chosen)** | Testable, swappable DB, clear ownership | More files |
| Flat (logic in routes) | Fast to prototype | Untestable, tight coupling |
| Domain-driven | Perfect separation | Overkill for this project size |

The service layer is where business rules live. Routes are thin — they validate input, call a service, return output. Repositories abstract SQLAlchemy so services don't know about SQL.

### Decision 2: Custom JWT vs Clerk
| Approach | Cost | Control | Effort |
|----------|------|---------|--------|
| **Custom JWT (chosen)** | Free | Full control, no vendor lock-in | 2-3 days |
| Clerk.dev | Free to 10K MAU | Easy Google OAuth | 1 day |

**Why Custom JWT:** Full open-source stack philosophy. We implement JWT with `python-jose` and `passlib`. Clerk is documented as a drop-in alternative for teams that want faster auth setup.

### Decision 3: Async SQLAlchemy
**Why async:** Every I/O operation in our app is async — HTTP calls to LLMs, WebSocket connections, database queries. Using sync SQLAlchemy would block the event loop and kill throughput. `asyncpg` is the fastest PostgreSQL driver for Python.

---

## Database Schema

```sql
-- ══════════════════════════════════════════════════════════════════════
-- Phase 1 Database Tables
-- Run via Alembic migration, not manually
-- ══════════════════════════════════════════════════════════════════════

-- ── Users ────────────────────────────────────────────────────────────
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    hashed_password VARCHAR(255),          -- null for OAuth-only users
    avatar_url VARCHAR(512),
    role VARCHAR(20) NOT NULL DEFAULT 'user',  -- 'user' | 'admin'
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,

    -- OAuth fields
    google_id VARCHAR(255) UNIQUE,         -- Google OAuth subject ID
    auth_provider VARCHAR(20) NOT NULL DEFAULT 'local', -- 'local' | 'google'

    -- Notification preferences
    fcm_token VARCHAR(512),                -- Firebase Cloud Messaging token
    email_notifications BOOLEAN NOT NULL DEFAULT TRUE,
    push_notifications BOOLEAN NOT NULL DEFAULT TRUE,

    -- Travel preferences (personalization)
    preferences JSONB NOT NULL DEFAULT '{}',
    -- example: {"currency": "INR", "language": "hi", "budget_range": "mid"}

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_google_id ON users(google_id) WHERE google_id IS NOT NULL;

-- ── API Keys (programmatic access) ──────────────────────────────────
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,            -- human-readable label
    key_hash VARCHAR(255) NOT NULL,        -- SHA-256 hash (never store raw key)
    key_prefix VARCHAR(8) NOT NULL,        -- first 8 chars for identification
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,                -- null = never expires
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_api_keys_user ON api_keys(user_id);
CREATE INDEX idx_api_keys_prefix ON api_keys(key_prefix);

-- ── Refresh Tokens ──────────────────────────────────────────────────
CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL UNIQUE,  -- hashed refresh token
    device_info VARCHAR(255),                 -- "Chrome on Windows"
    ip_address VARCHAR(45),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_hash ON refresh_tokens(token_hash);
```

---

## Key APIs

```
POST   /api/v1/auth/register          Register new user
POST   /api/v1/auth/login             Login (email + password)
POST   /api/v1/auth/refresh           Refresh access token
POST   /api/v1/auth/logout            Revoke refresh token
POST   /api/v1/auth/google            Google OAuth login
GET    /api/v1/auth/google/callback   Google OAuth callback

GET    /api/v1/users/me               Get current user profile
PATCH  /api/v1/users/me               Update profile
PATCH  /api/v1/users/me/preferences   Update travel preferences
DELETE /api/v1/users/me               Delete account (soft delete)

POST   /api/v1/api-keys               Create new API key
GET    /api/v1/api-keys               List user's API keys
DELETE /api/v1/api-keys/{id}          Revoke an API key

GET    /api/v1/health                  Health check
GET    /api/v1/health/ready            Readiness check (DB + Redis)
```

---

## Implementation

### Database Session Factory

```python
# apps/backend/src/parikrama/db/session.py
"""
Async SQLAlchemy engine and session factory.

Uses connection pooling with sensible defaults.
Always use `get_db()` dependency in routes — never create sessions manually.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from parikrama.config import settings

# connection pool — reuses connections instead of creating new ones per request
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,     # verify connections before using them
    echo=settings.DEBUG,    # log SQL in development only
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # keep objects usable after commit
)


async def get_db() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency that provides a scoped database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

### Base Model with Mixins

```python
# apps/backend/src/parikrama/models/base.py
"""
SQLAlchemy declarative base with reusable mixins.

Every model inherits TimestampMixin to get created_at/updated_at automatically.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all models."""
    pass


class TimestampMixin:
    """Adds created_at and updated_at columns to any model."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    """UUID primary key — better than auto-increment for distributed systems."""
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
```

### User Model

```python
# apps/backend/src/parikrama/models/user.py
"""User model — the core identity in PariKrama."""
from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from parikrama.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # OAuth
    google_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    auth_provider: Mapped[str] = mapped_column(String(20), default="local")

    # notifications
    fcm_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    email_notifications: Mapped[bool] = mapped_column(Boolean, default=True)
    push_notifications: Mapped[bool] = mapped_column(Boolean, default=True)

    # travel preferences as JSON (flexible schema)
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict)

    # relationships
    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User {self.email}>"
```

### API Key Model

```python
# apps/backend/src/parikrama/models/api_key.py (within user.py or separate)
"""API key model for programmatic access."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from parikrama.models.base import Base, UUIDPrimaryKeyMixin


class ApiKey(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "api_keys"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", nullable=False
    )

    user = relationship("User", back_populates="api_keys")


class RefreshToken(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    device_info: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", nullable=False
    )

    user = relationship("User", back_populates="refresh_tokens")
```

### Security Module

```python
# apps/backend/src/parikrama/core/security.py
"""
JWT token management and password hashing.

Uses python-jose for JWT (supports RS256 upgrade path) and
passlib with bcrypt for password hashing (industry standard).
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from parikrama.config import settings

# bcrypt is slow by design — that's the point (brute-force resistance)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain, hashed)


def create_access_token(
    subject: str,
    role: str = "user",
    expires_delta: timedelta | None = None,
) -> str:
    """Create a short-lived JWT access token."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": subject,     # user ID
        "role": role,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str) -> str:
    """Create a long-lived refresh token (stored hashed in DB)."""
    expire = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": subject,
        "exp": expire,
        "type": "refresh",
        "jti": secrets.token_hex(16),  # unique token ID
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises JWTError on failure."""
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a secure API key.
    Returns: (raw_key, key_hash, key_prefix)
    The raw_key is shown once to the user, then only the hash is stored.
    """
    raw_key = f"pk_{secrets.token_urlsafe(32)}"  # pk_ prefix identifies PariKrama keys
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:10]  # enough to identify which key
    return raw_key, key_hash, key_prefix


def hash_api_key(raw_key: str) -> str:
    """Hash an API key for lookup."""
    return hashlib.sha256(raw_key.encode()).hexdigest()
```

### Auth Service

```python
# apps/backend/src/parikrama/services/auth_service.py
"""
Authentication business logic.

Handles registration, login, token refresh, and OAuth.
All password operations go through security module — never raw strings.
"""
import uuid
from datetime import datetime, timezone

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from parikrama.config import settings
from parikrama.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
)
from parikrama.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from parikrama.models.user import ApiKey, RefreshToken, User
from parikrama.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)

logger = structlog.get_logger()


class AuthService:
    """Handles all authentication flows."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def register(self, data: RegisterRequest) -> TokenResponse:
        """Register a new local user and return tokens."""
        # check if email already taken
        existing = await self.db.execute(
            select(User).where(User.email == data.email)
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"Email {data.email} is already registered")

        user = User(
            email=data.email,
            name=data.name,
            hashed_password=hash_password(data.password),
            auth_provider="local",
        )
        self.db.add(user)
        await self.db.flush()  # get the user ID without committing

        tokens = await self._create_tokens(user)
        logger.info("user_registered", user_id=str(user.id), email=user.email)
        return tokens

    async def login(self, data: LoginRequest) -> TokenResponse:
        """Authenticate with email + password."""
        result = await self.db.execute(
            select(User).where(User.email == data.email)
        )
        user = result.scalar_one_or_none()

        if not user or not user.hashed_password:
            raise AuthenticationError("Invalid email or password")

        if not verify_password(data.password, user.hashed_password):
            raise AuthenticationError("Invalid email or password")

        if not user.is_active:
            raise AuthenticationError("Account is deactivated")

        tokens = await self._create_tokens(user)
        logger.info("user_login", user_id=str(user.id))
        return tokens

    async def refresh_access_token(self, refresh_token: str) -> TokenResponse:
        """Issue new access token using a valid refresh token."""
        try:
            payload = decode_token(refresh_token)
        except Exception:
            raise AuthenticationError("Invalid refresh token")

        if payload.get("type") != "refresh":
            raise AuthenticationError("Invalid token type")

        user_id = payload["sub"]
        result = await self.db.execute(
            select(User).where(User.id == uuid.UUID(user_id))
        )
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            raise AuthenticationError("User not found or inactive")

        access_token = create_access_token(str(user.id), role=user.role)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,  # reuse existing refresh token
            token_type="bearer",
        )

    async def google_oauth(self, code: str) -> TokenResponse:
        """Exchange Google OAuth code for tokens and create/login user."""
        # exchange code for Google tokens
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )
            if token_resp.status_code != 200:
                raise AuthenticationError("Failed to exchange Google OAuth code")
            google_tokens = token_resp.json()

            # fetch user info from Google
            userinfo_resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {google_tokens['access_token']}"},
            )
            if userinfo_resp.status_code != 200:
                raise AuthenticationError("Failed to fetch Google user info")
            google_user = userinfo_resp.json()

        # find or create user
        result = await self.db.execute(
            select(User).where(User.google_id == google_user["id"])
        )
        user = result.scalar_one_or_none()

        if not user:
            # check if email exists with local auth
            result = await self.db.execute(
                select(User).where(User.email == google_user["email"])
            )
            user = result.scalar_one_or_none()
            if user:
                # link Google account to existing user
                user.google_id = google_user["id"]
                user.avatar_url = google_user.get("picture")
            else:
                # brand new user
                user = User(
                    email=google_user["email"],
                    name=google_user.get("name", ""),
                    google_id=google_user["id"],
                    avatar_url=google_user.get("picture"),
                    auth_provider="google",
                    is_verified=True,  # Google already verified the email
                )
                self.db.add(user)

        await self.db.flush()
        tokens = await self._create_tokens(user)
        logger.info("google_oauth_login", user_id=str(user.id))
        return tokens

    async def _create_tokens(self, user: User) -> TokenResponse:
        """Generate access + refresh token pair."""
        access_token = create_access_token(str(user.id), role=user.role)
        refresh_token = create_refresh_token(str(user.id))
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
        )
```

### Pydantic Schemas

```python
# apps/backend/src/parikrama/schemas/auth.py
"""Request/response schemas for authentication endpoints."""
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class GoogleOAuthRequest(BaseModel):
    code: str


# apps/backend/src/parikrama/schemas/user.py
"""User-related schemas."""
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    name: str
    avatar_url: str | None
    role: str
    is_verified: bool
    preferences: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=100)
    avatar_url: str | None = None


class UserPreferencesUpdate(BaseModel):
    currency: str | None = Field(None, pattern="^[A-Z]{3}$")
    language: str | None = Field(None, pattern="^[a-z]{2}$")
    budget_range: str | None = Field(None, pattern="^(budget|mid|premium|luxury)$")


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ApiKeyResponse(BaseModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    last_used_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyCreatedResponse(ApiKeyResponse):
    """Only returned on creation — raw key shown once."""
    raw_key: str
```

### Auth Router

```python
# apps/backend/src/parikrama/api/v1/auth.py
"""Authentication endpoints — registration, login, OAuth, token refresh."""
import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from parikrama.db.session import get_db
from parikrama.schemas.auth import (
    GoogleOAuthRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from parikrama.services.auth_service import AuthService

logger = structlog.get_logger()
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user with email and password."""
    service = AuthService(db)
    return await service.register(data)


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login with email and password."""
    service = AuthService(db)
    return await service.login(data)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Refresh an expired access token."""
    service = AuthService(db)
    return await service.refresh_access_token(data.refresh_token)


@router.post("/google", response_model=TokenResponse)
async def google_oauth(data: GoogleOAuthRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate via Google OAuth."""
    service = AuthService(db)
    return await service.google_oauth(data.code)


@router.post("/logout", status_code=204)
async def logout():
    """
    Logout — client-side token deletion.
    For added security, implement token blacklisting with Redis in production.
    """
    return None
```

### FastAPI Dependencies

```python
# apps/backend/src/parikrama/dependencies.py
"""
FastAPI dependency injection — current user, admin check, API key auth.

These are used as `Depends()` in route parameters.
"""
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from parikrama.core.security import decode_token, hash_api_key
from parikrama.db.session import get_db
from parikrama.models.user import ApiKey, User

logger = structlog.get_logger()
bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate user from JWT bearer token."""
    try:
        payload = decode_token(credentials.credentials)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload.get("sub")
    result = await db.execute(
        select(User).where(User.id == uuid.UUID(user_id))
    )
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Ensure the current user has admin privileges."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


async def get_user_from_api_key(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticate via API key (for programmatic/MCP access)."""
    raw_key = credentials.credentials
    key_hash_val = hash_api_key(raw_key)

    result = await db.execute(
        select(ApiKey).where(
            ApiKey.key_hash == key_hash_val,
            ApiKey.is_active == True,
        )
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # check expiration
    if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="API key expired")

    # update last_used timestamp
    api_key.last_used_at = datetime.now(timezone.utc)

    # load the user behind this key
    result = await db.execute(
        select(User).where(User.id == api_key.user_id)
    )
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")

    return user
```

### Custom Exceptions

```python
# apps/backend/src/parikrama/core/exceptions.py
"""
Custom exception hierarchy for clean error handling.

Each exception maps to an HTTP status code. The exception handler middleware
catches these and returns proper JSON error responses.
"""
from fastapi import FastAPI, Request
from fastapi.responses import ORJSONResponse


class PariKramaError(Exception):
    """Base exception for all application errors."""
    status_code: int = 500
    detail: str = "An unexpected error occurred"

    def __init__(self, detail: str | None = None):
        self.detail = detail or self.__class__.detail
        super().__init__(self.detail)


class NotFoundError(PariKramaError):
    status_code = 404
    detail = "Resource not found"


class ConflictError(PariKramaError):
    status_code = 409
    detail = "Resource already exists"


class AuthenticationError(PariKramaError):
    status_code = 401
    detail = "Authentication failed"


class ForbiddenError(PariKramaError):
    status_code = 403
    detail = "Insufficient permissions"


class ValidationError(PariKramaError):
    status_code = 422
    detail = "Validation error"


class RateLimitError(PariKramaError):
    status_code = 429
    detail = "Rate limit exceeded"


class LLMError(PariKramaError):
    status_code = 502
    detail = "LLM service unavailable"


def register_exception_handlers(app: FastAPI) -> None:
    """Register custom exception handlers on the FastAPI app."""

    @app.exception_handler(PariKramaError)
    async def handle_parikrama_error(request: Request, exc: PariKramaError):
        return ORJSONResponse(
            status_code=exc.status_code,
            content={
                "error": type(exc).__name__,
                "detail": exc.detail,
                "path": str(request.url.path),
            },
        )
```

### Rate Limiting

```python
# apps/backend/src/parikrama/core/rate_limit.py
"""
Rate limiting using slowapi with Redis backend.

Different limits for different endpoint categories:
- Auth endpoints: strict (prevent brute force)
- Regular API: moderate
- Admin: relaxed (trusted users)
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from parikrama.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.REDIS_URL,
    default_limits=["100/minute"],       # general API limit
)

# named rate limits for specific endpoints
AUTH_RATE_LIMIT = "5/minute"             # prevent brute-force login
REGISTER_RATE_LIMIT = "3/minute"         # prevent spam registrations
API_KEY_RATE_LIMIT = "1000/hour"         # generous for programmatic access
TRIP_RATE_LIMIT = "10/minute"            # agent orchestration is expensive
VOICE_RATE_LIMIT = "20/minute"           # voice sessions
```

### Health Check Endpoint

```python
# apps/backend/src/parikrama/api/v1/health.py
"""
Health check endpoints for load balancers and monitoring.

/health  → basic liveness (is the process running?)
/ready   → readiness (can we serve traffic? DB + Redis connected?)
"""
import redis.asyncio as redis_client
import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from parikrama.config import settings
from parikrama.db.session import get_db

logger = structlog.get_logger()
router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    """Liveness probe — returns 200 if the server is running."""
    return {"status": "healthy", "service": "parikrama-backend"}


@router.get("/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """Readiness probe — verifies database and Redis connectivity."""
    checks = {}

    # postgres check
    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = "connected"
    except Exception as e:
        logger.error("postgres_health_failed", error=str(e))
        checks["postgres"] = "disconnected"

    # redis check
    try:
        r = redis_client.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        checks["redis"] = "connected"
    except Exception as e:
        logger.error("redis_health_failed", error=str(e))
        checks["redis"] = "disconnected"

    all_healthy = all(v == "connected" for v in checks.values())
    return {
        "status": "ready" if all_healthy else "degraded",
        "checks": checks,
    }
```

### Router Aggregator

```python
# apps/backend/src/parikrama/api/router.py
"""Central router that collects all versioned API routes."""
from fastapi import APIRouter

from parikrama.api.v1 import auth, health

api_router = APIRouter()

# v1 routes
api_router.include_router(auth.router, prefix="/v1")
api_router.include_router(health.router, prefix="/v1")

# add more routers as phases are implemented:
# api_router.include_router(users.router, prefix="/v1")
# api_router.include_router(trips.router, prefix="/v1")
# api_router.include_router(documents.router, prefix="/v1")
```

---

## Environment Variables Required

```bash
# New in Phase 1 (add to .env):
SECRET_KEY=your-64-char-random-string
JWT_SECRET_KEY=your-jwt-secret
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback
```

---

## Testing Strategy

| Test | Type | What It Validates |
|------|------|-------------------|
| Register creates user | Unit | User row in DB, password hashed |
| Duplicate email rejects | Unit | ConflictError raised |
| Login returns tokens | Unit | Valid JWT tokens generated |
| Wrong password rejects | Unit | AuthenticationError raised |
| Token decodes correctly | Unit | Payload extraction works |
| Expired token fails | Unit | JWTError on expired tokens |
| Admin-only route blocks user | Unit | 403 for non-admin role |
| API key auth works | Integration | Full key lifecycle |
| Rate limiting triggers | Integration | 429 after threshold |
| Health check reports status | Integration | DB + Redis connectivity |

---

## Definition of Done — Phase 1

- [ ] User model with all fields created via Alembic migration
- [ ] ApiKey and RefreshToken models migrated
- [ ] Registration endpoint creates user with hashed password
- [ ] Login endpoint returns JWT access + refresh tokens
- [ ] Token refresh endpoint works with valid refresh token
- [ ] Google OAuth flow exchanges code for user identity
- [ ] `get_current_user` dependency validates JWT on protected routes
- [ ] `require_admin` dependency blocks non-admin users
- [ ] API key generation, listing, and revocation endpoints work
- [ ] API key authentication works as alternative to JWT
- [ ] Rate limiting active on auth endpoints (5/min login, 3/min register)
- [ ] Custom exception handlers return structured JSON errors
- [ ] Health check reports DB and Redis status
- [ ] All auth endpoints have unit tests
- [ ] Structlog logs every auth event with correlation ID

## Common Pitfalls

| Pitfall | How to Avoid |
|---------|-------------|
| **Storing raw passwords** | Always use `hash_password()` — never store plaintext |
| **JWT secret in code** | Load from `settings.JWT_SECRET_KEY` env var |
| **Exposing API key on creation** | Return raw key ONCE, store only the hash |
| **Missing CORS on auth routes** | CORS middleware in `main.py` covers all routes |
| **Forgetting to refresh expired tokens** | Frontend must catch 401 and call `/refresh` |
| **OAuth redirect mismatch** | `GOOGLE_REDIRECT_URI` must match Google Console exactly |

## Scale-Up Path

| Component | Current | Scale Trigger | Upgrade To |
|-----------|---------|---------------|------------|
| Password Hashing | bcrypt (12 rounds) | Auth latency > 500ms | Argon2id |
| JWT Storage | Stateless | Need instant revocation | Redis token blacklist |
| Rate Limiting | In-memory (slowapi) | Multiple backend instances | Redis-backed distributed limiting |
| OAuth | Google only | User demand | Add GitHub, Microsoft via authlib |

---

*Phase 1 establishes the authentication boundary. Every subsequent phase's endpoints are protected by `get_current_user` or `require_admin` dependencies.*
