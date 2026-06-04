"""
Trip API routes — create, list, get, cancel, and status polling.

All routes require authentication.
"""

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from parikrama.core.exceptions import ValidationError
from parikrama.core.security import get_current_user_id
from parikrama.db.session import get_db
from parikrama.schemas.common import PaginatedResponse
from parikrama.schemas.trip import (
    CreateTripRequest,
    TripDetailResponse,
    TripResponse,
    TripStatusResponse,
)
from parikrama.services.trip_service import TripService

logger = structlog.get_logger()
router = APIRouter(prefix="/trips", tags=["Trips"])


@router.post("", response_model=TripResponse, status_code=202)
async def create_trip(
    body: CreateTripRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new trip planning session.

    Returns 202 Accepted — planning happens asynchronously.
    Poll `/trips/{id}/status` or connect to `/ws/trips/{id}` for live updates.
    """
    service = TripService(db)
    return await service.create_trip(user_id=user_id, request=body)


@router.get("", response_model=PaginatedResponse)
async def list_trips(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List all trips for the authenticated user with pagination."""
    service = TripService(db)
    return await service.list_trips(user_id=user_id, page=page, page_size=page_size, status=status)


@router.get("/{trip_id}", response_model=TripDetailResponse)
async def get_trip(
    trip_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get full trip details including agent run history."""
    service = TripService(db)
    return await service.get_trip(trip_id=trip_id, user_id=user_id)


@router.get("/{trip_id}/status", response_model=TripStatusResponse)
async def get_trip_status(
    trip_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Poll current planning status for a trip.

    Frontend can poll this at ~2s intervals or use WebSocket (Phase 5).
    """
    service = TripService(db)
    return await service.get_trip_status(trip_id=trip_id, user_id=user_id)


@router.post("/{trip_id}/cancel", response_model=TripResponse)
async def cancel_trip(
    trip_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a pending or planning trip."""
    try:
        service = TripService(db)
        return await service.cancel_trip(trip_id=trip_id, user_id=user_id)
    except ValueError as e:
        raise ValidationError(str(e)) from e
