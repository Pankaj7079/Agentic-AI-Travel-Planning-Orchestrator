"""
Trip API routes — create, list, get, cancel, status polling, export, and share.

All routes require authentication.
"""

import structlog
from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
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


def _generate_itinerary_html(trip: TripDetailResponse) -> str:
    """Generate a beautiful HTML itinerary for PDF export."""
    result = trip.result or {}
    itinerary = result.get("itinerary", [])
    breakdown = result.get("budget_breakdown", {})
    summary = result.get("summary", "")
    hotels = result.get("hotel_options", [])
    transports = result.get("transport_options", [])

    days_html = ""
    for i, day in enumerate(itinerary):
        activities_html = ""
        for act in day.get("activities", []):
            cost = f"₹{act.get('cost_inr', 0):,}" if act.get("cost_inr", 0) > 0 else ""
            activities_html += f"""
            <div style="padding:8px 12px;background:#f8fafc;border-radius:8px;margin-bottom:6px;">
              <strong>{act.get('time', '')}</strong> — {act.get('activity', act.get('name', ''))}
              {f"<br><small style='color:#64748b'>📍 {act.get('location', '')}</small>" if act.get('location') else ""}
              {f"<br><small style='color:#059669;font-weight:600'>{cost}</small>" if cost else ""}
              {f"<br><em style='color:#7c3aed;font-size:12px'>💡 {act.get('tips', '')}</em>" if act.get('tips') else ""}
            </div>"""

        meals_html = ""
        for meal in day.get("meals", []):
            meals_html += f"""
            <div style="padding:4px 0;font-size:13px;">
              🍽️ <strong>{meal.get('type', '').title()}</strong>: {meal.get('suggestion', '')}
              {f" — ₹{meal.get('estimated_cost_inr', 0):,}" if meal.get('estimated_cost_inr') else ""}
            </div>"""

        tips_html = ""
        if day.get("tips"):
            tips_html = "<div style='padding:8px 12px;background:#fef3c7;border-radius:8px;margin-top:8px;'>"
            for tip in day["tips"]:
                tips_html += f"<div style='font-size:12px;color:#92400e;'>• {tip}</div>"
            tips_html += "</div>"

        days_html += f"""
        <div style="page-break-inside:avoid;margin-bottom:24px;">
          <h3 style="color:#4f46e5;border-bottom:2px solid #e0e7ff;padding-bottom:6px;">
            Day {i+1}: {day.get('title', f'Day {i+1}')}
          </h3>
          {f"<div style='font-size:13px;color:#64748b;margin-bottom:8px;'>Total: ₹{day.get('estimated_cost_inr', 0):,}</div>" if day.get('estimated_cost_inr') else ""}
          <h4 style="font-size:13px;color:#64748b;margin:8px 0 4px;">Activities</h4>
          {activities_html}
          {f"<h4 style='font-size:13px;color:#64748b;margin:8px 0 4px;'>Meals</h4>{meals_html}" if meals_html else ""}
          {tips_html}
        </div>"""

    budget_html = ""
    if breakdown:
        budget_html = f"""
        <div style="margin:24px 0;padding:16px;background:#f0fdf4;border-radius:12px;">
          <h3 style="color:#059669;margin-bottom:8px;">💰 Budget Breakdown</h3>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:13px;">
            <div>Transport: ₹{breakdown.get('transport_inr', 0):,}</div>
            <div>Accommodation: ₹{breakdown.get('accommodation_inr', 0):,}</div>
            <div>Food: ₹{breakdown.get('food_inr', 0):,}</div>
            <div>Activities: ₹{breakdown.get('activities_inr', 0):,}</div>
            <div>Misc: ₹{breakdown.get('misc_inr', 0):,}</div>
            <div><strong>Total: ₹{breakdown.get('total_inr', 0):,}</strong></div>
          </div>
        </div>"""

    hotels_html = ""
    if hotels:
        hotels_html = "<div style='margin:24px 0;'><h3 style='color:#0891b2;margin-bottom:8px;'>🏨 Recommended Hotels</h3>"
        for h in hotels[:3]:
            hotels_html += f"""
            <div style='padding:8px 12px;background:#f0fdfa;border-radius:8px;margin-bottom:6px;font-size:13px;'>
              <strong>{h.get('name', '')}</strong> — {h.get('type', 'Hotel').replace('_', ' ').title()}<br>
              ⭐ {h.get('rating', 'N/A')} · ₹{h.get('price_per_night_inr', 0):,}/night
              {f" · {h.get('location', '')}" if h.get('location') else ""}
            </div>"""
        hotels_html += "</div>"

    transport_html = ""
    if transports:
        transport_html = "<div style='margin:24px 0;'><h3 style='color:#7c3aed;margin-bottom:8px;'>🚌 Transport Options</h3>"
        for t in transports[:3]:
            transport_html += f"""
            <div style='padding:8px 12px;background:#f5f3ff;border-radius:8px;margin-bottom:6px;font-size:13px;'>
              <strong>{t.get('type', 'Bus').title()}</strong> — {t.get('operator', '')}<br>
              {t.get('departure_time', '')} · {t.get('duration_hours', 0)}h · ₹{t.get('price_inr', 0):,}
            </div>"""
        transport_html += "</div>"

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>{trip.request.get('origin', '')} → {trip.request.get('destination', '')} Itinerary</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 800px; margin: 0 auto; padding: 40px 20px; color: #1e293b; line-height: 1.6; }}
  @media print {{ body {{ padding: 20px; }} }}
</style></head><body>
  <div style="text-align:center;margin-bottom:32px;">
    <h1 style="font-size:28px;margin-bottom:4px;">✈️ {trip.request.get('origin', 'Origin')} → {trip.request.get('destination', 'Destination')}</h1>
    <p style="color:#64748b;font-size:14px;">{trip.request.get('days', 0)} days · {trip.request.get('travelers', 1)} traveler(s) · ₹{(trip.request.get('budget_inr', 0) or 0):,} budget</p>
    {f'<p style="color:#64748b;font-size:13px;margin-top:8px;">{summary}</p>' if summary else ""}
  </div>
  {budget_html}
  {hotels_html}
  {transport_html}
  {days_html}
  <div style="text-align:center;margin-top:40px;padding:16px;background:#f1f5f9;border-radius:12px;color:#64748b;font-size:12px;">
    Generated by <strong>PariKrama</strong> — AI Travel Planning Orchestrator
  </div>
</body></html>"""


@router.get("/{trip_id}/export/pdf")
async def export_trip_pdf(
    trip_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Export trip itinerary as a PDF-like HTML download."""
    service = TripService(db)
    trip = await service.get_trip(trip_id=trip_id, user_id=user_id)

    if trip.status != "completed":
        raise ValidationError("Trip planning is not yet completed")

    html_content = _generate_itinerary_html(trip)

    return HTMLResponse(
        content=html_content,
        headers={
            "Content-Disposition": f'attachment; filename="trip-{trip.destination or trip_id[:8]}.html"',
            "Content-Type": "text/html; charset=utf-8",
        },
    )


@router.post("/{trip_id}/share")
async def create_share_link(
    trip_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Create a shareable link for the trip itinerary."""
    service = TripService(db)
    trip = await service.get_trip(trip_id=trip_id, user_id=user_id)
    return {
        "share_url": f"/shared/trip/{trip_id}",
        "trip_id": trip_id,
        "destination": trip.request.get("destination", ""),
    }
