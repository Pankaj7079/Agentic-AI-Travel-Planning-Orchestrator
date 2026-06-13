"""
Approval endpoints — human-in-the-loop decision gates.

Users can view pending approvals, approve with optional modifications,
or reject to cancel the trip. All endpoints require authentication.

Routes:
    GET  /approvals              — list pending approvals
    GET  /approvals/{id}         — get single approval (any status)
    POST /approvals/{id}/approve — approve and resume pipeline
    POST /approvals/{id}/reject  — reject and cancel trip
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from parikrama.core.security import get_current_user
from parikrama.db.session import get_db
from parikrama.models.user import User
from parikrama.services.approval_service import ApprovalService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/approvals", tags=["approvals"])

# ── Dependency aliases ─────────────────────────────────────────────────────────

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


# ── Request / Response schemas ────────────────────────────────────────────────


class ApproveRequest(BaseModel):
    """Request body for approving an approval request."""

    modifications: dict[str, Any] | None = None


class RejectRequest(BaseModel):
    """Request body for rejecting an approval request."""

    reason: str = ""


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("", summary="List pending approval requests")
async def list_approvals(
    db: DbDep,
    current_user: UserDep,
) -> list[dict[str, Any]]:
    """
    Return all pending approval requests for the authenticated user.

    Approvals expire after 1 hour — the Celery Beat task auto-expires them.
    """
    svc = ApprovalService(db)
    return await svc.list_pending(str(current_user.id))


@router.get("/{approval_id}", summary="Get approval request details")
async def get_approval(
    approval_id: str,
    db: DbDep,
    current_user: UserDep,
) -> dict[str, Any]:
    """Get a single approval request (any status) by ID."""
    svc = ApprovalService(db)
    try:
        return await svc.get(approval_id, str(current_user.id))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{approval_id}/approve", summary="Approve and resume pipeline")
async def approve_request(
    approval_id: str,
    body: ApproveRequest,
    db: DbDep,
    current_user: UserDep,
) -> dict[str, Any]:
    """
    Approve a pending request and resume the trip planning pipeline.

    Optionally pass modifications (e.g. a different hotel preference) that
    will be injected into the resumed graph state.
    """
    svc = ApprovalService(db)
    try:
        result = await svc.approve(approval_id, str(current_user.id), body.modifications)
        await db.commit()
        logger.info(
            "approval_approved_via_api",
            approval_id=approval_id,
            user_id=str(current_user.id),
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{approval_id}/reject", summary="Reject and cancel trip")
async def reject_request(
    approval_id: str,
    body: RejectRequest,
    db: DbDep,
    current_user: UserDep,
) -> dict[str, Any]:
    """
    Reject a pending approval and cancel the associated trip.

    The trip status is set to 'cancelled' and the pipeline is stopped.
    """
    svc = ApprovalService(db)
    try:
        result = await svc.reject(approval_id, str(current_user.id), body.reason)
        await db.commit()
        logger.info(
            "approval_rejected_via_api",
            approval_id=approval_id,
            user_id=str(current_user.id),
            reason=body.reason,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
