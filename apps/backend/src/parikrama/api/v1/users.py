"""
User profile API routes — view and update profile, change password, stats.
"""

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from parikrama.core.security import get_current_user_id
from parikrama.db.session import get_db
from parikrama.schemas.common import MessageResponse
from parikrama.schemas.user import (
    ChangePasswordRequest,
    UpdateProfileRequest,
    UserProfileResponse,
    UserStatsResponse,
)
from parikrama.services.user_service import UserService

logger = structlog.get_logger()
router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get the authenticated user's full profile."""
    service = UserService(db)
    return await service.get_profile(user_id)


@router.patch("/me", response_model=UserProfileResponse)
async def update_my_profile(
    body: UpdateProfileRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Update name, notification preferences, or FCM token."""
    service = UserService(db)
    return await service.update_profile(user_id, body)


@router.post("/me/change-password", response_model=MessageResponse)
async def change_password(
    body: ChangePasswordRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Change password. Requires current password for verification."""
    service = UserService(db)
    await service.change_password(user_id, body)
    return MessageResponse(message="Password changed successfully")


@router.get("/me/stats", response_model=UserStatsResponse)
async def get_my_stats(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get trip and cost statistics for the authenticated user."""
    service = UserService(db)
    return await service.get_stats(user_id)
