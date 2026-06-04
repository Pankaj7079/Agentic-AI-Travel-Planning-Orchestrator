"""
User service — profile management and user statistics.
"""

import uuid

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from parikrama.core.exceptions import AuthenticationError, NotFoundError
from parikrama.core.security import hash_password, verify_password
from parikrama.models.trip import Trip
from parikrama.models.user import User
from parikrama.schemas.user import (
    ChangePasswordRequest,
    UpdateProfileRequest,
    UserProfileResponse,
    UserStatsResponse,
)

logger = structlog.get_logger()


class UserService:
    """Handles user profile management."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_profile(self, user_id: str) -> UserProfileResponse:
        """Get full user profile."""
        user = await self._get_user(user_id)
        return UserProfileResponse.model_validate(user)

    async def update_profile(self, user_id: str, data: UpdateProfileRequest) -> UserProfileResponse:
        """Update user profile fields."""
        user = await self._get_user(user_id)

        if data.name is not None:
            user.name = data.name
        if data.email_notifications is not None:
            user.email_notifications = data.email_notifications
        if data.push_notifications is not None:
            user.push_notifications = data.push_notifications
        if data.fcm_token is not None:
            user.fcm_token = data.fcm_token

        await self.db.flush()
        await self.db.refresh(user)
        logger.info("profile_updated", user_id=user_id)
        return UserProfileResponse.model_validate(user)

    async def change_password(self, user_id: str, data: ChangePasswordRequest) -> None:
        """Change password — requires current password verification."""
        user = await self._get_user(user_id)

        if not user.hashed_password:
            raise AuthenticationError(
                "Password change not available for Google-authenticated accounts"
            )

        if not verify_password(data.current_password, user.hashed_password):
            raise AuthenticationError("Current password is incorrect")

        user.hashed_password = hash_password(data.new_password)
        await self.db.flush()
        logger.info("password_changed", user_id=user_id)

    async def get_stats(self, user_id: str) -> UserStatsResponse:
        """Get user trip and cost statistics."""
        uid = uuid.UUID(user_id)

        # trip counts
        total_result = await self.db.execute(select(func.count(Trip.id)).where(Trip.user_id == uid))
        total_trips = total_result.scalar_one() or 0

        completed_result = await self.db.execute(
            select(func.count(Trip.id)).where(Trip.user_id == uid, Trip.status == "completed")
        )
        completed_trips = completed_result.scalar_one() or 0

        # cost and tokens
        cost_result = await self.db.execute(
            select(
                func.sum(Trip.total_cost_usd).label("total_cost"),
                func.sum(Trip.total_tokens_used).label("total_tokens"),
            ).where(Trip.user_id == uid)
        )
        cost_row = cost_result.one()

        # most visited destination
        dest_result = await self.db.execute(
            select(
                Trip.request["destination"].as_string().label("dest"),
                func.count().label("cnt"),
            )
            .where(Trip.user_id == uid, Trip.status == "completed")
            .group_by("dest")
            .order_by(func.count().desc())
            .limit(1)
        )
        top_dest = dest_result.one_or_none()

        return UserStatsResponse(
            total_trips=total_trips,
            completed_trips=completed_trips,
            total_cost_usd=float(cost_row.total_cost or 0),
            total_tokens_used=int(cost_row.total_tokens or 0),
            favourite_destination=top_dest.dest if top_dest else None,
        )

    async def _get_user(self, user_id: str) -> User:
        result = await self.db.execute(select(User).where(User.id == uuid.UUID(user_id)))
        user = result.scalar_one_or_none()
        if not user:
            raise NotFoundError("User not found")
        return user
