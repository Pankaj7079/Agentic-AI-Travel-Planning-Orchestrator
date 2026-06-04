"""
User profile endpoint tests — get/update profile, change password, stats.
"""

import pytest
from httpx import AsyncClient


async def _register_and_token(client: AsyncClient, email: str) -> str:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "name": "Profile User", "password": "password123"},
    )
    return resp.json()["tokens"]["access_token"]


@pytest.mark.asyncio
async def test_get_profile(client: AsyncClient):
    """User can get their own full profile."""
    token = await _register_and_token(client, "user1@example.com")

    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "user1@example.com"
    assert "email_notifications" in data
    assert "push_notifications" in data


@pytest.mark.asyncio
async def test_update_profile_name(client: AsyncClient):
    """User can update their name."""
    token = await _register_and_token(client, "user2@example.com")

    response = await client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "New Name"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"


@pytest.mark.asyncio
async def test_update_notification_prefs(client: AsyncClient):
    """User can toggle notification preferences."""
    token = await _register_and_token(client, "user3@example.com")

    response = await client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"email_notifications": False, "push_notifications": False},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email_notifications"] is False
    assert data["push_notifications"] is False


@pytest.mark.asyncio
async def test_change_password_success(client: AsyncClient):
    """User can change their password with correct current password."""
    token = await _register_and_token(client, "user4@example.com")

    response = await client.post(
        "/api/v1/users/me/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "current_password": "password123",
            "new_password": "newpassword456",
        },
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Password changed successfully"

    # verify old password no longer works
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "user4@example.com", "password": "password123"},
    )
    assert login_resp.status_code == 401


@pytest.mark.asyncio
async def test_change_password_wrong_current(client: AsyncClient):
    """Wrong current password returns 401."""
    token = await _register_and_token(client, "user5@example.com")

    response = await client.post(
        "/api/v1/users/me/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "wrongpassword", "new_password": "newpassword456"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_user_stats(client: AsyncClient):
    """User stats endpoint returns trip counts and costs."""
    token = await _register_and_token(client, "user6@example.com")

    response = await client.get(
        "/api/v1/users/me/stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_trips"] == 0
    assert data["completed_trips"] == 0
    assert data["total_cost_usd"] == 0.0


@pytest.mark.asyncio
async def test_profile_unauthenticated(client: AsyncClient):
    """Accessing profile without token returns 401."""
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401
