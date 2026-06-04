"""
Auth API routes — register, login, Google OAuth, token refresh, and profile.
"""

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from parikrama.core.security import get_current_user_id
from parikrama.db.session import get_db
from parikrama.schemas.auth import (
    AuthResponse,
    GoogleAuthRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from parikrama.services.auth_service import AuthService

logger = structlog.get_logger()
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user with email and password."""
    service = AuthService(db)
    return await service.register(
        email=body.email,
        name=body.name,
        password=body.password,
    )


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate with email and password."""
    service = AuthService(db)
    return await service.login(email=body.email, password=body.password)


@router.post("/google", response_model=AuthResponse)
async def google_auth(body: GoogleAuthRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate or register via Google OAuth."""
    service = AuthService(db)
    return await service.google_auth(
        code=body.code,
        redirect_uri=body.redirect_uri,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Issue new tokens using a refresh token."""
    service = AuthService(db)
    return await service.refresh_tokens(body.refresh_token)


@router.get("/me", response_model=UserResponse)
async def get_profile(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's profile."""
    service = AuthService(db)
    return await service.get_user_profile(user_id)
