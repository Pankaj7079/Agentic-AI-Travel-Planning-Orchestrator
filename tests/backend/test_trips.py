"""
Trip endpoint tests — create, list, get, status, cancel.
"""

import pytest
from httpx import AsyncClient


async def _register_and_token(client: AsyncClient, email: str) -> str:
    """Helper: register a user and return access token."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "name": "Test User", "password": "password123"},
    )
    return resp.json()["tokens"]["access_token"]


@pytest.mark.asyncio
async def test_create_trip_success(client: AsyncClient):
    """Create a trip returns 202 with pending status."""
    token = await _register_and_token(client, "trip1@example.com")

    response = await client.post(
        "/api/v1/trips",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "origin": "Delhi",
            "destination": "Manali",
            "days": 5,
            "budget_inr": 15000,
            "travelers": 2,
        },
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "pending"
    assert data["request"]["origin"] == "Delhi"
    assert data["request"]["destination"] == "Manali"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_trip_unauthenticated(client: AsyncClient):
    """Creating trip without auth returns 401."""
    response = await client.post(
        "/api/v1/trips",
        json={"origin": "Delhi", "destination": "Goa", "days": 3, "budget_inr": 10000},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_trips(client: AsyncClient):
    """List trips returns paginated results."""
    token = await _register_and_token(client, "trip2@example.com")

    # create 2 trips
    for dest in ["Manali", "Goa"]:
        await client.post(
            "/api/v1/trips",
            headers={"Authorization": f"Bearer {token}"},
            json={"origin": "Delhi", "destination": dest, "days": 3, "budget_inr": 10000},
        )

    response = await client.get(
        "/api/v1/trips",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_get_trip_detail(client: AsyncClient):
    """Get trip detail includes agent_runs list."""
    token = await _register_and_token(client, "trip3@example.com")

    create_resp = await client.post(
        "/api/v1/trips",
        headers={"Authorization": f"Bearer {token}"},
        json={"origin": "Mumbai", "destination": "Ladakh", "days": 7, "budget_inr": 30000},
    )
    trip_id = create_resp.json()["id"]

    response = await client.get(
        f"/api/v1/trips/{trip_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == trip_id
    assert "agent_runs" in data


@pytest.mark.asyncio
async def test_get_trip_status(client: AsyncClient):
    """Trip status endpoint returns progress info."""
    token = await _register_and_token(client, "trip4@example.com")

    create_resp = await client.post(
        "/api/v1/trips",
        headers={"Authorization": f"Bearer {token}"},
        json={"origin": "Delhi", "destination": "Jaipur", "days": 2, "budget_inr": 5000},
    )
    trip_id = create_resp.json()["id"]

    response = await client.get(
        f"/api/v1/trips/{trip_id}/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"
    assert "progress_percent" in data
    assert "message" in data
    assert data["is_complete"] is False


@pytest.mark.asyncio
async def test_cancel_trip(client: AsyncClient):
    """Cancel a pending trip changes status to cancelled."""
    token = await _register_and_token(client, "trip5@example.com")

    create_resp = await client.post(
        "/api/v1/trips",
        headers={"Authorization": f"Bearer {token}"},
        json={"origin": "Delhi", "destination": "Shimla", "days": 4, "budget_inr": 8000},
    )
    trip_id = create_resp.json()["id"]

    cancel_resp = await client.post(
        f"/api/v1/trips/{trip_id}/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_trip_not_accessible_by_other_user(client: AsyncClient):
    """User cannot access another user's trip."""
    token_a = await _register_and_token(client, "tripa@example.com")
    token_b = await _register_and_token(client, "tripb@example.com")

    create_resp = await client.post(
        "/api/v1/trips",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"origin": "Delhi", "destination": "Kedarnath", "days": 5, "budget_inr": 20000},
    )
    trip_id = create_resp.json()["id"]

    # user B tries to access user A's trip
    response = await client.get(
        f"/api/v1/trips/{trip_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_trip_invalid_budget(client: AsyncClient):
    """Budget below minimum (500) is rejected with 422."""
    token = await _register_and_token(client, "trip6@example.com")
    response = await client.post(
        "/api/v1/trips",
        headers={"Authorization": f"Bearer {token}"},
        json={"origin": "Delhi", "destination": "Goa", "days": 5, "budget_inr": 100},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_trips_filter_by_status(client: AsyncClient):
    """List trips filtered by status only returns matching trips."""
    token = await _register_and_token(client, "trip7@example.com")

    # create a trip (pending), then cancel it
    create_resp = await client.post(
        "/api/v1/trips",
        headers={"Authorization": f"Bearer {token}"},
        json={"origin": "Delhi", "destination": "Agra", "days": 1, "budget_inr": 3000},
    )
    trip_id = create_resp.json()["id"]
    await client.post(
        f"/api/v1/trips/{trip_id}/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )

    # filter for cancelled only
    response = await client.get(
        "/api/v1/trips?status=cancelled",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert all(t["status"] == "cancelled" for t in data["items"])
