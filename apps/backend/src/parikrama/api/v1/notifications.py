"""
Notification inbox endpoints.

Provides the notification history, unread count, and mark-read actions
for the frontend notification bell component.

Routes:
    GET   /notifications                 — list (paginated, ?unread_only=true)
    GET   /notifications/unread-count    — fast count for the bell badge
    PATCH /notifications/{id}/read       — mark single as read
    POST  /notifications/read-all        — mark all as read
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from parikrama.core.security import get_current_user
from parikrama.db.session import get_db
from parikrama.models.notification import Notification
from parikrama.models.user import User
from parikrama.services.notification_service import NotificationService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


# ── Helpers ────────────────────────────────────────────────────────────────────


def _serialize(n: Notification) -> dict[str, Any]:
    return {
        "id": str(n.id),
        "type": n.type,
        "title": n.title,
        "body": n.body,
        "data": n.data,
        "channels_sent": n.channels_sent,
        "is_read": n.is_read,
        "read_at": n.read_at.isoformat() if n.read_at else None,
        "created_at": n.created_at.isoformat(),
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.get("", summary="List notifications")
async def list_notifications(
    db: DbDep,
    current_user: UserDep,
    unread_only: bool = Query(False, description="Return only unread notifications"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """
    Return the user's notification inbox (newest first).

    Use ?unread_only=true to filter to unread notifications only.
    Supports pagination via limit/offset.
    """
    query = (
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if unread_only:
        query = query.where(Notification.is_read.is_(False))

    result = await db.execute(query)
    notifications = result.scalars().all()

    # total count for pagination
    count_q = select(func.count(Notification.id)).where(Notification.user_id == current_user.id)
    if unread_only:
        count_q = count_q.where(Notification.is_read.is_(False))
    total_result = await db.execute(count_q)
    total = total_result.scalar_one()

    return {
        "notifications": [_serialize(n) for n in notifications],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/unread-count", summary="Get unread notification count")
async def get_unread_count(
    db: DbDep,
    current_user: UserDep,
) -> dict[str, int]:
    """
    Fast endpoint for the notification bell badge count.

    Uses the partial index idx_notifications_unread for O(1) performance.
    """
    result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == current_user.id,
            Notification.is_read.is_(False),
        )
    )
    count = result.scalar_one()
    return {"unread_count": count}


@router.patch("/{notification_id}/read", summary="Mark notification as read")
async def mark_notification_read(
    notification_id: str,
    db: DbDep,
    current_user: UserDep,
) -> dict[str, Any]:
    """Mark a single notification as read."""
    svc = NotificationService(db)
    found = await svc.mark_read(notification_id, str(current_user.id))
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification {notification_id} not found",
        )
    await db.commit()
    return {"status": "read", "notification_id": notification_id}


@router.post("/read-all", summary="Mark all notifications as read")
async def mark_all_read(
    db: DbDep,
    current_user: UserDep,
) -> dict[str, Any]:
    """Mark all unread notifications for the current user as read."""
    svc = NotificationService(db)
    count = await svc.mark_all_read(str(current_user.id))
    await db.commit()
    return {"status": "ok", "marked_read": count}
