"""
User schemas — profile view and update request models.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

# ── Requests ──────────────────────────────────────────────────────────


class UpdateProfileRequest(BaseModel):
    """User profile update payload."""

    name: str | None = Field(default=None, min_length=2, max_length=100)
    email_notifications: bool | None = None
    push_notifications: bool | None = None
    fcm_token: str | None = None


class ChangePasswordRequest(BaseModel):
    """Password change payload — requires current password for verification."""

    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


# ── Responses ─────────────────────────────────────────────────────────


class UserProfileResponse(BaseModel):
    """Full user profile including notification prefs."""

    id: UUID
    email: str
    name: str
    role: str
    avatar_url: str | None
    is_verified: bool
    auth_provider: str
    email_notifications: bool
    push_notifications: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserStatsResponse(BaseModel):
    """User activity statistics."""

    total_trips: int
    completed_trips: int
    total_cost_usd: float
    total_tokens_used: int
    favourite_destination: str | None
