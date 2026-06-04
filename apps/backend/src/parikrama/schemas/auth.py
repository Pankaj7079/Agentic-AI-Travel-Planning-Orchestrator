"""
Pydantic schemas for auth requests and responses.

Schemas handle validation — if a field is wrong, the user
gets a clear error message before any business logic runs.
"""

from pydantic import BaseModel, EmailStr, Field

# ── Requests ──────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    """User registration payload."""

    email: EmailStr
    name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    """Email + password login."""

    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    """Token refresh payload."""

    refresh_token: str


class GoogleAuthRequest(BaseModel):
    """Google OAuth callback payload."""

    code: str
    redirect_uri: str | None = None


# ── Responses ─────────────────────────────────────────────────────────


class TokenResponse(BaseModel):
    """JWT token pair returned on login/register."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserResponse(BaseModel):
    """Public user profile."""

    id: str
    email: str
    name: str
    role: str
    avatar_url: str | None = None
    is_verified: bool
    auth_provider: str

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    """Combined auth response with tokens and user profile."""

    user: UserResponse
    tokens: TokenResponse
