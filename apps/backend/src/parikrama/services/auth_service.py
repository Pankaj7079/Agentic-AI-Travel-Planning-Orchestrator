"""
Auth service — business logic for registration, login, and token management.

Handles both local (email+password) and Google OAuth flows.
"""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from parikrama.config import settings
from parikrama.core.exceptions import AuthenticationError, ConflictError, NotFoundError
from parikrama.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from parikrama.models.user import RefreshToken, User
from parikrama.schemas.auth import AuthResponse, TokenResponse, UserResponse

logger = structlog.get_logger()


class AuthService:
    """Handles user authentication lifecycle."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def register(self, email: str, name: str, password: str) -> AuthResponse:
        """Register a new user with email and password."""
        # check for existing user
        existing = await self._get_user_by_email(email)
        if existing:
            raise ConflictError(f"User with email {email} already exists")

        # create user
        user = User(
            email=email,
            name=name,
            hashed_password=hash_password(password),
            auth_provider="local",
            role="user",
            is_active=True,
            is_verified=False,
        )
        self.db.add(user)
        await self.db.flush()

        # generate tokens
        tokens = await self._create_token_pair(user)

        logger.info("user_registered", user_id=str(user.id), email=email)

        return AuthResponse(
            user=self._to_user_response(user),
            tokens=tokens,
        )

    async def login(self, email: str, password: str) -> AuthResponse:
        """Authenticate with email and password."""
        user = await self._get_user_by_email(email)
        if not user:
            raise AuthenticationError("Invalid email or password")

        if not user.hashed_password:
            raise AuthenticationError("This account uses Google sign-in. Please login with Google.")

        if not verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid email or password")

        if not user.is_active:
            raise AuthenticationError("Account is deactivated")

        # generate tokens
        tokens = await self._create_token_pair(user)

        logger.info("user_logged_in", user_id=str(user.id), method="local")

        return AuthResponse(
            user=self._to_user_response(user),
            tokens=tokens,
        )

    async def google_auth(self, code: str, redirect_uri: str | None = None) -> AuthResponse:
        """Authenticate or register via Google OAuth."""
        # exchange code for Google token
        google_user = await self._exchange_google_code(code, redirect_uri)

        # check if user exists
        user = await self._get_user_by_email(google_user["email"])

        if user:
            # existing user — update Google info if needed
            if not user.google_id:
                user.google_id = google_user["sub"]
                user.auth_provider = "google"
            if google_user.get("picture"):
                user.avatar_url = google_user["picture"]
        else:
            # new user — create account
            user = User(
                email=google_user["email"],
                name=google_user.get("name", google_user["email"].split("@")[0]),
                auth_provider="google",
                google_id=google_user["sub"],
                avatar_url=google_user.get("picture"),
                is_active=True,
                is_verified=True,  # Google verifies email
                role="user",
            )
            self.db.add(user)
            await self.db.flush()
            logger.info("user_registered_google", user_id=str(user.id))

        tokens = await self._create_token_pair(user)

        logger.info("user_logged_in", user_id=str(user.id), method="google")

        return AuthResponse(
            user=self._to_user_response(user),
            tokens=tokens,
        )

    async def refresh_tokens(self, refresh_token_raw: str) -> TokenResponse:
        """Issue new access + refresh tokens using a valid refresh token."""
        payload = decode_token(refresh_token_raw)

        if payload.get("type") != "refresh":
            raise AuthenticationError("Invalid token type")

        user_id = payload.get("sub")
        if not user_id:
            raise AuthenticationError("Invalid refresh token")

        # verify user still exists and is active
        user = await self._get_user_by_id(user_id)
        if not user or not user.is_active:
            raise AuthenticationError("User not found or deactivated")

        # revoke old refresh token (rotation)
        # In production, verify the token hash against stored tokens
        # and revoke the old one

        tokens = await self._create_token_pair(user)

        logger.info("tokens_refreshed", user_id=str(user.id))
        return tokens

    async def get_user_profile(self, user_id: str) -> UserResponse:
        """Get user profile by ID."""
        user = await self._get_user_by_id(user_id)
        if not user:
            raise NotFoundError("User not found")
        return self._to_user_response(user)

    # ── Private helpers ───────────────────────────────────────────────

    async def _get_user_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def _get_user_by_id(self, user_id: str) -> User | None:
        result = await self.db.execute(select(User).where(User.id == uuid.UUID(user_id)))
        return result.scalar_one_or_none()

    async def _create_token_pair(self, user: User) -> TokenResponse:
        """Generate access + refresh token pair."""
        access_token = create_access_token(user_id=str(user.id), role=user.role)
        refresh_token_raw, refresh_token_hash = create_refresh_token(user_id=str(user.id))

        # store refresh token hash in DB
        token_record = RefreshToken(
            user_id=user.id,
            token_hash=refresh_token_hash,
            expires_at=str(
                datetime.now(UTC) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
            ),
        )
        self.db.add(token_record)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token_raw,
            expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def _exchange_google_code(self, code: str, redirect_uri: str | None) -> dict:
        """Exchange Google OAuth code for user info."""
        async with httpx.AsyncClient() as client:
            # get tokens from Google
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": redirect_uri or settings.GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )

            if token_response.status_code != 200:
                raise AuthenticationError("Google authentication failed")

            tokens = token_response.json()

            # get user info from Google
            user_response = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )

            if user_response.status_code != 200:
                raise AuthenticationError("Failed to get Google user info")

            return user_response.json()

    def _to_user_response(self, user: User) -> UserResponse:
        return UserResponse(
            id=str(user.id),
            email=user.email,
            name=user.name,
            role=user.role,
            avatar_url=user.avatar_url,
            is_verified=user.is_verified,
            auth_provider=user.auth_provider,
        )
