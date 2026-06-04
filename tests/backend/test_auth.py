"""
Auth endpoint tests — register, login, token refresh, and profile.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    """Registering a new user returns tokens and user profile."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "name": "Test User",
            "password": "securepass123",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "user" in data
    assert "tokens" in data
    assert data["user"]["email"] == "test@example.com"
    assert data["user"]["role"] == "user"
    assert data["tokens"]["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    """Registering with an existing email returns 409."""
    # register first time
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "dupe@example.com",
            "name": "User One",
            "password": "password123",
        },
    )
    # register again with same email
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "dupe@example.com",
            "name": "User Two",
            "password": "password456",
        },
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    """Login with correct credentials returns tokens."""
    # register first
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "login@example.com",
            "name": "Login User",
            "password": "mypassword123",
        },
    )
    # login
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "mypassword123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["tokens"]["access_token"]
    assert data["user"]["email"] == "login@example.com"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    """Login with wrong password returns 401."""
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "wrong@example.com",
            "name": "Wrong Pass",
            "password": "correctpass123",
        },
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "wrong@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_profile(client: AsyncClient):
    """Authenticated user can get their profile."""
    # register and get token
    reg_response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "profile@example.com",
            "name": "Profile User",
            "password": "password123",
        },
    )
    token = reg_response.json()["tokens"]["access_token"]

    # get profile
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "profile@example.com"


@pytest.mark.asyncio
async def test_get_profile_unauthorized(client: AsyncClient):
    """Accessing profile without token returns 401."""
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_register_short_password(client: AsyncClient):
    """Password under 8 chars is rejected with 422."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "short@example.com",
            "name": "Short Pass",
            "password": "abc",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_token_refresh(client: AsyncClient):
    """Refresh token returns new access + refresh tokens."""
    # register and get refresh token
    reg_response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "refresh@example.com",
            "name": "Refresh User",
            "password": "password123",
        },
    )
    refresh_token = reg_response.json()["tokens"]["refresh_token"]

    # refresh
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["access_token"]
    assert data["refresh_token"]
